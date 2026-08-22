import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-payments-api-test-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _post(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _setup_family(prefix: str, *, overpayment_allowed: bool = True):
    client.put("/api/cam/profile", json={"name": f"{prefix} Academy"})
    p1 = _post("/api/cam/players", {"name": f"{prefix} Aarav", "status": "active"})
    p2 = _post("/api/cam/players", {"name": f"{prefix} Maya", "status": "active"})
    program = _post("/api/cam/programs", {"name": f"{prefix} U15", "program_type": "group", "status": "active"})
    e1 = _post("/api/cam/enrollments", {"player_id": p1["id"], "program_id": program["id"], "enrollment_type": "regular", "start_date": "2026-09-01"})
    e2 = _post("/api/cam/enrollments", {"player_id": p2["id"], "program_id": program["id"], "enrollment_type": "regular", "start_date": "2026-09-01"})
    plan = _post(
        "/api/cam/fee-plans",
        {"name": f"{prefix} Monthly 200", "amount_cents": 20000, "currency": "USD", "billing_frequency": "monthly", "due_day_of_month": 1, "program_id": program["id"], "status": "active"},
    )
    for enrollment in (e1, e2):
        response = client.put(f"/api/cam/enrollments/{enrollment['id']}/billing", json={"fee_plan_id": plan["id"], "discount_type": "none", "discount_value": 0})
        assert response.status_code == 200, response.text
    account = _post(
        "/api/cam/billing-accounts",
        {"account_name": f"{prefix} Family", "player_ids": [p1["id"], p2["id"]], "overpayment_allowed": overpayment_allowed, "status": "active"},
    )
    i1 = _post("/api/cam/invoices/from-enrollment", {"account_id": account["id"], "enrollment_id": e1["id"], "issue_date": "2026-09-01", "due_date": "2026-09-15"})
    i2 = _post("/api/cam/invoices/from-enrollment", {"account_id": account["id"], "enrollment_id": e2["id"], "issue_date": "2026-09-01", "due_date": "2026-09-15"})
    return {"players": (p1, p2), "enrollments": (e1, e2), "account": account, "invoices": (i1, i2)}


def test_payment_lifecycle_full_partial_credit_refund_receipt_idempotency_and_family_reconciliation():
    data = _setup_family("PayAPI")
    p1, p2 = data["players"]
    account = data["account"]
    i1, i2 = data["invoices"]
    account_id = int(account["id"])

    # AM-PAY-002 + AM-PAY-005: partial manual cash payment leaves exact remaining balance.
    partial = _post(
        "/api/cam/payments",
        {
            "account_id": account_id,
            "amount_cents": 8000,
            "method": "cash",
            "received_on": "2026-09-05",
            "idempotency_key": "api-partial-cash-001",
            "notes": "Front desk cash",
            "allocations": [{"invoice_id": i1["id"], "amount_cents": 8000}],
        },
    )
    assert partial["method"] == "cash"
    assert int(partial["allocated_cents"]) == 8000
    invoice1_partial = client.get(f"/api/cam/invoices/{i1['id']}").json()
    assert invoice1_partial["status"] == "partially_paid"
    assert int(invoice1_partial["amount_paid_cents"]) == 8000
    assert int(invoice1_partial["balance_due_cents"]) == 12000

    # AM-PAY-001 + AM-PAY-005: manual check completes the invoice.
    final = _post(
        "/api/cam/payments",
        {
            "account_id": account_id,
            "amount_cents": 12000,
            "method": "check",
            "received_on": "2026-09-06",
            "idempotency_key": "api-final-check-001",
            "external_reference": "CHECK-1042",
            "allocations": [{"invoice_id": i1["id"], "amount_cents": 12000}],
        },
    )
    invoice1_paid = client.get(f"/api/cam/invoices/{i1['id']}").json()
    assert invoice1_paid["status"] == "paid"
    assert int(invoice1_paid["balance_due_cents"]) == 0

    # AM-PAY-006: deterministic receipt links account, invoice, player, amount, method and date.
    receipt = client.get(f"/api/cam/payments/{final['id']}/receipt")
    assert receipt.status_code == 200, receipt.text
    receipt_json = receipt.json()
    assert receipt_json["receipt_number"].startswith("RCT-")
    assert receipt_json["account_name"] == "PayAPI Family"
    assert int(receipt_json["amount_cents"]) == 12000
    assert receipt_json["method"] == "check"
    assert receipt_json["received_on"] == "2026-09-06"
    assert receipt_json["allocations"][0]["invoice_number"] == i1["invoice_number"]
    assert receipt_json["allocations"][0]["player_name"] == p1["name"]

    # AM-PAY-008: exact retry with same idempotency key returns same transaction, not a duplicate.
    retry = client.post(
        "/api/cam/payments",
        json={
            "account_id": account_id,
            "amount_cents": 12000,
            "method": "check",
            "received_on": "2026-09-06",
            "idempotency_key": "api-final-check-001",
            "external_reference": "CHECK-1042",
            "allocations": [{"invoice_id": i1["id"], "amount_cents": 12000}],
        },
    )
    assert retry.status_code in (200, 201), retry.text
    assert int(retry.json()["id"]) == int(final["id"])
    family_payments = client.get(f"/api/cam/payments?account_id={account_id}").json()
    assert len(family_payments) == 2
    changed_retry = client.post(
        "/api/cam/payments",
        json={
            "account_id": account_id,
            "amount_cents": 11000,
            "method": "check",
            "received_on": "2026-09-06",
            "idempotency_key": "api-final-check-001",
            "allocations": [{"invoice_id": i1["id"], "amount_cents": 11000}],
        },
    )
    assert changed_retry.status_code == 409

    # AM-PAY-003: $250 against $200 invoice creates $50 family credit, never negative invoice balance.
    overpay = _post(
        "/api/cam/payments",
        {
            "account_id": account_id,
            "amount_cents": 25000,
            "method": "card",
            "received_on": "2026-09-07",
            "idempotency_key": "api-overpay-card-001",
            "external_reference": "CARD-SETTLED-001",
            "allocations": [{"invoice_id": i2["id"], "amount_cents": 20000}],
        },
    )
    assert int(overpay["unapplied_cents"]) == 5000
    invoice2_paid = client.get(f"/api/cam/invoices/{i2['id']}").json()
    assert invoice2_paid["status"] == "paid"
    assert int(invoice2_paid["balance_due_cents"]) == 0
    ledger_credit = client.get(f"/api/cam/billing-accounts/{account_id}/ledger").json()
    assert int(ledger_credit["outstanding_cents"]) == 0
    assert int(ledger_credit["credit_cents"]) == 5000
    assert int(ledger_credit["net_balance_cents"]) == -5000

    # AM-PAY-004: refund consumes credit first, then reverses allocation and reopens invoice correctly.
    refunded = _post(
        f"/api/cam/payments/{overpay['id']}/refunds",
        {
            "amount_cents": 7000,
            "refunded_on": "2026-09-08",
            "reason": "Family requested refund",
            "idempotency_key": "api-refund-overpay-001",
        },
    )
    payment_after_refund = refunded["payment"]
    assert int(payment_after_refund["refunded_cents"]) == 7000
    assert int(payment_after_refund["unapplied_cents"]) == 0
    assert payment_after_refund["status"] == "partially_refunded"
    invoice2_reopened = client.get(f"/api/cam/invoices/{i2['id']}").json()
    assert invoice2_reopened["status"] == "partially_paid"
    assert int(invoice2_reopened["amount_paid_cents"]) == 18000
    assert int(invoice2_reopened["balance_due_cents"]) == 2000
    refund_retry = client.post(
        f"/api/cam/payments/{overpay['id']}/refunds",
        json={"amount_cents": 7000, "refunded_on": "2026-09-08", "reason": "Family requested refund", "idempotency_key": "api-refund-overpay-001"},
    )
    assert refund_retry.status_code in (200, 201)
    assert int(refund_retry.json()["refund"]["id"]) == int(refunded["refund"]["id"])

    # AM-PAY-009: family reconciliation spans both players/invoices/payments after refund.
    ledger = client.get(f"/api/cam/billing-accounts/{account_id}/ledger")
    assert ledger.status_code == 200, ledger.text
    ledger_json = ledger.json()
    assert len(ledger_json["invoices"]) == 2
    assert len(ledger_json["payments"]) == 3
    assert int(ledger_json["outstanding_cents"]) == 2000
    assert int(ledger_json["credit_cents"]) == 0
    assert int(ledger_json["net_balance_cents"]) == 2000
    assert {row["invoice_number"] for row in ledger_json["invoices"]} == {i1["invoice_number"], i2["invoice_number"]}
    assert p2["name"] != p1["name"]


def test_excess_payment_is_rejected_when_family_disallows_overpayment():
    # AM-PAY-007: payment above invoice amount is rejected when family credit is disabled.
    data = _setup_family("NoOverpayAPI", overpayment_allowed=False)
    account = data["account"]
    invoice = data["invoices"][0]
    response = client.post(
        "/api/cam/payments",
        json={
            "account_id": account["id"],
            "amount_cents": 21000,
            "method": "card",
            "received_on": "2026-09-05",
            "idempotency_key": "api-no-overpay-001",
            "allocations": [{"invoice_id": invoice["id"], "amount_cents": 20000}],
        },
    )
    assert response.status_code == 409
    assert "does not allow" in response.json()["detail"].lower()
    unchanged = client.get(f"/api/cam/invoices/{invoice['id']}").json()
    assert unchanged["status"] == "open"
    assert int(unchanged["amount_paid_cents"]) == 0
    assert client.get(f"/api/cam/payments?account_id={account['id']}").json() == []
