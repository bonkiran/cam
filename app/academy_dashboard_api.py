from __future__ import annotations

import gzip
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .academy_auth_api import current_access_user, require_access_admin
from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-dashboard"])

WEATHER_API_KEY = os.environ.get("WEATHER_COM_API_KEY", "").strip()
_WEATHER_CACHE_SECONDS = 15 * 60
_weather_cache: dict[str, tuple[float, dict]] = {}
_weather_lock = threading.Lock()


class MatchConfirmationPayload(BaseModel):
    status: Literal["awaiting", "confirmed", "declined"]


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_match_confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'awaiting',
            responded_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(match_id) REFERENCES academy_matches(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            UNIQUE(match_id, player_id)
        );
        CREATE INDEX IF NOT EXISTS idx_match_confirmations_match ON academy_match_confirmations(match_id);
        CREATE INDEX IF NOT EXISTS idx_match_confirmations_player ON academy_match_confirmations(player_id);
        CREATE INDEX IF NOT EXISTS idx_match_confirmations_status ON academy_match_confirmations(status);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy() -> dict | None:
    return fetch_one("SELECT * FROM academies ORDER BY id LIMIT 1")


def _local_today(profile: dict | None) -> date:
    timezone_name = str((profile or {}).get("timezone") or "America/New_York")
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:
        timezone = ZoneInfo("America/New_York")
    return datetime.now(timezone).date()


def _money_metrics(today: date) -> dict:
    month_start = today.replace(day=1).isoformat()
    today_iso = today.isoformat()
    payment_rows = fetch_all(
        """
        SELECT amount_cents,refunded_cents,status,received_on
        FROM academy_payments
        WHERE received_on>=? AND received_on<=?
        """,
        (month_start, today_iso),
    )
    received = sum(
        max(0, int(row.get("amount_cents") or 0) - int(row.get("refunded_cents") or 0))
        for row in payment_rows
        if str(row.get("status") or "posted") == "posted"
    )

    pending = 0
    late = 0
    invoices = fetch_all(
        """
        SELECT due_date,status,total_cents,amount_paid_cents,credit_applied_cents
        FROM academy_invoices
        WHERE status<>'void'
        """
    )
    for invoice in invoices:
        balance = max(
            0,
            int(invoice.get("total_cents") or 0)
            - int(invoice.get("amount_paid_cents") or 0)
            - int(invoice.get("credit_applied_cents") or 0),
        )
        if balance <= 0:
            continue
        if str(invoice.get("due_date") or "") < today_iso:
            late += balance
        else:
            pending += balance
    return {
        "fee_received_mtd_cents": received,
        "fee_pending_cents": pending,
        "fee_late_cents": late,
    }


def _session_row(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "session_kind": row.get("session_kind") or "batch",
        "session_date": row.get("session_date"),
        "start_time": row.get("start_time"),
        "duration_minutes": int(row.get("duration_minutes") or 0),
        "batch_name": row.get("batch_name"),
        "coach_name": " ".join(
            value for value in [row.get("coach_first_name"), row.get("coach_last_name")] if value
        ).strip() or None,
        "location": row.get("location"),
        "resource": row.get("resource"),
        "player_count": int(row.get("player_count") or 0),
        "status": row.get("status"),
    }


def _today_sessions(today: date) -> dict:
    rows = fetch_all(
        """
        SELECT s.*,b.name AS batch_name,c.first_name AS coach_first_name,c.last_name AS coach_last_name,
               (SELECT COUNT(*) FROM session_players sp WHERE sp.session_id=s.id) AS player_count
        FROM academy_sessions s
        LEFT JOIN batches b ON b.id=s.batch_id
        LEFT JOIN coaches c ON c.id=s.coach_id
        WHERE s.session_date=? AND s.status<>'cancelled'
        ORDER BY s.start_time,s.id
        """,
        (today.isoformat(),),
    )
    group_sessions = []
    private_sessions = []
    for row in rows:
        item = _session_row(row)
        if str(item["session_kind"]) == "private":
            private_sessions.append(item)
        else:
            group_sessions.append(item)
    return {"group": group_sessions, "private": private_sessions}


def _yesterday_attendance(today: date) -> dict:
    yesterday = today - timedelta(days=1)
    sessions = fetch_all(
        """
        SELECT s.id,s.session_date,s.start_time,s.session_kind,s.status,b.name AS batch_name,
               c.first_name AS coach_first_name,c.last_name AS coach_last_name
        FROM academy_sessions s
        LEFT JOIN batches b ON b.id=s.batch_id
        LEFT JOIN coaches c ON c.id=s.coach_id
        WHERE s.session_date=? AND s.status<>'cancelled'
        ORDER BY s.start_time,s.id
        """,
        (yesterday.isoformat(),),
    )
    summaries = []
    for session in sessions:
        roster = fetch_all(
            """
            SELECT sp.player_id,a.status AS attendance_status
            FROM session_players sp
            LEFT JOIN player_attendance a ON a.session_id=sp.session_id AND a.player_id=sp.player_id
            WHERE sp.session_id=?
            """,
            (int(session["id"]),),
        )
        counts = {"present": 0, "late": 0, "absent": 0, "excused": 0, "not_recorded": 0}
        for player in roster:
            status = str(player.get("attendance_status") or "not_recorded")
            if status not in counts:
                status = "not_recorded"
            counts[status] += 1
        coach = fetch_one(
            "SELECT status FROM coach_attendance WHERE session_id=?",
            (int(session["id"]),),
        )
        summaries.append(
            {
                "session_id": int(session["id"]),
                "session_date": session.get("session_date"),
                "start_time": session.get("start_time"),
                "session_kind": session.get("session_kind") or "batch",
                "label": session.get("batch_name") or "1-to-1 Session",
                "coach_name": " ".join(
                    value for value in [session.get("coach_first_name"), session.get("coach_last_name")] if value
                ).strip() or None,
                "roster_count": len(roster),
                **counts,
                "coach_status": coach.get("status") if coach else None,
            }
        )
    return {"date": yesterday.isoformat(), "sessions": summaries}


def _confirmation_summary(match_id: int) -> dict:
    squad = fetch_all("SELECT player_id FROM academy_match_squad WHERE match_id=?", (match_id,))
    squad_ids = {int(row["player_id"]) for row in squad}
    responses = fetch_all(
        "SELECT player_id,status FROM academy_match_confirmations WHERE match_id=?",
        (match_id,),
    )
    confirmed = 0
    declined = 0
    for response in responses:
        if int(response["player_id"]) not in squad_ids:
            continue
        if response.get("status") == "confirmed":
            confirmed += 1
        elif response.get("status") == "declined":
            declined += 1
    awaiting = max(0, len(squad_ids) - confirmed - declined)
    return {
        "squad_count": len(squad_ids),
        "confirmed": confirmed,
        "declined": declined,
        "awaiting": awaiting,
    }


def _upcoming_matches(today: date) -> list[dict]:
    end = today + timedelta(days=7)
    rows = fetch_all(
        """
        SELECT m.*,t.name AS team_name
        FROM academy_matches m
        JOIN academy_teams t ON t.id=m.team_id
        WHERE m.match_date>=? AND m.match_date<=? AND m.status='scheduled'
        ORDER BY m.match_date,m.start_time,m.id
        """,
        (today.isoformat(), end.isoformat()),
    )
    result = []
    for row in rows:
        result.append(
            {
                "id": int(row["id"]),
                "team_name": row.get("team_name"),
                "opponent": row.get("opponent"),
                "match_date": row.get("match_date"),
                "start_time": row.get("start_time"),
                "venue": row.get("venue"),
                "competition": row.get("competition"),
                "match_format": row.get("match_format"),
                **_confirmation_summary(int(row["id"])),
            }
        )
    return result


def _country_code(country: str | None) -> str | None:
    value = (country or "").strip()
    aliases = {
        "united states": "US",
        "united states of america": "US",
        "usa": "US",
        "us": "US",
        "canada": "CA",
        "ca": "CA",
        "india": "IN",
        "in": "IN",
        "united kingdom": "GB",
        "uk": "GB",
        "gb": "GB",
    }
    if value.lower() in aliases:
        return aliases[value.lower()]
    if len(value) == 2 and value.isalpha():
        return value.upper()
    return None


def _weather_request(postal_key: str) -> dict:
    now = time.monotonic()
    with _weather_lock:
        cached = _weather_cache.get(postal_key)
        if cached and now - cached[0] < _WEATHER_CACHE_SECONDS:
            return cached[1]

    query = urllib.parse.urlencode(
        {
            "postalKey": postal_key,
            "units": "e",
            "language": "en-US",
            "format": "json",
            "apiKey": WEATHER_API_KEY,
        }
    )
    request = urllib.request.Request(
        f"https://api.weather.com/v3/wx/forecast/daily/7day?{query}",
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "CAM-Academy-Dashboard/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read()
        if str(response.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
    with _weather_lock:
        _weather_cache[postal_key] = (now, payload)
    return payload


def _weekend_weather(profile: dict | None, today: date) -> dict:
    weekend_dates = [today + timedelta(days=i) for i in range(7) if (today + timedelta(days=i)).weekday() in (5, 6)]
    if not WEATHER_API_KEY:
        return {
            "provider": "The Weather Company / weather.com",
            "configured": False,
            "status": "api_key_required",
            "days": [],
        }
    postal_code = str((profile or {}).get("postal_code") or "").strip()
    country_code = _country_code((profile or {}).get("country"))
    if not postal_code or not country_code:
        return {
            "provider": "The Weather Company / weather.com",
            "configured": True,
            "status": "location_required",
            "days": [],
        }
    postal_key = f"{postal_code}:{country_code}"
    try:
        payload = _weather_request(postal_key)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        return {
            "provider": "The Weather Company / weather.com",
            "configured": True,
            "status": "unavailable",
            "days": [],
        }

    valid_times = payload.get("validTimeLocal") or []
    day_names = payload.get("dayOfWeek") or []
    highs = payload.get("temperatureMax") or []
    lows = payload.get("temperatureMin") or []
    narratives = payload.get("narrative") or []
    wanted = {value.isoformat() for value in weekend_dates}
    days = []
    for index, valid_time in enumerate(valid_times):
        day_date = str(valid_time or "")[:10]
        if day_date not in wanted:
            continue
        days.append(
            {
                "date": day_date,
                "day_of_week": day_names[index] if index < len(day_names) else None,
                "high_f": highs[index] if index < len(highs) else None,
                "low_f": lows[index] if index < len(lows) else None,
                "narrative": narratives[index] if index < len(narratives) else None,
            }
        )
    return {
        "provider": "The Weather Company / weather.com",
        "configured": True,
        "status": "ok" if days else "no_data",
        "days": days,
    }


_ensure_tables()


@router.get("/dashboard/operations")
def academy_operations_dashboard(user: dict = Depends(current_access_user)):
    profile = _academy()
    today = _local_today(profile)
    session_data = _today_sessions(today)
    metrics = _money_metrics(today)
    players = fetch_one("SELECT COUNT(*) AS count FROM players") or {"count": 0}
    metrics.update(
        {
            "players": int(players.get("count") or 0),
            "today_session_count": len(session_data["group"]) + len(session_data["private"]),
        }
    )
    return {
        "user": {
            "id": int(user["id"]),
            "display_name": user.get("display_name"),
            "role": user.get("role"),
        },
        "academy": {
            "id": int(profile["id"]) if profile else None,
            "name": profile.get("name") if profile else None,
            "city": profile.get("city") if profile else None,
            "state": profile.get("state") if profile else None,
        },
        "as_of": today.isoformat(),
        "metrics": metrics,
        "today_sessions": session_data,
        "yesterday_attendance": _yesterday_attendance(today),
        "upcoming_matches": _upcoming_matches(today),
        "weather": _weekend_weather(profile, today),
    }


@router.get("/matches/{match_id}/confirmations")
def match_confirmations(match_id: int, _: dict = Depends(current_access_user)):
    match = fetch_one("SELECT id FROM academy_matches WHERE id=?", (match_id,))
    if not match:
        raise HTTPException(404, "Match not found")
    squad = fetch_all(
        """
        SELECT s.player_id,p.name AS player_name,c.status,c.responded_at
        FROM academy_match_squad s
        JOIN players p ON p.id=s.player_id
        LEFT JOIN academy_match_confirmations c ON c.match_id=s.match_id AND c.player_id=s.player_id
        WHERE s.match_id=?
        ORDER BY p.name COLLATE NOCASE
        """,
        (match_id,),
    )
    for row in squad:
        row["status"] = row.get("status") or "awaiting"
    return {"match_id": match_id, "summary": _confirmation_summary(match_id), "players": squad}


@router.put("/matches/{match_id}/confirmations/{player_id}")
def update_match_confirmation(
    match_id: int,
    player_id: int,
    payload: MatchConfirmationPayload,
    _: dict = Depends(require_access_admin),
):
    squad = fetch_one(
        "SELECT id FROM academy_match_squad WHERE match_id=? AND player_id=?",
        (match_id, player_id),
    )
    if not squad:
        raise HTTPException(409, "Player must be selected in the match squad before confirmation")
    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM academy_match_confirmations WHERE match_id=? AND player_id=?",
            (match_id, player_id),
        ).fetchone()
        responded_at = "CURRENT_TIMESTAMP" if payload.status != "awaiting" else None
        if existing:
            if responded_at:
                conn.execute(
                    "UPDATE academy_match_confirmations SET status=?,responded_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (payload.status, int(existing["id"])),
                )
            else:
                conn.execute(
                    "UPDATE academy_match_confirmations SET status=?,responded_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (payload.status, int(existing["id"])),
                )
        else:
            if responded_at:
                conn.execute(
                    "INSERT INTO academy_match_confirmations(match_id,player_id,status,responded_at) VALUES(?,?,?,CURRENT_TIMESTAMP)",
                    (match_id, player_id, payload.status),
                )
            else:
                conn.execute(
                    "INSERT INTO academy_match_confirmations(match_id,player_id,status) VALUES(?,?,?)",
                    (match_id, player_id, payload.status),
                )
    return match_confirmations(match_id, _)
