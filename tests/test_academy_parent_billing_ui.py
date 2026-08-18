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
BASE_URL = "http://127.0.0.1:8785"


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
    raise RuntimeError(f"CAM parent billing test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict | None = None, headers: dict | None = None):
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else None


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _reset_shared_postgres_state(env: dict[str, str]) -> None:
    database_url = env.get("DATABASE_URL", "").strip()
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


def test_parent_portal_login_add_card_partial_payment_and_receipt():
    data_dir = tempfile.mkdtemp(prefix="cam-parent-billing-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["CAM_BOOTSTRAP_TOKEN"] = "parent-ui-bootstrap"
    env["CAM_PAYMENT_MODE"] = "sandbox"
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8785"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _reset_shared_postgres_state(env)

        _json_request("PUT", "/api/academy/profile", {"name": "Parent Portal UI Academy"})
        player = _json_request(
            "POST",
            "/api/academy/players",
            {
                "name": "UI Aarav Patel",
                "status": "active",
                "guardians": [
                    {
                        "first_name": "Priya",
                        "last_name": "Patel",
                        "relationship": "Mother",
                        "email": "priya.ui@example.test",
                        "phone": "4045550134",
                        "is_primary": True,
                        "billing_contact": True,
                        "pickup_authorized": True,
                    }
                ],
            },
        )
        guardian_id = int(player["guardians"][0]["id"])
        program = _json_request(
            "POST",
            "/api/academy/programs",
            {"name": "UI U13 Program", "program_type": "group", "status": "active"},
        )
        enrollment = _json_request(
            "POST",
            "/api/academy/enrollments",
            {
                "player_id": player["id"],
                "program_id": program["id"],
                "enrollment_type": "regular",
                "start_date": "2026-09-01",
            },
        )
        fee_plan = _json_request(
            "POST",
            "/api/academy/fee-plans",
            {
                "name": "UI U13 Monthly 175",
                "amount_cents": 17500,
                "currency": "USD",
                "billing_frequency": "monthly",
                "due_day_of_month": 1,
                "program_id": program["id"],
                "status": "active",
            },
        )
        account = _json_request(
            "POST",
            "/api/academy/billing-accounts",
            {
                "account_name": "Patel UI Family",
                "player_ids": [player["id"]],
                "primary_guardian_id": guardian_id,
                "overpayment_allowed": True,
                "status": "active",
            },
        )
        _json_request(
            "PUT",
            f"/api/academy/enrollments/{enrollment['id']}/billing",
            {"fee_plan_id": fee_plan["id"], "discount_type": "none", "discount_value": 0},
        )
        invoice = _json_request(
            "POST",
            "/api/academy/invoices/from-enrollment",
            {
                "account_id": account["id"],
                "enrollment_id": enrollment["id"],
                "issue_date": "2026-09-01",
                "due_date": "2026-09-15",
            },
        )

        bootstrap = _json_request(
            "POST",
            "/api/auth/bootstrap",
            {"display_name": "UI Academy Owner", "email": "owner.ui.billing@example.test", "password": "OwnerUIBilling!123"},
            {"X-CAM-Bootstrap": "parent-ui-bootstrap"},
        )
        owner_token = bootstrap["token"]
        _json_request(
            "POST",
            "/api/academy/access/users",
            {
                "display_name": "Priya Patel",
                "email": "parent.qa@cam.test",
                "password": "ParentTest!123",
                "role": "parent",
                "guardian_id": guardian_id,
                "status": "active",
            },
            _auth(owner_token),
        )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1100})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=parent", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Parent Portal")).to_be_visible(timeout=15000)
                expect(page.locator("#academyParentLoginForm")).to_be_visible()

                login = page.locator("#academyParentLoginForm")
                login.locator('[name="email"]').fill("parent.qa@cam.test")
                login.locator('[name="password"]').fill("ParentTest!123")
                login.get_by_role("button", name="Sign In").click()

                expect(page.locator(".academy-parent-children").get_by_text("UI Aarav Patel", exact=True)).to_be_visible(timeout=15000)
                expect(page.get_by_text("$175.00", exact=True).first).to_be_visible()
                expect(page.get_by_text(invoice["invoice_number"], exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Add Test Card")).to_be_visible()

                page.get_by_role("button", name="Add Test Card").click()
                card_form = page.locator("#academySandboxCardForm")
                expect(card_form).to_be_visible()
                card_form.locator('[name="card_number"]').fill("4242 4242 4242 4242")
                card_form.locator('[name="exp_month"]').fill("12")
                card_form.locator('[name="exp_year"]').fill("2034")
                card_form.locator('[name="cvc"]').fill("123")
                card_form.get_by_role("button", name="Save Test Card").click()

                expect(page.get_by_text("Visa •••• 4242", exact=True)).to_be_visible(timeout=10000)
                expect(page.get_by_text("Default", exact=True)).to_be_visible()
                expect(page.get_by_text("4242 4242 4242 4242", exact=True)).to_have_count(0)

                page.get_by_role("button", name="Pay invoice").click()
                pay_form = page.locator("#academyParentPayForm")
                expect(pay_form).to_be_visible()
                pay_form.locator('[name="amount"]').fill("100.00")
                pay_form.get_by_role("button", name="Pay $175.00").click()

                expect(page.get_by_text("$75.00 remaining", exact=True)).to_be_visible(timeout=10000)
                expect(page.get_by_text("$100.00", exact=True).first).to_be_visible()
                receipt_button = page.locator('[data-view-receipt]').first
                expect(receipt_button).to_be_visible()
                receipt_number = receipt_button.inner_text()
                assert receipt_number.startswith("RCT-")

                receipt_button.click()
                receipt_panel = page.locator(".academy-parent-receipt")
                expect(receipt_panel.get_by_role("heading", name=receipt_number)).to_be_visible(timeout=10000)
                expect(receipt_panel.get_by_text("Payment received", exact=True)).to_be_visible()
                expect(receipt_panel.get_by_text("$100.00", exact=True)).to_be_visible()
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-parent-billing-ui-failure.png", full_page=True)
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
