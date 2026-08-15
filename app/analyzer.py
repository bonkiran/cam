from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .database import FRAME_DIR, UPLOAD_DIR, connection


class VideoAnalysisError(RuntimeError):
    pass


def _write_jpeg(frame: np.ndarray, path: Path, max_width: int = 960) -> None:
    h, w = frame.shape[:2]
    if w > max_width:
        scale = max_width / w
        frame = cv2.resize(frame, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise VideoAnalysisError(f"Could not write frame image: {path}")


def _motion_samples(cap: cv2.VideoCapture, fps: float, frame_count: int) -> list[dict]:
    # Five samples per second is enough for a useful first-pass motion timeline while
    # keeping long cricket clips tractable on a laptop.
    stride = max(1, int(round(fps / 5.0)))
    samples: list[dict] = []
    prev = None

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    i = 0
    while i < frame_count:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, (192, 108), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        score = 0.0 if prev is None else float(cv2.absdiff(gray, prev).mean())
        samples.append({"t": round(i / fps, 3), "score": round(score, 4)})
        prev = gray
        i += stride
    return samples


def _candidate_times(samples: list[dict], max_candidates: int = 18) -> set[float]:
    if len(samples) < 3:
        return set()

    scores = np.array([s["score"] for s in samples], dtype=np.float32)
    # Ignore tiny camera/noise changes by requiring at least the 70th-percentile score.
    threshold = float(np.percentile(scores, 70))
    local_peaks: list[tuple[float, float]] = []
    for i in range(1, len(samples) - 1):
        s = samples[i]["score"]
        if s >= threshold and s >= samples[i - 1]["score"] and s >= samples[i + 1]["score"]:
            local_peaks.append((float(s), float(samples[i]["t"])))

    local_peaks.sort(reverse=True)
    chosen: list[float] = []
    for _, t in local_peaks:
        if all(abs(t - existing) >= 0.8 for existing in chosen):
            chosen.append(t)
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
    nearest = min(samples, key=lambda s: abs(float(s["t"]) - timestamp))
    return float(nearest["score"])


def _extract_at(cap: cv2.VideoCapture, fps: float, timestamp: float):
    frame_number = max(0, int(round(timestamp * fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ok, frame = cap.read()
    if not ok:
        return None, frame_number
    return frame, frame_number


def analyze_video(video_id: int) -> None:
    with connection() as conn:
        video = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if not video:
            return
        conn.execute("UPDATE videos SET status='processing', error=NULL WHERE id=?", (video_id,))

    video_path = UPLOAD_DIR / video["stored_name"]
    frame_dir = FRAME_DIR / str(video_id)
    frame_dir.mkdir(parents=True, exist_ok=True)

    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise VideoAnalysisError("OpenCV could not open the uploaded video.")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if fps <= 0 or frame_count <= 0:
            raise VideoAnalysisError("The video does not expose valid FPS/frame metadata.")
        duration = frame_count / fps

        samples = _motion_samples(cap, fps, frame_count)
        candidates = _candidate_times(samples)
        selected = sorted(_timeline_times(duration) | candidates)

        frame_rows = []
        thumbnail_path = None
        candidate_lookup = set(candidates)

        # Clean old generated frame rows/files for a safe re-analysis.
        with connection() as conn:
            conn.execute("DELETE FROM frames WHERE video_id=?", (video_id,))
        for old in frame_dir.glob("*.jpg"):
            old.unlink(missing_ok=True)

        for idx, timestamp in enumerate(selected):
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
            frame_rows.append(
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

        if thumbnail_path is None and frame_rows:
            thumbnail_path = frame_rows[0][3]

        with connection() as conn:
            conn.executemany(
                """
                INSERT INTO frames(video_id,timestamp,frame_number,image_path,motion_score,is_candidate,kind)
                VALUES(?,?,?,?,?,?,?)
                """,
                frame_rows,
            )
            conn.execute(
                """
                UPDATE videos
                SET status='complete', fps=?, duration=?, width=?, height=?, frame_count=?,
                    thumbnail_path=?, motion_json=?, analyzed_at=CURRENT_TIMESTAMP, error=NULL
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
    except Exception as exc:
        with connection() as conn:
            conn.execute(
                "UPDATE videos SET status='failed', error=?, analyzed_at=CURRENT_TIMESTAMP WHERE id=?",
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
        raise VideoAnalysisError("Video analysis is not complete yet")

    cap = cv2.VideoCapture(str(UPLOAD_DIR / video["stored_name"]))
    if not cap.isOpened():
        raise VideoAnalysisError("Could not reopen source video")

    seq_dir = FRAME_DIR / str(video_id) / "sequences"
    seq_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for idx, offset in enumerate(offsets):
        t = max(0.0, min(duration - 0.001, center + float(offset)))
        frame, frame_number = _extract_at(cap, fps, t)
        if frame is None:
            continue
        name = f"seq_{center:010.3f}_{idx:02d}_{t:010.3f}.jpg"
        out = seq_dir / name
        _write_jpeg(frame, out, max_width=1280)
        results.append(
            {
                "timestamp": round(t, 3),
                "offset": round(float(offset), 3),
                "frame_number": frame_number,
                "image_url": f"/media/frames/{video_id}/sequences/{name}",
            }
        )

    cap.release()
    return results
