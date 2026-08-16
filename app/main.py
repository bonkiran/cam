from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analyzer import AnalysisCancelled, VideoAnalysisError, analyze_video, extract_sequence, prepare_video
from .database import FRAME_DIR, UPLOAD_DIR, connection, fetch_all, fetch_one, init_db, json_or_default

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"

app = FastAPI(title="CrickAnalysis", version="0.3.0")
init_db()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/media/frames", StaticFiles(directory=FRAME_DIR), name="frames")

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
ANALYSIS_MODES = {"quick", "shot", "full"}
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6").strip() or "gpt-5.6"

_cancel_lock = threading.Lock()
_cancel_events: dict[int, threading.Event] = {}

APP_HELP = """
CrickAnalysis app guide:
- Dashboard: high-level counts and recent uploaded analyses.
- Upload Video: enter a player name, choose Quick Review, Analyze Specific Shot, or Full Video Scan, then select a video.
- Quick Review: the recommended lightweight default. Reads metadata and generates a small preview set without scanning the whole video.
- Analyze Specific Shot: prepares the video quickly. In the review player, seek to the shot you care about and use slow motion, frame stepping, loop review, and Extract evidence sequence.
- Full Video Scan: optional heavier whole-video motion scan. It can take materially longer on large files.
- Video review controls: 0.1x, 0.25x, 0.5x, 1x playback; play/pause; -10 frames, -1 frame, +1 frame, +10 frames; loop around the selected moment; Coaching Full Screen; Extract evidence sequence.
- Coaching Full Screen expands the CrickAnalysis video stage so the custom coaching controls remain available.
- Players: local CrickAnalysis player profiles plus a CricClubs public lookup bridge by full name or CC Player ID. A true inline CricClubs data import will require official API access/credentials.
- Integrations: reference links to external cricket/video-analysis tools. They are reference links, not claimed technical integrations.
- Crick AI: the right-side assistant. It can explain how to use CrickAnalysis. When OPENAI_API_KEY is configured on the server it can also answer general/current cricket questions and use web search.
- Uploaded files on the current Render Free deployment use ephemeral local storage, so uploads/database data can be lost on restart or redeploy.
- Current automatic computer-vision output is still an MVP. Motion candidates are not claimed to be fully recognized cricket deliveries/shots, and biomechanics/ball/bat tracking are future model slices.
""".strip()


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


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


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


def _local_help_answer(message: str) -> str | None:
    q = message.lower()
    app_terms = {
        "upload", "quick review", "full video", "specific shot", "slow", "frame", "fullscreen",
        "full screen", "evidence", "player", "cricclubs", "integration", "cancel", "progress",
        "crickanalysis", "site", "app", "how do i", "where do i", "menu", "video",
    }
    if not any(term in q for term in app_terms):
        return None
    if "cricclubs" in q:
        return "Open Players and use CricClubs Player Lookup. Search by full name or CC Player ID. The current MVP opens a public CricClubs-focused lookup; a true inline data import will require official CricClubs API access."
    if "full screen" in q or "fullscreen" in q:
        return "Open an analyzed video and choose Coaching Full Screen. CrickAnalysis expands the whole video stage, so slow-motion, frame-step, loop, evidence, and time controls remain visible."
    if "slow" in q or "0.25" in q or "0.1" in q:
        return "In the video review workspace use 0.1×, 0.25×, 0.5×, or 1×. For exact technique review, pause and use -1/+1 frame or -10/+10 frames."
    if "evidence" in q:
        return "Seek to the exact shot/contact moment and choose Extract evidence sequence. The app captures a short set of source-video frames around that timestamp for detailed review."
    if "cancel" in q:
        return "While a video is in uploaded/processing state, use Cancel Analysis on the processing view. It cancels that analysis job without requiring a server restart."
    if "quick" in q:
        return "Quick Review is the recommended default: metadata plus a small preview-frame set, with no heavy full-video motion scan. It is intended to get you into the coaching player quickly."
    if "specific" in q or "shot" in q:
        return "Choose Analyze Specific Shot when you mainly want coaching review. The video is prepared lightly, then you seek to the exact shot and use slow motion, looping, frame stepping, and evidence extraction."
    if "full video" in q or "full scan" in q:
        return "Full Video Scan is optional and heavier. It scans the whole video for motion candidates and should only be used when you want broad candidate moments across the full recording."
    if "upload" in q:
        return "Open Upload Video, enter the player name, choose the review mode, select the video, preview it on the right, then choose Upload & Open Review. The displayed upload limit is read from the backend configuration."
    if "integration" in q:
        return "Open Integrations for the reference-tool library. Those cards are handy external links and are deliberately labeled as references rather than technical integrations."
    return "I can help with CrickAnalysis navigation, uploads, review modes, video controls, evidence extraction, Players/CricClubs lookup, Integrations, and processing/cancel behavior."


def _extract_response_text(payload: dict[str, Any]) -> str:
    pieces: list[str] = []
    for item in payload.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text" and content.get("text"):
                pieces.append(str(content["text"]))
    return "\n".join(pieces).strip()


def _call_crick_ai(message: str, context: dict[str, Any]) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    instructions = f"""You are Crick AI, the right-side assistant inside the CrickAnalysis web application.
Answer only cricket-related questions or questions about using CrickAnalysis. Be concise and practical.
For current cricket facts, schedules, players, news, rules changes, or other time-sensitive questions, use web search before answering.
When the user is on a video-analysis page, use supplied context such as player, video and timestamp, but never claim you visually inspected a frame unless the context explicitly contains analyzed visual evidence.
Do not claim the MVP has automatic biomechanics, ball tracking, bat tracking, delivery recognition or shot recognition unless the context explicitly says that output exists.

{APP_HELP}
"""
    body = {
        "model": OPENAI_MODEL,
        "store": False,
        "tools": [{"type": "web_search"}],
        "input": [
            {"role": "developer", "content": [{"type": "input_text", "text": instructions}]},
            {"role": "user", "content": [{"type": "input_text", "text": f"Current app context: {json.dumps(context, ensure_ascii=False)}\n\nQuestion: {message}"}]},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"Crick AI service returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Crick AI could not reach the AI service: {exc.reason}") from exc

    text = _extract_response_text(payload)
    if not text:
        raise RuntimeError("Crick AI returned no text response")
    return text


@app.get("/api/health")
def health():
    return {"ok": True, "service": "CrickAnalysis", "version": app.version}


@app.get("/api/config")
def config():
    return {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_upload_label": _limit_label(),
        "default_analysis_mode": "quick",
        "ai_configured": bool(OPENAI_API_KEY),
        "assistant_model": OPENAI_MODEL if OPENAI_API_KEY else None,
        "analysis_modes": {
            "quick": {"label": "Quick Review", "description": "Metadata plus a small preview set. No full-video motion scan."},
            "shot": {"label": "Analyze Specific Shot", "description": "Prepare the video quickly, then seek to the exact shot for slow-motion and evidence review."},
            "full": {"label": "Full Video Scan", "description": "Optional heavier scan across the entire video for motion candidates."},
        },
    }


@app.post("/api/assistant")
def assistant(payload: AssistantRequest):
    message = payload.message.strip()
    if not message:
        raise HTTPException(400, "Message is required")

    if not OPENAI_API_KEY:
        local_answer = _local_help_answer(message)
        if local_answer:
            return {"answer": local_answer, "mode": "app-help", "ai_configured": False}
        return {
            "answer": "Crick AI's general cricket mode is installed but the server does not yet have an OPENAI_API_KEY. CrickAnalysis help questions work now; configure the server key to enable general/current cricket Q&A and web search.",
            "mode": "setup-required",
            "ai_configured": False,
        }

    try:
        answer = _call_crick_ai(message, payload.context)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"answer": answer, "mode": "ai", "ai_configured": True, "model": OPENAI_MODEL}


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
                 player_name: str = Form(...),
                 analysis_mode: Literal["quick", "shot", "full"] = Form("quick")):
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported video type: {suffix or 'unknown'}")
    player_name = (player_name or "").strip()[:100]
    if not player_name:
        raise HTTPException(400, "Player name is required")
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
