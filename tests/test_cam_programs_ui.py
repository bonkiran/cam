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
BASE_URL = "http://127.0.0.1:8770"


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
    raise RuntimeError(f"CrickAnalysis programs test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_programs_and_enrollment_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-programs-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8770"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/cam/profile", {"name": "Programs UI Academy"})
        regular_player = _json_request(
            "POST", "/api/cam/players", {"name": "Programs UI Regular Player", "status": "active"}
        )
        trial_player = _json_request(
            "POST", "/api/cam/players", {"name": "Programs UI Trial Player", "status": "active"}
        )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1100})
            try:
                page.goto(f"{BASE_URL}/#cam?tab=programs", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Programs & Enrollment")).to_be_visible(timeout=15000)
                expect(page.get_by_role("button", name="Programs & Enrollment")).to_be_visible()

                # Create program.
                page.get_by_role("button", name="Add Program").click()
                program_form = page.locator("#camProgramForm")
                expect(program_form).to_be_visible()
                program_form.locator('[name="name"]').fill("UI U13 Development")
                program_form.locator('[name="code"]').fill("UI-U13")
                program_form.locator('[name="program_type"]').select_option("group")
                program_form.locator('[name="age_group"]').fill("U13")
                program_form.locator('[name="skill_level"]').fill("Developing")
                program_form.locator('[name="start_date"]').fill("2026-09-01")
                program_form.locator('[name="end_date"]').fill("2026-12-01")
                program_form.locator('[name="description"]').fill("UI-created development program")
                page.get_by_role("button", name="Create Program").click()
                program_row = page.locator(".cam-program-row", has_text="UI U13 Development")
                expect(program_row).to_be_visible(timeout=10000)
                expect(program_row).to_contain_text("0 current")

                # Edit program and verify the same row updates.
                program_row.get_by_role("button", name="Edit").click()
                program_form = page.locator("#camProgramForm")
                expect(program_form).to_be_visible()
                program_form.locator('[name="name"]').fill("UI U13 Development Plus")
                program_form.locator('[name="end_date"]').fill("2026-12-15")
                page.get_by_role("button", name="Save Program").click()
                program_row = page.locator(".cam-program-row", has_text="UI U13 Development Plus")
                expect(program_row).to_be_visible(timeout=10000)

                # Regular enrollment.
                page.get_by_role("button", name="Enroll Player").click()
                enrollment_form = page.locator("#camEnrollmentForm")
                expect(enrollment_form).to_be_visible()
                enrollment_form.locator('[name="player_id"]').select_option(label=regular_player["name"])
                enrollment_form.locator('[name="program_id"]').select_option(label="UI U13 Development Plus")
                enrollment_form.locator('[name="enrollment_type"]').select_option("regular")
                enrollment_form.locator('[name="start_date"]').fill("2026-09-01")
                enrollment_form.locator('[name="notes"]').fill("UI regular enrollment")
                page.get_by_role("button", name="Create Enrollment").click()
                regular_row = page.locator(".cam-enrollment-row", has_text=regular_player["name"])
                expect(regular_row).to_be_visible(timeout=10000)
                expect(regular_row).to_contain_text("regular")
                expect(regular_row).to_contain_text("active")

                # Duplicate current enrollment must be rejected in the UI.
                page.get_by_role("button", name="Enroll Player").click()
                enrollment_form = page.locator("#camEnrollmentForm")
                enrollment_form.locator('[name="player_id"]').select_option(label=regular_player["name"])
                enrollment_form.locator('[name="program_id"]').select_option(label="UI U13 Development Plus")
                enrollment_form.locator('[name="enrollment_type"]').select_option("regular")
                page.get_by_role("button", name="Create Enrollment").click()
                expect(page.locator("#enrollmentSaveStatus")).to_contain_text(
                    "Player already has a current enrollment in this program", timeout=10000
                )
                page.locator("#camEnrollmentForm").get_by_role("button", name="Cancel").click()

                # Freeze the regular enrollment and retain it in history.
                regular_row = page.locator(".cam-enrollment-row", has_text=regular_player["name"])
                regular_row.get_by_role("button", name="Freeze").click()
                action_form = page.locator("#camEnrollmentActionForm")
                expect(action_form).to_be_visible()
                action_form.locator('[name="effective_date"]').fill("2026-10-01")
                page.get_by_role("button", name="Confirm Freeze").click()
                regular_row = page.locator(".cam-enrollment-row", has_text=regular_player["name"])
                expect(regular_row).to_contain_text("frozen", timeout=10000)
                expect(regular_row).to_contain_text("Frozen: 2026-10-01")

                # Trial enrollment for another active player.
                page.get_by_role("button", name="Enroll Player").click()
                enrollment_form = page.locator("#camEnrollmentForm")
                enrollment_form.locator('[name="player_id"]').select_option(label=trial_player["name"])
                enrollment_form.locator('[name="program_id"]').select_option(label="UI U13 Development Plus")
                enrollment_form.locator('[name="enrollment_type"]').select_option("trial")
                enrollment_form.locator('[name="start_date"]').fill("2026-09-05")
                enrollment_form.locator('[name="end_date"]').fill("2026-09-05")
                page.get_by_role("button", name="Create Enrollment").click()
                trial_row = page.locator(".cam-enrollment-row", has_text=trial_player["name"])
                expect(trial_row).to_be_visible(timeout=10000)
                expect(trial_row).to_contain_text("trial")
                expect(trial_row).to_contain_text("active")

                # Cancel the frozen regular enrollment with reason and retain history.
                regular_row = page.locator(".cam-enrollment-row", has_text=regular_player["name"])
                regular_row.get_by_role("button", name="Cancel").click()
                action_form = page.locator("#camEnrollmentActionForm")
                action_form.locator('[name="effective_date"]').fill("2026-10-10")
                action_form.locator('[name="reason"]').fill("Schedule conflict")
                page.get_by_role("button", name="Confirm Cancellation").click()
                regular_row = page.locator(".cam-enrollment-row", has_text=regular_player["name"])
                expect(regular_row).to_contain_text("cancelled", timeout=10000)
                expect(regular_row).to_contain_text("Reason: Schedule conflict")

                # Both histories still exist and the trial remains active.
                expect(page.locator(".cam-enrollment-row", has_text=regular_player["name"])).to_have_count(1)
                expect(page.locator(".cam-enrollment-row", has_text=trial_player["name"])).to_have_count(1)
                trial_row = page.locator(".cam-enrollment-row", has_text=trial_player["name"])
                expect(trial_row).to_contain_text("active")

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/cam-programs-ui-failure.png", full_page=True)
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
