import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-track-a-reconcile-")
os.environ["CAM_BOOTSTRAP_TOKEN"] = "track-a-reconcile-bootstrap"
os.environ["CAM_PAYMENT_MODE"] = "sandbox"

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _post(path: str, payload: dict, token: str | None = None):
    response = client.post(path, json=payload, headers=_auth(token) if token else {})
    assert response.status_code in (200, 201), response.text
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
        "programs",
        "player_guardians",
        "guardians",
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


def test_reconcile_qa_046_052_053_exact_fee_and_manual_payment_permutations():
    _reset_shared_postgres_state()

    profile = client.put("/api/academy/profile", json={"name": "Track A Reconciliation Academy"})
    assert profile.status_code == 200, profile.text

    p1 = _post("/api/academy/players", {"name": "Reconcile Cash Player", "status": "active"})
    p2 = _post("/api/academy/players", {"name": "Reconcile Check Player", "status": "active"})
    program = _post(
        "/api/academy/programs",
        {"name": "1-to-1 Private Coaching", "program_type": "private", "status": "active"},
    )

    # QA-046: a private 1-to-1 service can use a per-session fee plan.
    plan = _post(
        "/api/academy/fee-plans",
        {
            "name": "Private Coaching Per Session",
            "amount_cents": 7500,
            "currency": "USD",
            "billing_frequency": "session",
            "program_id": program["id"],
            "status": "active",
        },
    )
    assert plan["billing_frequency"] == "session"
    assert int(plan["amount_cents"]) == 7500
    assert int(plan["program_id"]) == int(program["id"])

    e1 = _post(
        "/api/academy/enrollments",
        {"player_id": p1["id"], "program_id": program["id"], "enrollment_type": "regular", "start_date": "2026-09-01"},
    )
    e2 = _post(
        "/api/academy/enrollments",
        {"player_id": p2["id"], "program_id": program["id"], "enrollment_type": "regular", "start_date": "2026-09-01"},
    )
    for enrollment in (e1, e2):
        response = client.put(
            f"/api/academy/enrollments/{enrollment['id']}/billing",
            json={"fee_plan_id": plan["id"], "discount_type": "none", "discount_value": 0},
        )
        assert response.status_code == 200, response.text

    account = _post(
        "/api/academy/billing-accounts",
        {
            "account_name": "Reconciliation Family",
            "player_ids": [p1["id"], p2["id"]],
            "overpayment_allowed": True,
            "status": "active",
        },
    )
    i1 = _post(
        "/api/academy/invoices/from-enrollment",
        {"account_id": account["id"], "enrollment_id": e1["id"], "issue_date": "2026-09-01", "due_date": "2026-09-15"},
    )
    i2 = _post(
        "/api/academy/invoices/from-enrollment",
        {"account_id": account["id"], "enrollment_id": e2["id"], "issue_date": "2026-09-01", "due_date": "2026-09-15"},
    )

    # QA-052: full cash payment closes the invoice and produces a receipt.
    cash = _post(
        "/api/academy/payments",
        {
            "account_id": account["id"],
            "amount_cents": 7500,
            "method": "cash",
            "received_on": "2026-09-05",
            "idempotency_key": "reconcile-cash-full-001",
            "allocations": [{"invoice_id": i1["id"], "amount_cents": 7500}],
        },
    )
    assert cash["method"] == "cash"
    cash_invoice = client.get(f"/api/academy/invoices/{i1['id']}").json()
    assert cash_invoice["status"] == "paid"
    assert int(cash_invoice["balance_due_cents"]) == 0
    cash_receipt = client.get(f"/api/academy/payments/{cash['id']}/receipt")
    assert cash_receipt.status_code == 200, cash_receipt.text
    assert cash_receipt.json()["receipt_number"].startswith("RCT-")

    # QA-053: partial check payment leaves the exact remaining balance.
    check = _post(
        "/api/academy/payments",
        {
            "account_id": account["id"],
            "amount_cents": 3000,
            "method": "check",
            "received_on": "2026-09-06",
            "idempotency_key": "reconcile-check-partial-001",
            "external_reference": "CHECK-RECON-001",
            "allocations": [{"invoice_id": i2["id"], "amount_cents": 3000}],
        },
    )
    assert check["method"] == "check"
    check_invoice = client.get(f"/api/academy/invoices/{i2['id']}").json()
    assert check_invoice["status"] == "partially_paid"
    assert int(check_invoice["amount_paid_cents"]) == 3000
    assert int(check_invoice["balance_due_cents"]) == 4500


def test_reconcile_qa_070_payment_method_default_replace_remove_and_ownership():
    _reset_shared_postgres_state()

    profile = client.put("/api/academy/profile", json={"name": "Track A Payment Method Academy"})
    assert profile.status_code == 200, profile.text

    bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"display_name": "Track A Owner", "email": "tracka.owner@example.test", "password": "TrackAOwner!123"},
        headers={"X-CAM-Bootstrap": "track-a-reconcile-bootstrap"},
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_token = bootstrap.json()["token"]

    def create_parent(suffix: str):
        player = _post(
            "/api/academy/players",
            {
                "name": f"{suffix} Player",
                "status": "active",
                "guardians": [
                    {
                        "first_name": suffix,
                        "last_name": "Parent",
                        "relationship": "Parent",
                        "email": f"{suffix.lower()}@example.test",
                        "is_primary": True,
                        "billing_contact": True,
                        "pickup_authorized": True,
                    }
                ],
            },
            owner_token,
        )
        guardian_id = int(player["guardians"][0]["id"])
        user = _post(
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
        login = _post("/api/auth/login", {"email": user["email"], "password": "ParentPortal!123"})
        return login["token"]

    parent_a = create_parent("Alpha")
    parent_b = create_parent("Beta")

    first = _post(
        "/api/academy/parent/payment-methods/sandbox",
        {"card_number": "4242 4242 4242 4242", "exp_month": 12, "exp_year": 2034, "cvc": "123", "make_default": True},
        parent_a,
    )
    second = _post(
        "/api/academy/parent/payment-methods/sandbox",
        {"card_number": "4000 0000 0000 0341", "exp_month": 11, "exp_year": 2034, "cvc": "321", "make_default": False},
        parent_a,
    )
    assert first["is_default"] is True
    assert second["is_default"] is False

    # Switch the default to the replacement method.
    set_default = client.put(
        f"/api/academy/parent/payment-methods/{second['id']}/default",
        headers=_auth(parent_a),
    )
    assert set_default.status_code == 200, set_default.text
    assert set_default.json()["is_default"] is True
    methods = client.get("/api/academy/parent/payment-methods", headers=_auth(parent_a)).json()["payment_methods"]
    by_id = {int(row["id"]): row for row in methods}
    assert by_id[int(second["id"])]["is_default"] is True
    assert by_id[int(first["id"])]["is_default"] is False

    # Another parent cannot manipulate this parent's saved methods.
    foreign_default = client.put(
        f"/api/academy/parent/payment-methods/{first['id']}/default",
        headers=_auth(parent_b),
    )
    assert foreign_default.status_code == 404

    # Removing the default promotes the remaining active method automatically.
    removed = client.delete(
        f"/api/academy/parent/payment-methods/{second['id']}",
        headers=_auth(parent_a),
    )
    assert removed.status_code == 204
    methods_after = client.get("/api/academy/parent/payment-methods", headers=_auth(parent_a)).json()["payment_methods"]
    assert len(methods_after) == 1
    assert int(methods_after[0]["id"]) == int(first["id"])
    assert methods_after[0]["is_default"] is True
