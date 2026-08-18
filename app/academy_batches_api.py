from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-batches-sessions"])


class BatchPayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=40)
    program_id: int | None = Field(default=None, gt=0)
    capacity: int = Field(default=12, ge=1, le=500)
    location: str | None = Field(default=None, max_length=240)
    resource: str | None = Field(default=None, max_length=120)
    start_date: str | None = Field(default=None, max_length=20)
    end_date: str | None = Field(default=None, max_length=20)
    status: Literal["active", "inactive"] = "active"
    notes: str | None = Field(default=None, max_length=1500)


class BatchPlayerPayload(BaseModel):
    player_id: int = Field(gt=0)
    waitlist_if_full: bool = False
    joined_on: str | None = Field(default=None, max_length=20)


class BatchCoachPayload(BaseModel):
    coach_id: int = Field(gt=0)
    assignment_role: Literal["primary", "support"] = "primary"
    start_date: str | None = Field(default=None, max_length=20)


class RecurringSchedulePayload(BaseModel):
    start_date: str = Field(max_length=20)
    end_date: str = Field(max_length=20)
    weekdays: list[int] = Field(min_length=1, max_length=7)
    start_time: str = Field(max_length=10)
    duration_minutes: int = Field(default=60, ge=15, le=480)


class PrivateSessionPayload(BaseModel):
    player_id: int = Field(gt=0)
    coach_id: int = Field(gt=0)
    session_date: str = Field(max_length=20)
    start_time: str = Field(max_length=10)
    duration_minutes: int = Field(default=60, ge=15, le=480)
    location: str | None = Field(default=None, max_length=240)
    resource: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1500)


class SessionUpdatePayload(BaseModel):
    session_date: str = Field(max_length=20)
    start_time: str = Field(max_length=10)
    duration_minutes: int = Field(ge=15, le=480)
    coach_id: int | None = Field(default=None, gt=0)
    location: str | None = Field(default=None, max_length=240)
    resource: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1500)


class SessionCancelPayload(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class MakeupSessionPayload(BaseModel):
    session_date: str = Field(max_length=20)
    start_time: str = Field(max_length=10)
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    coach_id: int | None = Field(default=None, gt=0)
    location: str | None = Field(default=None, max_length=240)
    resource: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1500)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            program_id BIGINT,
            name TEXT NOT NULL,
            code TEXT,
            capacity INTEGER NOT NULL DEFAULT 12,
            location TEXT,
            resource TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_batches_program ON batches(program_id);
        CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);

        CREATE TABLE IF NOT EXISTS batch_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            joined_on TEXT,
            ended_on TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(batch_id) REFERENCES batches(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_batch_players_batch ON batch_players(batch_id);
        CREATE INDEX IF NOT EXISTS idx_batch_players_player ON batch_players(player_id);
        CREATE INDEX IF NOT EXISTS idx_batch_players_status ON batch_players(status);

        CREATE TABLE IF NOT EXISTS batch_coach_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id BIGINT NOT NULL,
            coach_id BIGINT NOT NULL,
            assignment_role TEXT NOT NULL DEFAULT 'primary',
            status TEXT NOT NULL DEFAULT 'active',
            start_date TEXT,
            end_date TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(batch_id) REFERENCES batches(id) ON DELETE CASCADE,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_batch_coaches_batch ON batch_coach_assignments(batch_id);
        CREATE INDEX IF NOT EXISTS idx_batch_coaches_coach ON batch_coach_assignments(coach_id);

        CREATE TABLE IF NOT EXISTS academy_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            batch_id BIGINT,
            original_session_id BIGINT,
            coach_id BIGINT,
            session_kind TEXT NOT NULL DEFAULT 'batch',
            session_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL DEFAULT 60,
            timezone TEXT NOT NULL,
            location TEXT,
            resource TEXT,
            status TEXT NOT NULL DEFAULT 'scheduled',
            cancellation_reason TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(batch_id) REFERENCES batches(id) ON DELETE SET NULL,
            FOREIGN KEY(original_session_id) REFERENCES academy_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_batch ON academy_sessions(batch_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_coach ON academy_sessions(coach_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_date ON academy_sessions(session_date);
        CREATE INDEX IF NOT EXISTS idx_sessions_status ON academy_sessions(status);

        CREATE TABLE IF NOT EXISTS session_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            participation_type TEXT NOT NULL DEFAULT 'roster',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES academy_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_session_players_session ON session_players(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_players_player ON session_players(player_id);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy(conn):
    row = conn.execute("SELECT id,timezone FROM academies ORDER BY id LIMIT 1").fetchone()
    return row


def _academy_timezone(conn) -> str:
    row = _academy(conn)
    return str(row["timezone"] or "America/New_York") if row else "America/New_York"


def _time_minutes(value: str) -> int:
    try:
        hh, mm = value.split(":", 1)
        hours = int(hh)
        minutes = int(mm)
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError
        return hours * 60 + minutes
    except Exception as exc:
        raise HTTPException(422, "Time must be HH:MM in 24-hour format") from exc


def _validate_date(value: str, label: str = "Date") -> date:
    try:
        return date.fromisoformat(value)
    except Exception as exc:
        raise HTTPException(422, f"{label} must be YYYY-MM-DD") from exc


def _batch(batch_id: int) -> dict:
    row = fetch_one(
        """
        SELECT b.*, p.name AS program_name,
               (SELECT COUNT(*) FROM batch_players bp WHERE bp.batch_id=b.id AND bp.status='active') AS active_player_count,
               (SELECT COUNT(*) FROM batch_players bp WHERE bp.batch_id=b.id AND bp.status='waitlisted') AS waitlist_count,
               (SELECT c.first_name || ' ' || c.last_name FROM batch_coach_assignments a JOIN coaches c ON c.id=a.coach_id
                 WHERE a.batch_id=b.id AND a.status='active' AND a.assignment_role='primary' ORDER BY a.id DESC LIMIT 1) AS primary_coach_name,
               (SELECT a.coach_id FROM batch_coach_assignments a WHERE a.batch_id=b.id AND a.status='active' AND a.assignment_role='primary' ORDER BY a.id DESC LIMIT 1) AS primary_coach_id
        FROM batches b LEFT JOIN programs p ON p.id=b.program_id WHERE b.id=?
        """,
        (batch_id,),
    )
    if not row:
        raise HTTPException(404, "Batch not found")
    return row


def _session(session_id: int) -> dict:
    row = fetch_one(
        """
        SELECT s.*, b.name AS batch_name, c.first_name AS coach_first_name, c.last_name AS coach_last_name,
               (SELECT COUNT(*) FROM session_players sp WHERE sp.session_id=s.id) AS player_count
        FROM academy_sessions s
        LEFT JOIN batches b ON b.id=s.batch_id
        LEFT JOIN coaches c ON c.id=s.coach_id
        WHERE s.id=?
        """,
        (session_id,),
    )
    if not row:
        raise HTTPException(404, "Session not found")
    row["coach_name"] = f"{row.get('coach_first_name') or ''} {row.get('coach_last_name') or ''}".strip() or None
    return row


def _check_coach_conflict(conn, coach_id: int | None, session_date: str, start_time: str, duration_minutes: int, exclude_session_id: int | None = None) -> None:
    if not coach_id:
        return
    start = _time_minutes(start_time)
    end = start + int(duration_minutes)
    sql = "SELECT id,start_time,duration_minutes FROM academy_sessions WHERE coach_id=? AND session_date=? AND status<>'cancelled'"
    params: list[object] = [coach_id, session_date]
    if exclude_session_id is not None:
        sql += " AND id<>?"
        params.append(exclude_session_id)
    for existing in conn.execute(sql, params).fetchall():
        other_start = _time_minutes(str(existing["start_time"]))
        other_end = other_start + int(existing["duration_minutes"])
        if start < other_end and other_start < end:
            raise HTTPException(409, "Coach has a conflicting session at this time")


def _active_batch_players(conn, batch_id: int) -> list[int]:
    rows = conn.execute("SELECT player_id FROM batch_players WHERE batch_id=? AND status='active' ORDER BY id", (batch_id,)).fetchall()
    return [int(row["player_id"]) for row in rows]


def _active_primary_coach(conn, batch_id: int) -> int | None:
    row = conn.execute(
        "SELECT coach_id FROM batch_coach_assignments WHERE batch_id=? AND status='active' AND assignment_role='primary' ORDER BY id DESC LIMIT 1",
        (batch_id,),
    ).fetchone()
    return int(row["coach_id"]) if row else None


def _insert_session(conn, *, batch_id: int | None, original_session_id: int | None, coach_id: int | None, session_kind: str,
                    session_date: str, start_time: str, duration_minutes: int, timezone: str, location: str | None,
                    resource: str | None, notes: str | None, player_ids: list[int]) -> int:
    _validate_date(session_date, "Session date")
    _time_minutes(start_time)
    _check_coach_conflict(conn, coach_id, session_date, start_time, duration_minutes)
    academy = _academy(conn)
    academy_id = int(academy["id"]) if academy else None
    row = conn.execute(
        """
        INSERT INTO academy_sessions(academy_id,batch_id,original_session_id,coach_id,session_kind,session_date,start_time,
                                     duration_minutes,timezone,location,resource,status,notes)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,'scheduled',?) RETURNING id
        """,
        (academy_id,batch_id,original_session_id,coach_id,session_kind,session_date,start_time,duration_minutes,timezone,
         _clean(location),_clean(resource),_clean(notes)),
    ).fetchone()
    session_id = int(row["id"])
    for player_id in player_ids:
        conn.execute("INSERT INTO session_players(session_id,player_id,participation_type) VALUES(?,?,'roster')", (session_id, player_id))
    return session_id


_ensure_tables()


@router.get("/batches")
def batches():
    rows = fetch_all("SELECT id FROM batches ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, name COLLATE NOCASE")
    return [_batch(int(row["id"])) for row in rows]


@router.get("/batches/{batch_id}")
def batch(batch_id: int):
    return _batch(batch_id)


@router.post("/batches", status_code=201)
def create_batch(payload: BatchPayload):
    name = _clean(payload.name) or ""
    with connection() as conn:
        if conn.execute("SELECT id FROM batches WHERE name=? COLLATE NOCASE", (name,)).fetchone():
            raise HTTPException(409, "A batch with this name already exists")
        if payload.program_id is not None:
            program = conn.execute("SELECT id,status FROM programs WHERE id=?", (payload.program_id,)).fetchone()
            if not program:
                raise HTTPException(404, "Program not found")
        academy = _academy(conn)
        academy_id = int(academy["id"]) if academy else None
        row = conn.execute(
            """
            INSERT INTO batches(academy_id,program_id,name,code,capacity,location,resource,start_date,end_date,status,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (academy_id,payload.program_id,name,_clean(payload.code),payload.capacity,_clean(payload.location),_clean(payload.resource),
             _clean(payload.start_date),_clean(payload.end_date),payload.status,_clean(payload.notes)),
        ).fetchone()
        batch_id = int(row["id"])
    return _batch(batch_id)


@router.put("/batches/{batch_id}")
def update_batch(batch_id: int, payload: BatchPayload):
    name = _clean(payload.name) or ""
    with connection() as conn:
        if not conn.execute("SELECT id FROM batches WHERE id=?", (batch_id,)).fetchone():
            raise HTTPException(404, "Batch not found")
        duplicate = conn.execute("SELECT id FROM batches WHERE name=? COLLATE NOCASE AND id<>?", (name,batch_id)).fetchone()
        if duplicate:
            raise HTTPException(409, "A batch with this name already exists")
        conn.execute(
            """
            UPDATE batches SET program_id=?,name=?,code=?,capacity=?,location=?,resource=?,start_date=?,end_date=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (payload.program_id,name,_clean(payload.code),payload.capacity,_clean(payload.location),_clean(payload.resource),
             _clean(payload.start_date),_clean(payload.end_date),payload.status,_clean(payload.notes),batch_id),
        )
    return _batch(batch_id)


@router.get("/batches/{batch_id}/players")
def batch_players(batch_id: int):
    _batch(batch_id)
    return fetch_all(
        """
        SELECT bp.*, p.name AS player_name, p.status AS player_status
        FROM batch_players bp JOIN players p ON p.id=bp.player_id
        WHERE bp.batch_id=? ORDER BY CASE WHEN bp.status='active' THEN 0 WHEN bp.status='waitlisted' THEN 1 ELSE 2 END, p.name COLLATE NOCASE
        """,
        (batch_id,),
    )


@router.post("/batches/{batch_id}/players", status_code=201)
def add_batch_player(batch_id: int, payload: BatchPlayerPayload):
    batch_row = _batch(batch_id)
    with connection() as conn:
        player = conn.execute("SELECT id,status FROM players WHERE id=?", (payload.player_id,)).fetchone()
        if not player:
            raise HTTPException(404, "Player not found")
        if str(player["status"] or "active") != "active":
            raise HTTPException(409, "Only active players can be added to a batch")
        current = conn.execute("SELECT id,status FROM batch_players WHERE batch_id=? AND player_id=? AND status IN ('active','waitlisted')", (batch_id,payload.player_id)).fetchone()
        if current:
            raise HTTPException(409, "Player already has a current batch membership")
        active_count = int(batch_row["active_player_count"] or 0)
        if active_count >= int(batch_row["capacity"]):
            if not payload.waitlist_if_full:
                raise HTTPException(409, "Batch is at capacity")
            membership_status = "waitlisted"
        else:
            membership_status = "active"
        row = conn.execute(
            "INSERT INTO batch_players(batch_id,player_id,status,joined_on) VALUES(?,?,?,?) RETURNING id",
            (batch_id,payload.player_id,membership_status,_clean(payload.joined_on)),
        ).fetchone()
        membership_id = int(row["id"])
    result = fetch_one("SELECT bp.*,p.name AS player_name FROM batch_players bp JOIN players p ON p.id=bp.player_id WHERE bp.id=?", (membership_id,))
    return result


@router.get("/batch-coach-assignments")
def batch_coach_assignments(batch_id: int | None = None, coach_id: int | None = None):
    sql = """
        SELECT a.*,b.name AS batch_name,c.first_name AS coach_first_name,c.last_name AS coach_last_name
        FROM batch_coach_assignments a JOIN batches b ON b.id=a.batch_id JOIN coaches c ON c.id=a.coach_id WHERE 1=1
    """
    params: list[object] = []
    if batch_id is not None:
        sql += " AND a.batch_id=?";params.append(batch_id)
    if coach_id is not None:
        sql += " AND a.coach_id=?";params.append(coach_id)
    sql += " ORDER BY a.id DESC"
    rows = fetch_all(sql,params)
    for row in rows:
        row["coach_name"] = f"{row.get('coach_first_name') or ''} {row.get('coach_last_name') or ''}".strip()
    return rows


@router.post("/batch-coach-assignments", status_code=201)
def create_batch_coach_assignment(payload: BatchCoachPayload, batch_id: int):
    _batch(batch_id)
    with connection() as conn:
        coach = conn.execute("SELECT id,status FROM coaches WHERE id=?", (payload.coach_id,)).fetchone()
        if not coach:
            raise HTTPException(404, "Coach not found")
        if str(coach["status"] or "active") != "active":
            raise HTTPException(409, "Only active coaches can be assigned to a batch")
        duplicate = conn.execute("SELECT id FROM batch_coach_assignments WHERE batch_id=? AND coach_id=? AND status='active'", (batch_id,payload.coach_id)).fetchone()
        if duplicate:
            raise HTTPException(409, "Coach is already actively assigned to this batch")
        if payload.assignment_role == "primary":
            conn.execute("UPDATE batch_coach_assignments SET status='inactive',end_date=?,updated_at=CURRENT_TIMESTAMP WHERE batch_id=? AND assignment_role='primary' AND status='active'", (_clean(payload.start_date),batch_id))
        row = conn.execute(
            "INSERT INTO batch_coach_assignments(batch_id,coach_id,assignment_role,status,start_date) VALUES(?,?,?,'active',?) RETURNING id",
            (batch_id,payload.coach_id,payload.assignment_role,_clean(payload.start_date)),
        ).fetchone()
        assignment_id = int(row["id"])
    return fetch_one(
        """
        SELECT a.*,b.name AS batch_name,c.first_name || ' ' || c.last_name AS coach_name
        FROM batch_coach_assignments a JOIN batches b ON b.id=a.batch_id JOIN coaches c ON c.id=a.coach_id WHERE a.id=?
        """,
        (assignment_id,),
    )


@router.post("/batches/{batch_id}/generate-sessions", status_code=201)
def generate_batch_sessions(batch_id: int, payload: RecurringSchedulePayload):
    batch_row = _batch(batch_id)
    start = _validate_date(payload.start_date, "Start date")
    end = _validate_date(payload.end_date, "End date")
    if end < start:
        raise HTTPException(422, "End date must be on or after start date")
    weekdays = set(payload.weekdays)
    if any(day < 0 or day > 6 for day in weekdays):
        raise HTTPException(422, "Weekdays must use 0=Monday through 6=Sunday")
    _time_minutes(payload.start_time)
    created_ids: list[int] = []
    with connection() as conn:
        coach_id = _active_primary_coach(conn,batch_id)
        timezone = _academy_timezone(conn)
        player_ids = _active_batch_players(conn,batch_id)
        current = start
        while current <= end:
            if current.weekday() in weekdays:
                session_date = current.isoformat()
                exists = conn.execute("SELECT id FROM academy_sessions WHERE batch_id=? AND session_date=? AND start_time=? AND status<>'cancelled'", (batch_id,session_date,payload.start_time)).fetchone()
                if not exists:
                    created_ids.append(_insert_session(
                        conn,batch_id=batch_id,original_session_id=None,coach_id=coach_id,session_kind="batch",
                        session_date=session_date,start_time=payload.start_time,duration_minutes=payload.duration_minutes,
                        timezone=timezone,location=batch_row.get("location"),resource=batch_row.get("resource"),notes=None,player_ids=player_ids,
                    ))
            current += timedelta(days=1)
    return {"created_count":len(created_ids),"session_ids":created_ids,"timezone":_session(created_ids[0])["timezone"] if created_ids else None}


@router.get("/sessions")
def sessions(batch_id: int | None = None, coach_id: int | None = None, session_date: str | None = None):
    sql = "SELECT id FROM academy_sessions WHERE 1=1"
    params: list[object] = []
    if batch_id is not None:
        sql += " AND batch_id=?";params.append(batch_id)
    if coach_id is not None:
        sql += " AND coach_id=?";params.append(coach_id)
    if session_date is not None:
        sql += " AND session_date=?";params.append(session_date)
    sql += " ORDER BY session_date,start_time,id"
    rows = fetch_all(sql,params)
    return [_session(int(row["id"])) for row in rows]


@router.get("/sessions/{session_id}")
def session(session_id: int):
    return _session(session_id)


@router.get("/sessions/{session_id}/players")
def session_players(session_id: int):
    _session(session_id)
    return fetch_all("SELECT sp.*,p.name AS player_name FROM session_players sp JOIN players p ON p.id=sp.player_id WHERE sp.session_id=? ORDER BY p.name COLLATE NOCASE", (session_id,))


@router.post("/sessions/private", status_code=201)
def create_private_session(payload: PrivateSessionPayload):
    with connection() as conn:
        player = conn.execute("SELECT id,status FROM players WHERE id=?", (payload.player_id,)).fetchone()
        coach = conn.execute("SELECT id,status FROM coaches WHERE id=?", (payload.coach_id,)).fetchone()
        if not player:
            raise HTTPException(404, "Player not found")
        if not coach:
            raise HTTPException(404, "Coach not found")
        if str(player["status"] or "active") != "active" or str(coach["status"] or "active") != "active":
            raise HTTPException(409, "Private sessions require an active player and active coach")
        session_id = _insert_session(
            conn,batch_id=None,original_session_id=None,coach_id=payload.coach_id,session_kind="private",
            session_date=payload.session_date,start_time=payload.start_time,duration_minutes=payload.duration_minutes,
            timezone=_academy_timezone(conn),location=payload.location,resource=payload.resource,notes=payload.notes,player_ids=[payload.player_id],
        )
    return _session(session_id)


@router.put("/sessions/{session_id}")
def update_session(session_id: int, payload: SessionUpdatePayload):
    current = _session(session_id)
    with connection() as conn:
        if payload.coach_id is not None:
            coach = conn.execute("SELECT id,status FROM coaches WHERE id=?", (payload.coach_id,)).fetchone()
            if not coach:
                raise HTTPException(404, "Coach not found")
            if str(coach["status"] or "active") != "active":
                raise HTTPException(409, "Only an active coach can be assigned to a session")
        _validate_date(payload.session_date,"Session date")
        _time_minutes(payload.start_time)
        _check_coach_conflict(conn,payload.coach_id,payload.session_date,payload.start_time,payload.duration_minutes,exclude_session_id=session_id)
        conn.execute(
            """
            UPDATE academy_sessions SET session_date=?,start_time=?,duration_minutes=?,coach_id=?,location=?,resource=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?
            """,
            (payload.session_date,payload.start_time,payload.duration_minutes,payload.coach_id,_clean(payload.location),_clean(payload.resource),_clean(payload.notes),session_id),
        )
    return _session(session_id)


@router.post("/sessions/{session_id}/cancel")
def cancel_session(session_id: int, payload: SessionCancelPayload):
    current = _session(session_id)
    if current["status"] == "cancelled":
        raise HTTPException(409, "Session is already cancelled")
    with connection() as conn:
        conn.execute("UPDATE academy_sessions SET status='cancelled',cancellation_reason=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (_clean(payload.reason),session_id))
    return _session(session_id)


@router.post("/sessions/{session_id}/makeup", status_code=201)
def create_makeup_session(session_id: int, payload: MakeupSessionPayload):
    original = _session(session_id)
    with connection() as conn:
        players = conn.execute("SELECT player_id FROM session_players WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        player_ids = [int(row["player_id"]) for row in players]
        new_id = _insert_session(
            conn,batch_id=original.get("batch_id"),original_session_id=session_id,coach_id=payload.coach_id if payload.coach_id is not None else original.get("coach_id"),
            session_kind="makeup",session_date=payload.session_date,start_time=payload.start_time,
            duration_minutes=payload.duration_minutes if payload.duration_minutes is not None else int(original["duration_minutes"]),
            timezone=str(original["timezone"]),location=payload.location if payload.location is not None else original.get("location"),
            resource=payload.resource if payload.resource is not None else original.get("resource"),notes=payload.notes,player_ids=player_ids,
        )
    return _session(new_id)


@router.get("/coaches/{coach_id}/workload")
def coach_workload(coach_id: int):
    coach = fetch_one("SELECT id,first_name,last_name FROM coaches WHERE id=?", (coach_id,))
    if not coach:
        raise HTTPException(404, "Coach not found")
    row = fetch_one(
        """
        SELECT COUNT(*) AS session_count, COALESCE(SUM(duration_minutes),0) AS total_minutes
        FROM academy_sessions WHERE coach_id=? AND status<>'cancelled'
        """,
        (coach_id,),
    )
    return {
        "coach_id":coach_id,
        "coach_name":f"{coach.get('first_name') or ''} {coach.get('last_name') or ''}".strip(),
        "session_count":int(row["session_count"] or 0),
        "total_minutes":int(row["total_minutes"] or 0),
        "total_hours":round(int(row["total_minutes"] or 0)/60,2),
    }
