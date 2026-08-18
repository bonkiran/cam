import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8780"


def _wait_for_server(url: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"CrickAnalysis payments UI server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _setup(tag: str):
    _json_request("PUT", "/api/academy/profile", {"name": f"Payment UI Academy {tag}"})
    p1 = _json_request("POST", "/api/academy/players", {"name": f"UI Pay Aarav {tag}", "status": "active"})
    p2 = _json_request("POST", "/api/academy/players", {"name": f"UI Pay Maya {tag}", "status": "active"})
    program = _json_request("POST", "/api/academy/programs", {"name": f"UI Pay U15 {tag}", "program_type": "group", "status": "active"})
    e1 = _json_request("POST", "/api/academy/enrollments", {"player_id": p1["id"], "program_id": program["id"], "enrollment_type": "regular", "start_date": "2026-09-01"})
    e2 = _json_request("POST", "/api/academy/enrollments", {"player_id": p2["id"], "program_id": program["id"], "enrollment_type": "regular", "start_date": "2026-09-01"})
    plan = _json_request("POST", "/api/academy/fee-plans", {"name": f"UI Pay Monthly 200 {tag}", "amount_cents": 20000, "billing_frequency": "monthly", "due_day_of_month": 1, "program_id": program["id"], "status": "active"})
    for enrollment in (e1, e2):
        _json_request("PUT", f"/api/academy/enrollments/{enrollment['id']}/billing", {"fee_plan_id": plan["id"], "discount_type": "none", "discount_value": 0})
    account = _json_request("POST", "/api/academy/billing-accounts", {"account_name": f"UI Pay Family {tag}", "player_ids": [p1["id"], p2["id"]], "overpayment_allowed": True, "status": "active"})
    i1 = _json_request("POST", "/api/academy/invoices/from-enrollment", {"account_id": account["id"], "enrollment_id": e1["id"], "issue_date": "2026-09-01", "due_date": "2026-09-15"})
    i2 = _json_request("POST", "/api/academy/invoices/from-enrollment", {"account_id": account["id"], "enrollment_id": e2["id"], "issue_date": "2026-09-01", "due_date": "2026-09-15"})
    return p1, p2, account, i1, i2


def _post_payment(page, account_id, invoice_id, amount, method, reference=""):
    page.locator("#openPaymentForm").click()
    form = page.locator("#academyPaymentForm")
    expect(form).to_be_visible()
    form.locator('[name="account_id"]').select_option(str(account_id))
    form.locator('[name="invoice_id"]').select_option(str(invoice_id))
    form.locator('[name="amount_dollars"]').fill(amount)
    form.locator('[name="method"]').select_option(method)
    form.locator('[name="received_on"]').fill("2026-09-05")
    if reference:
        form.locator('[name="external_reference"]').fill(reference)
    form.get_by_role("button", name="Post Payment").click()
    expect(page.locator("#academyPaymentForm")).to_have_count(0, timeout=10000)


def test_payment_ledger_ui_partial_full_credit_receipt_refund_and_reconciliation():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-payments-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)
    tag = uuid.uuid4().hex[:8]
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8780"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        p1, p2, account, i1, i2 = _setup(tag)
        account_id = int(account["id"])
        account_name = account["account_name"]
        cash_ref = f"CASH-{tag}"
        check_ref = f"CHECK-{tag}"
        card_ref = f"CARD-{tag}"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=fees", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Fees & Payments")).to_be_visible(timeout=15000)
                expect(page.locator("#openPaymentForm")).to_be_visible(timeout=15000)

                _post_payment(page, account_id, i1["id"], "80.00", "cash", cash_ref)
                partial_row = page.locator(".academy-payment-row", has_text=cash_ref)
                expect(partial_row).to_be_visible(timeout=10000)
                expect(partial_row).to_contain_text("$80.00")
                expect(partial_row).to_contain_text("cash")
                invoice1 = page.evaluate("async (id) => await (await fetch(`/api/academy/invoices/${id}`)).json()", i1["id"])
                assert invoice1["status"] == "partially_paid"
                assert int(invoice1["balance_due_cents"]) == 12000

                _post_payment(page, account_id, i1["id"], "120.00", "check", check_ref)
                check_row = page.locator(".academy-payment-row", has_text=check_ref)
                expect(check_row).to_be_visible(timeout=10000)
                check_row.get_by_role("button", name="Receipt").click()
                receipt = page.locator(".academy-payment-receipt")
                expect(receipt).to_be_visible()
                expect(receipt).to_contain_text("$120.00")
                expect(receipt).to_contain_text(i1["invoice_number"])
                expect(receipt).to_contain_text(p1["name"])
                expect(receipt).to_contain_text("check")
                receipt.get_by_role("button", name="Close").click()
                invoice1 = page.evaluate("async (id) => await (await fetch(`/api/academy/invoices/${id}`)).json()", i1["id"])
                assert invoice1["status"] == "paid"
                assert int(invoice1["balance_due_cents"]) == 0

                _post_payment(page, account_id, i2["id"], "250.00", "card", card_ref)
                overpay_row = page.locator(".academy-payment-row", has_text=card_ref)
                expect(overpay_row).to_be_visible(timeout=10000)
                expect(overpay_row).to_contain_text("Credit $50.00")
                ledger_row = page.locator(".academy-ledger-row", has_text=account_name)
                expect(ledger_row).to_contain_text("Credit $50.00", timeout=10000)
                expect(ledger_row).to_contain_text("Net -$50.00")

                overpay_row.get_by_role("button", name="Refund").click()
                refund_form = page.locator("#academyRefundForm")
                expect(refund_form).to_be_visible()
                refund_form.locator('[name="amount_dollars"]').fill("70.00")
                refund_form.locator('[name="refunded_on"]').fill("2026-09-08")
                refund_form.locator('[name="reason"]').fill("UI family refund")
                refund_form.get_by_role("button", name="Post Refund").click()
                expect(page.locator("#academyRefundForm")).to_have_count(0, timeout=10000)
                overpay_row = page.locator(".academy-payment-row", has_text=card_ref)
                expect(overpay_row).to_contain_text("Refunded $70.00", timeout=10000)
                ledger_row = page.locator(".academy-ledger-row", has_text=account_name)
                expect(ledger_row).to_contain_text("Outstanding $20.00")
                expect(ledger_row).to_contain_text("Credit $0.00")
                expect(ledger_row).to_contain_text("Net $20.00")

                invoice2 = page.evaluate("async (id) => await (await fetch(`/api/academy/invoices/${id}`)).json()", i2["id"])
                assert invoice2["status"] == "partially_paid"
                assert int(invoice2["amount_paid_cents"]) == 18000
                assert int(invoice2["balance_due_cents"]) == 2000

                ledger = page.evaluate("async (id) => await (await fetch(`/api/academy/billing-accounts/${id}/ledger`)).json()", account_id)
                assert len(ledger["invoices"]) == 2
                assert int(ledger["outstanding_cents"]) == 2000
                assert int(ledger["credit_cents"]) == 0
                assert int(ledger["net_balance_cents"]) == 2000
                assert p1["name"] != p2["name"]
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-payments-ui-failure.png", full_page=True)
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
