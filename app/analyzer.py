from __future__ import annotations

import json
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

import cv2
import numpy as np

from .database import FRAME_DIR, UPLOAD_DIR, connection


class VideoAnalysisError(RuntimeError):
    pass


class AnalysisCancelled(VideoAnalysisError):
    pass


ProgressFn = Callable[[int, str], None]


def _progress(video_id: int, percent: int, stage: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE videos SET progress_percent=?, progress_stage=? WHERE id=?",
            (max(0, min(100, int(percent))), stage, video_id),
        )


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled("Analysis cancelled by user.")


def _write_jpeg(frame: np.ndarray, path: Path, max_width: int = 960) -> None:
    h, w = frame.shape[:2]
    if w > max_width:
        scale = max_width / w
        frame = cv2.resize(frame, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise VideoAnalysisError(f"Could not write frame image: {path}")


def _video_metadata(cap: cv2.VideoCapture) -> tuple[float, int, int, int, float]:
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if fps <= 0 or frame_count <= 0:
        raise VideoAnalysisError("The video does not expose valid FPS/frame metadata.")
    return fps, frame_count, width, height, frame_count / fps


def _extract_at(cap: cv2.VideoCapture, fps: float, timestamp: float):
    frame_number = max(0, int(round(timestamp * fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ok, frame = cap.read()
    if not ok:
        return None, frame_number
    return frame, frame_number


def _preview_times(duration: float, count: int) -> list[float]:
    if duration <= 0:
        return [0.0]
    if count <= 1:
        return [min(duration - 0.001, duration / 2)]
    end = max(0.0, duration - 0.05)
    return [round((end * i) / (count - 1), 3) for i in range(count)]


def prepare_video(video_id: int, mode: str = "quick", cancel_event: Event | None = None) -> None:
    """Lightweight preparation for immediate coaching review.

    quick: metadata + 12 preview frames.
    shot: metadata + 6 preview frames; user then seeks to a shot and extracts evidence.
    No full-video motion scan is performed.
    """
    with connection() as conn:
        video = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if not video:
            return
        conn.execute(
            "UPDATE videos SET status='processing', analysis_mode=?, progress_percent=2, progress_stage='Opening video', error=NULL WHERE id=?",
            (mode, video_id),
        )

    video_path = UPLOAD_DIR / video["stored_name"]
    frame_dir = FRAME_DIR / str(video_id)
    frame_dir.mkdir(parents=True, exist_ok=True)

    try:
        _check_cancel(cancel_event)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise VideoAnalysisError("OpenCV could not open the uploaded video.")

        _progress(video_id, 10, "Reading video metadata")
        fps, frame_count, width, height, duration = _video_metadata(cap)

        preview_count = 6 if mode == "shot" else 12
        times = _preview_times(duration, preview_count)

        with connection() as conn:
            conn.execute("DELETE FROM frames WHERE video_id=?", (video_id,))
        for old in frame_dir.glob("*.jpg"):
            old.unlink(missing_ok=True)

        rows = []
        thumbnail_path = None
        for idx, timestamp in enumerate(times):
            _check_cancel(cancel_event)
            frame, frame_number = _extract_at(cap, fps, timestamp)
            if frame is None:
                continue
            name = f"{idx:04d}_{timestamp:010.3f}_preview.jpg"
            out = frame_dir / name
            _write_jpeg(frame, out)
            rel = f"/media/frames/{video_id}/{name}"
            if thumbnail_path is None and idx >= min(1, len(times) - 1):
                thumbnail_path = rel
            rows.append((video_id, timestamp, frame_number, rel, 0.0, 0, "preview"))
            pct = 20 + int(((idx + 1) / max(1, len(times))) * 70)
            _progress(video_id, pct, f"Generating preview frames {idx + 1}/{len(times)}")

        if thumbnail_path is None and rows:
            thumbnail_path = rows[0][3]

        _check_cancel(cancel_event)
        with connection() as conn:
            conn.executemany(
                """
                INSERT INTO frames(video_id,timestamp,frame_number,image_path,motion_score,is_candidate,kind)
                VALUES(?,?,?,?,?,?,?)
                """,
                rows,
            )
            conn.execute(
                """
                UPDATE videos
                SET status='complete', fps=?, duration=?, width=?, height=?, frame_count=?,
                    thumbnail_path=?, motion_json='[]', progress_percent=100,
                    progress_stage=?, analyzed_at=CURRENT_TIMESTAMP, error=NULL
                WHERE id=?
                """,
                (
                    fps,
                    duration,
                    width,
                    height,
                    frame_count,
                    thumbnail_path,
                    "Ready for shot review" if mode == "shot" else "Quick review ready",
                    video_id,
                ),
            )
        cap.release()
    except AnalysisCancelled:
        with connection() as conn:
            conn.execute(
                "UPDATE videos SET status='cancelled', progress_stage='Cancelled', error=NULL WHERE id=?",
                (video_id,),
            )
        raise
    except Exception as exc:
        with connection() as conn:
            conn.execute(
                "UPDATE videos SET status='failed', error=?, progress_stage='Analysis failed', analyzed_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(exc), video_id),
            )
        raise


def _motion_samples(
    video_id: int,
    cap: cv2.VideoCapture,
    fps: float,
    frame_count: int,
    cancel_event: Event | None = None,
) -> list[dict]:
    """Sequential full-video scan.

    We avoid repeatedly seeking to arbitrary compressed frames. Frames are decoded
    forward once, while image processing is only performed about five times/second.
    """
    stride = max(1, int(round(fps / 5.0)))
    samples: list[dict] = []
    prev = None
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    i = 0
    last_reported = -1
    while i < frame_count:
        _check_cancel(cancel_event)
        ok = cap.grab()
        if not ok:
            break
        if i % stride == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            small = cv2.resize(frame, (192, 108), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            score = 0.0 if prev is None else float(cv2.absdiff(gray, prev).mean())
            samples.append({"t": round(i / fps, 3), "score": round(score, 4)})
            prev = gray

        pct = 15 + int((i / max(1, frame_count)) * 55)
        if pct >= last_reported + 3:
            _progress(video_id, pct, "Scanning full video for motion candidates")
            last_reported = pct
        i += 1

    return samples


def _candidate_times(samples: list[dict], max_candidates: int = 18) -> set[float]:
    if len(samples) < 3:
        return set()
    scores = np.array([s["score"] for s in samples], dtype=np.float32)
    threshold = float(np.percentile(scores, 70))
    local_peaks: list[tuple[float, float]] = []
    for i in range(1, len(samples) - 1):
        score = samples[i]["score"]
        if score >= threshold and score >= samples[i - 1]["score"] and score >= samples[i + 1]["score"]:
            local_peaks.append((float(score), float(samples[i]["t"])))
    local_peaks.sort(reverse=True)
    chosen: list[float] = []
    for _, timestamp in local_peaks:
        if all(abs(timestamp - existing) >= 0.8 for existing in chosen):
            chosen.append(timestamp)
        if len(chosen) >= max_candidates:
            break
    return {round(t, 3) for t in chosen}


def _timeline_times(duration: float, max_frames: int = 70) -> set[float]:
    if duration <= 0:
        return {0.0}
    step = max(1.0, duration / max_frames)
    times = {0.0}
    t = step
    while t < duration:
        times.add(round(t, 3))
        t += step
    times.add(round(max(0.0, duration - 0.05), 3))
    return times


def _nearest_motion(samples: list[dict], timestamp: float) -> float:
    if not samples:
        return 0.0
    nearest = min(samples, key=lambda sample: abs(float(sample["t"]) - timestamp))
    return float(nearest["score"])


def analyze_video(video_id: int, cancel_event: Event | None = None) -> None:
    """Optional heavier full-video scan. This is never the default upload mode."""
    with connection() as conn:
        video = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if not video:
            return
        conn.execute(
            "UPDATE videos SET status='processing', analysis_mode='full', progress_percent=2, progress_stage='Opening video', error=NULL WHERE id=?",
            (video_id,),
        )

    video_path = UPLOAD_DIR / video["stored_name"]
    frame_dir = FRAME_DIR / str(video_id)
    frame_dir.mkdir(parents=True, exist_ok=True)

    try:
        _check_cancel(cancel_event)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise VideoAnalysisError("OpenCV could not open the uploaded video.")

        _progress(video_id, 8, "Reading video metadata")
        fps, frame_count, width, height, duration = _video_metadata(cap)

        samples = _motion_samples(video_id, cap, fps, frame_count, cancel_event)
        _check_cancel(cancel_event)
        _progress(video_id, 72, "Selecting candidate moments")
        candidates = _candidate_times(samples)
        selected = sorted(_timeline_times(duration) | candidates)

        rows = []
        thumbnail_path = None
        candidate_lookup = set(candidates)

        with connection() as conn:
            conn.execute("DELETE FROM frames WHERE video_id=?", (video_id,))
        for old in frame_dir.glob("*.jpg"):
            old.unlink(missing_ok=True)

        for idx, timestamp in enumerate(selected):
            _check_cancel(cancel_event)
            frame, frame_number = _extract_at(cap, fps, timestamp)
            if frame is None:
                continue
            is_candidate = 1 if round(timestamp, 3) in candidate_lookup else 0
            kind = "candidate" if is_candidate else "timeline"
            name = f"{idx:04d}_{timestamp:010.3f}_{kind}.jpg"
            out = frame_dir / name
            _write_jpeg(frame, out)
            rel = f"/media/frames/{video_id}/{name}"
            if thumbnail_path is None and timestamp >= min(2.0, duration / 3):
                thumbnail_path = rel
            rows.append(
                (
                    video_id,
                    float(timestamp),
                    int(frame_number),
                    rel,
                    _nearest_motion(samples, timestamp),
                    is_candidate,
                    kind,
                )
            )
            pct = 75 + int(((idx + 1) / max(1, len(selected))) * 22)
            if idx % 4 == 0 or idx == len(selected) - 1:
                _progress(video_id, pct, f"Generating analysis frames {idx + 1}/{len(selected)}")

        if thumbnail_path is None and rows:
            thumbnail_path = rows[0][3]

        _check_cancel(cancel_event)
        with connection() as conn:
            conn.executemany(
                """
                INSERT INTO frames(video_id,timestamp,frame_number,image_path,motion_score,is_candidate,kind)
                VALUES(?,?,?,?,?,?,?)
                """,
                rows,
            )
            conn.execute(
                """
                UPDATE videos
                SET status='complete', fps=?, duration=?, width=?, height=?, frame_count=?,
                    thumbnail_path=?, motion_json=?, progress_percent=100,
                    progress_stage='Full video scan ready', analyzed_at=CURRENT_TIMESTAMP, error=NULL
                WHERE id=?
                """,
                (
                    fps,
                    duration,
                    width,
                    height,
                    frame_count,
                    thumbnail_path,
                    json.dumps(samples),
                    video_id,
                ),
            )
        cap.release()
    except AnalysisCancelled:
        with connection() as conn:
            conn.execute(
                "UPDATE videos SET status='cancelled', progress_stage='Cancelled', error=NULL WHERE id=?",
                (video_id,),
            )
        raise
    except Exception as exc:
        with connection() as conn:
            conn.execute(
                "UPDATE videos SET status='failed', error=?, progress_stage='Analysis failed', analyzed_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(exc), video_id),
            )
        raise


def extract_sequence(video_id: int, center: float, offsets: Iterable[float]) -> list[dict]:
    with connection() as conn:
        video = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if not video:
            raise VideoAnalysisError("Video not found")

    fps = float(video["fps"] or 0)
    duration = float(video["duration"] or 0)
    if fps <= 0:
        raise VideoAnalysisError("Video preparation is not complete yet")

    cap = cv2.VideoCapture(str(UPLOAD_DIR / video["stored_name"]))
    if not cap.isOpened():
        raise VideoAnalysisError("Could not reopen source video")

    seq_dir = FRAME_DIR / str(video_id) / "sequences"
    seq_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for idx, offset in enumerate(offsets):
        timestamp = max(0.0, min(duration - 0.001, center + float(offset)))
        frame, frame_number = _extract_at(cap, fps, timestamp)
        if frame is None:
            continue
        name = f"seq_{center:010.3f}_{idx:02d}_{timestamp:010.3f}.jpg"
        out = seq_dir / name
        _write_jpeg(frame, out, max_width=1280)
        results.append(
            {
                "timestamp": round(timestamp, 3),
                "offset": round(float(offset), 3),
                "frame_number": frame_number,
                "image_url": f"/media/frames/{video_id}/sequences/{name}",
            }
        )

    cap.release()
    return results
