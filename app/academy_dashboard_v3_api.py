from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from .academy_auth_api import current_access_user
from .database import fetch_all, fetch_one

router = APIRouter(prefix="/api/academy/dashboard", tags=["academy-dashboard-v3"])
logger = logging.getLogger(__name__)

PROGRAM_BUCKETS = ("Beginners", "U11", "U13", "U14", "U15")


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


def _local_today(profile: dict | None) -> date:
    return datetime.now(_academy_timezone(profile)).date()


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


def _month_bounds(today: date) -> tuple[str, str]:
    start = today.replace(day=1)
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start.isoformat(), end.isoformat()


def _program_bucket(name: object, code: object = None, age_group: object = None) -> str | None:
    haystack = " ".join(str(value or "") for value in (name, code, age_group)).lower().replace("-", " ")
    compact = "".join(ch for ch in haystack if ch.isalnum())
    if "beginner" in haystack:
        return "Beginners"
    for bucket, markers in {
        "U11": ("u11", "under11", "under 11"),
        "U13": ("u13", "under13", "under 13"),
        "U14": ("u14", "under14", "under 14"),
        "U15": ("u15", "under15", "under 15"),
    }.items():
        if any(marker.replace(" ", "") in compact or marker in haystack for marker in markers):
            return bucket
    return None


def _program_counts() -> dict:
    buckets: dict[str, set[int]] = {name: set() for name in PROGRAM_BUCKETS}
    rows = fetch_all(
        """
        SELECT e.player_id,p.name,p.code,p.age_group
        FROM enrollments e
        JOIN programs p ON p.id=e.program_id
        WHERE e.status IN ('active','frozen') AND p.status='active'
        """
    )
    for row in rows:
        bucket = _program_bucket(row.get("name"), row.get("code"), row.get("age_group"))
        if bucket:
            buckets[bucket].add(int(row["player_id"]))
    total = fetch_one("SELECT COUNT(*) AS count FROM players WHERE COALESCE(status,'active')='active'") or {"count": 0}
    return {
        "buckets": {name: len(buckets[name]) for name in PROGRAM_BUCKETS},
        "total_players": int(total.get("count") or 0),
    }


def _new_enrollments(profile: dict | None, today: date) -> dict:
    timezone_value = _academy_timezone(profile)
    academy_id = int((profile or {}).get("id") or 0)
    clause = "WHERE c.academy_id=?" if academy_id else ""
    params: tuple[object, ...] = (academy_id,) if academy_id else ()
    rows = fetch_all(
        f"""
        SELECT c.enrollment_id,c.completed_at,e.player_id,e.parent_first_name,e.parent_last_name,p.name AS player_name,
               (SELECT bp.batch_id FROM batch_players bp
                 WHERE bp.player_id=e.player_id AND bp.status IN ('active','waitlisted')
                 ORDER BY CASE WHEN bp.status='active' THEN 0 ELSE 1 END,bp.id DESC LIMIT 1) AS batch_id,
               (SELECT b.name FROM batch_players bp JOIN batches b ON b.id=bp.batch_id
                 WHERE bp.player_id=e.player_id AND bp.status IN ('active','waitlisted')
                 ORDER BY CASE WHEN bp.status='active' THEN 0 ELSE 1 END,bp.id DESC LIMIT 1) AS batch_name,
               (SELECT bp.status FROM batch_players bp
                 WHERE bp.player_id=e.player_id AND bp.status IN ('active','waitlisted')
                 ORDER BY CASE WHEN bp.status='active' THEN 0 ELSE 1 END,bp.id DESC LIMIT 1) AS batch_status
        FROM academy_enrollment_completions c
        JOIN academy_enrollment_invites e ON e.id=c.enrollment_id
        LEFT JOIN players p ON p.id=e.player_id
        {clause}
        ORDER BY c.completed_at DESC,c.enrollment_id DESC
        """,
        params,
    )
    players = []
    for row in rows:
        completed = _parse_timestamp(row.get("completed_at"))
        if not completed:
            continue
        local = completed.astimezone(timezone_value)
        if local.year != today.year or local.month != today.month:
            continue
        parent_name = " ".join(
            part for part in [str(row.get("parent_first_name") or "").strip(), str(row.get("parent_last_name") or "").strip()] if part
        ) or "Parent / Guardian"
        players.append(
            {
                "enrollment_id": int(row["enrollment_id"]),
                "player_id": int(row["player_id"]),
                "player_name": row.get("player_name") or f"Player {row['player_id']}",
                "parent_name": parent_name,
                "enrolled_date": local.date().isoformat(),
                "batch_id": int(row["batch_id"]) if row.get("batch_id") else None,
                "batch_name": row.get("batch_name"),
                "batch_status": row.get("batch_status"),
            }
        )
    return {"count": len(players), "players": players}


def _registration_tracker(profile: dict | None, today: date) -> dict:
    timezone_value = _academy_timezone(profile)
    academy_id = int((profile or {}).get("id") or 0)
    clause = "WHERE i.academy_id=?" if academy_id else ""
    params: tuple[object, ...] = (academy_id,) if academy_id else ()
    rows = fetch_all(
        f"""
        SELECT i.id,i.parent_first_name,i.parent_last_name,i.sent_by_name,i.status,i.sent_at,i.last_activity_at,i.created_at,
               a.player_first_name,a.player_last_name,a.id AS application_id
        FROM academy_registration_invites i
        LEFT JOIN academy_registration_applications a ON a.invite_id=i.id
        {clause}
        ORDER BY COALESCE(
            CAST(i.last_activity_at AS TEXT),
            CAST(i.sent_at AS TEXT),
            CAST(i.created_at AS TEXT)
        ) DESC,i.id DESC
        """,
        params,
    )
    sent_count = 0
    current_month_rows = []
    for row in rows:
        sent_at = _parse_timestamp(row.get("sent_at"))
        activity_at = _parse_timestamp(row.get("last_activity_at") or row.get("sent_at") or row.get("created_at"))
        if sent_at:
            local_sent = sent_at.astimezone(timezone_value)
            if local_sent.year == today.year and local_sent.month == today.month:
                sent_count += 1
        if activity_at:
            local_activity = activity_at.astimezone(timezone_value)
            if local_activity.year != today.year or local_activity.month != today.month:
                continue
        parent_name = " ".join(
            part for part in [str(row.get("parent_first_name") or "").strip(), str(row.get("parent_last_name") or "").strip()] if part
        ) or "Parent / Guardian"
        player_name = " ".join(
            part for part in [str(row.get("player_first_name") or "").strip(), str(row.get("player_last_name") or "").strip()] if part
        ) or "Pending player details"
        current_month_rows.append(
            {
                "invite_id": int(row["id"]),
                "application_id": int(row["application_id"]) if row.get("application_id") else None,
                "parent_name": parent_name,
                "sent_by": row.get("sent_by_name") or "Academy Staff",
                "sent_at": sent_at.isoformat() if sent_at else None,
                "activity_at": activity_at.isoformat() if activity_at else None,
                "status": row.get("status") or "created",
                "player_name": player_name,
            }
        )
    return {
        "links_sent_count": sent_count,
        "tracker_count": len(current_month_rows),
        "rows": current_month_rows[:8],
    }


def _session_row(row: dict) -> dict:
    coach_name = " ".join(
        part for part in [str(row.get("coach_first_name") or "").strip(), str(row.get("coach_last_name") or "").strip()] if part
    ) or "Coach not assigned"
    return {
        "id": int(row["id"]),
        "session_kind": row.get("session_kind") or "batch",
        "session_date": row.get("session_date"),
        "start_time": row.get("start_time"),
        "duration_minutes": int(row.get("duration_minutes") or 0),
        "batch_name": row.get("batch_name"),
        "player_name": row.get("private_player_name"),
        "coach_name": coach_name,
        "location": row.get("location") or "Location not set",
        "resource": row.get("resource"),
        "player_count": int(row.get("player_count") or 0),
    }


def _today_sessions(today: date) -> dict:
    rows = fetch_all(
        """
        SELECT s.*,b.name AS batch_name,c.first_name AS coach_first_name,c.last_name AS coach_last_name,
               (SELECT COUNT(*) FROM session_players sp WHERE sp.session_id=s.id) AS player_count,
               (SELECT p.name FROM session_players sp JOIN players p ON p.id=sp.player_id
                 WHERE sp.session_id=s.id ORDER BY sp.id LIMIT 1) AS private_player_name
        FROM academy_sessions s
        LEFT JOIN batches b ON b.id=s.batch_id
        LEFT JOIN coaches c ON c.id=s.coach_id
        WHERE s.session_date=? AND s.status<>'cancelled'
        ORDER BY s.start_time,s.id
        """,
        (today.isoformat(),),
    )
    group, private = [], []
    for row in rows:
        item = _session_row(row)
        (private if str(item["session_kind"]) == "private" else group).append(item)
    return {"group": group, "private": private, "count": len(group) + len(private)}


def _fee_receipts(today: date) -> dict:
    start, end = _month_bounds(today)
    group_item_count = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM academy_invoice_items ii
        LEFT JOIN academy_fee_plans fp ON fp.id=ii.fee_plan_id
        LEFT JOIN programs pr ON pr.id=fp.program_id
        WHERE COALESCE(pr.program_type,'group')='group'
          AND COALESCE(fp.billing_frequency,'monthly') IN ('monthly','session')
        """
    ) or {"count": 0}
    group_scoped = int(group_item_count.get("count") or 0) > 0
    if group_scoped:
        received = fetch_one(
            """
            SELECT COALESCE(SUM(pa.amount_cents-pa.refunded_cents),0) AS total
            FROM academy_payment_allocations pa
            JOIN academy_payments p ON p.id=pa.payment_id
            WHERE p.status='posted' AND p.received_on>=? AND p.received_on<?
              AND EXISTS (
                SELECT 1 FROM academy_invoice_items ii
                LEFT JOIN academy_fee_plans fp ON fp.id=ii.fee_plan_id
                LEFT JOIN programs pr ON pr.id=fp.program_id
                WHERE ii.invoice_id=pa.invoice_id
                  AND COALESCE(pr.program_type,'group')='group'
                  AND COALESCE(fp.billing_frequency,'monthly') IN ('monthly','session')
              )
            """,
            (start, end),
        ) or {"total": 0}
        invoices = fetch_all(
            """
            SELECT i.total_cents,i.amount_paid_cents,i.credit_applied_cents
            FROM academy_invoices i
            WHERE i.status<>'void' AND i.issue_date>=? AND i.issue_date<?
              AND EXISTS (
                SELECT 1 FROM academy_invoice_items ii
                LEFT JOIN academy_fee_plans fp ON fp.id=ii.fee_plan_id
                LEFT JOIN programs pr ON pr.id=fp.program_id
                WHERE ii.invoice_id=i.id
                  AND COALESCE(pr.program_type,'group')='group'
                  AND COALESCE(fp.billing_frequency,'monthly') IN ('monthly','session')
              )
            """,
            (start, end),
        )
    else:
        received = fetch_one(
            """SELECT COALESCE(SUM(amount_cents-refunded_cents),0) AS total FROM academy_payments
               WHERE status='posted' AND received_on>=? AND received_on<?""",
            (start, end),
        ) or {"total": 0}
        invoices = fetch_all(
            """SELECT total_cents,amount_paid_cents,credit_applied_cents FROM academy_invoices
               WHERE status<>'void' AND issue_date>=? AND issue_date<?""",
            (start, end),
        )
    pending = sum(
        max(0, int(row.get("total_cents") or 0) - int(row.get("amount_paid_cents") or 0) - int(row.get("credit_applied_cents") or 0))
        for row in invoices
    )
    return {
        "group_session_fee_received_cents": int(received.get("total") or 0),
        "group_session_fee_pending_cents": pending,
        "scope": "group_fee_plans" if group_scoped else "academy_fee_fallback",
    }


def _academy_payments(today: date) -> dict:
    start, end = _month_bounds(today)
    coach = fetch_one(
        "SELECT COALESCE(SUM(amount_cents),0) AS total FROM academy_coach_payments WHERE status='paid' AND paid_on>=? AND paid_on<?",
        (start, end),
    ) or {"total": 0}
    facility = fetch_one(
        "SELECT COALESCE(SUM(amount_cents),0) AS total FROM academy_expenses WHERE expense_type='facility' AND status='paid' AND expense_date>=? AND expense_date<?",
        (start, end),
    ) or {"total": 0}
    academy = fetch_one(
        "SELECT COALESCE(SUM(amount_cents),0) AS total FROM academy_expenses WHERE expense_type='academy' AND status='paid' AND expense_date>=? AND expense_date<?",
        (start, end),
    ) or {"total": 0}
    return {
        "coach_salary_payments_cents": int(coach.get("total") or 0),
        "facility_payments_cents": int(facility.get("total") or 0),
        "academy_expenses_cents": int(academy.get("total") or 0),
    }


def _upcoming_events(today: date) -> dict:
    end = (today + timedelta(days=45)).isoformat()
    today_iso = today.isoformat()
    matches = fetch_all(
        """
        SELECT m.id,m.match_date,m.start_time,m.venue,m.opponent,m.competition,t.name AS team_name
        FROM academy_matches m JOIN academy_teams t ON t.id=m.team_id
        WHERE m.status='scheduled' AND m.match_date>=? AND m.match_date<=?
        ORDER BY m.match_date,m.start_time,m.id LIMIT 6
        """,
        (today_iso, end),
    )
    programs = fetch_all(
        """
        SELECT p.id,p.name,p.program_type,p.start_date,p.end_date,
               (SELECT b.location FROM batches b WHERE b.program_id=p.id AND b.status='active' ORDER BY b.id LIMIT 1) AS location,
               (SELECT s.start_time FROM academy_sessions s JOIN batches b ON b.id=s.batch_id
                 WHERE b.program_id=p.id AND s.status<>'cancelled' AND s.session_date>=?
                 ORDER BY s.session_date,s.start_time,s.id LIMIT 1) AS start_time
        FROM programs p
        WHERE p.status='active' AND p.program_type IN ('camp','clinic','other')
          AND COALESCE(p.end_date,p.start_date,?)>=?
        ORDER BY COALESCE(p.start_date,?),p.id LIMIT 6
        """,
        (today_iso, today_iso, today_iso, today_iso),
    )
    tournaments = fetch_all(
        """
        SELECT id,name,start_date,end_date,location,status,tournament_type
        FROM academy_tournaments
        WHERE status IN ('planned','open') AND end_date>=?
        ORDER BY start_date,id LIMIT 6
        """,
        (today_iso,),
    )
    return {"matches": matches, "programs": programs, "tournaments": tournaments}


def _attendance_by_batch(today: date) -> dict:
    latest = fetch_one(
        """SELECT MAX(session_date) AS session_date FROM academy_sessions
           WHERE session_kind<>'private' AND status<>'cancelled' AND session_date<=?""",
        (today.isoformat(),),
    ) or {}
    attendance_date = latest.get("session_date")
    if not attendance_date:
        return {"date": None, "latest_time": None, "total_scheduled": 0, "batches": []}
    sessions = fetch_all(
        """
        SELECT s.id,s.start_time,COALESCE(b.name,'Group Session') AS batch_name
        FROM academy_sessions s LEFT JOIN batches b ON b.id=s.batch_id
        WHERE s.session_date=? AND s.session_kind<>'private' AND s.status<>'cancelled'
        ORDER BY s.start_time,s.id
        """,
        (attendance_date,),
    )
    by_batch: dict[str, dict] = {}
    latest_time = None
    for session in sessions:
        latest_time = max(str(latest_time or ""), str(session.get("start_time") or "")) or latest_time
        roster = fetch_all(
            """
            SELECT a.status AS attendance_status
            FROM session_players sp
            LEFT JOIN player_attendance a ON a.session_id=sp.session_id AND a.player_id=sp.player_id
            WHERE sp.session_id=?
            """,
            (int(session["id"]),),
        )
        name = str(session.get("batch_name") or "Group Session")
        bucket = by_batch.setdefault(name, {"batch": name, "scheduled": 0, "present": 0, "late": 0, "absent": 0, "not_recorded": 0})
        for player in roster:
            bucket["scheduled"] += 1
            status = str(player.get("attendance_status") or "not_recorded")
            if status == "present":
                bucket["present"] += 1
            elif status == "late":
                bucket["late"] += 1
            elif status == "absent":
                bucket["absent"] += 1
            else:
                # Excused is intentionally not a dashboard column. It remains
                # part of the scheduled denominator and is grouped with other
                # non-attendance states for the completion percentage.
                bucket["not_recorded"] += 1
    batches = []
    for value in by_batch.values():
        attended = int(value["present"]) + int(value["late"])
        scheduled = int(value["scheduled"])
        value["attended"] = attended
        value["attendance_percent"] = round(attended * 100 / scheduled, 1) if scheduled else 0.0
        batches.append(value)
    return {
        "date": attendance_date,
        "latest_time": latest_time,
        "total_scheduled": sum(int(row["scheduled"]) for row in batches),
        "batches": batches,
    }


def _safe_section(name: str, fallback: dict, loader) -> tuple[dict, str | None]:
    """Return one dashboard section without allowing a single query to blank the whole page."""
    try:
        return loader(), None
    except Exception:
        logger.exception("Academy Dashboard v3 section failed: %s", name)
        return fallback, name


@router.get("/v3")
def academy_dashboard_v3(user: dict = Depends(current_access_user)):
    profile = _academy_for_user(user)
    today = _local_today(profile)
    academy_name = str((profile or {}).get("name") or "CAM Academy")

    warnings: list[str] = []

    def load(name: str, fallback: dict, loader) -> dict:
        value, warning = _safe_section(name, fallback, loader)
        if warning:
            warnings.append(warning)
        return value

    program_counts = load(
        "program_counts",
        {"buckets": {name: 0 for name in PROGRAM_BUCKETS}, "total_players": 0},
        _program_counts,
    )
    new_enrollments = load(
        "new_enrollments",
        {"count": 0, "players": []},
        lambda: _new_enrollments(profile, today),
    )
    registration_tracker = load(
        "registration_tracker",
        {"links_sent_count": 0, "tracker_count": 0, "rows": []},
        lambda: _registration_tracker(profile, today),
    )
    sessions = load(
        "sessions",
        {"group": [], "private": [], "count": 0},
        lambda: _today_sessions(today),
    )
    receipts = load(
        "receipts",
        {"group_session_fee_received_cents": 0, "group_session_fee_pending_cents": 0, "scope": "unavailable"},
        lambda: _fee_receipts(today),
    )
    payments = load(
        "payments",
        {"coach_salary_payments_cents": 0, "facility_payments_cents": 0, "academy_expenses_cents": 0},
        lambda: _academy_payments(today),
    )
    events = load(
        "events",
        {"matches": [], "programs": [], "tournaments": []},
        lambda: _upcoming_events(today),
    )
    attendance = load(
        "attendance",
        {"date": None, "latest_time": None, "total_scheduled": 0, "batches": []},
        lambda: _attendance_by_batch(today),
    )

    return {
        "user": {
            "id": int(user.get("id") or 0),
            "display_name": user.get("display_name") or "Admin",
            "role": user.get("role") or "admin",
        },
        "academy": {
            "id": int((profile or {}).get("id") or 0) or None,
            "name": academy_name,
            "city": (profile or {}).get("city"),
            "state": (profile or {}).get("state"),
            "postal_code": (profile or {}).get("postal_code"),
            "country": (profile or {}).get("country"),
            "timezone": str((profile or {}).get("timezone") or "America/New_York"),
        },
        "as_of": today.isoformat(),
        "month_label": today.strftime("%B %Y"),
        "program_counts": program_counts,
        "new_enrollments": new_enrollments,
        "registration_tracker": registration_tracker,
        "sessions": sessions,
        "receipts": receipts,
        "payments": payments,
        "events": events,
        "attendance": attendance,
        "degraded_sections": warnings,
    }
