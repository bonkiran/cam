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
BASE_URL = "http://127.0.0.1:8786"
SESSION_KEY = "cam-cam-session-v1"


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
    raise RuntimeError(f"CAM RBAC test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict | None = None, headers: dict | None = None):
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else None


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _set_session(page, token: str) -> None:
    # Establish the app origin before writing sessionStorage. The unauthenticated
    # Dashboard now completes by rendering its explicit authentication-required
    # state, so wait for that render to settle before changing routes. This keeps
    # a slow dashboard response from overwriting the next Academy tab.
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator("#camWorkspace .cam-tabs")).to_be_visible(timeout=15000)
    expect(page.get_by_text("Dashboard could not load: Authentication required", exact=True)).to_be_visible(timeout=15000)
    page.evaluate("([key,value]) => sessionStorage.setItem(key,value)", [SESSION_KEY, token])


def _reset_shared_postgres_state(env: dict[str, str]) -> None:
    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "academy_billing_security_audit",
        "academy_saved_payment_methods",
        "academy_review_actions",
        "academy_player_reviews",
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


def test_owner_browser_gets_session_aware_management_parent_does_not():
    data_dir = tempfile.mkdtemp(prefix="cam-rbac-enforcement-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["CAM_BOOTSTRAP_TOKEN"] = "rbac-ui-bootstrap"
    env["CAM_PAYMENT_MODE"] = "sandbox"
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8786"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _reset_shared_postgres_state(env)

        _json_request("PUT", "/api/cam/profile", {"name": "RBAC UI Academy"})
        player = _json_request(
            "POST",
            "/api/cam/players",
            {
                "name": "RBAC UI Aarav",
                "status": "active",
                "guardians": [
                    {
                        "first_name": "Priya",
                        "last_name": "Patel",
                        "relationship": "Mother",
                        "email": "priya.rbac.ui@example.test",
                        "is_primary": True,
                        "billing_contact": True,
                    }
                ],
            },
        )
        guardian_id = int(player["guardians"][0]["id"])

        bootstrap = _json_request(
            "POST",
            "/api/auth/bootstrap",
            {"display_name": "RBAC UI Owner", "email": "owner.rbac.ui@example.test", "password": "OwnerRBACUI!123"},
            {"X-CAM-Bootstrap": "rbac-ui-bootstrap"},
        )
        owner_token = bootstrap["token"]

        program = _json_request(
            "POST",
            "/api/cam/programs",
            {"name": "Secured U13 Program", "program_type": "group", "status": "active"},
            _auth(owner_token),
        )
        assert program["name"] == "Secured U13 Program"

        _json_request(
            "POST",
            "/api/cam/access/users",
            {
                "display_name": "Priya Patel",
                "email": "parent.rbac.ui@example.test",
                "password": "ParentRBACUI!123",
                "role": "parent",
                "guardian_id": guardian_id,
                "status": "active",
            },
            _auth(owner_token),
        )
        parent_login = _json_request(
            "POST",
            "/api/auth/login",
            {"email": "parent.rbac.ui@example.test", "password": "ParentRBACUI!123"},
        )
        parent_token = parent_login["token"]

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            owner_page = browser.new_page(viewport={"width": 1500, "height": 1000})
            anonymous_page = browser.new_page(viewport={"width": 1400, "height": 900})
            parent_page = browser.new_page(viewport={"width": 1400, "height": 900})
            try:
                # Existing Academy modules do not manually know about auth; the
                # shared fetch wrapper must attach the Owner session token.
                _set_session(owner_page, owner_token)
                owner_page.goto(f"{BASE_URL}/#cam?tab=programs", wait_until="domcontentloaded")
                expect(owner_page.get_by_role("heading", name="Programs & Enrollment")).to_be_visible(timeout=15000)
                expect(owner_page.get_by_text("Secured U13 Program", exact=True)).to_be_visible(timeout=10000)

                # No login-wall redirect: unauthenticated access stays on the
                # requested workspace and shows the API access state clearly.
                anonymous_page.goto(f"{BASE_URL}/#cam?tab=programs", wait_until="domcontentloaded")
                expect(anonymous_page.get_by_text("Authentication required", exact=True)).to_be_visible(timeout=15000)
                assert "cam?tab=programs" in anonymous_page.url

                # A valid Parent session is still forbidden from generic
                # management, but can use the dedicated Parent Portal. Use a
                # wording-stable substring so copy changes do not masquerade as
                # RBAC failures while the actual authorization state is preserved.
                _set_session(parent_page, parent_token)
                parent_page.goto(f"{BASE_URL}/#cam?tab=programs", wait_until="domcontentloaded")
                expect(parent_page.get_by_text("Owner or admin access is required for Academy management", exact=True)).to_be_visible(timeout=15000)
                parent_page.goto(f"{BASE_URL}/#cam?tab=parent", wait_until="domcontentloaded")
                expect(parent_page.get_by_role("heading", name="Parent Portal")).to_be_visible(timeout=15000)
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                owner_page.screenshot(path="test-results/cam-rbac-owner-ui-failure.png", full_page=True)
                anonymous_page.screenshot(path="test-results/cam-rbac-anonymous-ui-failure.png", full_page=True)
                parent_page.screenshot(path="test-results/cam-rbac-parent-ui-failure.png", full_page=True)
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
