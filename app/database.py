from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # SQLite-only local development remains supported.
    psycopg = None
    dict_row = None

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CRICKANALYSIS_DATA_DIR", str(BASE_DIR / "data"))).expanduser().resolve()
DB_PATH = DATA_DIR / "crickanalysis.db"
UPLOAD_DIR = DATA_DIR / "uploads"
FRAME_DIR = DATA_DIR / "frames"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
POSTGRES_ENABLED = bool(DATABASE_URL)

for path in (DATA_DIR, UPLOAD_DIR, FRAME_DIR):
    path.mkdir(parents=True, exist_ok=True)


class HybridRow(dict):
    """PostgreSQL row that supports both row['id'] and row[0] access like sqlite3.Row."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class CursorAdapter:
    def __init__(self, cursor, *, postgres: bool, lastrowid: int = 0):
        self._cursor = cursor
        self._postgres = postgres
        self.lastrowid = lastrowid

    def _row(self, row):
        if row is None:
            return None
        if self._postgres and isinstance(row, dict) and not isinstance(row, HybridRow):
            return HybridRow(row)
        return row

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self._cursor.fetchall()]

    @property
    def rowcount(self) -> int:
        return int(getattr(self._cursor, "rowcount", -1))


_ID_TABLES = {"academies", "players", "guardians", "videos", "frames", "events", "biomechanics_runs"}


def _translate_postgres_sql(sql: str) -> str:
    """Translate the small SQLite-flavored SQL surface used by the MVP to PostgreSQL."""
    translated = sql
    translated = re.sub(
        r"([A-Za-z_][A-Za-z0-9_.]*)\s*=\s*\?\s+COLLATE\s+NOCASE",
        r"LOWER(\1)=LOWER(?)",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"([A-Za-z_][A-Za-z0-9_.]*)\s+COLLATE\s+NOCASE",
        r"LOWER(\1)",
        translated,
        flags=re.IGNORECASE,
    )
    translated = translated.replace("?", "%s")
    return translated


class ConnectionAdapter:
    def __init__(self, raw, *, postgres: bool):
        self._raw = raw
        self._postgres = postgres

    def execute(self, sql: str, params: Iterable[Any] = ()) -> CursorAdapter:
        if not self._postgres:
            cursor = self._raw.execute(sql, tuple(params))
            return CursorAdapter(cursor, postgres=False, lastrowid=int(cursor.lastrowid or 0))

        translated = _translate_postgres_sql(sql)
        insert_match = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", translated, flags=re.IGNORECASE)
        table = insert_match.group(1).lower() if insert_match else None
        needs_id = bool(table in _ID_TABLES and " RETURNING " not in translated.upper())
        if needs_id:
            translated = translated.rstrip().rstrip(";") + " RETURNING id"

        cursor = self._raw.cursor()
        cursor.execute(translated, tuple(params))
        lastrowid = 0
        if needs_id:
            row = cursor.fetchone()
            if row:
                lastrowid = int(row["id"])
        return CursorAdapter(cursor, postgres=True, lastrowid=lastrowid)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> CursorAdapter:
        row_list = [tuple(row) for row in rows]
        if not self._postgres:
            cursor = self._raw.executemany(sql, row_list)
            return CursorAdapter(cursor, postgres=False, lastrowid=int(cursor.lastrowid or 0))
        cursor = self._raw.cursor()
        cursor.executemany(_translate_postgres_sql(sql), row_list)
        return CursorAdapter(cursor, postgres=True)

    def executescript(self, script: str) -> None:
        if not self._postgres:
            self._raw.executescript(script)
            return
        for statement in (part.strip() for part in script.split(";")):
            if not statement:
                continue
            statement = statement.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
            self.execute(statement)


if psycopg is not None:
    IntegrityErrors = (sqlite3.IntegrityError, psycopg.IntegrityError)
else:
    IntegrityErrors = (sqlite3.IntegrityError,)


def database_backend() -> str:
    return "postgresql" if POSTGRES_ENABLED else "sqlite"


@contextmanager
def connection():
    if POSTGRES_ENABLED:
        if psycopg is None:
            raise RuntimeError("DATABASE_URL is configured but psycopg is not installed")
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        conn = ConnectionAdapter(raw, postgres=True)
    else:
        raw = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        conn = ConnectionAdapter(raw, postgres=False)

    try:
        yield conn
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def _table_columns(conn: ConnectionAdapter, table: str) -> set[str]:
    if POSTGRES_ENABLED:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        ).fetchall()
        return {str(row["column_name"]) for row in rows}
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_video_columns(conn: ConnectionAdapter) -> None:
    columns = _table_columns(conn, "videos")
    additions = {
        "analysis_mode": "TEXT NOT NULL DEFAULT 'quick'",
        "progress_percent": "INTEGER NOT NULL DEFAULT 0",
        "progress_stage": "TEXT NOT NULL DEFAULT 'Uploaded'",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE videos ADD COLUMN {name} {definition}")


def _ensure_player_columns(conn: ConnectionAdapter) -> None:
    """Extend legacy video-analysis players into the academy master player record."""
    columns = _table_columns(conn, "players")
    additions = {
        "academy_id": "BIGINT REFERENCES academies(id) ON DELETE SET NULL",
        "first_name": "TEXT",
        "last_name": "TEXT",
        "preferred_name": "TEXT",
        "date_of_birth": "TEXT",
        "gender": "TEXT",
        "batting_style": "TEXT",
        "bowling_style": "TEXT",
        "skill_level": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "address_line1": "TEXT",
        "address_line2": "TEXT",
        "city": "TEXT",
        "state": "TEXT",
        "postal_code": "TEXT",
        "country": "TEXT",
        "emergency_contact_name": "TEXT",
        "emergency_contact_phone": "TEXT",
        "joined_on": "TEXT",
        "status": "TEXT NOT NULL DEFAULT 'active'",
        "updated_at": "TIMESTAMP",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE players ADD COLUMN {name} {definition}")


def _sqlite_schema() -> str:
    return """
        CREATE TABLE IF NOT EXISTS academies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            website TEXT,
            address_line1 TEXT,
            address_line2 TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            country TEXT NOT NULL DEFAULT 'United States',
            timezone TEXT NOT NULL DEFAULT 'America/New_York',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            handedness TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS guardians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id INTEGER,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            relationship TEXT,
            email TEXT,
            phone TEXT,
            address_line1 TEXT,
            address_line2 TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            country TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS player_guardians (
            player_id INTEGER NOT NULL,
            guardian_id INTEGER NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0,
            billing_contact INTEGER NOT NULL DEFAULT 0,
            pickup_authorized INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(player_id, guardian_id),
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(guardian_id) REFERENCES guardians(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_player_guardians_player ON player_guardians(player_id);
        CREATE INDEX IF NOT EXISTS idx_guardians_academy ON guardians(academy_id);

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
        CREATE INDEX IF NOT EXISTS idx_frames_video_time ON frames(video_id, timestamp);

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
        CREATE INDEX IF NOT EXISTS idx_events_video_time ON events(video_id, timestamp);
    """


def _postgres_schema() -> str:
    return """
        CREATE TABLE IF NOT EXISTS academies (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            website TEXT,
            address_line1 TEXT,
            address_line2 TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            country TEXT NOT NULL DEFAULT 'United States',
            timezone TEXT NOT NULL DEFAULT 'America/New_York',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS players (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            handedness TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_players_name_nocase ON players (LOWER(name));

        CREATE TABLE IF NOT EXISTS guardians (
            id BIGSERIAL PRIMARY KEY,
            academy_id BIGINT REFERENCES academies(id) ON DELETE SET NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            relationship TEXT,
            email TEXT,
            phone TEXT,
            address_line1 TEXT,
            address_line2 TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            country TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS player_guardians (
            player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            guardian_id BIGINT NOT NULL REFERENCES guardians(id) ON DELETE CASCADE,
            is_primary INTEGER NOT NULL DEFAULT 0,
            billing_contact INTEGER NOT NULL DEFAULT 0,
            pickup_authorized INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(player_id, guardian_id)
        );
        CREATE INDEX IF NOT EXISTS idx_player_guardians_player ON player_guardians(player_id);
        CREATE INDEX IF NOT EXISTS idx_guardians_academy ON guardians(academy_id);

        CREATE TABLE IF NOT EXISTS videos (
            id BIGSERIAL PRIMARY KEY,
            player_id BIGINT REFERENCES players(id) ON DELETE SET NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            file_size BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'uploaded',
            analysis_mode TEXT NOT NULL DEFAULT 'quick',
            progress_percent INTEGER NOT NULL DEFAULT 0,
            progress_stage TEXT NOT NULL DEFAULT 'Uploaded',
            error TEXT,
            fps DOUBLE PRECISION,
            duration DOUBLE PRECISION,
            width INTEGER,
            height INTEGER,
            frame_count BIGINT,
            thumbnail_path TEXT,
            motion_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            analyzed_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS frames (
            id BIGSERIAL PRIMARY KEY,
            video_id BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            timestamp DOUBLE PRECISION NOT NULL,
            frame_number BIGINT NOT NULL,
            image_path TEXT NOT NULL,
            motion_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            is_candidate INTEGER NOT NULL DEFAULT 0,
            kind TEXT NOT NULL DEFAULT 'timeline',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_frames_video_time ON frames(video_id, timestamp);

        CREATE TABLE IF NOT EXISTS events (
            id BIGSERIAL PRIMARY KEY,
            video_id BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            timestamp DOUBLE PRECISION NOT NULL,
            event_type TEXT NOT NULL,
            label TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_events_video_time ON events(video_id, timestamp);
    """


def init_db() -> None:
    with connection() as conn:
        conn.executescript(_postgres_schema() if POSTGRES_ENABLED else _sqlite_schema())
        _ensure_player_columns(conn)
        _ensure_video_columns(conn)


def row_dict(row) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def fetch_one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    with connection() as conn:
        return row_dict(conn.execute(sql, tuple(params)).fetchone())


def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connection() as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connection() as conn:
        cur = conn.execute(sql, tuple(params))
        return int(cur.lastrowid or 0)


def execute_many(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    with connection() as conn:
        conn.executemany(sql, [tuple(row) for row in rows])


def json_or_default(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
