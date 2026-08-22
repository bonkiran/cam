from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/cam", tags=["cam-coaches"])


class CoachPayload(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    preferred_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=80)
    specialties: list[str] = Field(default_factory=list, max_length=20)
    availability: str | None = Field(default=None, max_length=1500)
    certifications: str | None = Field(default=None, max_length=1500)
    joined_on: str | None = Field(default=None, max_length=20)
    status: Literal["active", "inactive"] = "active"
    notes: str | None = Field(default=None, max_length=2000)


class CoachPlayerAssignmentPayload(BaseModel):
    coach_id: int = Field(gt=0)
    player_id: int = Field(gt=0)
    assignment_role: Literal["primary", "support"] = "primary"
    start_date: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS coaches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            preferred_name TEXT,
            email TEXT,
            phone TEXT,
            specialties_json TEXT NOT NULL DEFAULT '[]',
            availability TEXT,
            certifications TEXT,
            joined_on TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_coaches_academy ON coaches(academy_id);
        CREATE INDEX IF NOT EXISTS idx_coaches_status ON coaches(status);
        CREATE INDEX IF NOT EXISTS idx_coaches_name ON coaches(last_name, first_name);

        CREATE TABLE IF NOT EXISTS coach_player_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            coach_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            assignment_role TEXT NOT NULL DEFAULT 'primary',
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE RESTRICT,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_coach_player_coach ON coach_player_assignments(coach_id);
        CREATE INDEX IF NOT EXISTS idx_coach_player_player ON coach_player_assignments(player_id);
        CREATE INDEX IF NOT EXISTS idx_coach_player_status ON coach_player_assignments(status);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _decode_specialties(row: dict) -> dict:
    out = dict(row)
    raw = out.pop("specialties_json", None)
    try:
        out["specialties"] = json.loads(raw or "[]")
    except Exception:
        out["specialties"] = []
    return out


def _coach(coach_id: int) -> dict:
    row = fetch_one(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM coach_player_assignments a WHERE a.coach_id=c.id AND a.status='active') AS assigned_player_count
        FROM coaches c WHERE c.id=?
        """,
        (coach_id,),
    )
    if not row:
        raise HTTPException(404, "Coach not found")
    return _decode_specialties(row)


def _assignment(assignment_id: int) -> dict:
    row = fetch_one(
        """
        SELECT a.*, c.first_name AS coach_first_name, c.last_name AS coach_last_name,
               p.name AS player_name
        FROM coach_player_assignments a
        JOIN coaches c ON c.id=a.coach_id
        JOIN players p ON p.id=a.player_id
        WHERE a.id=?
        """,
        (assignment_id,),
    )
    if not row:
        raise HTTPException(404, "Coach-player assignment not found")
    row["coach_name"] = f"{row.get('coach_first_name','')} {row.get('coach_last_name','')}".strip()
    return row


_ensure_tables()


@router.get("/coaches")
def coaches():
    rows = fetch_all(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM coach_player_assignments a WHERE a.coach_id=c.id AND a.status='active') AS assigned_player_count
        FROM coaches c
        ORDER BY CASE WHEN c.status='active' THEN 0 ELSE 1 END, c.last_name COLLATE NOCASE, c.first_name COLLATE NOCASE
        """
    )
    return [_decode_specialties(row) for row in rows]


@router.get("/coaches/{coach_id}")
def coach(coach_id: int):
    return _coach(coach_id)


@router.post("/coaches", status_code=201)
def create_coach(payload: CoachPayload):
    first = _clean(payload.first_name) or ""
    last = _clean(payload.last_name) or ""
    with connection() as conn:
        academy_id = _academy_id(conn)
        row = conn.execute(
            """
            INSERT INTO coaches(academy_id,first_name,last_name,preferred_name,email,phone,specialties_json,
                                availability,certifications,joined_on,status,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (
                academy_id, first, last, _clean(payload.preferred_name), _clean(payload.email), _clean(payload.phone),
                json.dumps([str(x).strip() for x in payload.specialties if str(x).strip()]),
                _clean(payload.availability), _clean(payload.certifications), _clean(payload.joined_on),
                payload.status, _clean(payload.notes),
            ),
        ).fetchone()
        coach_id = int(row["id"])
    return _coach(coach_id)


@router.put("/coaches/{coach_id}")
def update_coach(coach_id: int, payload: CoachPayload):
    first = _clean(payload.first_name) or ""
    last = _clean(payload.last_name) or ""
    with connection() as conn:
        if not conn.execute("SELECT id FROM coaches WHERE id=?", (coach_id,)).fetchone():
            raise HTTPException(404, "Coach not found")
        conn.execute(
            """
            UPDATE coaches SET first_name=?,last_name=?,preferred_name=?,email=?,phone=?,specialties_json=?,
                               availability=?,certifications=?,joined_on=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                first, last, _clean(payload.preferred_name), _clean(payload.email), _clean(payload.phone),
                json.dumps([str(x).strip() for x in payload.specialties if str(x).strip()]),
                _clean(payload.availability), _clean(payload.certifications), _clean(payload.joined_on),
                payload.status, _clean(payload.notes), coach_id,
            ),
        )
    return _coach(coach_id)


@router.get("/coach-player-assignments")
def coach_player_assignments(coach_id: int | None = None, player_id: int | None = None):
    sql = """
        SELECT a.*, c.first_name AS coach_first_name, c.last_name AS coach_last_name, p.name AS player_name
        FROM coach_player_assignments a
        JOIN coaches c ON c.id=a.coach_id
        JOIN players p ON p.id=a.player_id
        WHERE 1=1
    """
    params: list[object] = []
    if coach_id is not None:
        sql += " AND a.coach_id=?"
        params.append(coach_id)
    if player_id is not None:
        sql += " AND a.player_id=?"
        params.append(player_id)
    sql += " ORDER BY a.id DESC"
    rows = fetch_all(sql, params)
    for row in rows:
        row["coach_name"] = f"{row.get('coach_first_name','')} {row.get('coach_last_name','')}".strip()
    return rows


@router.post("/coach-player-assignments", status_code=201)
def create_coach_player_assignment(payload: CoachPlayerAssignmentPayload):
    with connection() as conn:
        coach = conn.execute("SELECT id,status FROM coaches WHERE id=?", (payload.coach_id,)).fetchone()
        if not coach:
            raise HTTPException(404, "Coach not found")
        if str(coach["status"] or "active") != "active":
            raise HTTPException(409, "Only active coaches can receive new player assignments")
        player = conn.execute("SELECT id,status FROM players WHERE id=?", (payload.player_id,)).fetchone()
        if not player:
            raise HTTPException(404, "Player not found")
        if str(player["status"] or "active") != "active":
            raise HTTPException(409, "Only active players can receive a coach assignment")
        existing = conn.execute(
            "SELECT id FROM coach_player_assignments WHERE coach_id=? AND player_id=? AND status='active'",
            (payload.coach_id, payload.player_id),
        ).fetchone()
        if existing:
            raise HTTPException(409, "This coach is already actively assigned to this player")
        academy_id = _academy_id(conn)
        row = conn.execute(
            """
            INSERT INTO coach_player_assignments(academy_id,coach_id,player_id,assignment_role,start_date,status,notes)
            VALUES(?,?,?,?,?,'active',?) RETURNING id
            """,
            (
                academy_id, payload.coach_id, payload.player_id, payload.assignment_role,
                _clean(payload.start_date), _clean(payload.notes),
            ),
        ).fetchone()
        assignment_id = int(row["id"])
    return _assignment(assignment_id)


@router.post("/coach-player-assignments/{assignment_id}/end")
def end_coach_player_assignment(assignment_id: int, end_date: str | None = None):
    with connection() as conn:
        row = conn.execute("SELECT id,status FROM coach_player_assignments WHERE id=?", (assignment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Coach-player assignment not found")
        if str(row["status"]) != "active":
            raise HTTPException(409, "Coach-player assignment is already inactive")
        conn.execute(
            "UPDATE coach_player_assignments SET status='inactive',end_date=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (_clean(end_date), assignment_id),
        )
    return _assignment(assignment_id)
