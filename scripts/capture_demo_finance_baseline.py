from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("CRICKANALYSIS_BASE_URL", "https://crickanalysis.onrender.com").rstrip("/")
OUTPUT = Path(os.environ.get("DEMO_FINANCE_BASELINE_PATH", "demo_finance_baseline.json"))


def get(path: str):
    request = urllib.request.Request(
        BASE_URL + path,
        headers={"User-Agent": "CrickAnalysis-Demo-Baseline/1.0"},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    month = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m")
    dashboard = get("/api/cam/dashboard/operations")
    finance = get(f"/api/cam/finance/operations-summary?month={month}")
    metrics = dashboard.get("metrics") or {}

    baseline = {
        "month": month,
        "fee_received_mtd_cents": int(metrics.get("fee_received_mtd_cents") or 0),
        "fee_pending_cents": int(metrics.get("fee_pending_cents") or 0),
        "fee_late_cents": int(metrics.get("fee_late_cents") or 0),
        "coach_salary_paid_mtd_cents": int(finance.get("coach_salary_paid_mtd_cents") or 0),
        "facility_payments_mtd_cents": int(finance.get("facility_payments_mtd_cents") or 0),
        "academy_expenses_mtd_cents": int(finance.get("academy_expenses_mtd_cents") or 0),
    }
    OUTPUT.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    print("DEMO_FINANCE_BASELINE_CAPTURED")
    print(json.dumps(baseline, indent=2))


if __name__ == "__main__":
    main()
