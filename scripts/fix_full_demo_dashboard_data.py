from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("CRICKANALYSIS_BASE_URL", "https://crickanalysis.onrender.com").rstrip("/")

COACH_PAYROLL = {
    "Coach Priya": {"hours": 18, "rate_cents": 5500},
    "Coach Daniel": {"hours": 16, "rate_cents": 5000},
    "Coach Meera": {"hours": 14, "rate_cents": 4800},
    "Coach Arjun": {"hours": 15, "rate_cents": 6000},
    "Coach Michael": {"hours": 12, "rate_cents": 4500},
}

PLAYER_FIELDS = [
    "name", "first_name", "last_name", "preferred_name", "date_of_birth", "gender",
    "batting_style", "bowling_style", "handedness", "skill_level", "email", "phone",
    "address_line1", "address_line2", "city", "state", "postal_code", "country",
    "emergency_contact_name", "emergency_contact_phone", "joined_on", "status", "notes",
]

GUARDIAN_FIELDS = [
    "id", "first_name", "last_name", "relationship", "email", "phone",
    "address_line1", "address_line2", "city", "state", "postal_code", "country",
    "is_primary", "billing_contact", "pickup_authorized",
]


def request(method: str, path: str, payload=None, *, retries: int = 5):
    url = BASE_URL + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": "CrickAnalysis-Demo-Dashboard-Fix/1.0"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=40) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last = RuntimeError(f"{method} {path} -> HTTP {exc.code}: {body}")
            if exc.code < 500:
                raise last
        except Exception as exc:
            last = exc
        if attempt < retries:
            time.sleep(3 * attempt)
    raise RuntimeError(f"{method} {path} failed after {retries} attempts: {last}")


def get(path: str):
    return request("GET", path)


def post(path: str, payload):
    return request("POST", path, payload)


def put(path: str, payload):
    return request("PUT", path, payload)


def wait_for_new_finance_api():
    for attempt in range(1, 61):
        try:
            storage = get("/api/system/storage")
            if storage and storage.get("database") == "postgresql":
                payments = get("/api/academy/coach-payments")
                print(f"service ready on attempt {attempt}: PostgreSQL + coach-payments API ({len(payments)} rows)")
                return
        except Exception as exc:
            print(f"service readiness attempt {attempt}: {exc}")
        time.sleep(10)
    raise RuntimeError("New coach-payments API did not become available within 10 minutes")


def player_number(player: dict) -> int | None:
    match = re.search(r"player\s+(\d+)\s+of\s+45", str(player.get("notes") or ""), re.IGNORECASE)
    return int(match.group(1)) if match else None


def player_payload(player: dict, joined_on: str) -> dict:
    payload = {field: player.get(field) for field in PLAYER_FIELDS}
    payload["joined_on"] = joined_on
    payload["guardians"] = [
        {field: guardian.get(field) for field in GUARDIAN_FIELDS}
        for guardian in (player.get("guardians") or [])
    ]
    return payload


def set_five_current_month_registrations(today: date) -> list[dict]:
    players = get("/api/academy/players")
    demo_players = [row for row in players if player_number(row) is not None]
    demo_players.sort(key=lambda row: player_number(row) or 999)
    if len(demo_players) != 45:
        raise RuntimeError(f"Expected 45 full-demo players, found {len(demo_players)}")

    month_start = today.replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    two_months_end = previous_month_start - timedelta(days=1)
    two_months_start = two_months_end.replace(day=1)

    updated = []
    for index, player in enumerate(demo_players):
        if index < 5:
            offset = min(index, max(0, today.day - 1))
            joined = month_start + timedelta(days=offset)
        elif index < 25:
            joined = previous_month_start + timedelta(days=(index - 5) % min(28, previous_month_end.day))
        else:
            joined = two_months_start + timedelta(days=(index - 25) % min(28, two_months_end.day))
        saved = put(f"/api/academy/players/{int(player['id'])}", player_payload(player, joined.isoformat()))
        updated.append(saved)
        print("registration date", saved.get("name"), "->", saved.get("joined_on"))

    month_prefix = today.strftime("%Y-%m")
    current = [row for row in updated if str(row.get("joined_on") or "").startswith(month_prefix)]
    if len(current) != 5:
        raise RuntimeError(f"Expected exactly 5 current-month DEMO registrations, got {len(current)}")
    return current


def seed_coach_salary_payments(today: date) -> list[dict]:
    coaches = get("/api/academy/coaches")
    by_preferred = {str(row.get("preferred_name") or ""): row for row in coaches}
    cycle = today.strftime("%Y-%m")
    month_start = today.replace(day=1)
    paid_on = max(month_start, today - timedelta(days=3))
    period_end = min(today, paid_on)

    payments = []
    for preferred_name, spec in COACH_PAYROLL.items():
        coach = by_preferred.get(preferred_name)
        if not coach:
            raise RuntimeError(f"Missing DEMO coach {preferred_name!r}")
        hours = float(spec["hours"])
        rate_cents = int(spec["rate_cents"])
        amount_cents = int(round(hours * rate_cents))
        payment = post(
            "/api/academy/coach-payments",
            {
                "coach_id": int(coach["id"]),
                "amount_cents": amount_cents,
                "paid_on": paid_on.isoformat(),
                "payment_method": "bank",
                "hours_worked": hours,
                "period_start": month_start.isoformat(),
                "period_end": period_end.isoformat(),
                "status": "paid",
                "external_reference": f"DEMO-{cycle}-COACH-PAY-{int(coach['id'])}",
                "notes": f"DEMO DATA — {hours:g} hours × ${rate_cents / 100:.0f}/hr.",
            },
        )
        payments.append(payment)
        print("coach salary", preferred_name, amount_cents)

    expected_total = sum(int(spec["hours"] * spec["rate_cents"]) for spec in COACH_PAYROLL.values())
    seeded_total = sum(int(row.get("amount_cents") or 0) for row in payments)
    if seeded_total != expected_total:
        raise RuntimeError(f"Coach salary total mismatch: expected {expected_total}, got {seeded_total}")
    return payments


def main():
    wait_for_new_finance_api()
    today = __import__("datetime").datetime.now(ZoneInfo("America/New_York")).date()
    cycle = today.strftime("%Y-%m")

    current_registrations = set_five_current_month_registrations(today)
    coach_payments = seed_coach_salary_payments(today)
    summary = get(f"/api/academy/finance/operations-summary?month={cycle}")

    expected_salary = sum(int(spec["hours"] * spec["rate_cents"]) for spec in COACH_PAYROLL.values())
    if int(summary.get("coach_salary_paid_mtd_cents") or 0) < expected_salary:
        raise RuntimeError(
            f"Finance summary coach salary is too low: expected at least {expected_salary}, "
            f"got {summary.get('coach_salary_paid_mtd_cents')}"
        )

    print("DEMO_DASHBOARD_CORRECTION_COMPLETE")
    print(json.dumps({
        "cycle": cycle,
        "current_month_registration_count": len(current_registrations),
        "current_month_registrations": [row.get("name") for row in current_registrations],
        "coach_salary_payment_count": len(coach_payments),
        "seeded_coach_salary_paid_cents": expected_salary,
        "operations_summary": summary,
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DEMO_DASHBOARD_CORRECTION_FAILED: {exc}", file=sys.stderr)
        raise
