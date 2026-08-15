from __future__ import annotations

import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analyzer import VideoAnalysisError, analyze_video, extract_sequence
from .database import FRAME_DIR, UPLOAD_DIR, connection, fetch_all, fetch_one, init_db, json_or_default

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"

app = FastAPI(title="CrickAnalysis", version="0.1.0")
init_db()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/media/frames", StaticFiles(directory=FRAME_DIR), name="frames")

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
# Local default is 2 GB. Render deployment overrides this to 1 GB initially.


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


def _analyze_background(video_id: int):
    try:
        analyze_video(video_id)
    except Exception:
        # Failure is persisted by the analyzer; background exceptions must not kill the API.
        pass


@app.get("/api/health")
def health():
    return {"ok": True, "service": "CrickAnalysis", "version": app.version}


@app.get("/api/dashboard")
def dashboard():
    with connection() as conn:
        video_count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM videos WHERE status='complete'").fetchone()[0]
        player_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        boundaries = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type IN ('four','six')"
        ).fetchone()[0]
        sixes = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='six'").fetchone()[0]
    recent = fetch_all(
        """
        SELECT v.*, p.name AS player_name,
               (SELECT COUNT(*) FROM events e WHERE e.video_id=v.id) AS event_count
        FROM videos v LEFT JOIN players p ON p.id=v.player_id
        ORDER BY v.id DESC LIMIT 6
        """
    )
    return {
        "video_count": video_count,
        "completed_count": completed,
        "player_count": player_count,
        "boundaries": boundaries,
        "sixes": sixes,
        "recent": [_safe_video(v) for v in recent],
    }


@app.get("/api/players")
def players():
    return fetch_all(
        """
        SELECT p.*, COUNT(v.id) AS video_count,
               SUM(CASE WHEN v.status='complete' THEN 1 ELSE 0 END) AS completed_analyses
        FROM players p LEFT JOIN videos v ON v.player_id=p.id
        GROUP BY p.id ORDER BY p.name COLLATE NOCASE
        """
    )


@app.get("/api/videos")
def videos():
    rows = fetch_all(
        """
        SELECT v.*, p.name AS player_name,
               (SELECT COUNT(*) FROM events e WHERE e.video_id=v.id) AS event_count
        FROM videos v LEFT JOIN players p ON p.id=v.player_id
        ORDER BY v.id DESC
        """
    )
    return [_safe_video(r) for r in rows]


@app.post("/api/videos", status_code=201)
def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    player_name: str = Form("Unknown Player"),
):
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
                raise HTTPException(413, "Video exceeds the 2 GB local MVP upload limit")
            out.write(chunk)

    with connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO videos(player_id,original_name,stored_name,file_size,status)
            VALUES(?,?,?,?, 'uploaded')
            """,
            (player_id, file.filename or stored_name, stored_name, size),
        )
        video_id = int(cur.lastrowid)

    background_tasks.add_task(_analyze_background, video_id)
    return _safe_video(
        fetch_one(
            """
            SELECT v.*, p.name AS player_name, 0 AS event_count
            FROM videos v LEFT JOIN players p ON p.id=v.player_id WHERE v.id=?
            """,
            (video_id,),
        )
    )


@app.get("/api/videos/{video_id}")
def video_detail(video_id: int):
    video = fetch_one(
        """
        SELECT v.*, p.name AS player_name,
               (SELECT COUNT(*) FROM events e WHERE e.video_id=v.id) AS event_count
        FROM videos v LEFT JOIN players p ON p.id=v.player_id WHERE v.id=?
        """,
        (video_id,),
    )
    return _safe_video(video)


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
        cur = conn.execute(
            "INSERT INTO events(video_id,timestamp,event_type,label,notes) VALUES(?,?,?,?,?)",
            (video_id, payload.timestamp, payload.event_type, payload.label, payload.notes),
        )
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
        return {
            "video_id": video_id,
            "center_timestamp": payload.center_timestamp,
            "frames": extract_sequence(video_id, payload.center_timestamp, payload.offsets),
        }
    except VideoAnalysisError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/videos/{video_id}/reanalyze")
def reanalyze(video_id: int, background_tasks: BackgroundTasks):
    if not fetch_one("SELECT id FROM videos WHERE id=?", (video_id,)):
        raise HTTPException(404, "Video not found")
    background_tasks.add_task(_analyze_background, video_id)
    return {"ok": True, "video_id": video_id, "status": "processing"}


@app.get("/{path:path}")
def spa(path: str):
    # Serve API/media through their mounted routes above; all other paths get the SPA shell.
    index = STATIC_DIR / "index.html"
    return FileResponse(index)
