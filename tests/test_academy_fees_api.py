import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-fees-api-test-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _post(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_fee_plan_family_account_enrollment_discount_and_unique_invoices():
    profile = client.put("/api/academy/profile", json={"name": "Fees Test Academy"})
    assert profile.status_code == 200, profile.text

    player = _post(
        "/api/academy/players",
        {
            "name": "Fees Aarav Patel",
            "status": "active",
            "guardians": [
                {
                    "first_name": "Demo",
                    "last_name": "Patel",
                    "relationship": "Parent",
                    "email": "billing@example.test",
                    "is_primary": True,
                    "billing_contact": True,
                    "pickup_authorized": True,
                }
            ],
        },
    )
    guardian_id = int(player["guardians"][0]["id"])

    other_player = _post("/api/academy/players", {"name": "Fees Other Player", "status": "active"})
    program = _post(
        "/api/academy/programs",
        {"name": "Fees U15 Advanced", "program_type": "group", "status": "active"},
    )
    enrollment = _post(
        "/api/academy/enrollments",
        {"player_id": player["id"], "program_id": program["id"], "enrollment_type": "regular", "start_date": "2026-09-01"},
    )

    # AM-FEE-001: $200 monthly tuition, due on the 1st, stored in integer cents.
    fee_plan = _post(
        "/api/academy/fee-plans",
        {
            "name": "U15 Monthly 200",
            "amount_cents": 20000,
            "currency": "USD",
            "billing_frequency": "monthly",
            "due_day_of_month": 1,
            "program_id": program["id"],
            "status": "active",
        },
    )
    assert int(fee_plan["amount_cents"]) == 20000
    assert int(fee_plan["due_day_of_month"]) == 1
    assert int(fee_plan["program_id"]) == int(program["id"])

    duplicate = client.post(
        "/api/academy/fee-plans",
        json={"name": "U15 Monthly 200", "amount_cents": 20000, "billing_frequency": "monthly", "due_day_of_month": 1},
    )
    assert duplicate.status_code == 409

    invalid_due_day = client.post(
        "/api/academy/fee-plans",
        json={"name": "Invalid Due Day", "amount_cents": 20000, "billing_frequency": "monthly", "due_day_of_month": 31},
    )
    assert invalid_due_day.status_code == 422

    # AM-FEE-002: create a family billing account linked to the real player/guardian.
    account = _post(
        "/api/academy/billing-accounts",
        {
            "account_name": "Patel Family",
            "player_ids": [player["id"]],
            "primary_guardian_id": guardian_id,
            "overpayment_allowed": True,
            "status": "active",
        },
    )
    account_id = int(account["id"])
    assert account["guardian_name"] == "Demo Patel"
    assert [int(p["player_id"]) for p in account["players"]] == [int(player["id"])]
    assert int(account["balance_cents"]) == 0

    # AM-ENR-003 + AM-ENR-009 + AM-FEE-005: $200 less 10% = $180.
    billing = client.put(
        f"/api/academy/enrollments/{enrollment['id']}/billing",
        json={"fee_plan_id": fee_plan["id"], "discount_type": "percent", "discount_value": 1000, "notes": "Sibling-style test discount"},
    )
    assert billing.status_code == 200, billing.text
    billing_json = billing.json()
    assert billing_json["fee_plan_name"] == "U15 Monthly 200"
    assert billing_json["discount_type"] == "percent"
    assert int(billing_json["discount_value"]) == 1000
    assert int(billing_json["due_day_of_month"]) == 1

    invalid_percent = client.put(
        f"/api/academy/enrollments/{enrollment['id']}/billing",
        json={"fee_plan_id": fee_plan["id"], "discount_type": "percent", "discount_value": 10001},
    )
    assert invalid_percent.status_code == 422

    # Restore valid billing after rejected update attempt.
    billing = client.put(
        f"/api/academy/enrollments/{enrollment['id']}/billing",
        json={"fee_plan_id": fee_plan["id"], "discount_type": "percent", "discount_value": 1000},
    )
    assert billing.status_code == 200

    # AM-FEE-003/004/005: invoice generation, deterministic totals, unique numbers.
    invoice1 = _post(
        "/api/academy/invoices/from-enrollment",
        {
            "account_id": account_id,
            "enrollment_id": enrollment["id"],
            "issue_date": "2026-09-01",
            "due_date": "2026-09-15",
        },
    )
    assert invoice1["invoice_number"].startswith("INV-")
    assert int(invoice1["subtotal_cents"]) == 20000
    assert int(invoice1["discount_cents"]) == 2000
    assert int(invoice1["total_cents"]) == 18000
    assert int(invoice1["balance_due_cents"]) == 18000
    assert len(invoice1["items"]) == 1
    assert int(invoice1["items"][0]["line_total_cents"]) == 18000

    invoice2 = _post(
        "/api/academy/invoices/from-enrollment",
        {
            "account_id": account_id,
            "enrollment_id": enrollment["id"],
            "issue_date": "2026-10-01",
            "due_date": "2026-10-15",
        },
    )
    assert invoice2["invoice_number"] != invoice1["invoice_number"]
    assert int(invoice2["id"]) != int(invoice1["id"])

    numbers = [row["invoice_number"] for row in client.get("/api/academy/invoices").json()]
    assert len(numbers) == len(set(numbers))
    assert {invoice1["invoice_number"], invoice2["invoice_number"]}.issubset(set(numbers))

    account_after = client.get(f"/api/academy/billing-accounts/{account_id}")
    assert account_after.status_code == 200
    assert int(account_after.json()["invoiced_cents"]) == 36000
    assert int(account_after.json()["balance_cents"]) == 36000

    # Wrong family account cannot invoice a different player's enrollment.
    other_account = _post(
        "/api/academy/billing-accounts",
        {"account_name": "Other Family", "player_ids": [other_player["id"]], "overpayment_allowed": False},
    )
    wrong_account = client.post(
        "/api/academy/invoices/from-enrollment",
        json={
            "account_id": other_account["id"],
            "enrollment_id": enrollment["id"],
            "issue_date": "2026-11-01",
            "due_date": "2026-11-15",
        },
    )
    assert wrong_account.status_code == 409

    bad_due_date = client.post(
        "/api/academy/invoices/from-enrollment",
        json={
            "account_id": account_id,
            "enrollment_id": enrollment["id"],
            "issue_date": "2026-12-10",
            "due_date": "2026-12-01",
        },
    )
    assert bad_due_date.status_code == 422
