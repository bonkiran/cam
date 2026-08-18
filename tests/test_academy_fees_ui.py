import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8779"


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
    raise RuntimeError(f"CrickAnalysis fees test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_fees_foundation_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-fees-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8779"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/academy/profile", {"name": "Fees UI Academy"})
        player = _json_request(
            "POST",
            "/api/academy/players",
            {
                "name": "UI Fees Aarav",
                "status": "active",
                "guardians": [{"first_name": "UI", "last_name": "Patel", "relationship": "Parent", "is_primary": True, "billing_contact": True}],
            },
        )
        program = _json_request("POST", "/api/academy/programs", {"name": "UI Fees U15", "program_type": "group", "status": "active"})
        enrollment = _json_request(
            "POST",
            "/api/academy/enrollments",
            {"player_id": player["id"], "program_id": program["id"], "enrollment_type": "regular", "start_date": "2026-09-01"},
        )
        assert enrollment["player_name"] == "UI Fees Aarav"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=fees", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Fees & Payments")).to_be_visible(timeout=15000)
                expect(page.locator("#openFeePlan")).to_be_visible()

                # AM-FEE-001: $200 monthly plan, due on the 1st.
                page.locator("#openFeePlan").click()
                fee_form = page.locator("#academyFeePlanForm")
                expect(fee_form).to_be_visible()
                fee_form.locator('[name="name"]').fill("UI U15 Monthly")
                fee_form.locator('[name="amount_dollars"]').fill("200.00")
                fee_form.locator('[name="billing_frequency"]').select_option("monthly")
                fee_form.locator('[name="due_day_of_month"]').fill("1")
                fee_form.locator('[name="program_id"]').select_option(str(program["id"]))
                fee_form.get_by_role("button", name="Create Fee Plan").click()
                fee_row = page.locator(".academy-fee-row", has_text="UI U15 Monthly").first
                expect(fee_row).to_be_visible(timeout=10000)
                expect(fee_row).to_contain_text("$200.00")
                expect(fee_row).to_contain_text("due day 1")
                expect(fee_row).to_contain_text("UI Fees U15")

                # AM-FEE-002: family billing account.
                page.locator("#openBillingAccount").click()
                account_form = page.locator("#academyBillingAccountForm")
                expect(account_form).to_be_visible()
                account_form.locator('[name="account_name"]').fill("UI Patel Family")
                account_form.locator(f'input[name="player_id"][value="{player["id"]}"]').check()
                guardian_id = player["guardians"][0]["id"]
                account_form.locator('[name="primary_guardian_id"]').select_option(str(guardian_id))
                account_form.get_by_role("button", name="Create Billing Account").click()
                account_row = page.locator(".academy-fee-row", has_text="UI Patel Family").first
                expect(account_row).to_be_visible(timeout=10000)
                expect(account_row).to_contain_text("UI Fees Aarav")
                expect(account_row).to_contain_text("$0.00")

                # AM-ENR-003/009 + AM-FEE-005: assign fee and 10% discount.
                page.locator("#openEnrollmentBilling").click()
                billing_form = page.locator("#academyEnrollmentBillingForm")
                expect(billing_form).to_be_visible()
                billing_form.locator('[name="enrollment_id"]').select_option(str(enrollment["id"]))
                fee_plan_id = page.evaluate("""
                    async () => (await (await fetch('/api/academy/fee-plans')).json()).find(x => x.name === 'UI U15 Monthly').id
                """)
                billing_form.locator('[name="fee_plan_id"]').select_option(str(fee_plan_id))
                billing_form.locator('[name="discount_type"]').select_option("percent")
                billing_form.locator('[name="discount_display"]').fill("10")
                billing_form.get_by_role("button", name="Save Enrollment Billing").click()
                configured_row = page.locator(".academy-fee-row", has_text="UI Fees Aarav · UI Fees U15")
                expect(configured_row).to_be_visible(timeout=10000)
                expect(configured_row).to_contain_text("UI U15 Monthly")
                expect(configured_row).to_contain_text("10%")

                # AM-FEE-003/004/005: generate two invoices; $200 - 10% = $180.
                account_id = page.evaluate("""
                    async () => (await (await fetch('/api/academy/billing-accounts')).json()).find(x => x.account_name === 'UI Patel Family').id
                """)
                for issue_date, due_date in (("2026-09-01", "2026-09-15"), ("2026-10-01", "2026-10-15")):
                    page.locator("#openInvoiceForm").click()
                    invoice_form = page.locator("#academyEnrollmentInvoiceForm")
                    expect(invoice_form).to_be_visible()
                    invoice_form.locator('[name="account_id"]').select_option(str(account_id))
                    invoice_form.locator('[name="enrollment_id"]').select_option(str(enrollment["id"]))
                    invoice_form.locator('[name="issue_date"]').fill(issue_date)
                    invoice_form.locator('[name="due_date"]').fill(due_date)
                    invoice_form.get_by_role("button", name="Generate Invoice").click()
                    expect(page.locator("#academyEnrollmentInvoiceForm")).to_have_count(0, timeout=10000)

                invoice_rows = page.locator(".academy-invoice-row", has_text="UI Patel Family")
                expect(invoice_rows).to_have_count(2)
                expect(invoice_rows.first).to_contain_text("$200.00")
                expect(invoice_rows.first).to_contain_text("$20.00")
                expect(invoice_rows.first).to_contain_text("$180.00")

                invoices = page.evaluate(
                    "async (id) => await (await fetch(`/api/academy/invoices?account_id=${id}`)).json()",
                    account_id,
                )
                numbers = [row["invoice_number"] for row in invoices]
                assert len(numbers) == len(set(numbers)) == 2
                assert all(int(row["subtotal_cents"]) == 20000 for row in invoices)
                assert all(int(row["discount_cents"]) == 2000 for row in invoices)
                assert all(int(row["total_cents"]) == 18000 for row in invoices)

                account = page.evaluate("async (id) => await (await fetch(`/api/academy/billing-accounts/${id}`)).json()", account_id)
                assert int(account["balance_cents"]) == 36000
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-fees-ui-failure.png", full_page=True)
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
