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
BASE_URL = "http://127.0.0.1:8771"


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
    raise RuntimeError(f"CrickAnalysis coaches test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_coaches_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-coaches-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8771"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/academy/profile", {"name": "Coaches UI Academy"})
        player = _json_request("POST", "/api/academy/players", {"name": "UI Coach Player", "status": "active"})

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1100})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=coaches", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Coaches")).to_be_visible(timeout=15000)

                # Create coach with specialties, availability and certification details.
                page.get_by_role("button", name="Add Coach").click()
                form = page.locator("#academyCoachForm")
                expect(form).to_be_visible()
                form.locator('[name="first_name"]').fill("Meera")
                form.locator('[name="last_name"]').fill("Patel")
                form.locator('[name="preferred_name"]').fill("Coach Meera")
                form.locator('[name="email"]').fill("meera@example.com")
                form.locator('[name="phone"]').fill("555-1000")
                form.locator('[name="joined_on"]').fill("2026-08-10")
                form.locator('[name="specialties"]').fill("Batting, Fast Bowling")
                form.locator('[name="certifications"]').fill("USA Cricket Level 1")
                form.locator('[name="availability"]').fill("Mon/Wed 5-9 PM; Sat mornings")
                form.locator('[name="notes"]').fill("UI coach record")
                page.get_by_role("button", name="Create Coach").click()

                coach_row = page.locator(".academy-coach-row", has_text="Meera Patel")
                expect(coach_row).to_be_visible(timeout=10000)
                expect(coach_row).to_contain_text("Batting")
                expect(coach_row).to_contain_text("Fast Bowling")
                expect(coach_row).to_contain_text("Mon/Wed 5-9 PM; Sat mornings")
                expect(coach_row).to_contain_text("active")

                # Edit profile and persist updated specialties/availability.
                coach_row.get_by_role("button", name="Edit").click()
                form = page.locator("#academyCoachForm")
                expect(form).to_be_visible()
                form.locator('[name="phone"]').fill("555-1100")
                form.locator('[name="specialties"]').fill("Batting, Wicketkeeping")
                form.locator('[name="availability"]').fill("Tue/Thu 6-9 PM")
                page.get_by_role("button", name="Save Coach").click()
                coach_row = page.locator(".academy-coach-row", has_text="Meera Patel")
                expect(coach_row).to_contain_text("Wicketkeeping", timeout=10000)
                expect(coach_row).to_contain_text("Tue/Thu 6-9 PM")

                # Assign coach directly to the existing player.
                page.get_by_role("button", name="Assign Player").click()
                assignment_form = page.locator("#academyCoachAssignmentForm")
                expect(assignment_form).to_be_visible()
                assignment_form.locator('[name="coach_id"]').select_option(label="Meera Patel")
                assignment_form.locator('[name="player_id"]').select_option(label=player["name"])
                assignment_form.locator('[name="assignment_role"]').select_option("primary")
                assignment_form.locator('[name="start_date"]').fill("2026-09-01")
                assignment_form.locator('[name="notes"]').fill("Primary batting development coach")
                page.get_by_role("button", name="Create Assignment").click()
                assignment_row = page.locator(".academy-coach-assignment-row", has_text="Meera Patel")
                expect(assignment_row).to_be_visible(timeout=10000)
                expect(assignment_row).to_contain_text("UI Coach Player")
                expect(assignment_row).to_contain_text("primary")
                expect(assignment_row).to_contain_text("active")
                coach_row = page.locator(".academy-coach-row", has_text="Meera Patel")
                expect(coach_row).to_contain_text("1 player assignment")

                # Deactivate coach; history/assignment must remain visible.
                coach_row.get_by_role("button", name="Edit").click()
                form = page.locator("#academyCoachForm")
                form.locator('[name="status"]').select_option("inactive")
                page.get_by_role("button", name="Save Coach").click()
                coach_row = page.locator(".academy-coach-row", has_text="Meera Patel")
                expect(coach_row).to_contain_text("inactive", timeout=10000)
                assignment_row = page.locator(".academy-coach-assignment-row", has_text="Meera Patel")
                expect(assignment_row).to_be_visible()

                # End assignment but retain it in history.
                assignment_row.get_by_role("button", name="End").click()
                end_form = page.locator("#academyEndCoachAssignmentForm")
                expect(end_form).to_be_visible()
                end_form.locator('[name="end_date"]').fill("2026-10-15")
                page.get_by_role("button", name="End Assignment").click()
                assignment_row = page.locator(".academy-coach-assignment-row", has_text="Meera Patel")
                expect(assignment_row).to_contain_text("inactive", timeout=10000)
                expect(assignment_row).to_contain_text("End: 2026-10-15")

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-coaches-ui-failure.png", full_page=True)
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
