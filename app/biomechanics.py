from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Literal

import cv2
import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from .database import DATA_DIR, UPLOAD_DIR, connection, fetch_all, fetch_one

router = APIRouter()

POSE_ENGINE_URL = os.environ.get("POSE_ENGINE_URL", "").strip().rstrip("/")
POSE_ENGINE_UPLOAD_TIMEOUT = int(os.environ.get("POSE_ENGINE_UPLOAD_TIMEOUT", "900"))
POSE_ENGINE_POLL_SECONDS = float(os.environ.get("POSE_ENGINE_POLL_SECONDS", "3"))
POSE_ENGINE_MAX_WAIT_SECONDS = int(os.environ.get("POSE_ENGINE_MAX_WAIT_SECONDS", "180"))
BIOMECH_DIR = DATA_DIR / "biomechanics"
BIOMECH_DIR.mkdir(parents=True, exist_ok=True)

POSE_ENGINE_PROVIDER = "PoseForge-compatible SAM-3D"
METRIC_VERSION = "crickanalysis-geometry-v1"

SKELETON_KEYS = (
    "pelvis", "spine3", "neck", "head",
    "lead_shoulder", "lead_elbow", "lead_wrist",
    "trail_shoulder", "trail_elbow", "trail_wrist",
    "lead_hip", "lead_knee", "lead_ankle", "lead_foot",
    "trail_hip", "trail_knee", "trail_ankle", "trail_foot",
)

BONES = (
    ("pelvis", "spine3"), ("spine3", "neck"), ("neck", "head"),
    ("spine3", "lead_shoulder"), ("lead_shoulder", "lead_elbow"), ("lead_elbow", "lead_wrist"),
    ("spine3", "trail_shoulder"), ("trail_shoulder", "trail_elbow"), ("trail_elbow", "trail_wrist"),
    ("pelvis", "lead_hip"), ("lead_hip", "lead_knee"), ("lead_knee", "lead_ankle"), ("lead_ankle", "lead_foot"),
    ("pelvis", "trail_hip"), ("trail_hip", "trail_knee"), ("trail_knee", "trail_ankle"), ("trail_ankle", "trail_foot"),
)


class BiomechanicsError(RuntimeError):
    pass


class BiomechanicsCreate(BaseModel):
    center_timestamp: float = Field(ge=0)
    window_seconds: float = Field(default=6.0, ge=3.0, le=8.0)
    handedness: Literal["right", "left"] = "right"
    camera_view: Literal["front", "side", "other"] = "other"
    height_cm: float | None = Field(default=None, ge=100, le=230)


def _ensure_table() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS biomechanics_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL,
                center_timestamp REAL NOT NULL,
                window_seconds REAL NOT NULL,
                start_timestamp REAL,
                end_timestamp REAL,
                handedness TEXT NOT NULL,
                camera_view TEXT NOT NULL,
                height_cm REAL,
                status TEXT NOT NULL DEFAULT 'queued',
                progress_percent INTEGER NOT NULL DEFAULT 0,
                progress_stage TEXT NOT NULL DEFAULT 'Queued',
                error TEXT,
                person_id TEXT,
                people_json TEXT,
                result_path TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_biomechanics_video
            ON biomechanics_runs(video_id, id DESC);
            """
        )


def pose_engine_configured() -> bool:
    return bool(POSE_ENGINE_URL)


def _row(run_id: int) -> dict[str, Any]:
    _ensure_table()
    row = fetch_one("SELECT * FROM biomechanics_runs WHERE id=?", (run_id,))
    if not row:
        raise BiomechanicsError("Biomechanics run not found")
    return row


def _update(run_id: int, *, status: str | None = None, percent: int | None = None,
            stage: str | None = None, error: str | None = None, **fields: Any) -> None:
    assignments: list[str] = []
    values: list[Any] = []
    if status is not None:
        assignments.append("status=?")
        values.append(status)
    if percent is not None:
        assignments.append("progress_percent=?")
        values.append(max(0, min(100, int(percent))))
    if stage is not None:
        assignments.append("progress_stage=?")
        values.append(stage)
    if error is not None:
        assignments.append("error=?")
        values.append(error)
    for key, value in fields.items():
        if key not in {"start_timestamp", "end_timestamp", "person_id", "people_json", "result_path", "completed_at"}:
            continue
        assignments.append(f"{key}=?")
        values.append(value)
    if not assignments:
        return
    values.append(run_id)
    with connection() as conn:
        conn.execute(f"UPDATE biomechanics_runs SET {', '.join(assignments)} WHERE id=?", tuple(values))


def _safe_run(row: dict[str, Any], include_result: bool = False) -> dict[str, Any]:
    run = dict(row)
    raw_people = run.pop("people_json", None)
    try:
        run["people"] = json.loads(raw_people) if raw_people else []
    except json.JSONDecodeError:
        run["people"] = []
    result_path = run.get("result_path")
    run["result"] = None
    if include_result and result_path:
        path = Path(result_path)
        if path.exists():
            try:
                run["result"] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                run["result"] = None
    return run


def _video_source(video_id: int) -> tuple[dict[str, Any], Path]:
    video = fetch_one("SELECT * FROM videos WHERE id=?", (video_id,))
    if not video:
        raise BiomechanicsError("Video not found")
    source = UPLOAD_DIR / video["stored_name"]
    if not source.exists():
        raise BiomechanicsError("Source video is no longer available on this server")
    return video, source


def _fit_size(width: int, height: int, max_long_side: int = 960) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise BiomechanicsError("Video has invalid dimensions")
    longest = max(width, height)
    if longest <= max_long_side:
        out_w, out_h = width, height
    else:
        scale = max_long_side / longest
        out_w = max(2, int(round(width * scale)))
        out_h = max(2, int(round(height * scale)))
    if out_w % 2:
        out_w -= 1
    if out_h % 2:
        out_h -= 1
    return max(2, out_w), max(2, out_h)


def _extract_clip(video_id: int, run_id: int, center: float, window_seconds: float) -> dict[str, Any]:
    video, source = _video_source(video_id)
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise BiomechanicsError("OpenCV could not open the source video")

    fps = float(video.get("fps") or cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(video.get("frame_count") or cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = float(video.get("duration") or (frame_count / fps if fps > 0 else 0))
    width = int(video.get("width") or cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(video.get("height") or cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if fps <= 0 or duration <= 0:
        cap.release()
        raise BiomechanicsError("Video metadata is not ready for a biomechanics scan")

    half = window_seconds / 2.0
    start = max(0.0, center - half)
    end = min(duration, center + half)
    if end - start < 1.0:
        cap.release()
        raise BiomechanicsError("Selected shot window is too close to the video edge")

    out_dir = BIOMECH_DIR / str(video_id) / str(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "shot_clip.mp4"

    out_w, out_h = _fit_size(width, height)
    target_fps = min(30.0, fps)
    stride = max(1, int(round(fps / target_fps)))
    effective_fps = fps / stride

    start_frame = max(0, int(math.floor(start * fps)))
    end_frame = min(frame_count - 1, int(math.ceil(end * fps))) if frame_count > 0 else int(math.ceil(end * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    writer = cv2.VideoWriter(
        str(out_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        effective_fps,
        (out_w, out_h),
    )
    if not writer.isOpened():
        cap.release()
        raise BiomechanicsError("Could not create the short biomechanics clip")

    source_index = start_frame
    written = 0
    try:
        while source_index <= end_frame:
            ok, frame = cap.read()
            if not ok:
                break
            if (source_index - start_frame) % stride == 0:
                if (frame.shape[1], frame.shape[0]) != (out_w, out_h):
                    frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
                writer.write(frame)
                written += 1
            source_index += 1
    finally:
        writer.release()
        cap.release()

    if written < 2 or not out_path.exists() or out_path.stat().st_size <= 0:
        raise BiomechanicsError("Could not extract enough frames for the shot clip")

    actual_end = min(end, start + written / effective_fps)
    return {
        "path": out_path,
        "start": round(start, 4),
        "end": round(actual_end, 4),
        "fps": effective_fps,
        "frame_count": written,
        "width": out_w,
        "height": out_h,
    }


def _engine_get(path: str, timeout: float = 30.0) -> requests.Response:
    response = requests.get(f"{POSE_ENGINE_URL}{path}", timeout=timeout)
    response.raise_for_status()
    return response


def _submit_to_engine(clip_path: Path) -> list[str]:
    if not POSE_ENGINE_URL:
        raise BiomechanicsError("Pose engine is not configured. Set POSE_ENGINE_URL to a PoseForge-compatible SAM-3D service.")
    with clip_path.open("rb") as handle:
        response = requests.post(
            f"{POSE_ENGINE_URL}/upload",
            files={"video": (clip_path.name, handle, "video/mp4")},
            timeout=POSE_ENGINE_UPLOAD_TIMEOUT,
        )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    people = payload.get("people") if isinstance(payload, dict) else None
    if isinstance(people, list) and people:
        return sorted(str(p) for p in people)

    deadline = time.time() + POSE_ENGINE_MAX_WAIT_SECONDS
    while time.time() < deadline:
        try:
            data = _engine_get("/people").json()
        except (requests.RequestException, ValueError):
            data = []
        if isinstance(data, list) and data:
            return sorted(str(p) for p in data)
        time.sleep(POSE_ENGINE_POLL_SECONDS)
    raise BiomechanicsError("Pose engine finished upload but did not publish any tracked people before the timeout")


def _fetch_person_joints(person_id: str) -> list[Any]:
    response = _engine_get(f"/person/{person_id}/joints", timeout=120)
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise BiomechanicsError(f"No joints timeline returned for {person_id}")
    return payload


def _extract_frame_joints(frame_data: Any) -> list[list[float]] | None:
    joints: Any = None
    if isinstance(frame_data, dict):
        joints = frame_data.get("pred_joint_coords") or frame_data.get("mhr_joints") or frame_data.get("joints")
    elif isinstance(frame_data, list):
        joints = frame_data
    if not isinstance(joints, list) or not joints:
        return None

    # PoseForge's SAM-3D output contains an extra leading element before the
    # body-joint indexing used by its viewer. Only strip it when the shape
    # is large enough to preserve the highest keypoint index used here.
    if len(joints) >= 127:
        joints = joints[1:]

    normalized: list[list[float]] = []
    for joint in joints:
        if not isinstance(joint, (list, tuple)) or len(joint) < 3:
            normalized.append([math.nan, math.nan, math.nan])
            continue
        try:
            normalized.append([float(joint[0]), float(joint[1]), float(joint[2])])
        except (TypeError, ValueError):
            normalized.append([math.nan, math.nan, math.nan])
    return normalized


def _valid_point(point: list[float] | None) -> bool:
    return bool(point and len(point) >= 3 and all(math.isfinite(float(v)) for v in point[:3]))


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _horizontal_distance(a: list[float], b: list[float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2)


def _angle_at(a: list[float], b: list[float], c: list[float]) -> float | None:
    ba = [a[i] - b[i] for i in range(3)]
    bc = [c[i] - b[i] for i in range(3)]
    ba_n = math.sqrt(sum(v * v for v in ba))
    bc_n = math.sqrt(sum(v * v for v in bc))
    if ba_n <= 1e-9 or bc_n <= 1e-9:
        return None
    cosine = sum(ba[i] * bc[i] for i in range(3)) / (ba_n * bc_n)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _angle_from_vertical(pelvis: list[float], neck: list[float]) -> float | None:
    vector = [neck[i] - pelvis[i] for i in range(3)]
    norm = math.sqrt(sum(v * v for v in vector))
    if norm <= 1e-9:
        return None
    cosine = vector[1] / norm
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _keypoint_map(handedness: str) -> dict[str, int]:
    is_left = handedness.lower() == "left"
    return {
        "pelvis": 0,
        "spine3": 36,
        "neck": 109,
        "head": 125,
        "lead_shoulder": 38 if is_left else 74,
        "lead_elbow": 39 if is_left else 75,
        "lead_wrist": 40 if is_left else 76,
        "trail_shoulder": 74 if is_left else 38,
        "trail_elbow": 75 if is_left else 39,
        "trail_wrist": 76 if is_left else 40,
        "lead_hip": 17 if is_left else 1,
        "lead_knee": 18 if is_left else 2,
        "lead_ankle": 20 if is_left else 5,
        "lead_foot": 23 if is_left else 7,
        "trail_hip": 1 if is_left else 17,
        "trail_knee": 2 if is_left else 18,
        "trail_ankle": 5 if is_left else 20,
        "trail_foot": 7 if is_left else 23,
    }


def _named_skeleton(joints: list[list[float]], mapping: dict[str, int]) -> dict[str, list[float] | None]:
    result: dict[str, list[float] | None] = {}
    for name in SKELETON_KEYS:
        index = mapping[name]
        point = joints[index] if 0 <= index < len(joints) else None
        result[name] = [round(float(v), 6) for v in point[:3]] if _valid_point(point) else None
    return result


def _body_height_proxy(points: dict[str, list[float] | None]) -> float | None:
    head = points.get("head")
    lead_ankle = points.get("lead_ankle")
    trail_ankle = points.get("trail_ankle")
    if not (_valid_point(head) and _valid_point(lead_ankle) and _valid_point(trail_ankle)):
        return None
    mid_ankle = [(lead_ankle[i] + trail_ankle[i]) / 2.0 for i in range(3)]
    value = _distance(head, mid_ankle)
    return value if value > 1e-9 else None


def _metrics_for_frame(points: dict[str, list[float] | None],
                       first_head: list[float] | None,
                       height_cm: float | None) -> dict[str, float | None]:
    required_knee = [points.get("lead_hip"), points.get("lead_knee"), points.get("lead_ankle")]
    knee = _angle_at(required_knee[0], required_knee[1], required_knee[2]) if all(_valid_point(p) for p in required_knee) else None

    pelvis = points.get("pelvis")
    neck = points.get("neck")
    trunk = _angle_from_vertical(pelvis, neck) if _valid_point(pelvis) and _valid_point(neck) else None

    lead_ankle = points.get("lead_ankle")
    trail_ankle = points.get("trail_ankle")
    proxy = _body_height_proxy(points)
    stance_ratio = None
    if _valid_point(lead_ankle) and _valid_point(trail_ankle) and proxy:
        stance_ratio = _distance(lead_ankle, trail_ankle) / proxy

    head = points.get("head")
    head_disp_ratio = None
    head_offset_ratio = None
    if _valid_point(head) and proxy:
        if _valid_point(first_head):
            head_disp_ratio = _horizontal_distance(head, first_head) / proxy
        if _valid_point(pelvis):
            head_offset_ratio = _horizontal_distance(head, pelvis) / proxy

    return {
        "front_knee_angle_deg": round(knee, 2) if knee is not None else None,
        "trunk_lean_deg": round(trunk, 2) if trunk is not None else None,
        "stance_width_ratio": round(stance_ratio, 4) if stance_ratio is not None else None,
        "stance_width_cm": round(stance_ratio * height_cm, 2) if stance_ratio is not None and height_cm else None,
        "head_displacement_ratio": round(head_disp_ratio, 4) if head_disp_ratio is not None else None,
        "head_displacement_cm": round(head_disp_ratio * height_cm, 2) if head_disp_ratio is not None and height_cm else None,
        "head_offset_from_pelvis_ratio": round(head_offset_ratio, 4) if head_offset_ratio is not None else None,
        "head_offset_from_pelvis_cm": round(head_offset_ratio * height_cm, 2) if head_offset_ratio is not None and height_cm else None,
    }


def _numeric_summary(frames: list[dict[str, Any]], key: str) -> dict[str, float] | None:
    values = [frame["metrics"].get(key) for frame in frames]
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not clean:
        return None
    return {
        "min": round(min(clean), 3),
        "max": round(max(clean), 3),
        "mean": round(sum(clean) / len(clean), 3),
    }


def _build_result(run: dict[str, Any], clip: dict[str, Any], person_id: str,
                  people: list[str], joints_timeline: list[Any]) -> dict[str, Any]:
    mapping = _keypoint_map(run["handedness"])
    valid_frames: list[tuple[int, dict[str, list[float] | None]]] = []
    for index, frame_data in enumerate(joints_timeline):
        joints = _extract_frame_joints(frame_data)
        if not joints or len(joints) <= max(mapping.values()):
            continue
        points = _named_skeleton(joints, mapping)
        if _valid_point(points.get("head")) and _valid_point(points.get("pelvis")):
            valid_frames.append((index, points))

    if not valid_frames:
        raise BiomechanicsError("Pose engine returned a joints timeline, but no usable body frames were found")

    first_head = valid_frames[0][1].get("head")
    source_count = len(joints_timeline)
    start = float(clip["start"])
    end = float(clip["end"])
    span = max(0.001, end - start)

    frames: list[dict[str, Any]] = []
    for source_index, points in valid_frames:
        progress = source_index / max(1, source_count - 1)
        timestamp = start + progress * span
        frames.append(
            {
                "pose_frame_index": source_index,
                "timestamp": round(timestamp, 4),
                "skeleton": points,
                "metrics": _metrics_for_frame(points, first_head, run.get("height_cm")),
            }
        )

    metric_keys = (
        "front_knee_angle_deg",
        "trunk_lean_deg",
        "stance_width_ratio",
        "stance_width_cm",
        "head_displacement_ratio",
        "head_displacement_cm",
        "head_offset_from_pelvis_ratio",
        "head_offset_from_pelvis_cm",
    )
    summary = {key: _numeric_summary(frames, key) for key in metric_keys}
    return {
        "schema_version": 1,
        "metric_version": METRIC_VERSION,
        "provider_contract": POSE_ENGINE_PROVIDER,
        "grading": "none",
        "warning": "Experimental geometry only. No elite/good/poor technique grading is applied.",
        "run_id": run["id"],
        "video_id": run["video_id"],
        "center_timestamp": run["center_timestamp"],
        "start_timestamp": start,
        "end_timestamp": end,
        "clip_fps": clip["fps"],
        "clip_frame_count": clip["frame_count"],
        "handedness": run["handedness"],
        "camera_view": run["camera_view"],
        "height_cm": run.get("height_cm"),
        "person_id": person_id,
        "detected_people": people,
        "bones": [list(bone) for bone in BONES],
        "frames": frames,
        "summary": summary,
    }


def _run_scan(run_id: int) -> None:
    try:
        run = _row(run_id)
        _update(run_id, status="processing", percent=5, stage="Extracting short shot clip")
        clip = _extract_clip(
            int(run["video_id"]),
            run_id,
            float(run["center_timestamp"]),
            float(run["window_seconds"]),
        )
        _update(
            run_id,
            percent=25,
            stage="Sending clip to SAM-3D pose engine",
            start_timestamp=clip["start"],
            end_timestamp=clip["end"],
        )
        people = _submit_to_engine(clip["path"])
        _update(run_id, percent=68, stage=f"Reading pose tracks ({len(people)} detected)", people_json=json.dumps(people))

        candidates: list[tuple[int, str, list[Any]]] = []
        for person_id in people:
            try:
                timeline = _fetch_person_joints(person_id)
            except (BiomechanicsError, requests.RequestException, ValueError):
                continue
            usable = sum(1 for item in timeline if _extract_frame_joints(item))
            candidates.append((usable, person_id, timeline))

        if not candidates:
            raise BiomechanicsError("No usable person joints timeline was available from the pose engine")

        candidates.sort(key=lambda item: item[0], reverse=True)
        _, selected_person, timeline = candidates[0]
        _update(run_id, percent=82, stage=f"Computing cricket geometry for {selected_person}", person_id=selected_person)

        run = _row(run_id)
        result = _build_result(run, clip, selected_person, people, timeline)
        result_path = BIOMECH_DIR / str(run["video_id"]) / str(run_id) / "result.json"
        result_path.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
        _update(
            run_id,
            status="complete",
            percent=100,
            stage="Biomechanics scan ready",
            result_path=str(result_path),
            completed_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
    except requests.RequestException as exc:
        _update(run_id, status="failed", percent=100, stage="Pose engine request failed", error=str(exc))
    except Exception as exc:
        _update(run_id, status="failed", percent=100, stage="Biomechanics scan failed", error=str(exc))


@router.get("/api/biomechanics/config")
def biomechanics_config():
    return {
        "configured": pose_engine_configured(),
        "provider_contract": POSE_ENGINE_PROVIDER,
        "metric_version": METRIC_VERSION,
        "max_window_seconds": 8,
        "min_window_seconds": 3,
        "grading": False,
        "message": (
            "Pose engine connected."
            if pose_engine_configured()
            else "GPU pose engine not connected. Configure POSE_ENGINE_URL with a PoseForge-compatible SAM-3D service."
        ),
    }


@router.post("/api/videos/{video_id}/biomechanics", status_code=202)
def create_biomechanics_run(video_id: int, payload: BiomechanicsCreate, background_tasks: BackgroundTasks):
    _ensure_table()
    if not pose_engine_configured():
        raise HTTPException(
            503,
            "GPU pose engine is not configured yet. Set POSE_ENGINE_URL to a PoseForge-compatible SAM-3D service.",
        )
    video = fetch_one("SELECT id,status,duration,fps FROM videos WHERE id=?", (video_id,))
    if not video:
        raise HTTPException(404, "Video not found")
    if video["status"] != "complete" or not video.get("fps"):
        raise HTTPException(409, "Prepare the video before starting a biomechanics scan")
    duration = float(video.get("duration") or 0)
    if duration and payload.center_timestamp > duration:
        raise HTTPException(400, "Biomechanics center timestamp is beyond the video duration")

    with connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO biomechanics_runs(
                video_id,center_timestamp,window_seconds,handedness,camera_view,height_cm,
                status,progress_percent,progress_stage
            ) VALUES(?,?,?,?,?,?, 'queued',0,'Queued for pose analysis')
            """,
            (
                video_id,
                payload.center_timestamp,
                payload.window_seconds,
                payload.handedness,
                payload.camera_view,
                payload.height_cm,
            ),
        )
        run_id = int(cur.lastrowid)
    background_tasks.add_task(_run_scan, run_id)
    return _safe_run(_row(run_id))


@router.get("/api/videos/{video_id}/biomechanics")
def list_biomechanics_runs(video_id: int):
    _ensure_table()
    if not fetch_one("SELECT id FROM videos WHERE id=?", (video_id,)):
        raise HTTPException(404, "Video not found")
    rows = fetch_all("SELECT * FROM biomechanics_runs WHERE video_id=? ORDER BY id DESC", (video_id,))
    return [_safe_run(row, include_result=False) for row in rows]


@router.get("/api/biomechanics/{run_id}")
def biomechanics_run(run_id: int):
    try:
        return _safe_run(_row(run_id), include_result=True)
    except BiomechanicsError as exc:
        raise HTTPException(404, str(exc)) from exc
