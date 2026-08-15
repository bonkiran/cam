from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CRICKANALYSIS_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
DB_PATH = DATA_DIR / "crickanalysis.db"
UPLOAD_DIR = DATA_DIR / "uploads"
FRAME_DIR = DATA_DIR / "frames"

for path in (DATA_DIR, UPLOAD_DIR, FRAME_DIR):
    path.mkdir(parents=True, exist_ok=True)


@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_video_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
    additions = {
        "analysis_mode": "TEXT NOT NULL DEFAULT 'quick'",
        "progress_percent": "INTEGER NOT NULL DEFAULT 0",
        "progress_stage": "TEXT NOT NULL DEFAULT 'Uploaded'",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE videos ADD COLUMN {name} {definition}")


def init_db() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                handedness TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL UNIQUE,
                file_size INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'uploaded',
                analysis_mode TEXT NOT NULL DEFAULT 'quick',
                progress_percent INTEGER NOT NULL DEFAULT 0,
                progress_stage TEXT NOT NULL DEFAULT 'Uploaded',
                error TEXT,
                fps REAL,
                duration REAL,
                width INTEGER,
                height INTEGER,
                frame_count INTEGER,
                thumbnail_path TEXT,
                motion_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                analyzed_at TEXT,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                frame_number INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                motion_score REAL NOT NULL DEFAULT 0,
                is_candidate INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL DEFAULT 'timeline',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_frames_video_time
            ON frames(video_id, timestamp);

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                label TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_events_video_time
            ON events(video_id, timestamp);
            """
        )
        _ensure_video_columns(conn)


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def fetch_one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    with connection() as conn:
        return row_dict(conn.execute(sql, tuple(params)).fetchone())


def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connection() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connection() as conn:
        cur = conn.execute(sql, tuple(params))
        return int(cur.lastrowid or 0)


def execute_many(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    with connection() as conn:
        conn.executemany(sql, [tuple(r) for r in rows])


def json_or_default(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
