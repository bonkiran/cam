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
BASE_URL = "http://127.0.0.1:8772"


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
    raise RuntimeError(f"CrickAnalysis batches test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_editor_gone(page, selector: str):
    expect(page.locator(selector)).to_have_count(0, timeout=10000)


def _batch_session_row(page, session_date: str):
    return page.locator(".academy-session-row").filter(has_text="UI U15 Mon Wed").filter(has_text=session_date)


def _private_session_row(page, session_date: str):
    return page.locator(".academy-session-row").filter(has_text="UI Private Coach").filter(has_text=session_date)


def test_batches_and_sessions_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-batches-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8772"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/academy/profile", {"name": "Batches UI Academy", "timezone": "America/New_York"})
        program = _json_request("POST", "/api/academy/programs", {"name": "UI U15 Program", "program_type": "group", "status": "active"})
        coach1 = _json_request("POST", "/api/academy/coaches", {"first_name": "UI", "last_name": "Batch Coach", "specialties": ["Batting"], "status": "active"})
        coach2 = _json_request("POST", "/api/academy/coaches", {"first_name": "UI", "last_name": "Private Coach", "specialties": ["Bowling"], "status": "active"})
        p1 = _json_request("POST", "/api/academy/players", {"name": "UI Batch Player One", "status": "active"})
        p2 = _json_request("POST", "/api/academy/players", {"name": "UI Batch Player Two", "status": "active"})
        p3 = _json_request("POST", "/api/academy/players", {"name": "UI Batch Player Three", "status": "active"})

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=batches", wait_until="domcontentloaded")
                expect(page.get_by_role("button", name="Add Batch")).to_be_visible(timeout=15000)
                expect(page.get_by_text("America/New_York", exact=False).first).to_be_visible()

                # Create a capacity-2 batch attached to the real Program.
                page.get_by_role("button", name="Add Batch").click()
                form = page.locator("#academyBatchForm")
                expect(form).to_be_visible()
                form.locator('[name="name"]').fill("UI U15 Mon Wed")
                form.locator('[name="code"]').fill("UI-U15-MW")
                form.locator('[name="program_id"]').select_option(str(program["id"]))
                form.locator('[name="capacity"]').fill("2")
                form.locator('[name="location"]').fill("UI Indoor Center")
                form.locator('[name="resource"]').fill("Net 3")
                form.locator('[name="start_date"]').fill("2026-09-01")
                form.locator('[name="end_date"]').fill("2026-12-15")
                page.get_by_role("button", name="Create Batch").click()
                _wait_editor_gone(page, "#academyBatchForm")
                batch_row = page.locator(".academy-batch-row", has_text="UI U15 Mon Wed")
                expect(batch_row).to_be_visible(timeout=10000)
                expect(batch_row).to_contain_text("0/2 active")
                expect(batch_row).to_contain_text("UI Indoor Center")
                expect(batch_row).to_contain_text("Net 3")

                # Assign the real Coach as primary batch coach.
                page.get_by_role("button", name="Assign Coach").click()
                form = page.locator("#academyBatchCoachForm")
                form.locator('[name="batch_id"]').select_option(label="UI U15 Mon Wed")
                form.locator('[name="coach_id"]').select_option(label="UI Batch Coach")
                form.locator('[name="assignment_role"]').select_option("primary")
                form.locator('[name="start_date"]').fill("2026-09-01")
                page.get_by_role("button", name="Assign Coach").last.click()
                _wait_editor_gone(page, "#academyBatchCoachForm")
                batch_row = page.locator(".academy-batch-row", has_text="UI U15 Mon Wed")
                expect(batch_row).to_contain_text("UI Batch Coach", timeout=10000)

                # Add two active roster players.
                for player in (p1, p2):
                    page.get_by_role("button", name="Add Player").click()
                    form = page.locator("#academyBatchPlayerForm")
                    form.locator('[name="batch_id"]').select_option(label="UI U15 Mon Wed")
                    form.locator('[name="player_id"]').select_option(label=player["name"])
                    form.locator('[name="waitlist_if_full"]').select_option("false")
                    page.get_by_role("button", name="Add Player").last.click()
                    _wait_editor_gone(page, "#academyBatchPlayerForm")
                batch_row = page.locator(".academy-batch-row", has_text="UI U15 Mon Wed")
                expect(batch_row).to_contain_text("2/2 active", timeout=10000)

                # Third player must be rejected when capacity is full.
                page.get_by_role("button", name="Add Player").click()
                form = page.locator("#academyBatchPlayerForm")
                form.locator('[name="batch_id"]').select_option(label="UI U15 Mon Wed")
                form.locator('[name="player_id"]').select_option(label=p3["name"])
                form.locator('[name="waitlist_if_full"]').select_option("false")
                page.get_by_role("button", name="Add Player").last.click()
                expect(page.locator("#batchPlayerStatus")).to_contain_text("Batch is at capacity", timeout=10000)

                # Explicit waitlist choice should then succeed for the same player.
                form.locator('[name="waitlist_if_full"]').select_option("true")
                page.get_by_role("button", name="Add Player").last.click()
                _wait_editor_gone(page, "#academyBatchPlayerForm")
                waitlist_row = page.locator(".academy-batch-membership-row", has_text=p3["name"])
                expect(waitlist_row).to_contain_text("waitlisted", timeout=10000)
                batch_row = page.locator(".academy-batch-row", has_text="UI U15 Mon Wed")
                expect(batch_row).to_contain_text("1 waitlisted")

                # Generate Mon/Wed sessions. Scope assertions to this batch because PostgreSQL
                # intentionally retains records created by earlier regression steps.
                page.get_by_role("button", name="Generate Sessions").click()
                form = page.locator("#academyBatchScheduleForm")
                form.locator('[name="batch_id"]').select_option(label="UI U15 Mon Wed")
                form.locator('[name="start_date"]').fill("2026-09-07")
                form.locator('[name="end_date"]').fill("2026-09-16")
                form.locator('[name="start_time"]').fill("19:00")
                form.locator('[name="duration_minutes"]').fill("60")
                form.locator('[name="weekday"][value="0"]').check()
                form.locator('[name="weekday"][value="2"]').check()
                page.get_by_role("button", name="Generate Sessions").last.click()
                _wait_editor_gone(page, "#academyBatchScheduleForm")
                ui_batch_sessions = page.locator(".academy-session-row").filter(has_text="UI U15 Mon Wed")
                expect(ui_batch_sessions).to_have_count(4, timeout=10000)
                for d in ("2026-09-07", "2026-09-09", "2026-09-14", "2026-09-16"):
                    row = _batch_session_row(page, d)
                    expect(row).to_have_count(1)
                    expect(row).to_contain_text("America/New_York")
                    expect(row).to_contain_text("Net 3")
                    expect(row).to_contain_text("2 players")

                # Edit one occurrence only.
                row_0907 = _batch_session_row(page, "2026-09-07")
                row_0907.get_by_role("button", name="Edit").click()
                form = page.locator("#academySessionEditForm")
                form.locator('[name="start_time"]').fill("20:15")
                form.locator('[name="resource"]').fill("Net 4")
                page.get_by_role("button", name="Save Session").click()
                _wait_editor_gone(page, "#academySessionEditForm")
                row_0907 = _batch_session_row(page, "2026-09-07")
                expect(row_0907).to_contain_text("20:15", timeout=10000)
                expect(row_0907).to_contain_text("Net 4")
                expect(_batch_session_row(page, "2026-09-14")).to_contain_text("19:00")

                # Cancel one occurrence and retain reason/history.
                row_0909 = _batch_session_row(page, "2026-09-09")
                row_0909.get_by_role("button", name="Cancel").click()
                form = page.locator("#academySessionCancelForm")
                form.locator('[name="reason"]').fill("Facility closure")
                page.get_by_role("button", name="Confirm Cancellation").click()
                _wait_editor_gone(page, "#academySessionCancelForm")
                row_0909 = _batch_session_row(page, "2026-09-09")
                expect(row_0909).to_contain_text("cancelled", timeout=10000)
                expect(row_0909).to_contain_text("Reason: Facility closure")

                # Create a make-up; original remains cancelled and copied roster has 2 players.
                row_0909.get_by_role("button", name="Make-up").click()
                form = page.locator("#academyMakeupSessionForm")
                form.locator('[name="session_date"]').fill("2026-09-10")
                form.locator('[name="start_time"]').fill("18:00")
                page.get_by_role("button", name="Create Make-up").click()
                _wait_editor_gone(page, "#academyMakeupSessionForm")
                makeup_row = _batch_session_row(page, "2026-09-10")
                expect(makeup_row).to_have_count(1, timeout=10000)
                expect(makeup_row).to_contain_text("2 players")
                expect(_batch_session_row(page, "2026-09-09")).to_contain_text("cancelled")

                # Create a private session with the second coach.
                page.get_by_role("button", name="Private Session").click()
                form = page.locator("#academyPrivateSessionForm")
                form.locator('[name="player_id"]').select_option(label=p1["name"])
                form.locator('[name="coach_id"]').select_option(label="UI Private Coach")
                form.locator('[name="session_date"]').fill("2026-09-08")
                form.locator('[name="start_time"]').fill("18:00")
                form.locator('[name="duration_minutes"]').fill("60")
                form.locator('[name="location"]').fill("UI Indoor Center")
                form.locator('[name="resource"]').fill("Lane 1")
                page.get_by_role("button", name="Create Private Session").click()
                _wait_editor_gone(page, "#academyPrivateSessionForm")
                private_row = _private_session_row(page, "2026-09-08")
                expect(private_row).to_have_count(1, timeout=10000)
                expect(private_row).to_contain_text("Private session")
                expect(private_row).to_contain_text("Lane 1")
                expect(private_row).to_contain_text("1 player")

                # A second overlapping session for that coach must be rejected.
                page.get_by_role("button", name="Private Session").click()
                form = page.locator("#academyPrivateSessionForm")
                form.locator('[name="player_id"]').select_option(label=p2["name"])
                form.locator('[name="coach_id"]').select_option(label="UI Private Coach")
                form.locator('[name="session_date"]').fill("2026-09-08")
                form.locator('[name="start_time"]').fill("18:30")
                form.locator('[name="duration_minutes"]').fill("60")
                page.get_by_role("button", name="Create Private Session").click()
                expect(page.locator("#privateSessionStatus")).to_contain_text("conflicting session", timeout=10000)

                # Workload is scoped by the newly created coach ID, so pre-existing
                # PostgreSQL test records cannot affect this calculation.
                workload = _json_request("GET", f"/api/academy/coaches/{coach1['id']}/workload")
                assert workload["coach_name"] == "UI Batch Coach"
                assert workload["session_count"] == 4
                assert workload["total_minutes"] == 240

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-batches-ui-failure.png", full_page=True)
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
