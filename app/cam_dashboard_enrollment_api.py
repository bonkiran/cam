from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from .cam_auth_api import current_access_user
from .database import fetch_all, fetch_one

router = APIRouter(prefix="/api/cam/dashboard", tags=["cam-dashboard-enrollments"])


def _academy_for_user(user: dict) -> dict | None:
    academy_id = int(user.get("academy_id") or 0)
    if academy_id:
        return fetch_one("SELECT * FROM academies WHERE id=?", (academy_id,))
    return fetch_one("SELECT * FROM academies ORDER BY id LIMIT 1")


def _academy_timezone(profile: dict | None) -> ZoneInfo:
    timezone_name = str((profile or {}).get("timezone") or "America/New_York")
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("America/New_York")


def _parse_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _monthly_enrollments(profile: dict | None, today: date) -> dict:
    timezone_value = _academy_timezone(profile)
    academy_id = int((profile or {}).get("id") or 0)
    params: tuple = ()
    academy_clause = ""
    if academy_id:
        academy_clause = "WHERE c.academy_id=?"
        params = (academy_id,)

    rows = fetch_all(
        f"""
        SELECT c.enrollment_id,c.completed_at,e.player_id,p.name AS player_name,
               (SELECT bp.id
                  FROM batch_players bp
                 WHERE bp.player_id=e.player_id AND bp.status IN ('active','waitlisted')
                 ORDER BY CASE WHEN bp.status='active' THEN 0 ELSE 1 END,bp.id DESC
                 LIMIT 1) AS batch_membership_id,
               (SELECT bp.batch_id
                  FROM batch_players bp
                 WHERE bp.player_id=e.player_id AND bp.status IN ('active','waitlisted')
                 ORDER BY CASE WHEN bp.status='active' THEN 0 ELSE 1 END,bp.id DESC
                 LIMIT 1) AS batch_id,
               (SELECT b.name
                  FROM batch_players bp JOIN batches b ON b.id=bp.batch_id
                 WHERE bp.player_id=e.player_id AND bp.status IN ('active','waitlisted')
                 ORDER BY CASE WHEN bp.status='active' THEN 0 ELSE 1 END,bp.id DESC
                 LIMIT 1) AS batch_name,
               (SELECT bp.status
                  FROM batch_players bp
                 WHERE bp.player_id=e.player_id AND bp.status IN ('active','waitlisted')
                 ORDER BY CASE WHEN bp.status='active' THEN 0 ELSE 1 END,bp.id DESC
                 LIMIT 1) AS batch_status,
               (SELECT bp.joined_on
                  FROM batch_players bp
                 WHERE bp.player_id=e.player_id AND bp.status IN ('active','waitlisted')
                 ORDER BY CASE WHEN bp.status='active' THEN 0 ELSE 1 END,bp.id DESC
                 LIMIT 1) AS batch_joined_on
        FROM academy_enrollment_completions c
        JOIN academy_enrollment_invites e ON e.id=c.enrollment_id
        LEFT JOIN players p ON p.id=e.player_id
        {academy_clause}
        ORDER BY c.completed_at DESC,c.enrollment_id DESC
        """,
        params,
    )

    players = []
    for row in rows:
        completed_at = _parse_timestamp(row.get("completed_at"))
        if completed_at is None:
            continue
        local_completed = completed_at.astimezone(timezone_value)
        if local_completed.year != today.year or local_completed.month != today.month:
            continue
        players.append(
            {
                "enrollment_id": int(row["enrollment_id"]),
                "player_id": int(row["player_id"]),
                "player_name": row.get("player_name") or f"Player {row['player_id']}",
                "enrolled_at": completed_at.isoformat(),
                "enrolled_date": local_completed.date().isoformat(),
                "batch_membership_id": int(row["batch_membership_id"]) if row.get("batch_membership_id") else None,
                "batch_id": int(row["batch_id"]) if row.get("batch_id") else None,
                "batch_name": row.get("batch_name"),
                "batch_status": row.get("batch_status"),
                "batch_joined_on": row.get("batch_joined_on"),
            }
        )

    return {
        "period": today.strftime("%Y-%m"),
        "period_label": today.strftime("%B %Y"),
        "count": len(players),
        "players": players,
    }


@router.get("/new-player-enrollments")
def new_player_enrollments(user: dict = Depends(current_access_user)):
    profile = _academy_for_user(user)
    timezone_value = _academy_timezone(profile)
    today = datetime.now(timezone_value).date()
    return _monthly_enrollments(profile, today)
