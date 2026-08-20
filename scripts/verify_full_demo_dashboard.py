from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("CRICKANALYSIS_BASE_URL", "https://crickanalysis.onrender.com").rstrip("/")

EXPECTED = {
    "players": 46,
    "fee_received_mtd_cents": 337600,
    "fee_pending_cents": 230400,
    "fee_late_cents": 152000,
    "coach_salary_paid_mtd_cents": 390200,
    "facility_payments_mtd_cents": 222500,
    "academy_expenses_mtd_cents": 268500,
}


def get(path: str):
    req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": "CrickAnalysis-Demo-Verify/1.0"})
    with urllib.request.urlopen(req, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    dashboard = get("/api/academy/dashboard/operations")
    month = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m")
    finance = get(f"/api/academy/finance/operations-summary?month={month}")
    players = get("/api/academy/players")

    metrics = dashboard.get("metrics") or {}
    actual = {
        "players": int(metrics.get("players") or 0),
        "fee_received_mtd_cents": int(metrics.get("fee_received_mtd_cents") or 0),
        "fee_pending_cents": int(metrics.get("fee_pending_cents") or 0),
        "fee_late_cents": int(metrics.get("fee_late_cents") or 0),
        "coach_salary_paid_mtd_cents": int(finance.get("coach_salary_paid_mtd_cents") or 0),
        "facility_payments_mtd_cents": int(finance.get("facility_payments_mtd_cents") or 0),
        "academy_expenses_mtd_cents": int(finance.get("academy_expenses_mtd_cents") or 0),
    }

    current_month_registrations = [
        row for row in players if str(row.get("joined_on") or "").startswith(month)
    ]
    demo_current = [row for row in current_month_registrations if str(row.get("name") or "").startswith("DEMO ")]

    errors = []
    for key, expected in EXPECTED.items():
        if actual[key] != expected:
            errors.append(f"{key}: expected {expected}, got {actual[key]}")
    if len(demo_current) != 5:
        errors.append(f"current-month DEMO registrations: expected 5, got {len(demo_current)}")

    report = {
        "expected": EXPECTED,
        "actual": actual,
        "current_month_demo_registrations": [row.get("name") for row in demo_current],
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }
    print("FULL_DEMO_DASHBOARD_RECONCILIATION")
    print(json.dumps(report, indent=2))
    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    main()
