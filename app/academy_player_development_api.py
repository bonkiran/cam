from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .academy_attendance_api import SessionAttendancePayload, save_session_attendance as _save_attendance
from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-player-development"])

EVIDENCE_TYPE_PRACTICED = "practiced"
ATTENDED_STATUSES = {"present", "late"}
MAX_SESSION_SKILLS = 8

SKILL_CATALOG = [
    ("stance_setup", "Stance & Setup", "Batting", 10),
    ("front_foot_movement", "Front-Foot Movement", "Batting", 20),
    ("back_foot_movement", "Back-Foot Movement", "Batting", 30),
    ("cover_drive", "Cover Drive", "Batting", 40),
    ("straight_drive", "Straight Drive", "Batting", 50),
    ("short_ball_response", "Short-Ball Response", "Batting", 60),
    ("shot_selection", "Shot Selection", "Batting", 70),
    ("timing_balance", "Timing & Balance", "Batting", 80),
    ("line_length", "Line & Length", "Bowling", 110),
    ("run_up_rhythm", "Run-Up Rhythm", "Bowling", 120),
    ("release_control", "Release Control", "Bowling", 130),
    ("spin_control", "Spin Control", "Bowling", 140),
    ("catching", "Catching", "Fielding", 210),
    ("ground_fielding", "Ground Fielding", "Fielding", 220),
    ("throwing_accuracy", "Throwing Accuracy", "Fielding", 230),
    ("running_between_wickets", "Running Between Wickets", "Game Skills", 310),
    ("game_scenarios", "Game Scenarios", "Game Skills", 320),
    ("agility_conditioning", "Agility & Conditioning", "Fitness", 410),
]


class SessionFocusPayload(BaseModel):
    skill_keys: list[str] = Field(default_factory=list, max_length=MAX_SESSION_SKILLS)


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS development_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            display_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_development_skills_category ON development_skills(category,display_order);

        CREATE TABLE IF NOT EXISTS session_development_focus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            session_id BIGINT NOT NULL,
            skill_id BIGINT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(session_id) REFERENCES academy_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(skill_id) REFERENCES development_skills(id) ON DELETE CASCADE,
            UNIQUE(session_id,skill_id)
        );
        CREATE INDEX IF NOT EXISTS idx_session_development_focus_session ON session_development_focus(session_id);

        CREATE TABLE IF NOT EXISTS player_development_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            player_id BIGINT NOT NULL,
            session_id BIGINT NOT NULL,
            skill_id BIGINT NOT NULL,
            evidence_type TEXT NOT NULL DEFAULT 'practiced',
            exposure_minutes INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'group_session',
            coach_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(session_id) REFERENCES academy_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(skill_id) REFERENCES development_skills(id) ON DELETE CASCADE,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE SET NULL,
            UNIQUE(player_id,session_id,skill_id,evidence_type)
        );
        CREATE INDEX IF NOT EXISTS idx_player_development_evidence_player ON player_development_evidence(player_id);
        CREATE INDEX IF NOT EXISTS idx_player_development_evidence_session ON player_development_evidence(session_id);
        CREATE INDEX IF NOT EXISTS idx_player_development_evidence_skill ON player_development_evidence(skill_id);
    """
    with connection() as conn:
        conn.executescript(schema)
        for key, name, category, order in SKILL_CATALOG:
            conn.execute(
                """
                INSERT INTO development_skills(skill_key,name,category,display_order,active)
                VALUES(?,?,?,?,1)
                ON CONFLICT(skill_key) DO NOTHING
                """,
                (key, name, category, order),
            )


def _session(conn, session_id: int):
    row = conn.execute(
        """
        SELECT id,academy_id,batch_id,coach_id,session_kind,session_date,duration_minutes,status
        FROM academy_sessions WHERE id=?
        """,
        (session_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    return row


def _normalize_skill_keys(keys: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in keys:
        key = str(value or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    if len(normalized) > MAX_SESSION_SKILLS:
        raise HTTPException(422, f"A session can have at most {MAX_SESSION_SKILLS} development focus skills")
    return normalized


def _skill_rows_for_keys(conn, keys: list[str]) -> list:
    if not keys:
        return []
    rows = []
    for key in keys:
        row = conn.execute(
            "SELECT id,skill_key,name,category,display_order FROM development_skills WHERE skill_key=? AND active=1",
            (key,),
        ).fetchone()
        if row:
            rows.append(row)
    found = {str(row["skill_key"]) for row in rows}
    unknown = [key for key in keys if key not in found]
    if unknown:
        raise HTTPException(422, f"Unknown development skill(s): {', '.join(unknown)}")
    return rows


def _source_for_session(session) -> str:
    return "group_session" if session["batch_id"] is not None else "private_session"


def _sync_session_practice_evidence(conn, session_id: int) -> int:
    """Make Practiced evidence exactly match focus x attended players for a session.

    Present and late count as attended. Absent and excused never receive passive
    development evidence. This function is intentionally idempotent so attendance
    corrections and focus edits can safely be saved more than once.
    """
    session = _session(conn, session_id)
    focus_rows = conn.execute(
        """
        SELECT ds.id AS skill_id
        FROM session_development_focus sdf
        JOIN development_skills ds ON ds.id=sdf.skill_id
        WHERE sdf.session_id=? AND ds.active=1
        ORDER BY ds.display_order,ds.id
        """,
        (session_id,),
    ).fetchall()
    skill_ids = [int(row["skill_id"]) for row in focus_rows]

    attendance_rows = conn.execute(
        """
        SELECT player_id,status
        FROM player_attendance
        WHERE session_id=?
        """,
        (session_id,),
    ).fetchall()
    attended_player_ids = [
        int(row["player_id"])
        for row in attendance_rows
        if str(row["status"]).lower() in ATTENDED_STATUSES
    ]

    desired = {
        (player_id, skill_id)
        for player_id in attended_player_ids
        for skill_id in skill_ids
    }
    if str(session["status"]).lower() == "cancelled":
        desired = set()

    existing = conn.execute(
        """
        SELECT id,player_id,skill_id
        FROM player_development_evidence
        WHERE session_id=? AND evidence_type=?
        """,
        (session_id, EVIDENCE_TYPE_PRACTICED),
    ).fetchall()
    for row in existing:
        pair = (int(row["player_id"]), int(row["skill_id"]))
        if pair not in desired:
            conn.execute("DELETE FROM player_development_evidence WHERE id=?", (int(row["id"]),))

    academy_id = session["academy_id"]
    coach_id = session["coach_id"]
    exposure_minutes = int(session["duration_minutes"] or 0)
    source = _source_for_session(session)
    for player_id, skill_id in sorted(desired):
        conn.execute(
            """
            INSERT INTO player_development_evidence(
                academy_id,player_id,session_id,skill_id,evidence_type,exposure_minutes,source,coach_id
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(player_id,session_id,skill_id,evidence_type)
            DO UPDATE SET exposure_minutes=excluded.exposure_minutes,
                          source=excluded.source,
                          coach_id=excluded.coach_id,
                          updated_at=CURRENT_TIMESTAMP
            """,
            (
                academy_id,
                player_id,
                session_id,
                skill_id,
                EVIDENCE_TYPE_PRACTICED,
                exposure_minutes,
                source,
                coach_id,
            ),
        )

    count_row = conn.execute(
        "SELECT COUNT(*) AS n FROM player_development_evidence WHERE session_id=? AND evidence_type=?",
        (session_id, EVIDENCE_TYPE_PRACTICED),
    ).fetchone()
    return int(count_row["n"] or 0)


def _focus_response(conn, session_id: int) -> dict:
    session = _session(conn, session_id)
    rows = conn.execute(
        """
        SELECT ds.skill_key,ds.name,ds.category,ds.display_order
        FROM session_development_focus sdf
        JOIN development_skills ds ON ds.id=sdf.skill_id
        WHERE sdf.session_id=?
        ORDER BY ds.display_order,ds.name
        """,
        (session_id,),
    ).fetchall()
    evidence_count = conn.execute(
        "SELECT COUNT(*) AS n FROM player_development_evidence WHERE session_id=? AND evidence_type=?",
        (session_id, EVIDENCE_TYPE_PRACTICED),
    ).fetchone()
    return {
        "session_id": session_id,
        "session_date": session["session_date"],
        "skill_keys": [str(row["skill_key"]) for row in rows],
        "skills": [dict(row) for row in rows],
        "evidence_type": EVIDENCE_TYPE_PRACTICED,
        "evidence_label": "Practiced / Exposed",
        "claim_level": "training_exposure_only",
        "generated_evidence_count": int(evidence_count["n"] or 0),
    }


_ensure_tables()


@router.get("/development/skills")
def development_skills():
    return fetch_all(
        """
        SELECT skill_key,name,category,display_order
        FROM development_skills
        WHERE active=1
        ORDER BY display_order,name
        """
    )


@router.get("/sessions/{session_id}/development-focus")
def session_development_focus(session_id: int):
    with connection() as conn:
        return _focus_response(conn, session_id)


@router.put("/sessions/{session_id}/development-focus")
def save_session_development_focus(session_id: int, payload: SessionFocusPayload):
    keys = _normalize_skill_keys(payload.skill_keys)
    with connection() as conn:
        session = _session(conn, session_id)
        if str(session["status"]).lower() == "cancelled":
            raise HTTPException(409, "Development focus cannot be set for a cancelled session")
        skills = _skill_rows_for_keys(conn, keys)
        conn.execute("DELETE FROM session_development_focus WHERE session_id=?", (session_id,))
        for skill in skills:
            conn.execute(
                """
                INSERT INTO session_development_focus(academy_id,session_id,skill_id)
                VALUES(?,?,?)
                ON CONFLICT(session_id,skill_id) DO NOTHING
                """,
                (session["academy_id"], session_id, int(skill["id"])),
            )
        _sync_session_practice_evidence(conn, session_id)
        return _focus_response(conn, session_id)


@router.put("/sessions/{session_id}/attendance")
def save_session_attendance_with_development(session_id: int, payload: SessionAttendancePayload):
    # Reuse the proven attendance implementation, then reconcile passive player
    # development evidence. This enhanced route is registered before the legacy
    # attendance router in run.py, so existing clients keep the same contract.
    result = _save_attendance(session_id, payload)
    with connection() as conn:
        _sync_session_practice_evidence(conn, session_id)
        result["development"] = _focus_response(conn, session_id)
    return result


@router.get("/players/{player_id}/development-history")
def player_development_history(player_id: int, skill_key: str | None = None):
    player = fetch_one("SELECT id,name FROM players WHERE id=?", (player_id,))
    if not player:
        raise HTTPException(404, "Player not found")
    sql = """
        SELECT e.id,e.player_id,e.session_id,e.evidence_type,e.exposure_minutes,e.source,e.coach_id,
               e.created_at,e.updated_at,ds.skill_key,ds.name AS skill_name,ds.category,
               s.session_date,s.duration_minutes,s.batch_id,b.name AS batch_name
        FROM player_development_evidence e
        JOIN development_skills ds ON ds.id=e.skill_id
        JOIN academy_sessions s ON s.id=e.session_id
        LEFT JOIN batches b ON b.id=s.batch_id
        WHERE e.player_id=?
    """
    params: list[object] = [player_id]
    if skill_key:
        sql += " AND ds.skill_key=?"
        params.append(skill_key.strip().lower())
    sql += " ORDER BY s.session_date DESC,e.id DESC"
    rows = fetch_all(sql, params)
    for row in rows:
        row["evidence_label"] = "Practiced / Exposed"
        row["claim_level"] = "training_exposure_only"
        row["improvement_claimed"] = False
    return {"player_id": player_id, "player_name": player["name"], "evidence": rows}


@router.get("/players/{player_id}/development-summary")
def player_development_summary(player_id: int):
    player = fetch_one("SELECT id,name FROM players WHERE id=?", (player_id,))
    if not player:
        raise HTTPException(404, "Player not found")
    rows = fetch_all(
        """
        SELECT ds.skill_key,ds.name AS skill_name,ds.category,
               COUNT(DISTINCT e.session_id) AS practiced_sessions,
               COALESCE(SUM(e.exposure_minutes),0) AS exposure_minutes,
               MIN(s.session_date) AS first_practiced_on,
               MAX(s.session_date) AS last_practiced_on
        FROM player_development_evidence e
        JOIN development_skills ds ON ds.id=e.skill_id
        JOIN academy_sessions s ON s.id=e.session_id
        WHERE e.player_id=? AND e.evidence_type=?
        GROUP BY ds.skill_key,ds.name,ds.category,ds.display_order
        ORDER BY ds.display_order,ds.name
        """,
        (player_id, EVIDENCE_TYPE_PRACTICED),
    )
    return {
        "player_id": player_id,
        "player_name": player["name"],
        "evidence_type": EVIDENCE_TYPE_PRACTICED,
        "evidence_label": "Practiced / Exposed",
        "claim_level": "training_exposure_only",
        "improvement_claimed": False,
        "skills": rows,
    }
