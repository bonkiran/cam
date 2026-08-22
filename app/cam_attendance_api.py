from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/cam", tags=["cam-attendance"])

AttendanceStatus = Literal["present", "late", "absent"]


class AttendancePolicyPayload(BaseModel):
    repeated_absence_threshold: int = Field(default=3, ge=1, le=20)
    absence_lookback_days: int = Field(default=30, ge=1, le=365)
    default_makeup_for_absent: bool = True


class PlayerAttendanceEntry(BaseModel):
    player_id: int = Field(gt=0)
    status: AttendanceStatus
    absence_reason: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    make_up_eligible: bool | None = None


class SessionAttendancePayload(BaseModel):
    players: list[PlayerAttendanceEntry] = Field(min_length=1, max_length=200)
    coach_status: AttendanceStatus | None = None
    coach_notes: str | None = Field(default=None, max_length=1000)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS attendance_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT UNIQUE,
            repeated_absence_threshold INTEGER NOT NULL DEFAULT 3,
            absence_lookback_days INTEGER NOT NULL DEFAULT 30,
            default_makeup_for_absent INTEGER NOT NULL DEFAULT 1,
            default_makeup_for_excused INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS player_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            session_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            status TEXT NOT NULL,
            absence_reason TEXT,
            notes TEXT,
            make_up_eligible INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(session_id) REFERENCES academy_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            UNIQUE(session_id, player_id)
        );
        CREATE INDEX IF NOT EXISTS idx_player_attendance_session ON player_attendance(session_id);
        CREATE INDEX IF NOT EXISTS idx_player_attendance_player ON player_attendance(player_id);
        CREATE INDEX IF NOT EXISTS idx_player_attendance_status ON player_attendance(status);

        CREATE TABLE IF NOT EXISTS coach_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            session_id BIGINT NOT NULL UNIQUE,
            coach_id BIGINT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(session_id) REFERENCES academy_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_coach_attendance_coach ON coach_attendance(coach_id);

        CREATE TABLE IF NOT EXISTS attendance_change_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            entity_type TEXT NOT NULL,
            attendance_id BIGINT NOT NULL,
            session_id BIGINT NOT NULL,
            subject_id BIGINT NOT NULL,
            before_json TEXT,
            after_json TEXT NOT NULL,
            changed_by TEXT NOT NULL DEFAULT 'cam-admin',
            changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(session_id) REFERENCES academy_sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_attendance_history_session ON attendance_change_history(session_id);
        CREATE INDEX IF NOT EXISTS idx_attendance_history_subject ON attendance_change_history(entity_type,subject_id);

        CREATE TABLE IF NOT EXISTS attendance_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            player_id BIGINT NOT NULL,
            alert_type TEXT NOT NULL DEFAULT 'repeated_absence',
            occurrence_count INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            lookback_days INTEGER NOT NULL,
            last_session_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_attendance_alerts_player ON attendance_alerts(player_id);
        CREATE INDEX IF NOT EXISTS idx_attendance_alerts_status ON attendance_alerts(status);
    """
    with connection() as conn:
        conn.executescript(schema)
        # Normalize historical four-state attendance into the current three-state model.
        conn.execute("UPDATE player_attendance SET status='absent' WHERE status='excused'")
        conn.execute("UPDATE coach_attendance SET status='absent' WHERE status='excused'")


def _academy(conn):
    return conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()


def _academy_id(conn) -> int | None:
    row = _academy(conn)
    return int(row["id"]) if row else None


def _policy(conn) -> dict:
    academy_id = _academy_id(conn)
    if academy_id is None:
        return {
            "academy_id": None,
            "repeated_absence_threshold": 3,
            "absence_lookback_days": 30,
            "default_makeup_for_absent": True,
        }
    row = conn.execute("SELECT * FROM attendance_policies WHERE academy_id=?", (academy_id,)).fetchone()
    if not row:
        created = conn.execute(
            """
            INSERT INTO attendance_policies(academy_id,repeated_absence_threshold,absence_lookback_days,
                                            default_makeup_for_absent,default_makeup_for_excused)
            VALUES(?,3,30,1,1) RETURNING id
            """,
            (academy_id,),
        ).fetchone()
        row = conn.execute("SELECT * FROM attendance_policies WHERE id=?", (int(created["id"]),)).fetchone()
    out = dict(row)
    out["default_makeup_for_absent"] = bool(out.get("default_makeup_for_absent"))
    out.pop("default_makeup_for_excused", None)
    return out


def _session_context(session_id: int) -> dict:
    row = fetch_one(
        """
        SELECT s.*, b.name AS batch_name, c.first_name AS coach_first_name, c.last_name AS coach_last_name
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


def _session_roster(conn, session_id: int) -> list[int]:
    rows = conn.execute("SELECT player_id FROM session_players WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    return [int(row["player_id"]) for row in rows]


def _attendance_state(row) -> dict | None:
    if not row:
        return None
    out = dict(row)
    if "make_up_eligible" in out:
        out["make_up_eligible"] = bool(out["make_up_eligible"])
    return out


def _history(conn, *, entity_type: str, attendance_id: int, session_id: int, subject_id: int, before: dict | None, after: dict) -> None:
    academy_id = _academy_id(conn)
    conn.execute(
        """
        INSERT INTO attendance_change_history(academy_id,entity_type,attendance_id,session_id,subject_id,before_json,after_json,changed_by)
        VALUES(?,?,?,?,?,?,?,'cam-admin')
        """,
        (
            academy_id,
            entity_type,
            attendance_id,
            session_id,
            subject_id,
            json.dumps(before, sort_keys=True) if before is not None else None,
            json.dumps(after, sort_keys=True),
        ),
    )


def _default_makeup(status: str, policy: dict) -> bool:
    if status == "absent":
        return bool(policy["default_makeup_for_absent"])
    return False


def _refresh_absence_alert(conn, player_id: int, session_date: str, policy: dict) -> None:
    session_day = date.fromisoformat(session_date)
    from_day = (session_day - timedelta(days=int(policy["absence_lookback_days"]) - 1)).isoformat()
    count_row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM player_attendance a
        JOIN academy_sessions s ON s.id=a.session_id
        WHERE a.player_id=? AND a.status='absent' AND s.session_date>=? AND s.session_date<=?
        """,
        (player_id, from_day, session_date),
    ).fetchone()
    count = int(count_row["n"] or 0)
    threshold = int(policy["repeated_absence_threshold"])
    open_alert = conn.execute(
        "SELECT id FROM attendance_alerts WHERE player_id=? AND alert_type='repeated_absence' AND status='open' ORDER BY id DESC LIMIT 1",
        (player_id,),
    ).fetchone()
    academy_id = _academy_id(conn)
    if count >= threshold:
        if open_alert:
            conn.execute(
                """
                UPDATE attendance_alerts SET occurrence_count=?,threshold=?,lookback_days=?,last_session_date=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (count, threshold, int(policy["absence_lookback_days"]), session_date, int(open_alert["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO attendance_alerts(academy_id,player_id,alert_type,occurrence_count,threshold,lookback_days,last_session_date,status)
                VALUES(?,?,'repeated_absence',?,?,? ,?,'open')
                """,
                (academy_id, player_id, count, threshold, int(policy["absence_lookback_days"]), session_date),
            )
    elif open_alert:
        conn.execute(
            "UPDATE attendance_alerts SET status='resolved',occurrence_count=?,last_session_date=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (count, session_date, int(open_alert["id"])),
        )


_ensure_tables()


@router.get("/attendance/policy")
def attendance_policy():
    with connection() as conn:
        return _policy(conn)


@router.put("/attendance/policy")
def update_attendance_policy(payload: AttendancePolicyPayload):
    with connection() as conn:
        academy_id = _academy_id(conn)
        if academy_id is None:
            raise HTTPException(409, "Configure the Academy profile before attendance policy")
        current = _policy(conn)
        conn.execute(
            """
            UPDATE attendance_policies SET repeated_absence_threshold=?,absence_lookback_days=?,
                   default_makeup_for_absent=?,default_makeup_for_excused=0,updated_at=CURRENT_TIMESTAMP
            WHERE academy_id=?
            """,
            (
                payload.repeated_absence_threshold,
                payload.absence_lookback_days,
                1 if payload.default_makeup_for_absent else 0,
                academy_id,
            ),
        )
        return _policy(conn)


@router.get("/sessions/{session_id}/attendance")
def session_attendance(session_id: int):
    session = _session_context(session_id)
    roster = fetch_all(
        """
        SELECT sp.player_id,p.name AS player_name,p.status AS player_status,
               a.id AS attendance_id,a.status AS attendance_status,a.absence_reason,a.notes,a.make_up_eligible,a.updated_at
        FROM session_players sp
        JOIN players p ON p.id=sp.player_id
        LEFT JOIN player_attendance a ON a.session_id=sp.session_id AND a.player_id=sp.player_id
        WHERE sp.session_id=? ORDER BY p.name COLLATE NOCASE
        """,
        (session_id,),
    )
    for row in roster:
        row["make_up_eligible"] = bool(row.get("make_up_eligible")) if row.get("attendance_id") else False
    coach = fetch_one(
        """
        SELECT ca.*, c.first_name AS coach_first_name,c.last_name AS coach_last_name
        FROM coach_attendance ca JOIN coaches c ON c.id=ca.coach_id WHERE ca.session_id=?
        """,
        (session_id,),
    )
    if coach:
        coach["coach_name"] = f"{coach.get('coach_first_name') or ''} {coach.get('coach_last_name') or ''}".strip()
    return {"session": session, "players": roster, "coach_attendance": coach}


@router.put("/sessions/{session_id}/attendance")
def save_session_attendance(session_id: int, payload: SessionAttendancePayload):
    session = _session_context(session_id)
    if session["status"] == "cancelled":
        raise HTTPException(409, "Attendance cannot be taken for a cancelled session")
    with connection() as conn:
        roster = set(_session_roster(conn, session_id))
        supplied = [entry.player_id for entry in payload.players]
        if len(supplied) != len(set(supplied)):
            raise HTTPException(422, "Duplicate player appears in attendance payload")
        invalid = [player_id for player_id in supplied if player_id not in roster]
        if invalid:
            raise HTTPException(409, "Attendance can only be recorded for players on this session roster")
        policy = _policy(conn)
        academy_id = _academy_id(conn)

        for entry in payload.players:
            existing_row = conn.execute(
                "SELECT * FROM player_attendance WHERE session_id=? AND player_id=?",
                (session_id, entry.player_id),
            ).fetchone()
            before = _attendance_state(existing_row)
            makeup = _default_makeup(entry.status, policy) if entry.make_up_eligible is None else bool(entry.make_up_eligible)
            reason = _clean(entry.absence_reason) if entry.status == "absent" else None
            notes = _clean(entry.notes)
            if existing_row:
                attendance_id = int(existing_row["id"])
                conn.execute(
                    """
                    UPDATE player_attendance SET status=?,absence_reason=?,notes=?,make_up_eligible=?,updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (entry.status, reason, notes, 1 if makeup else 0, attendance_id),
                )
            else:
                created = conn.execute(
                    """
                    INSERT INTO player_attendance(academy_id,session_id,player_id,status,absence_reason,notes,make_up_eligible)
                    VALUES(?,?,?,?,?,?,?) RETURNING id
                    """,
                    (academy_id, session_id, entry.player_id, entry.status, reason, notes, 1 if makeup else 0),
                ).fetchone()
                attendance_id = int(created["id"])
            after_row = conn.execute("SELECT * FROM player_attendance WHERE id=?", (attendance_id,)).fetchone()
            after = _attendance_state(after_row) or {}
            comparable_before = None if before is None else {k: before.get(k) for k in ("status","absence_reason","notes","make_up_eligible")}
            comparable_after = {k: after.get(k) for k in ("status","absence_reason","notes","make_up_eligible")}
            if comparable_before != comparable_after:
                _history(
                    conn,
                    entity_type="player",
                    attendance_id=attendance_id,
                    session_id=session_id,
                    subject_id=entry.player_id,
                    before=comparable_before,
                    after=comparable_after,
                )
            _refresh_absence_alert(conn, entry.player_id, str(session["session_date"]), policy)

        if payload.coach_status is not None:
            coach_id = session.get("coach_id")
            if not coach_id:
                raise HTTPException(409, "This session has no assigned coach")
            existing_coach = conn.execute("SELECT * FROM coach_attendance WHERE session_id=?", (session_id,)).fetchone()
            before = dict(existing_coach) if existing_coach else None
            if existing_coach:
                attendance_id = int(existing_coach["id"])
                conn.execute(
                    "UPDATE coach_attendance SET status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (payload.coach_status, _clean(payload.coach_notes), attendance_id),
                )
            else:
                created = conn.execute(
                    "INSERT INTO coach_attendance(academy_id,session_id,coach_id,status,notes) VALUES(?,?,?,?,?) RETURNING id",
                    (academy_id, session_id, int(coach_id), payload.coach_status, _clean(payload.coach_notes)),
                ).fetchone()
                attendance_id = int(created["id"])
            after_row = conn.execute("SELECT * FROM coach_attendance WHERE id=?", (attendance_id,)).fetchone()
            after = dict(after_row)
            comparable_before = None if before is None else {k: before.get(k) for k in ("status","notes")}
            comparable_after = {k: after.get(k) for k in ("status","notes")}
            if comparable_before != comparable_after:
                _history(
                    conn,
                    entity_type="coach",
                    attendance_id=attendance_id,
                    session_id=session_id,
                    subject_id=int(coach_id),
                    before=comparable_before,
                    after=comparable_after,
                )

    return session_attendance(session_id)


@router.get("/players/{player_id}/attendance-summary")
def player_attendance_summary(player_id: int):
    player = fetch_one("SELECT id,name FROM players WHERE id=?", (player_id,))
    if not player:
        raise HTTPException(404, "Player not found")
    rows = fetch_all(
        """
        SELECT a.status,a.make_up_eligible,s.session_date,s.id AS session_id
        FROM player_attendance a JOIN academy_sessions s ON s.id=a.session_id
        WHERE a.player_id=? ORDER BY s.session_date,s.id
        """,
        (player_id,),
    )
    counts = {status: 0 for status in ("present", "late", "absent")}
    makeup_count = 0
    for row in rows:
        status = str(row["status"])
        if status in counts:
            counts[status] += 1
        if bool(row.get("make_up_eligible")):
            makeup_count += 1
    denominator = counts["present"] + counts["late"] + counts["absent"]
    attended = counts["present"] + counts["late"]
    percentage = round(attended * 100 / denominator, 1) if denominator else None
    return {
        "player_id": player_id,
        "player_name": player["name"],
        "recorded_sessions": len(rows),
        **counts,
        "attendance_denominator": denominator,
        "attendance_percentage": percentage,
        "make_up_eligible_count": makeup_count,
        "calculation_rule": "present + late count as attended; absent counts against percentage",
    }


@router.get("/attendance/history")
def attendance_history(session_id: int | None = None, entity_type: str | None = None, subject_id: int | None = None):
    sql = "SELECT * FROM attendance_change_history WHERE 1=1"
    params: list[object] = []
    if session_id is not None:
        sql += " AND session_id=?"
        params.append(session_id)
    if entity_type is not None:
        sql += " AND entity_type=?"
        params.append(entity_type)
    if subject_id is not None:
        sql += " AND subject_id=?"
        params.append(subject_id)
    sql += " ORDER BY id DESC"
    rows = fetch_all(sql, params)
    for row in rows:
        try:
            row["before"] = json.loads(row.pop("before_json") or "null")
        except Exception:
            row["before"] = None
        try:
            row["after"] = json.loads(row.pop("after_json") or "{}")
        except Exception:
            row["after"] = {}
    return rows


@router.get("/attendance/alerts")
def attendance_alerts(status: str | None = "open", player_id: int | None = None):
    sql = """
        SELECT a.*,p.name AS player_name
        FROM attendance_alerts a JOIN players p ON p.id=a.player_id WHERE 1=1
    """
    params: list[object] = []
    if status:
        sql += " AND a.status=?"
        params.append(status)
    if player_id is not None:
        sql += " AND a.player_id=?"
        params.append(player_id)
    sql += " ORDER BY a.id DESC"
    return fetch_all(sql, params)


@router.post("/attendance/alerts/{alert_id}/acknowledge")
def acknowledge_attendance_alert(alert_id: int):
    with connection() as conn:
        row = conn.execute("SELECT id FROM attendance_alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Attendance alert not found")
        conn.execute("UPDATE attendance_alerts SET status='acknowledged',updated_at=CURRENT_TIMESTAMP WHERE id=?", (alert_id,))
    return fetch_one("SELECT * FROM attendance_alerts WHERE id=?", (alert_id,))
