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
BASE_URL = "http://127.0.0.1:8784"


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
    raise RuntimeError(f"CAM-14 test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_cam14_training_focus_is_one_session_action_and_passive_evidence_follows_attendance():
    data_dir = tempfile.mkdtemp(prefix="cam14-player-development-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["CAM_TEMP_ADMIN_MODE"] = "1"

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8784"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/academy/profile", {"name": "CAM-14 UI Academy", "timezone": "America/New_York"})
        program = _json_request("POST", "/api/academy/programs", {"name": "U13 Development", "program_type": "group", "status": "active"})
        coach = _json_request("POST", "/api/academy/coaches", {"first_name": "UI", "last_name": "Moat Coach", "status": "active"})
        p1 = _json_request("POST", "/api/academy/players", {"name": "UI CAM14 Player One", "status": "active"})
        p2 = _json_request("POST", "/api/academy/players", {"name": "UI CAM14 Player Two", "status": "active"})
        batch = _json_request("POST", "/api/academy/batches", {"name": "UI U13 CAM14", "program_id": program["id"], "capacity": 16, "status": "active"})
        _json_request("POST", f"/api/academy/batch-coach-assignments?batch_id={batch['id']}", {"coach_id": coach["id"], "assignment_role": "primary", "start_date": "2026-08-01"})
        _json_request("POST", f"/api/academy/batches/{batch['id']}/players", {"player_id": p1["id"], "joined_on": "2026-08-01"})
        _json_request("POST", f"/api/academy/batches/{batch['id']}/players", {"player_id": p2["id"], "joined_on": "2026-08-01"})
        generated = _json_request(
            "POST",
            f"/api/academy/batches/{batch['id']}/generate-sessions",
            {"start_date": "2026-08-24", "end_date": "2026-08-24", "weekdays": [0], "start_time": "18:00", "duration_minutes": 90},
        )
        session_id = int(generated["session_ids"][0])

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=attendance", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Attendance", exact=True)).to_be_visible(timeout=15000)
                page.locator("#attendanceSessionSelect").select_option(str(session_id))
                expect(page.locator("#academyAttendanceForm")).to_have_attribute("data-session-id", str(session_id), timeout=10000)

                expect(page.get_by_role("heading", name="Today's Development Focus", exact=True)).to_be_visible(timeout=10000)
                expect(page.get_by_text("does not claim the player improved", exact=False)).to_be_visible()

                front_foot = page.get_by_role("button", name="Front-Foot Movement", exact=True)
                cover_drive = page.get_by_role("button", name="Cover Drive", exact=True)
                front_foot.click()
                cover_drive.click()
                expect(front_foot).to_have_attribute("aria-pressed", "true")
                expect(cover_drive).to_have_attribute("aria-pressed", "true")
                expect(page.locator("[data-selected-count]")).to_have_text("2")

                with page.expect_response(
                    lambda response: response.url.endswith(f"/api/academy/sessions/{session_id}/development-focus")
                    and response.request.method == "PUT",
                    timeout=10000,
                ) as focus_response:
                    page.get_by_role("button", name="Save Training Focus", exact=True).click()
                assert focus_response.value.ok
                expect(page.locator(".academy-development-focus-status")).to_contain_text(
                    "evidence will link automatically", timeout=10000
                )

                page.get_by_role("button", name="Mark All Present", exact=True).click()
                p2_row = page.locator(".academy-attendance-player", has_text=p2["name"])
                p2_row.locator('[name="attendance_status"]').select_option("absent")
                p2_row.locator('[name="absence_reason"]').fill("School")

                with page.expect_response(
                    lambda response: response.url.endswith(f"/api/academy/sessions/{session_id}/attendance")
                    and response.request.method == "PUT",
                    timeout=10000,
                ) as attendance_response:
                    page.get_by_role("button", name="Save Attendance", exact=True).click()
                assert attendance_response.value.ok

                p1_history = _json_request("GET", f"/api/academy/players/{p1['id']}/development-history")
                p2_history = _json_request("GET", f"/api/academy/players/{p2['id']}/development-history")
                assert len(p1_history["evidence"]) == 2
                assert {row["skill_key"] for row in p1_history["evidence"]} == {"front_foot_movement", "cover_drive"}
                assert all(row["improvement_claimed"] is False for row in p1_history["evidence"])
                assert all(int(row["exposure_minutes"]) == 90 for row in p1_history["evidence"])
                assert p2_history["evidence"] == []

                # Re-opening the same session keeps the focus selected; the coach
                # does not have to re-enter player-by-player development data.
                page.reload(wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Today's Development Focus", exact=True)).to_be_visible(timeout=15000)
                expect(page.get_by_role("button", name="Front-Foot Movement", exact=True)).to_have_attribute("aria-pressed", "true")
                expect(page.get_by_role("button", name="Cover Drive", exact=True)).to_have_attribute("aria-pressed", "true")

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/cam14-player-development-ui-failure.png", full_page=True)
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
