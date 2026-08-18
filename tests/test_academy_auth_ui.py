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
BASE_URL = "http://127.0.0.1:8782"


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
    raise RuntimeError(f"CAM access test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_academy_access_roles_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="cam-access-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["CAM_BOOTSTRAP_TOKEN"] = "ui-bootstrap-key"
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8782"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/academy/profile", {"name": "Access UI Academy"})
        coach = _json_request(
            "POST",
            "/api/academy/coaches",
            {"first_name": "Maya", "last_name": "Shah", "email": "maya@example.test", "status": "active"},
        )
        player = _json_request(
            "POST",
            "/api/academy/players",
            {
                "name": "Access UI Aarav",
                "status": "active",
                "guardians": [
                    {
                        "first_name": "Neha",
                        "last_name": "Shah",
                        "relationship": "Parent",
                        "email": "neha@example.test",
                        "is_primary": True,
                        "billing_contact": True,
                    }
                ],
            },
        )
        guardian_id = int(player["guardians"][0]["id"])
        assert int(coach["id"]) > 0
        assert guardian_id > 0

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1150})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=access", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Access & Roles")).to_be_visible(timeout=15000)
                expect(page.locator("#academyBootstrapForm")).to_be_visible()
                expect(page.get_by_text("Bootstrap is configured on the server.")).to_be_visible()

                bootstrap = page.locator("#academyBootstrapForm")
                bootstrap.locator('[name="display_name"]').fill("UI Academy Owner")
                bootstrap.locator('[name="email"]').fill("ui-owner@example.test")
                bootstrap.locator('[name="password"]').fill("OwnerUIPass!123")
                bootstrap.locator('[name="bootstrap_token"]').fill("ui-bootstrap-key")
                bootstrap.get_by_role("button", name="Create Owner Account").click()

                expect(page.get_by_text("Signed in as")).to_be_visible(timeout=10000)
                expect(page.get_by_text("UI Academy Owner")).to_be_visible()
                expect(page.locator("#academyAddAccessUser")).to_be_visible()
                expect(page.locator(".academy-access-role-card")).to_have_count(5)
                expect(page.locator(".academy-access-user-row", has_text="ui-owner@example.test")).to_be_visible()

                # Create a coach account and link it to the actual coach record.
                page.locator("#academyAddAccessUser").click()
                form = page.locator("#academyAccessUserForm")
                expect(form).to_be_visible()
                form.locator('[name="display_name"]').fill("Coach Maya")
                form.locator('[name="email"]').fill("coach-ui@example.test")
                form.locator('[name="password"]').fill("CoachUIPass!123")
                form.locator('[name="role"]').select_option("coach")
                expect(form.locator('[name="linked_id"]')).to_contain_text("Maya Shah")
                form.locator('[name="linked_id"]').select_option(str(coach["id"]))
                form.get_by_role("button", name="Create Access User").click()

                coach_row = page.locator(".academy-access-user-row", has_text="coach-ui@example.test")
                expect(coach_row).to_be_visible(timeout=10000)
                expect(coach_row).to_contain_text("Coach")
                expect(coach_row).to_contain_text("Linked: Maya Shah")

                # Create a parent account and link it to the real guardian record.
                page.locator("#academyAddAccessUser").click()
                parent_form = page.locator("#academyAccessUserForm")
                parent_form.locator('[name="display_name"]').fill("Parent Neha")
                parent_form.locator('[name="email"]').fill("parent-ui@example.test")
                parent_form.locator('[name="password"]').fill("ParentUIPass!123")
                parent_form.locator('[name="role"]').select_option("parent")
                expect(parent_form.locator('[name="linked_id"]')).to_contain_text("Neha Shah")
                parent_form.locator('[name="linked_id"]').select_option(str(guardian_id))
                parent_form.get_by_role("button", name="Create Access User").click()

                parent_row = page.locator(".academy-access-user-row", has_text="parent-ui@example.test")
                expect(parent_row).to_be_visible(timeout=10000)
                expect(parent_row).to_contain_text("Parent")
                expect(parent_row).to_contain_text("Linked: Neha Shah")

                expect(page.locator(".academy-access-audit-row")).to_have_count(3)

                # Non-admin roles can authenticate and see only their own access profile.
                page.locator("#academyAccessLogout").click()
                expect(page.locator("#academyLoginForm")).to_be_visible(timeout=10000)
                login = page.locator("#academyLoginForm")
                login.locator('[name="email"]').fill("coach-ui@example.test")
                login.locator('[name="password"]').fill("CoachUIPass!123")
                login.get_by_role("button", name="Sign In").click()

                expect(page.get_by_text("YOUR ACADEMY ACCESS")).to_be_visible(timeout=10000)
                expect(page.get_by_role("heading", name="Coach Maya")).to_be_visible()
                expect(page.get_by_text("Linked Academy identity: Maya Shah")).to_be_visible()
                expect(page.locator("#academyAddAccessUser")).to_have_count(0)
                expect(page.get_by_text("reviews · manage")).to_be_visible()
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-access-ui-failure.png", full_page=True)
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
