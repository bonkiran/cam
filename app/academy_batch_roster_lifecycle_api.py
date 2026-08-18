from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-batch-roster-lifecycle"])


class BatchPlayerPayload(BaseModel):
    player_id: int = Field(gt=0)
    waitlist_if_full: bool = False
    joined_on: str | None = Field(default=None, max_length=20)


class MembershipLifecyclePayload(BaseModel):
    effective_date: str | None = Field(default=None, max_length=20)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _date(value: str | None, label: str) -> date:
    if not value:
        return date.today()
    try:
        parsed = date.fromisoformat(value)
    except Exception as exc:
        raise HTTPException(422, f"{label} must be YYYY-MM-DD") from exc
    if parsed > date.today():
        raise HTTPException(422, f"{label} cannot be in the future for an immediate roster change")
    return parsed


def _batch_row(conn, batch_id: int):
    row = conn.execute("SELECT id,capacity,status FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Batch not found")
    return row


def _membership_row(conn, batch_id: int, membership_id: int):
    row = conn.execute(
        """
        SELECT bp.*,p.name AS player_name,p.status AS player_status
        FROM batch_players bp JOIN players p ON p.id=bp.player_id
        WHERE bp.batch_id=? AND bp.id=?
        """,
        (batch_id, membership_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Batch membership not found")
    return row


def _membership_detail(membership_id: int) -> dict:
    row = fetch_one(
        """
        SELECT bp.*,p.name AS player_name,p.status AS player_status,b.name AS batch_name
        FROM batch_players bp
        JOIN players p ON p.id=bp.player_id
        JOIN batches b ON b.id=bp.batch_id
        WHERE bp.id=?
        """,
        (membership_id,),
    )
    if not row:
        raise HTTPException(404, "Batch membership not found")
    return row


def _future_sync_start(requested: date) -> str:
    # Historical session rosters are immutable. Even when a membership has a
    # back-dated joined/ended date, only today and future scheduled sessions are
    # synchronized by a roster lifecycle action.
    return max(requested, date.today()).isoformat()


def _sync_future_session_roster(conn, *, batch_id: int, player_id: int, effective_date: date, include: bool) -> int:
    session_rows = conn.execute(
        """
        SELECT id FROM academy_sessions
        WHERE batch_id=? AND status='scheduled' AND session_date>=?
        ORDER BY session_date,start_time,id
        """,
        (batch_id, _future_sync_start(effective_date)),
    ).fetchall()
    changed = 0
    for session in session_rows:
        session_id = int(session["id"])
        current = conn.execute(
            "SELECT id FROM session_players WHERE session_id=? AND player_id=?",
            (session_id, player_id),
        ).fetchone()
        if include and not current:
            conn.execute(
                "INSERT INTO session_players(session_id,player_id,participation_type) VALUES(?,?,'roster')",
                (session_id, player_id),
            )
            changed += 1
        elif not include and current:
            conn.execute("DELETE FROM session_players WHERE id=?", (int(current["id"]),))
            changed += 1
    return changed


@router.post("/batches/{batch_id}/players", status_code=201)
def add_batch_player_with_future_sync(batch_id: int, payload: BatchPlayerPayload):
    """Add a roster/waitlist membership and keep future generated sessions coherent.

    This intentionally replaces the original add-member handler at app assembly
    time. Existing API shape is preserved, while active members added after
    sessions have already been generated are inserted into future scheduled
    batch-session rosters.
    """
    joined = _date(payload.joined_on, "Joined on") if payload.joined_on else date.today()
    with connection() as conn:
        batch = _batch_row(conn, batch_id)
        if str(batch["status"] or "active") != "active":
            raise HTTPException(409, "Players can only be added to an active batch")
        player = conn.execute("SELECT id,status FROM players WHERE id=?", (payload.player_id,)).fetchone()
        if not player:
            raise HTTPException(404, "Player not found")
        if str(player["status"] or "active") != "active":
            raise HTTPException(409, "Only active players can be added to a batch")
        current = conn.execute(
            "SELECT id FROM batch_players WHERE batch_id=? AND player_id=? AND status IN ('active','waitlisted')",
            (batch_id, payload.player_id),
        ).fetchone()
        if current:
            raise HTTPException(409, "Player already has a current batch membership")

        active_count = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM batch_players WHERE batch_id=? AND status='active'",
                (batch_id,),
            ).fetchone()["count"]
        )
        if active_count >= int(batch["capacity"]):
            if not payload.waitlist_if_full:
                raise HTTPException(409, "Batch is at capacity")
            membership_status = "waitlisted"
        else:
            membership_status = "active"

        row = conn.execute(
            "INSERT INTO batch_players(batch_id,player_id,status,joined_on) VALUES(?,?,?,?) RETURNING id",
            (batch_id, payload.player_id, membership_status, _clean(payload.joined_on) or joined.isoformat()),
        ).fetchone()
        membership_id = int(row["id"])
        if membership_status == "active":
            _sync_future_session_roster(
                conn,
                batch_id=batch_id,
                player_id=payload.player_id,
                effective_date=joined,
                include=True,
            )
    return _membership_detail(membership_id)


@router.post("/batches/{batch_id}/players/{membership_id}/end")
def end_batch_membership(batch_id: int, membership_id: int, payload: MembershipLifecyclePayload):
    effective = _date(payload.effective_date, "Effective date")
    with connection() as conn:
        _batch_row(conn, batch_id)
        membership = _membership_row(conn, batch_id, membership_id)
        if str(membership["status"]) not in {"active", "waitlisted"}:
            raise HTTPException(409, "Batch membership is already inactive")

        prior_status = str(membership["status"])
        conn.execute(
            "UPDATE batch_players SET status='inactive',ended_on=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (effective.isoformat(), membership_id),
        )
        if prior_status == "active":
            _sync_future_session_roster(
                conn,
                batch_id=batch_id,
                player_id=int(membership["player_id"]),
                effective_date=effective,
                include=False,
            )
    return _membership_detail(membership_id)


@router.post("/batches/{batch_id}/players/{membership_id}/promote")
def promote_waitlisted_member(batch_id: int, membership_id: int, payload: MembershipLifecyclePayload):
    effective = _date(payload.effective_date, "Effective date")
    with connection() as conn:
        batch = _batch_row(conn, batch_id)
        if str(batch["status"] or "active") != "active":
            raise HTTPException(409, "Waitlisted players can only be promoted into an active batch")
        membership = _membership_row(conn, batch_id, membership_id)
        if str(membership["status"]) != "waitlisted":
            raise HTTPException(409, "Only a waitlisted membership can be promoted")
        if str(membership["player_status"] or "active") != "active":
            raise HTTPException(409, "Only an active player can be promoted from the waitlist")

        active_count = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM batch_players WHERE batch_id=? AND status='active'",
                (batch_id,),
            ).fetchone()["count"]
        )
        if active_count >= int(batch["capacity"]):
            raise HTTPException(409, "Batch is still at capacity")

        conn.execute(
            "UPDATE batch_players SET status='active',ended_on=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (membership_id,),
        )
        _sync_future_session_roster(
            conn,
            batch_id=batch_id,
            player_id=int(membership["player_id"]),
            effective_date=effective,
            include=True,
        )
    return _membership_detail(membership_id)
