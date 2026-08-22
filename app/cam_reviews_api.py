from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .cam_auth_api import _audit, current_access_user
from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/cam/reviews", tags=["cam-player-reviews"])

ReviewType = Literal["session", "periodic", "assessment"]
ReviewStatus = Literal["draft", "published"]
ReviewCategory = Literal["general", "batting", "bowling", "fielding", "fitness"]
ActionStatus = Literal["open", "completed"]


class ReviewActionPayload(BaseModel):
    category: ReviewCategory = "general"
    title: str = Field(min_length=2, max_length=180)
    detail: str | None = Field(default=None, max_length=1200)
    target_date: str | None = Field(default=None, max_length=20)


class PlayerReviewPayload(BaseModel):
    player_id: int = Field(gt=0)
    coach_id: int | None = Field(default=None, gt=0)
    session_id: int | None = Field(default=None, gt=0)
    review_date: str = Field(max_length=20)
    review_type: ReviewType = "session"
    period_label: str = Field(min_length=2, max_length=120)
    batting_score: int = Field(ge=1, le=5)
    bowling_score: int = Field(ge=1, le=5)
    fielding_score: int = Field(ge=1, le=5)
    fitness_score: int = Field(ge=1, le=5)
    batting_notes: str | None = Field(default=None, max_length=2500)
    bowling_notes: str | None = Field(default=None, max_length=2500)
    fielding_notes: str | None = Field(default=None, max_length=2500)
    fitness_notes: str | None = Field(default=None, max_length=2500)
    strengths: str | None = Field(default=None, max_length=3000)
    focus_areas: str | None = Field(default=None, max_length=3000)
    coach_summary: str = Field(min_length=2, max_length=5000)
    next_steps: str | None = Field(default=None, max_length=3000)
    actions: list[ReviewActionPayload] = Field(default_factory=list, max_length=20)


class ActionStatusPayload(BaseModel):
    status: ActionStatus


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _validate_date(value: str, label: str = "Date") -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except Exception as exc:
        raise HTTPException(422, f"{label} must be YYYY-MM-DD") from exc


def _can_manage(user: dict) -> bool:
    return user.get("role") in {"owner", "admin", "coach"} and "reviews.manage" in user.get("permissions", [])


def _require_manage(user: dict) -> None:
    if not _can_manage(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Coach, admin, or owner review access is required")


def _family_player_ids(user: dict) -> set[int]:
    if user.get("role") == "player":
        player_id = user.get("player_id")
        return {int(player_id)} if player_id else set()
    if user.get("role") == "parent":
        guardian_id = user.get("guardian_id")
        if not guardian_id:
            return set()
        return {
            int(row["player_id"])
            for row in fetch_all("SELECT player_id FROM player_guardians WHERE guardian_id=?", (guardian_id,))
        }
    return set()


def _can_view_player(user: dict, player_id: int) -> bool:
    if _can_manage(user):
        return True
    return "reviews.view" in user.get("permissions", []) and int(player_id) in _family_player_ids(user)


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_player_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            player_id BIGINT NOT NULL,
            coach_id BIGINT,
            session_id BIGINT,
            created_by_user_id BIGINT NOT NULL,
            review_date TEXT NOT NULL,
            review_type TEXT NOT NULL DEFAULT 'session',
            period_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            batting_score INTEGER NOT NULL,
            bowling_score INTEGER NOT NULL,
            fielding_score INTEGER NOT NULL,
            fitness_score INTEGER NOT NULL,
            batting_notes TEXT,
            bowling_notes TEXT,
            fielding_notes TEXT,
            fitness_notes TEXT,
            strengths TEXT,
            focus_areas TEXT,
            coach_summary TEXT NOT NULL,
            next_steps TEXT,
            published_at TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE SET NULL,
            FOREIGN KEY(session_id) REFERENCES academy_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by_user_id) REFERENCES academy_users(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_academy_reviews_player ON academy_player_reviews(player_id);
        CREATE INDEX IF NOT EXISTS idx_academy_reviews_coach ON academy_player_reviews(coach_id);
        CREATE INDEX IF NOT EXISTS idx_academy_reviews_status ON academy_player_reviews(status);
        CREATE INDEX IF NOT EXISTS idx_academy_reviews_date ON academy_player_reviews(review_date);

        CREATE TABLE IF NOT EXISTS academy_review_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id BIGINT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            title TEXT NOT NULL,
            detail TEXT,
            target_date TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            completed_at TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(review_id) REFERENCES academy_player_reviews(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_review_actions_review ON academy_review_actions(review_id);
        CREATE INDEX IF NOT EXISTS idx_review_actions_status ON academy_review_actions(status);
    """
    with connection() as conn:
        conn.executescript(schema)


def _review_actions(review_id: int) -> list[dict]:
    return fetch_all(
        "SELECT * FROM academy_review_actions WHERE review_id=? ORDER BY CASE WHEN status='open' THEN 0 ELSE 1 END,id",
        (review_id,),
    )


def _review_row(review_id: int) -> dict:
    row = fetch_one(
        """
        SELECT r.*,p.name AS player_name,p.batting_style,p.bowling_style,p.skill_level,
               c.first_name AS coach_first_name,c.last_name AS coach_last_name,
               s.session_date,s.start_time,s.session_kind,b.name AS batch_name,
               u.display_name AS created_by_name
        FROM academy_player_reviews r
        JOIN players p ON p.id=r.player_id
        LEFT JOIN coaches c ON c.id=r.coach_id
        LEFT JOIN academy_sessions s ON s.id=r.session_id
        LEFT JOIN batches b ON b.id=s.batch_id
        LEFT JOIN academy_users u ON u.id=r.created_by_user_id
        WHERE r.id=?
        """,
        (review_id,),
    )
    if not row:
        raise HTTPException(404, "Player review not found")
    row["coach_name"] = " ".join(
        value for value in [row.pop("coach_first_name", None), row.pop("coach_last_name", None)] if value
    ).strip() or None
    scores = [int(row[key]) for key in ("batting_score", "bowling_score", "fielding_score", "fitness_score")]
    row["overall_score"] = round(sum(scores) / len(scores), 2)
    row["actions"] = _review_actions(review_id)
    return row


def _validate_context(conn, payload: PlayerReviewPayload, user: dict) -> int | None:
    if not conn.execute("SELECT id FROM players WHERE id=?", (payload.player_id,)).fetchone():
        raise HTTPException(404, "Player not found")

    coach_id = payload.coach_id
    if user.get("role") == "coach":
        linked = user.get("coach_id")
        if not linked:
            raise HTTPException(409, "Coach access account must be linked to a coach record")
        if coach_id is not None and int(coach_id) != int(linked):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Coaches cannot submit a review as another coach")
        coach_id = int(linked)
    elif coach_id is None:
        raise HTTPException(422, "coach_id is required for owner or admin reviews")

    if coach_id is not None and not conn.execute("SELECT id FROM coaches WHERE id=?", (coach_id,)).fetchone():
        raise HTTPException(404, "Coach not found")

    if payload.session_id is not None:
        if not conn.execute("SELECT id FROM academy_sessions WHERE id=?", (payload.session_id,)).fetchone():
            raise HTTPException(404, "Session not found")
        if not conn.execute(
            "SELECT id FROM session_players WHERE session_id=? AND player_id=?",
            (payload.session_id, payload.player_id),
        ).fetchone():
            raise HTTPException(422, "Selected player was not on the selected session roster")

    for action in payload.actions:
        if action.target_date:
            _validate_date(action.target_date, "Action target date")
    return coach_id


def _replace_actions(conn, review_id: int, actions: list[ReviewActionPayload]) -> None:
    conn.execute("DELETE FROM academy_review_actions WHERE review_id=?", (review_id,))
    for action in actions:
        conn.execute(
            "INSERT INTO academy_review_actions(review_id,category,title,detail,target_date,status) VALUES(?,?,?,?,?,'open')",
            (review_id, action.category, action.title.strip(), _clean(action.detail), _clean(action.target_date)),
        )


def _write_review(conn, review_id: int | None, payload: PlayerReviewPayload, user: dict) -> int:
    _validate_date(payload.review_date, "Review date")
    coach_id = _validate_context(conn, payload, user)
    values = (
        payload.player_id, coach_id, payload.session_id, payload.review_date, payload.review_type,
        payload.period_label.strip(), payload.batting_score, payload.bowling_score,
        payload.fielding_score, payload.fitness_score, _clean(payload.batting_notes),
        _clean(payload.bowling_notes), _clean(payload.fielding_notes), _clean(payload.fitness_notes),
        _clean(payload.strengths), _clean(payload.focus_areas), payload.coach_summary.strip(), _clean(payload.next_steps),
    )
    if review_id is None:
        row = conn.execute(
            """
            INSERT INTO academy_player_reviews(
                academy_id,player_id,coach_id,session_id,created_by_user_id,review_date,review_type,period_label,status,
                batting_score,bowling_score,fielding_score,fitness_score,batting_notes,bowling_notes,fielding_notes,
                fitness_notes,strengths,focus_areas,coach_summary,next_steps
            ) VALUES(?,?,?,?,?,?,?,?, 'draft',?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (_academy_id(conn), values[0], values[1], values[2], int(user["id"]), *values[3:]),
        ).fetchone()
        review_id = int(row["id"])
    else:
        conn.execute(
            """
            UPDATE academy_player_reviews SET player_id=?,coach_id=?,session_id=?,review_date=?,review_type=?,period_label=?,
                batting_score=?,bowling_score=?,fielding_score=?,fitness_score=?,batting_notes=?,bowling_notes=?,fielding_notes=?,
                fitness_notes=?,strengths=?,focus_areas=?,coach_summary=?,next_steps=?,updated_at=CURRENT_TIMESTAMP WHERE id=?
            """,
            (*values, review_id),
        )
    _replace_actions(conn, review_id, payload.actions)
    return review_id


_ensure_tables()


@router.get("")
def list_reviews(player_id: int | None = None, review_status: ReviewStatus | None = None,
                 user: dict = Depends(current_access_user)):
    clauses: list[str] = []
    params: list[object] = []
    if player_id is not None:
        clauses.append("player_id=?")
        params.append(player_id)

    if _can_manage(user):
        if review_status:
            clauses.append("status=?")
            params.append(review_status)
    else:
        if "reviews.view" not in user.get("permissions", []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Review access is not allowed for this account")
        allowed = sorted(_family_player_ids(user))
        if not allowed:
            return []
        if player_id is not None and int(player_id) not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This player is not linked to your account")
        placeholders = ",".join("?" for _ in allowed)
        clauses.append(f"player_id IN ({placeholders})")
        params.extend(allowed)
        clauses.append("status='published'")

    sql = "SELECT id FROM academy_player_reviews"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY review_date DESC,id DESC"
    return [_review_row(int(row["id"])) for row in fetch_all(sql, params)]


@router.get("/reference")
def review_reference(user: dict = Depends(current_access_user)):
    _require_manage(user)
    if user.get("role") == "coach":
        coach_id = user.get("coach_id")
        if not coach_id:
            raise HTTPException(409, "Coach access account is not linked to a coach record")
        coaches = fetch_all("SELECT id,first_name,last_name,status FROM coaches WHERE id=?", (coach_id,))
    else:
        coaches = fetch_all("SELECT id,first_name,last_name,status FROM coaches WHERE status='active' ORDER BY last_name COLLATE NOCASE,first_name COLLATE NOCASE")
    return {
        "viewer": user,
        "players": fetch_all("SELECT id,name,status,skill_level FROM players WHERE status='active' ORDER BY name COLLATE NOCASE"),
        "coaches": coaches,
        "sessions": fetch_all(
            """
            SELECT s.id,s.session_date,s.start_time,s.session_kind,s.coach_id,b.name AS batch_name
            FROM academy_sessions s LEFT JOIN batches b ON b.id=s.batch_id
            WHERE s.status<>'cancelled' ORDER BY s.session_date DESC,s.start_time DESC LIMIT 250
            """
        ),
    }


@router.get("/trend/{player_id}")
def player_review_trend(player_id: int, user: dict = Depends(current_access_user)):
    if not _can_view_player(user, player_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This player review history is not available to your account")
    clauses = ["player_id=?"]
    params: list[object] = [player_id]
    if not _can_manage(user):
        clauses.append("status='published'")
    rows = fetch_all(
        f"SELECT id,review_date,period_label,status,batting_score,bowling_score,fielding_score,fitness_score FROM academy_player_reviews WHERE {' AND '.join(clauses)} ORDER BY review_date,id",
        params,
    )
    points = []
    for row in rows:
        scores = [int(row[key]) for key in ("batting_score", "bowling_score", "fielding_score", "fitness_score")]
        row["overall_score"] = round(sum(scores) / len(scores), 2)
        points.append(row)
    delta = round(float(points[-1]["overall_score"]) - float(points[0]["overall_score"]), 2) if len(points) >= 2 else None
    return {"player_id": player_id, "points": points, "overall_delta": delta}


@router.get("/{review_id}")
def get_review(review_id: int, user: dict = Depends(current_access_user)):
    row = _review_row(review_id)
    if not _can_view_player(user, int(row["player_id"])):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This review is not available to your account")
    if not _can_manage(user) and row.get("status") != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Player review not found")
    return row


@router.post("", status_code=201)
def create_review(payload: PlayerReviewPayload, user: dict = Depends(current_access_user)):
    _require_manage(user)
    with connection() as conn:
        review_id = _write_review(conn, None, payload, user)
        _audit(conn, "create_player_review", int(user["id"]), detail=f"review_id={review_id};player_id={payload.player_id}")
    return _review_row(review_id)


@router.put("/{review_id}")
def update_review(review_id: int, payload: PlayerReviewPayload, user: dict = Depends(current_access_user)):
    _require_manage(user)
    existing = _review_row(review_id)
    if existing.get("status") != "draft":
        raise HTTPException(409, "Published report cards are immutable; create a new review instead")
    if user.get("role") == "coach" and int(existing.get("created_by_user_id") or 0) != int(user["id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Coaches can edit only reviews they created")
    with connection() as conn:
        _write_review(conn, review_id, payload, user)
        _audit(conn, "update_player_review", int(user["id"]), detail=f"review_id={review_id}")
    return _review_row(review_id)


@router.post("/{review_id}/publish")
def publish_review(review_id: int, user: dict = Depends(current_access_user)):
    _require_manage(user)
    existing = _review_row(review_id)
    if existing.get("status") == "published":
        return existing
    if user.get("role") == "coach" and int(existing.get("created_by_user_id") or 0) != int(user["id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Coaches can publish only reviews they created")
    with connection() as conn:
        conn.execute("UPDATE academy_player_reviews SET status='published',published_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (review_id,))
        _audit(conn, "publish_player_review", int(user["id"]), detail=f"review_id={review_id};player_id={existing['player_id']}")
    return _review_row(review_id)


@router.put("/{review_id}/actions/{action_id}")
def update_action_status(review_id: int, action_id: int, payload: ActionStatusPayload,
                         user: dict = Depends(current_access_user)):
    _require_manage(user)
    review = _review_row(review_id)
    if user.get("role") == "coach" and review.get("coach_id") and int(review["coach_id"]) != int(user.get("coach_id") or 0):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action item belongs to another coach's review")
    with connection() as conn:
        if not conn.execute("SELECT id FROM academy_review_actions WHERE id=? AND review_id=?", (action_id, review_id)).fetchone():
            raise HTTPException(404, "Review action item not found")
        if payload.status == "completed":
            conn.execute("UPDATE academy_review_actions SET status='completed',completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (action_id,))
        else:
            conn.execute("UPDATE academy_review_actions SET status='open',completed_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?", (action_id,))
        _audit(conn, "update_review_action", int(user["id"]), detail=f"review_id={review_id};action_id={action_id};status={payload.status}")
    return _review_row(review_id)
