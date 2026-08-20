import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-finance-ops-test-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _post(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_coach_rates_and_expense_summary_are_persistent_and_idempotent():
    client.put("/api/academy/profile", json={"name": "Finance Ops Test Academy"})
    coach = _post(
        "/api/academy/coaches",
        {
            "first_name": "Test",
            "last_name": "Coach",
            "preferred_name": "Coach Test",
            "specialties": ["Batting"],
            "status": "active",
        },
    )

    rate_payload = {
        "coach_id": coach["id"],
        "rate_type": "hourly",
        "rate_cents": 5500,
        "effective_from": "2026-08-01",
        "status": "active",
        "external_reference": "TEST-COACH-RATE-001",
        "notes": "Automated test rate",
    }
    rate = _post("/api/academy/coach-rates", rate_payload)
    assert rate["coach_name"] == "Coach Test"
    assert int(rate["rate_cents"]) == 5500

    duplicate_rate = _post("/api/academy/coach-rates", rate_payload)
    assert int(duplicate_rate["id"]) == int(rate["id"])

    academy_expense = _post(
        "/api/academy/expenses",
        {
            "expense_type": "academy",
            "category": "Equipment",
            "vendor": "Test Cricket Store",
            "amount_cents": 65000,
            "expense_date": "2026-08-05",
            "payment_method": "card",
            "status": "paid",
            "external_reference": "TEST-ACADEMY-EXP-001",
        },
    )
    facility_expense = _post(
        "/api/academy/expenses",
        {
            "expense_type": "facility",
            "category": "Facility Rental",
            "vendor": "Test Indoor Center",
            "facility_name": "Test Indoor Center",
            "amount_cents": 120000,
            "expense_date": "2026-08-06",
            "payment_method": "bank",
            "status": "paid",
            "recurring": True,
            "external_reference": "TEST-FACILITY-EXP-001",
        },
    )
    assert academy_expense["expense_type"] == "academy"
    assert facility_expense["recurring"] is True

    duplicate_expense = _post(
        "/api/academy/expenses",
        {
            "expense_type": "facility",
            "category": "Facility Rental",
            "vendor": "Test Indoor Center",
            "facility_name": "Test Indoor Center",
            "amount_cents": 120000,
            "expense_date": "2026-08-06",
            "payment_method": "bank",
            "status": "paid",
            "recurring": True,
            "external_reference": "TEST-FACILITY-EXP-001",
        },
    )
    assert int(duplicate_expense["id"]) == int(facility_expense["id"])

    summary = client.get("/api/academy/finance/operations-summary?month=2026-08")
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert int(data["coach_rates_configured"]) == 1
    assert int(data["academy_expense_count"]) == 1
    assert int(data["academy_expenses_mtd_cents"]) == 65000
    assert int(data["facility_expense_count"]) == 1
    assert int(data["facility_payments_mtd_cents"]) == 120000
    assert data["coach_salary_tracking_configured"] is False

    rates = client.get("/api/academy/coach-rates?status=active").json()
    expenses = client.get("/api/academy/expenses?month=2026-08").json()
    assert len(rates) == 1
    assert len(expenses) == 2
