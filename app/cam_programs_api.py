from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/cam", tags=["cam-programs"])


class ProgramPayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=1200)
    program_type: Literal["group", "private", "camp", "clinic", "other"] = "group"
    age_group: str | None = Field(default=None, max_length=80)
    skill_level: str | None = Field(default=None, max_length=80)
    start_date: str | None = Field(default=None, max_length=20)
    end_date: str | None = Field(default=None, max_length=20)
    status: Literal["active", "inactive"] = "active"


class EnrollmentPayload(BaseModel):
    player_id: int = Field(gt=0)
    program_id: int = Field(gt=0)
    enrollment_type: Literal["regular", "trial"] = "regular"
    start_date: str | None = Field(default=None, max_length=20)
    end_date: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1500)


class EnrollmentUpdatePayload(BaseModel):
    start_date: str | None = Field(default=None, max_length=20)
    end_date: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1500)


class FreezePayload(BaseModel):
    effective_date: str | None = Field(default=None, max_length=20)


class CancelPayload(BaseModel):
    effective_date: str | None = Field(default=None, max_length=20)
    reason: str | None = Field(default=None, max_length=500)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            name TEXT NOT NULL,
            code TEXT,
            description TEXT,
            program_type TEXT NOT NULL DEFAULT 'group',
            age_group TEXT,
            skill_level TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_programs_academy ON programs(academy_id);
        CREATE INDEX IF NOT EXISTS idx_programs_status ON programs(status);

        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            player_id BIGINT NOT NULL,
            program_id BIGINT NOT NULL,
            enrollment_type TEXT NOT NULL DEFAULT 'regular',
            status TEXT NOT NULL DEFAULT 'active',
            start_date TEXT,
            end_date TEXT,
            frozen_on TEXT,
            cancelled_on TEXT,
            cancellation_reason TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_enrollments_player ON enrollments(player_id);
        CREATE INDEX IF NOT EXISTS idx_enrollments_program ON enrollments(program_id);
        CREATE INDEX IF NOT EXISTS idx_enrollments_status ON enrollments(status);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _program(program_id: int) -> dict:
    row = fetch_one(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM enrollments e WHERE e.program_id=p.id AND e.status IN ('active','frozen')) AS current_enrollment_count,
               (SELECT COUNT(*) FROM enrollments e WHERE e.program_id=p.id) AS lifetime_enrollment_count
        FROM programs p
        WHERE p.id=?
        """,
        (program_id,),
    )
    if not row:
        raise HTTPException(404, "Program not found")
    return row


def _enrollment(enrollment_id: int) -> dict:
    row = fetch_one(
        """
        SELECT e.*, p.name AS player_name, p.status AS player_status,
               pr.name AS program_name, pr.status AS program_status
        FROM enrollments e
        JOIN players p ON p.id=e.player_id
        JOIN programs pr ON pr.id=e.program_id
        WHERE e.id=?
        """,
        (enrollment_id,),
    )
    if not row:
        raise HTTPException(404, "Enrollment not found")
    return row


def _check_program_name(conn, name: str, exclude_id: int | None = None) -> None:
    sql = "SELECT id FROM programs WHERE name=? COLLATE NOCASE"
    params: list[object] = [name]
    if exclude_id is not None:
        sql += " AND id<>?"
        params.append(exclude_id)
    if conn.execute(sql, params).fetchone():
        raise HTTPException(409, "A program with this name already exists")


_ensure_tables()


@router.get("/programs")
def programs():
    return fetch_all(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM enrollments e WHERE e.program_id=p.id AND e.status IN ('active','frozen')) AS current_enrollment_count,
               (SELECT COUNT(*) FROM enrollments e WHERE e.program_id=p.id) AS lifetime_enrollment_count
        FROM programs p
        ORDER BY CASE WHEN p.status='active' THEN 0 ELSE 1 END, p.name COLLATE NOCASE
        """
    )


@router.get("/programs/{program_id}")
def program(program_id: int):
    return _program(program_id)


@router.post("/programs", status_code=201)
def create_program(payload: ProgramPayload):
    name = _clean(payload.name) or ""
    with connection() as conn:
        _check_program_name(conn, name)
        academy_id = _academy_id(conn)
        row = conn.execute(
            """
            INSERT INTO programs(academy_id,name,code,description,program_type,age_group,skill_level,start_date,end_date,status)
            VALUES(?,?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (
                academy_id, name, _clean(payload.code), _clean(payload.description), payload.program_type,
                _clean(payload.age_group), _clean(payload.skill_level), _clean(payload.start_date),
                _clean(payload.end_date), payload.status,
            ),
        ).fetchone()
        program_id = int(row["id"])
    return _program(program_id)


@router.put("/programs/{program_id}")
def update_program(program_id: int, payload: ProgramPayload):
    name = _clean(payload.name) or ""
    with connection() as conn:
        if not conn.execute("SELECT id FROM programs WHERE id=?", (program_id,)).fetchone():
            raise HTTPException(404, "Program not found")
        _check_program_name(conn, name, exclude_id=program_id)
        conn.execute(
            """
            UPDATE programs SET name=?,code=?,description=?,program_type=?,age_group=?,skill_level=?,
                start_date=?,end_date=?,status=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                name, _clean(payload.code), _clean(payload.description), payload.program_type,
                _clean(payload.age_group), _clean(payload.skill_level), _clean(payload.start_date),
                _clean(payload.end_date), payload.status, program_id,
            ),
        )
    return _program(program_id)


@router.get("/enrollments")
def enrollments(player_id: int | None = None, program_id: int | None = None):
    sql = """
        SELECT e.*, p.name AS player_name, p.status AS player_status,
               pr.name AS program_name, pr.status AS program_status
        FROM enrollments e
        JOIN players p ON p.id=e.player_id
        JOIN programs pr ON pr.id=e.program_id
        WHERE 1=1
    """
    params: list[object] = []
    if player_id is not None:
        sql += " AND e.player_id=?"
        params.append(player_id)
    if program_id is not None:
        sql += " AND e.program_id=?"
        params.append(program_id)
    sql += " ORDER BY e.id DESC"
    return fetch_all(sql, params)


@router.get("/enrollments/{enrollment_id}")
def enrollment(enrollment_id: int):
    return _enrollment(enrollment_id)


@router.post("/enrollments", status_code=201)
def create_enrollment(payload: EnrollmentPayload):
    with connection() as conn:
        player = conn.execute("SELECT id,name,status FROM players WHERE id=?", (payload.player_id,)).fetchone()
        if not player:
            raise HTTPException(404, "Player not found")
        if str(player["status"] or "active") != "active":
            raise HTTPException(409, "Only active players can be enrolled")

        program = conn.execute("SELECT id,name,status FROM programs WHERE id=?", (payload.program_id,)).fetchone()
        if not program:
            raise HTTPException(404, "Program not found")
        if str(program["status"] or "active") != "active":
            raise HTTPException(409, "Only active programs can accept enrollment")

        current = conn.execute(
            "SELECT id,status FROM enrollments WHERE player_id=? AND program_id=? AND status IN ('active','frozen')",
            (payload.player_id, payload.program_id),
        ).fetchone()
        if current:
            raise HTTPException(409, "Player already has a current enrollment in this program")

        academy_id = _academy_id(conn)
        row = conn.execute(
            """
            INSERT INTO enrollments(academy_id,player_id,program_id,enrollment_type,status,start_date,end_date,notes)
            VALUES(?,?,?,?, 'active', ?,?,?) RETURNING id
            """,
            (
                academy_id, payload.player_id, payload.program_id, payload.enrollment_type,
                _clean(payload.start_date), _clean(payload.end_date), _clean(payload.notes),
            ),
        ).fetchone()
        enrollment_id = int(row["id"])
    return _enrollment(enrollment_id)


@router.put("/enrollments/{enrollment_id}")
def update_enrollment(enrollment_id: int, payload: EnrollmentUpdatePayload):
    with connection() as conn:
        if not conn.execute("SELECT id FROM enrollments WHERE id=?", (enrollment_id,)).fetchone():
            raise HTTPException(404, "Enrollment not found")
        conn.execute(
            """
            UPDATE enrollments SET start_date=?,end_date=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?
            """,
            (_clean(payload.start_date), _clean(payload.end_date), _clean(payload.notes), enrollment_id),
        )
    return _enrollment(enrollment_id)


@router.post("/enrollments/{enrollment_id}/freeze")
def freeze_enrollment(enrollment_id: int, payload: FreezePayload):
    with connection() as conn:
        row = conn.execute("SELECT id,status FROM enrollments WHERE id=?", (enrollment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Enrollment not found")
        if str(row["status"]) != "active":
            raise HTTPException(409, "Only an active enrollment can be frozen")
        conn.execute(
            "UPDATE enrollments SET status='frozen',frozen_on=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (_clean(payload.effective_date), enrollment_id),
        )
    return _enrollment(enrollment_id)


@router.post("/enrollments/{enrollment_id}/cancel")
def cancel_enrollment(enrollment_id: int, payload: CancelPayload):
    with connection() as conn:
        row = conn.execute("SELECT id,status FROM enrollments WHERE id=?", (enrollment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Enrollment not found")
        if str(row["status"]) == "cancelled":
            raise HTTPException(409, "Enrollment is already cancelled")
        conn.execute(
            """
            UPDATE enrollments SET status='cancelled',cancelled_on=?,cancellation_reason=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (_clean(payload.effective_date), _clean(payload.reason), enrollment_id),
        )
    return _enrollment(enrollment_id)
