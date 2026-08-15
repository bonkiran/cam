from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analyzer import AnalysisCancelled, VideoAnalysisError, analyze_video, extract_sequence, prepare_video
from .database import FRAME_DIR, UPLOAD_DIR, connection, fetch_all, fetch_one, init_db, json_or_default

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"

app = FastAPI(title="CrickAnalysis", version="0.2.0")
init_db()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/media/frames", StaticFiles(directory=FRAME_DIR), name="frames")

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
ANALYSIS_MODES = {"quick", "shot", "full"}

_cancel_lock = threading.Lock()
_cancel_events: dict[int, threading.Event] = {}


class EventCreate(BaseModel):
    timestamp: float = Field(ge=0)
    event_type: Literal["four", "six", "dot", "single", "two", "three", "wicket", "other"]
    label: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class SequenceRequest(BaseModel):
    center_timestamp: float = Field(ge=0)
    offsets: list[float] = Field(
        default_factory=lambda: [-1.0, -0.65, -0.35, -0.15, 0.0, 0.2, 0.5, 0.85],
        min_length=1,
        max_length=24,
    )


def _safe_video(video: dict | None) -> dict:
    if not video:
        raise HTTPException(404, "Video not found")
    video = dict(video)
    video["video_url"] = f"/media/uploads/{video['stored_name']}"
    video["motion"] = json_or_default(video.pop("motion_json", None), [])
    return video


def _limit_label() -> str:
    mb = MAX_UPLOAD_BYTES / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:g} GB"
    return f"{mb:g} MB"


def _new_cancel_event(video_id: int) -> threading.Event:
    event = threading.Event()
    with _cancel_lock:
        old = _cancel_events.get(video_id)
        if old:
            old.set()
        _cancel_events[video_id] = event
    return event


def _run_background(video_id: int, mode: str, cancel_event: threading.Event) -> None:
    try:
        if mode == "full":
            analyze_video(video_id, cancel_event=cancel_event)
        else:
            prepare_video(video_id, mode=mode, cancel_event=cancel_event)
    except AnalysisCancelled:
        pass
    except Exception:
        pass
    finally:
        with _cancel_lock:
            if _cancel_events.get(video_id) is cancel_event:
                _cancel_events.pop(video_id, None)


def _schedule_analysis(background_tasks: BackgroundTasks, video_id: int, mode: str) -> None:
    cancel_event = _new_cancel_event(video_id)
    background_tasks.add_task(_run_background, video_id, mode, cancel_event)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "CrickAnalysis", "version": app.version}


@app.get("/api/config")
def config():
    return {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_upload_label": _limit_label(),
        "default_analysis_mode": "quick",
        "analysis_modes": {
            "quick": {"label": "Quick Review", "description": "Metadata plus a small preview set. No full-video motion scan."},
            "shot": {"label": "Analyze Specific Shot", "description": "Prepare the video quickly, then seek to the exact shot for slow-motion and evidence review."},
            "full": {"label": "Full Video Scan", "description": "Optional heavier scan across the entire video for motion candidates."},
        },
    }


@app.get("/api/dashboard")
def dashboard():
    with connection() as conn:
        video_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM videos WHERE status='complete'").fetchone()[0]
        player_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        boundaries = conn.execute("SELECT COUNT(*) FROM events WHERE event_type IN ('four','six')").fetchone()[0]
        sixes = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='six'").fetchone()[0]
    recent = fetch_all("""SELECT v.*, p.name AS player_name,
               (SELECT COUNT(*) FROM events e WHERE e.video_id=v.id) AS event_count
        FROM videos v LEFT JOIN players p ON p.id=v.player_id
        ORDER BY v.id DESC LIMIT 6""")
    return {"video_count": video_count, "completed_count": completed, "player_count": player_count,
            "boundaries": boundaries, "sixes": sixes, "recent": [_safe_video(v) for v in recent]}


@app.get("/api/players")
def players():
    return fetch_all("""SELECT p.*, COUNT(v.id) AS video_count,
               SUM(CASE WHEN v.status='complete' THEN 1 ELSE 0 END) AS completed_analyses
        FROM players p LEFT JOIN videos v ON v.player_id=p.id
        GROUP BY p.id ORDER BY p.name COLLATE NOCASE""")


@app.get("/api/videos")
def videos():
    rows = fetch_all("""SELECT v.*, p.name AS player_name,
               (SELECT COUNT(*) FROM events e WHERE e.video_id=v.id) AS event_count
        FROM videos v LEFT JOIN players p ON p.id=v.player_id
        ORDER BY v.id DESC""")
    return [_safe_video(r) for r in rows]


@app.post("/api/videos", status_code=201)
def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                 player_name: str = Form("Unknown Player"),
                 analysis_mode: Literal["quick", "shot", "full"] = Form("quick")):
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported video type: {suffix or 'unknown'}")
    player_name = (player_name or "Unknown Player").strip()[:100]
    with connection() as conn:
        player = conn.execute("SELECT id FROM players WHERE name=? COLLATE NOCASE", (player_name,)).fetchone()
        if player:
            player_id = int(player["id"])
        else:
            cur = conn.execute("INSERT INTO players(name) VALUES(?)", (player_name,))
            player_id = int(cur.lastrowid)

    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = UPLOAD_DIR / stored_name
    size = 0
    with destination.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(413, f"Video exceeds the configured {_limit_label()} upload limit")
            out.write(chunk)

    with connection() as conn:
        cur = conn.execute("""INSERT INTO videos(player_id,original_name,stored_name,file_size,status,
                analysis_mode,progress_percent,progress_stage)
            VALUES(?,?,?,?, 'uploaded', ?, 0, 'Upload accepted')""",
            (player_id, file.filename or stored_name, stored_name, size, analysis_mode))
        video_id = int(cur.lastrowid)

    _schedule_analysis(background_tasks, video_id, analysis_mode)
    return _safe_video(fetch_one("""SELECT v.*, p.name AS player_name, 0 AS event_count
            FROM videos v LEFT JOIN players p ON p.id=v.player_id WHERE v.id=?""", (video_id,)))


@app.get("/api/videos/{video_id}")
def video_detail(video_id: int):
    return _safe_video(fetch_one("""SELECT v.*, p.name AS player_name,
               (SELECT COUNT(*) FROM events e WHERE e.video_id=v.id) AS event_count
        FROM videos v LEFT JOIN players p ON p.id=v.player_id WHERE v.id=?""", (video_id,)))


@app.get("/api/videos/{video_id}/frames")
def video_frames(video_id: int, candidates_only: bool = False):
    if not fetch_one("SELECT id FROM videos WHERE id=?", (video_id,)):
        raise HTTPException(404, "Video not found")
    sql = "SELECT * FROM frames WHERE video_id=?"
    params = [video_id]
    if candidates_only:
        sql += " AND is_candidate=1"
    sql += " ORDER BY timestamp"
    return fetch_all(sql, params)


@app.get("/api/videos/{video_id}/events")
def video_events(video_id: int):
    if not fetch_one("SELECT id FROM videos WHERE id=?", (video_id,)):
        raise HTTPException(404, "Video not found")
    return fetch_all("SELECT * FROM events WHERE video_id=? ORDER BY timestamp", (video_id,))


@app.post("/api/videos/{video_id}/events", status_code=201)
def create_event(video_id: int, payload: EventCreate):
    video = fetch_one("SELECT * FROM videos WHERE id=?", (video_id,))
    if not video:
        raise HTTPException(404, "Video not found")
    duration = float(video.get("duration") or 0)
    if duration and payload.timestamp > duration + 0.1:
        raise HTTPException(400, "Event timestamp is beyond video duration")
    with connection() as conn:
        cur = conn.execute("INSERT INTO events(video_id,timestamp,event_type,label,notes) VALUES(?,?,?,?,?)",
            (video_id, payload.timestamp, payload.event_type, payload.label, payload.notes))
        event_id = int(cur.lastrowid)
    return fetch_one("SELECT * FROM events WHERE id=?", (event_id,))


@app.delete("/api/events/{event_id}", status_code=204)
def delete_event(event_id: int):
    with connection() as conn:
        row = conn.execute("SELECT id FROM events WHERE id=?", (event_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Event not found")
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))


@app.post("/api/videos/{video_id}/extract-sequence")
def create_sequence(video_id: int, payload: SequenceRequest):
    try:
        return {"video_id": video_id, "center_timestamp": payload.center_timestamp,
                "frames": extract_sequence(video_id, payload.center_timestamp, payload.offsets)}
    except VideoAnalysisError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/videos/{video_id}/cancel")
def cancel_analysis(video_id: int):
    video = fetch_one("SELECT id,status FROM videos WHERE id=?", (video_id,))
    if not video:
        raise HTTPException(404, "Video not found")
    with _cancel_lock:
        cancel_event = _cancel_events.get(video_id)
        if cancel_event:
            cancel_event.set()
    if video["status"] in {"uploaded", "processing"}:
        with connection() as conn:
            conn.execute("UPDATE videos SET status='cancelled', progress_stage='Cancelling analysis' WHERE id=?", (video_id,))
    return {"ok": True, "video_id": video_id, "status": "cancelled"}


@app.post("/api/videos/{video_id}/reanalyze")
def reanalyze(video_id: int, background_tasks: BackgroundTasks,
              mode: Literal["quick", "shot", "full"] | None = None):
    video = fetch_one("SELECT id,analysis_mode FROM videos WHERE id=?", (video_id,))
    if not video:
        raise HTTPException(404, "Video not found")
    selected_mode = mode or video.get("analysis_mode") or "quick"
    if selected_mode not in ANALYSIS_MODES:
        raise HTTPException(400, "Unsupported analysis mode")
    with connection() as conn:
        conn.execute("UPDATE videos SET status='uploaded', analysis_mode=?, progress_percent=0, progress_stage='Queued for analysis', error=NULL WHERE id=?",
            (selected_mode, video_id))
    _schedule_analysis(background_tasks, video_id, selected_mode)
    return {"ok": True, "video_id": video_id, "status": "processing", "analysis_mode": selected_mode}


@app.get("/{path:path}")
def spa(path: str):
    return FileResponse(STATIC_DIR / "index.html")
