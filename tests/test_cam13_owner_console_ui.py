import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8793"
SESSION_KEY = "cam-academy-session-v1"


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
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
    raise RuntimeError(f"CAM-13 test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload=None, headers=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise AssertionError(f"{method} {path} failed: {exc.code} {detail}") from exc


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _reset_postgres_if_needed(env: dict[str, str]) -> None:
    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


def test_owner_admin_console_has_clean_navigation_and_contextual_workflows():
    data_dir = tempfile.mkdtemp(prefix="cam13-owner-ui-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["CAM_BOOTSTRAP_TOKEN"] = "cam13-ui-bootstrap"
    env["CAM_PAYMENT_MODE"] = "sandbox"
    env["PYTHONPATH"] = str(REPO_ROOT)
    _reset_postgres_if_needed(env)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8793"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/academy/profile", {"name": "Owner Console Academy", "timezone": "America/New_York"})
        bootstrap = _json_request(
            "POST",
            "/api/auth/bootstrap",
            {
                "display_name": "Academy Owner",
                "email": "owner.cam13.ui@example.test",
                "password": "OwnerCam13UI!123",
            },
            {"X-CAM-Bootstrap": "cam13-ui-bootstrap"},
        )
        token = bootstrap["token"]
        headers = _auth(token)

        player = _json_request(
            "POST",
            "/api/academy/players",
            {
                "name": "Aarav Owner Console",
                "first_name": "Aarav",
                "last_name": "Patel",
                "joined_on": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
                "status": "active",
                "guardians": [
                    {
                        "first_name": "Priya",
                        "last_name": "Patel",
                        "relationship": "Mother",
                        "email": "priya.cam13.ui@example.test",
                        "phone": "+1-404-555-0101",
                        "is_primary": True,
                        "billing_contact": True,
                        "pickup_authorized": True,
                    }
                ],
            },
            headers,
        )
        coach = _json_request(
            "POST",
            "/api/academy/coaches",
            {"first_name": "Ravi", "last_name": "Coach", "status": "active"},
            headers,
        )
        _json_request(
            "POST",
            "/api/academy/sessions/private",
            {
                "player_id": player["id"],
                "coach_id": coach["id"],
                "session_date": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
                "start_time": "18:00",
                "duration_minutes": 60,
                "location": "Indoor Center",
            },
            headers,
        )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            try:
                page.goto(BASE_URL, wait_until="domcontentloaded")
                page.evaluate("([key,value]) => sessionStorage.setItem(key,value)", [SESSION_KEY, token])
                page.goto(f"{BASE_URL}/#academy", wait_until="domcontentloaded")

                owner_tabs = page.locator("#academyWorkspace .academy-tabs [data-owner-console-tab]:visible")
                expect(owner_tabs).to_have_count(7, timeout=20000)
                assert owner_tabs.all_text_contents() == [
                    "Dashboard",
                    "Players",
                    "Programs",
                    "Coaches",
                    "Finance",
                    "Reports",
                    "Settings",
                ]

                page.get_by_role("button", name="Programs", exact=True).click()
                expect(page.get_by_role("heading", name="Programs & Enrollment")).to_be_visible(timeout=15000)
                context = page.locator(".academy-owner-context-nav")
                expect(context).to_be_visible(timeout=10000)
                assert context.locator("button").all_text_contents() == [
                    "Programs & Enrollment",
                    "Batches & Sessions",
                    "Matches",
                    "Tournaments",
                ]

                page.get_by_role("button", name="Settings", exact=True).click()
                expect(page.get_by_role("heading", name="Settings", exact=True)).to_be_visible(timeout=10000)
                expect(page.get_by_role("button", name="Academy Profile")).to_be_visible()
                expect(page.get_by_role("button", name="Access & Roles")).to_be_visible()
                expect(page.get_by_role("button", name="Fee Setup")).to_be_visible()
                expect(page.get_by_role("button", name="Integrations")).to_be_visible()

                page.get_by_role("button", name="Players", exact=True).click()
                expect(page.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)
                expect(page.get_by_role("button", name="Player 360", exact=True)).to_be_visible(timeout=10000)
                page.get_by_role("button", name="Player 360", exact=True).click()
                expect(page.locator(".academy-owner-player360")).to_be_visible(timeout=15000)
                expect(page.get_by_role("heading", name="Aarav Owner Console", exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name="Parents & Guardians", exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name="CricClubs Profile", exact=True)).to_be_visible()

                page.get_by_role("button", name="Dashboard", exact=True).click()
                expect(page.locator("#academyOwnerSnapshot")).to_be_visible(timeout=15000)
                expect(page.get_by_role("heading", name="Batch Breakdown", exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name="New Player Registrations", exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name="Current Month Academy Outgoings", exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Reschedule", exact=True)).to_be_visible(timeout=10000)
                expect(page.get_by_role("button", name="Cancel", exact=True)).to_be_visible(timeout=10000)

                page.get_by_role("button", name="Reschedule", exact=True).click()
                expect(page.get_by_role("heading", name="Reschedule Session", exact=True)).to_be_visible(timeout=10000)
                expect(page.get_by_text("Mobile push", exact=True)).to_be_visible()
                expect(page.get_by_text("WhatsApp", exact=True)).to_be_visible()
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
