from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import _table_columns, connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/cam", tags=["cam-tournaments"])


class TournamentPayload(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    tournament_type: Literal["internal", "external"] = "external"
    organizer: str | None = Field(default=None, max_length=180)
    start_date: str = Field(min_length=8, max_length=20)
    end_date: str = Field(min_length=8, max_length=20)
    location: str | None = Field(default=None, max_length=240)
    status: Literal["planned", "open", "completed", "cancelled"] = "planned"
    notes: str | None = Field(default=None, max_length=1500)


class TournamentEntryPayload(BaseModel):
    team_id: int = Field(gt=0)
    registered_on: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


class TournamentEntryUpdatePayload(BaseModel):
    status: Literal["registered", "withdrawn"]
    notes: str | None = Field(default=None, max_length=1000)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except Exception as exc:
        raise HTTPException(422, f"{label} must be YYYY-MM-DD") from exc


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            name TEXT NOT NULL,
            tournament_type TEXT NOT NULL DEFAULT 'external',
            organizer TEXT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            location TEXT,
            status TEXT NOT NULL DEFAULT 'planned',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_academy_tournaments_dates ON academy_tournaments(start_date,end_date);
        CREATE INDEX IF NOT EXISTS idx_academy_tournaments_status ON academy_tournaments(status);

        CREATE TABLE IF NOT EXISTS academy_tournament_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id BIGINT NOT NULL,
            team_id BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'registered',
            registered_on TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(tournament_id) REFERENCES academy_tournaments(id) ON DELETE CASCADE,
            FOREIGN KEY(team_id) REFERENCES academy_teams(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_academy_tournament_entries_tournament ON academy_tournament_entries(tournament_id);
        CREATE INDEX IF NOT EXISTS idx_academy_tournament_entries_team ON academy_tournament_entries(team_id);
    """
    with connection() as conn:
        conn.executescript(schema)
        if "tournament_type" not in _table_columns(conn, "academy_tournaments"):
            conn.execute("ALTER TABLE academy_tournaments ADD COLUMN tournament_type TEXT NOT NULL DEFAULT 'external'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_academy_tournaments_type ON academy_tournaments(tournament_type)")


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _tournament(tournament_id: int) -> dict:
    row = fetch_one(
        """
        SELECT t.*,
               (SELECT COUNT(*) FROM academy_tournament_entries e WHERE e.tournament_id=t.id AND e.status='registered') AS registered_team_count
        FROM academy_tournaments t WHERE t.id=?
        """,
        (tournament_id,),
    )
    if not row:
        raise HTTPException(404, "Tournament not found")
    return row


def _team(team_id: int) -> dict:
    row = fetch_one("SELECT id,name,status FROM academy_teams WHERE id=?", (team_id,))
    if not row:
        raise HTTPException(404, "Team not found")
    return row


def _validate_dates(start_date: str, end_date: str) -> None:
    start = _date(start_date, "Start date")
    end = _date(end_date, "End date")
    if end < start:
        raise HTTPException(422, "End date must be on or after start date")


_ensure_tables()


@router.get("/tournaments")
def tournaments():
    rows = fetch_all("SELECT id FROM academy_tournaments ORDER BY start_date DESC,id DESC")
    return [_tournament(int(row["id"])) for row in rows]


@router.get("/tournaments/{tournament_id}")
def tournament(tournament_id: int):
    return _tournament(tournament_id)


@router.post("/tournaments", status_code=201)
def create_tournament(payload: TournamentPayload):
    _validate_dates(payload.start_date, payload.end_date)
    name = _clean(payload.name) or ""
    with connection() as conn:
        duplicate = conn.execute(
            "SELECT id FROM academy_tournaments WHERE name=? COLLATE NOCASE AND start_date=?",
            (name, payload.start_date),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "A tournament with this name and start date already exists")
        row = conn.execute(
            """
            INSERT INTO academy_tournaments(academy_id,name,tournament_type,organizer,start_date,end_date,location,status,notes)
            VALUES(?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (_academy_id(conn), name, payload.tournament_type, _clean(payload.organizer), payload.start_date, payload.end_date,
             _clean(payload.location), payload.status, _clean(payload.notes)),
        ).fetchone()
        tournament_id = int(row["id"])
    return _tournament(tournament_id)


@router.put("/tournaments/{tournament_id}")
def update_tournament(tournament_id: int, payload: TournamentPayload):
    _tournament(tournament_id)
    _validate_dates(payload.start_date, payload.end_date)
    name = _clean(payload.name) or ""
    with connection() as conn:
        duplicate = conn.execute(
            "SELECT id FROM academy_tournaments WHERE name=? COLLATE NOCASE AND start_date=? AND id<>?",
            (name, payload.start_date, tournament_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "A tournament with this name and start date already exists")
        conn.execute(
            """
            UPDATE academy_tournaments SET name=?,tournament_type=?,organizer=?,start_date=?,end_date=?,location=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (name, payload.tournament_type, _clean(payload.organizer), payload.start_date, payload.end_date, _clean(payload.location),
             payload.status, _clean(payload.notes), tournament_id),
        )
    return _tournament(tournament_id)


@router.get("/tournaments/{tournament_id}/entries")
def tournament_entries(tournament_id: int):
    _tournament(tournament_id)
    return fetch_all(
        """
        SELECT e.*,t.name AS team_name,t.age_group AS team_age_group
        FROM academy_tournament_entries e JOIN academy_teams t ON t.id=e.team_id
        WHERE e.tournament_id=? ORDER BY CASE WHEN e.status='registered' THEN 0 ELSE 1 END,t.name COLLATE NOCASE
        """,
        (tournament_id,),
    )


@router.post("/tournaments/{tournament_id}/entries", status_code=201)
def register_team(tournament_id: int, payload: TournamentEntryPayload):
    tournament_row = _tournament(tournament_id)
    if tournament_row["status"] in ("completed", "cancelled"):
        raise HTTPException(409, "Teams cannot be registered to a completed or cancelled tournament")
    team_row = _team(payload.team_id)
    if team_row["status"] != "active":
        raise HTTPException(409, "Only an active team can be registered")
    with connection() as conn:
        duplicate = conn.execute(
            "SELECT id FROM academy_tournament_entries WHERE tournament_id=? AND team_id=? AND status='registered'",
            (tournament_id, payload.team_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "Team is already registered for this tournament")
        row = conn.execute(
            """
            INSERT INTO academy_tournament_entries(tournament_id,team_id,status,registered_on,notes)
            VALUES(?,?,'registered',?,?) RETURNING id
            """,
            (tournament_id, payload.team_id, _clean(payload.registered_on), _clean(payload.notes)),
        ).fetchone()
        entry_id = int(row["id"])
    return fetch_one(
        """
        SELECT e.*,t.name AS team_name,t.age_group AS team_age_group
        FROM academy_tournament_entries e JOIN academy_teams t ON t.id=e.team_id WHERE e.id=?
        """,
        (entry_id,),
    )


@router.put("/tournament-entries/{entry_id}")
def update_tournament_entry(entry_id: int, payload: TournamentEntryUpdatePayload):
    current = fetch_one("SELECT id FROM academy_tournament_entries WHERE id=?", (entry_id,))
    if not current:
        raise HTTPException(404, "Tournament entry not found")
    with connection() as conn:
        conn.execute(
            "UPDATE academy_tournament_entries SET status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (payload.status, _clean(payload.notes), entry_id),
        )
    return fetch_one(
        """
        SELECT e.*,t.name AS team_name,t.age_group AS team_age_group
        FROM academy_tournament_entries e JOIN academy_teams t ON t.id=e.team_id WHERE e.id=?
        """,
        (entry_id,),
    )
