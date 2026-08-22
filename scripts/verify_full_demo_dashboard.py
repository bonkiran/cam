from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("CRICKANALYSIS_BASE_URL", "https://crickanalysis.onrender.com").rstrip("/")
BASELINE_PATH = Path(os.environ.get("DEMO_FINANCE_BASELINE_PATH", "demo_finance_baseline.json"))

# Contributions from the controlled 45-player DEMO fixture only. Real/non-DEMO
# finance data is intentionally preserved and is accounted for through the
# baseline captured immediately after DEMO cleanup and before reseeding.
DEMO_CONTRIBUTION = {
    "fee_received_mtd_cents": 337600,
    "fee_pending_cents": 230400,
    "fee_late_cents": 152000,
    "coach_salary_paid_mtd_cents": 390200,
    "facility_payments_mtd_cents": 222500,
    "academy_expenses_mtd_cents": 268500,
}

TARGET_PLAYER_NAMES = {
    "DEMO Aarav Patel", "DEMO Maya Rao", "DEMO Rohan Singh", "DEMO Zoe Carter",
    "DEMO Arjun Mehta", "DEMO Anaya Iyer", "DEMO Vihaan Shah", "DEMO Aditi Nair",
    "DEMO Kabir Reddy", "DEMO Isha Kapoor", "DEMO Neel Joshi", "DEMO Riya Menon",
    "DEMO Dev Malhotra", "DEMO Tara Kulkarni", "DEMO Aryan Desai", "DEMO Saanvi Gupta",
    "DEMO Krish Verma", "DEMO Nisha Bhat", "DEMO Aditya Kumar", "DEMO Meera Pillai",
    "DEMO Ishaan Bose", "DEMO Kavya Jain", "DEMO Reyansh Sethi", "DEMO Siya Anand",
    "DEMO Dhruv Khanna", "DEMO Myra Chopra", "DEMO Arnav Saxena", "DEMO Kiara Fernandes",
    "DEMO Yash Chawla", "DEMO Diya Prasad", "DEMO Samar Banerjee", "DEMO Anika George",
    "DEMO Veer Narang", "DEMO Rhea Thomas", "DEMO Neil Mathew", "DEMO Aanya Das",
    "DEMO Kian Joseph", "DEMO Avni Varma", "DEMO Rishi Menon", "DEMO Leela Krishnan",
    "DEMO Ethan Miller", "DEMO Olivia Johnson", "DEMO Liam Davis", "DEMO Sophia Wilson",
    "DEMO Noah Brown",
}


def get(path: str):
    req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": "CrickAnalysis-Demo-Verify/2.0"})
    with urllib.request.urlopen(req, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    if not BASELINE_PATH.exists():
        raise RuntimeError(f"Baseline file not found: {BASELINE_PATH}")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    dashboard = get("/api/cam/dashboard/operations")
    month = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m")
    finance = get(f"/api/cam/finance/operations-summary?month={month}")
    players = get("/api/cam/players")

    if str(baseline.get("month")) != month:
        raise RuntimeError(f"Baseline month mismatch: expected {month}, got {baseline.get('month')}")

    metrics = dashboard.get("metrics") or {}
    actual = {
        "fee_received_mtd_cents": int(metrics.get("fee_received_mtd_cents") or 0),
        "fee_pending_cents": int(metrics.get("fee_pending_cents") or 0),
        "fee_late_cents": int(metrics.get("fee_late_cents") or 0),
        "coach_salary_paid_mtd_cents": int(finance.get("coach_salary_paid_mtd_cents") or 0),
        "facility_payments_mtd_cents": int(finance.get("facility_payments_mtd_cents") or 0),
        "academy_expenses_mtd_cents": int(finance.get("academy_expenses_mtd_cents") or 0),
    }
    expected = {
        key: int(baseline.get(key) or 0) + int(value)
        for key, value in DEMO_CONTRIBUTION.items()
    }

    target_players = [row for row in players if str(row.get("name") or "") in TARGET_PLAYER_NAMES]
    demo_current = [
        row for row in target_players
        if str(row.get("joined_on") or "").startswith(month)
    ]

    errors = []
    for key, expected_value in expected.items():
        if actual[key] != expected_value:
            errors.append(f"{key}: expected {expected_value}, got {actual[key]}")
    if len(target_players) != 45:
        errors.append(f"controlled DEMO players: expected 45, got {len(target_players)}")
    if len(demo_current) != 5:
        errors.append(f"current-month controlled DEMO registrations: expected 5, got {len(demo_current)}")

    report = {
        "baseline_preserved_non_demo": baseline,
        "demo_contribution": DEMO_CONTRIBUTION,
        "expected_final": expected,
        "actual_final": actual,
        "controlled_demo_players": len(target_players),
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
