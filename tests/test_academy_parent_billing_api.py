import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-parent-billing-api-test-")
os.environ["CAM_BOOTSTRAP_TOKEN"] = "parent-billing-bootstrap"
os.environ["CAM_PAYMENT_MODE"] = "sandbox"

from fastapi.testclient import TestClient
from app.database import fetch_all
from run import app

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _post(path: str, payload: dict, token: str | None = None, expected=(200, 201)):
    response = client.post(path, json=payload, headers=_auth(token) if token else {})
    assert response.status_code in expected, response.text
    return response.json() if response.content else None


def _reset_shared_postgres_state() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "academy_billing_security_audit",
        "academy_saved_payment_methods",
        "academy_refunds",
        "academy_payment_allocations",
        "academy_payments",
        "academy_invoice_items",
        "academy_invoices",
        "academy_enrollment_billing",
        "academy_billing_account_players",
        "academy_billing_accounts",
        "academy_fee_plans",
        "academy_auth_sessions",
        "academy_access_audit",
        "academy_users",
        "enrollments",
        "player_guardians",
        "guardians",
        "programs",
        "players",
        "academies",
    ]
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            existing = []
            for table in candidates:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cursor.fetchone()[0] is not None:
                    existing.append(table)
            if existing:
                cursor.execute(f"TRUNCATE TABLE {', '.join(existing)} RESTART IDENTITY CASCADE")
        conn.commit()


def _create_family(owner_token: str, suffix: str, amount_cents: int = 17500):
    # Once Access is bootstrapped, all generic Academy management setup must be
    # performed under the Owner/Admin session. Parent-specific calls remain scoped
    # to the linked Parent account later in the scenario.
    player = _post(
        "/api/academy/players",
        {
            "name": f"Parent Billing {suffix} Player",
            "status": "active",
            "guardians": [
                {
                    "first_name": suffix,
                    "last_name": "Parent",
                    "relationship": "Parent",
                    "email": f"{suffix.lower()}@example.test",
                    "phone": "4045550100",
                    "is_primary": True,
                    "billing_contact": True,
                    "pickup_authorized": True,
                }
            ],
        },
        owner_token,
    )
    guardian_id = int(player["guardians"][0]["id"])
    program = _post(
        "/api/academy/programs",
        {"name": f"{suffix} U13 Program", "program_type": "group", "status": "active"},
        owner_token,
    )
    enrollment = _post(
        "/api/academy/enrollments",
        {
            "player_id": player["id"],
            "program_id": program["id"],
            "enrollment_type": "regular",
            "start_date": "2026-09-01",
        },
        owner_token,
    )
    fee_plan = _post(
        "/api/academy/fee-plans",
        {
            "name": f"{suffix} U13 Monthly",
            "amount_cents": amount_cents,
            "currency": "USD",
            "billing_frequency": "monthly",
            "due_day_of_month": 1,
            "program_id": program["id"],
            "status": "active",
        },
        owner_token,
    )
    account = _post(
        "/api/academy/billing-accounts",
        {
            "account_name": f"{suffix} Family",
            "player_ids": [player["id"]],
            "primary_guardian_id": guardian_id,
            "overpayment_allowed": True,
            "status": "active",
        },
        owner_token,
    )
    billing = client.put(
        f"/api/academy/enrollments/{enrollment['id']}/billing",
        json={"fee_plan_id": fee_plan["id"], "discount_type": "none", "discount_value": 0},
        headers=_auth(owner_token),
    )
    assert billing.status_code == 200, billing.text
    invoice = _post(
        "/api/academy/invoices/from-enrollment",
        {
            "account_id": account["id"],
            "enrollment_id": enrollment["id"],
            "issue_date": "2026-09-01",
            "due_date": "2026-09-15",
        },
        owner_token,
    )
    parent_user = _post(
        "/api/academy/access/users",
        {
            "display_name": f"{suffix} Parent",
            "email": f"portal-{suffix.lower()}@example.test",
            "password": "ParentPortal!123",
            "role": "parent",
            "guardian_id": guardian_id,
            "status": "active",
        },
        owner_token,
    )
    login = _post(
        "/api/auth/login",
        {"email": parent_user["email"], "password": "ParentPortal!123"},
    )
    return {
        "player": player,
        "guardian_id": guardian_id,
        "program": program,
        "enrollment": enrollment,
        "fee_plan": fee_plan,
        "account": account,
        "invoice": invoice,
        "parent_user": parent_user,
        "parent_token": login["token"],
    }


def test_parent_login_saved_test_card_full_payment_receipt_and_family_isolation():
    _reset_shared_postgres_state()

    profile = client.put("/api/academy/profile", json={"name": "Parent Billing Test Academy"})
    assert profile.status_code == 200, profile.text

    bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"display_name": "Academy Owner", "email": "owner.billing@example.test", "password": "OwnerBilling!123"},
        headers={"X-CAM-Bootstrap": "parent-billing-bootstrap"},
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_token = bootstrap.json()["token"]

    family = _create_family(owner_token, "Patel", 17500)
    other_family = _create_family(owner_token, "Shah", 12500)
    parent_token = family["parent_token"]

    no_auth = client.get("/api/academy/parent/billing")
    assert no_auth.status_code == 401

    summary = client.get("/api/academy/parent/billing", headers=_auth(parent_token))
    assert summary.status_code == 200, summary.text
    summary_json = summary.json()
    assert summary_json["payment_mode"] == "sandbox"
    assert [int(row["id"]) for row in summary_json["players"]] == [int(family["player"]["id"])]
    assert [int(row["id"]) for row in summary_json["accounts"]] == [int(family["account"]["id"])]
    assert int(summary_json["accounts"][0]["balance_cents"]) == 17500
    assert summary_json["payment_methods"] == []

    real_like_card = client.post(
        "/api/academy/parent/payment-methods/sandbox",
        json={"card_number": "4111111111111111", "exp_month": 12, "exp_year": 2034, "cvc": "123"},
        headers=_auth(parent_token),
    )
    assert real_like_card.status_code == 422

    success_method = _post(
        "/api/academy/parent/payment-methods/sandbox",
        {
            "card_number": "4242 4242 4242 4242",
            "exp_month": 12,
            "exp_year": 2034,
            "cvc": "123",
            "make_default": True,
        },
        parent_token,
    )
    assert success_method["brand"] == "Visa"
    assert success_method["last4"] == "4242"
    assert success_method["is_default"] is True
    assert "card_number" not in success_method
    assert "cvc" not in success_method

    stored_rows = fetch_all("SELECT * FROM academy_saved_payment_methods")
    stored_columns = {key for row in stored_rows for key in row.keys()}
    assert "card_number" not in stored_columns
    assert "cvc" not in stored_columns
    assert all("4242424242424242" not in str(value) for row in stored_rows for value in row.values() if value is not None)

    declined_method = _post(
        "/api/academy/parent/payment-methods/sandbox",
        {
            "card_number": "4000 0000 0000 9995",
            "exp_month": 11,
            "exp_year": 2034,
            "cvc": "321",
            "make_default": False,
        },
        parent_token,
    )
    assert declined_method["last4"] == "9995"

    # Declined cards are still evaluated when the Parent submits the required
    # full balance. The balance must remain unchanged after the decline.
    failed = client.post(
        f"/api/academy/parent/invoices/{family['invoice']['id']}/pay",
        json={"payment_method_id": declined_method["id"], "amount_cents": 17500},
        headers=_auth(parent_token),
    )
    assert failed.status_code == 402
    after_failed = client.get("/api/academy/parent/billing", headers=_auth(parent_token)).json()
    assert int(after_failed["accounts"][0]["invoices"][0]["balance_due_cents"]) == 17500
    assert after_failed["accounts"][0]["payments"] == []

    # Parent/Guardian self-service cannot intentionally leave an outstanding
    # balance. A partial request is rejected before any payment is posted.
    partial = client.post(
        f"/api/academy/parent/invoices/{family['invoice']['id']}/pay",
        json={"payment_method_id": success_method["id"], "amount_cents": 10000},
        headers=_auth(parent_token),
    )
    assert partial.status_code == 409
    assert "full invoice balance" in partial.text
    after_partial = client.get("/api/academy/parent/billing", headers=_auth(parent_token)).json()
    assert int(after_partial["accounts"][0]["invoices"][0]["balance_due_cents"]) == 17500
    assert after_partial["accounts"][0]["payments"] == []

    full_payment = client.post(
        f"/api/academy/parent/invoices/{family['invoice']['id']}/pay",
        json={"payment_method_id": success_method["id"]},
        headers=_auth(parent_token),
    )
    assert full_payment.status_code == 200, full_payment.text
    full_json = full_payment.json()
    assert int(full_json["payment"]["amount_cents"]) == 17500
    assert full_json["payment"]["receipt_number"].startswith("RCT-")
    assert int(full_json["invoice"]["balance_due_cents"]) == 0
    assert full_json["invoice"]["status"] == "paid"
    payment_id = int(full_json["payment"]["id"])

    receipt = client.get(f"/api/academy/parent/receipts/{payment_id}", headers=_auth(parent_token))
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["receipt_number"] == full_json["payment"]["receipt_number"]
    assert int(receipt.json()["amount_cents"]) == 17500

    paid_again = client.post(
        f"/api/academy/parent/invoices/{family['invoice']['id']}/pay",
        json={"payment_method_id": success_method["id"]},
        headers=_auth(parent_token),
    )
    assert paid_again.status_code == 409

    cross_family = client.post(
        f"/api/academy/parent/invoices/{other_family['invoice']['id']}/pay",
        json={"payment_method_id": success_method["id"], "amount_cents": 12500},
        headers=_auth(parent_token),
    )
    assert cross_family.status_code == 403

    other_parent_summary = client.get(
        "/api/academy/parent/billing",
        headers=_auth(other_family["parent_token"]),
    )
    assert other_parent_summary.status_code == 200
    other_json = other_parent_summary.json()
    assert [int(row["id"]) for row in other_json["players"]] == [int(other_family["player"]["id"])]
    assert int(other_json["accounts"][0]["balance_cents"]) == 12500

    removed = client.delete(
        f"/api/academy/parent/payment-methods/{declined_method['id']}",
        headers=_auth(parent_token),
    )
    assert removed.status_code == 204
    methods_after = client.get("/api/academy/parent/payment-methods", headers=_auth(parent_token)).json()
    assert [row["last4"] for row in methods_after["payment_methods"]] == ["4242"]

    audit = client.get("/api/academy/parent/billing-audit", headers=_auth(parent_token))
    assert audit.status_code == 200
    actions = [row["action"] for row in audit.json()]
    assert "add_payment_method" in actions
    assert "parent_invoice_payment" in actions
    assert "remove_payment_method" in actions
