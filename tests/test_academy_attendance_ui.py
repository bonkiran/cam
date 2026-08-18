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
BASE_URL = "http://127.0.0.1:8774"


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
    raise RuntimeError(f"CrickAnalysis attendance test server did not become ready: {last_error}")


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


def _select_session(page, session_id: int):
    page.locator("#attendanceSessionSelect").select_option(str(session_id))
    form = page.locator("#academyAttendanceForm")
    expect(form).to_have_attribute("data-session-id", str(session_id), timeout=10000)
    return form


def _player_row(page, name: str):
    row = page.locator(".academy-attendance-player", has_text=name)
    expect(row).to_be_visible(timeout=10000)
    return row


def _save(page):
    form = page.locator("#academyAttendanceForm")
    session_id = form.get_attribute("data-session-id")
    assert session_id
    with page.expect_response(
        lambda response: f"/api/academy/sessions/{session_id}/attendance" in response.url
        and response.request.method == "PUT",
        timeout=10000,
    ) as response_info:
        page.get_by_role("button", name="Save Attendance").click()
    assert response_info.value.ok
    expect(page.locator("#academyAttendanceForm")).to_have_attribute(
        "data-session-id", session_id, timeout=10000
    )


def test_attendance_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-attendance-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8774"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/academy/profile", {"name": "Attendance UI Academy", "timezone": "America/New_York"})
        program = _json_request("POST", "/api/academy/programs", {"name": "Attendance UI Program", "program_type": "group", "status": "active"})
        coach = _json_request("POST", "/api/academy/coaches", {"first_name": "UI", "last_name": "Attendance Coach", "status": "active"})
        p1 = _json_request("POST", "/api/academy/players", {"name": "UI Attendance Player One", "status": "active"})
        p2 = _json_request("POST", "/api/academy/players", {"name": "UI Attendance Player Two", "status": "active"})
        batch = _json_request("POST", "/api/academy/batches", {"name": "Attendance UI Batch", "program_id": program["id"], "capacity": 5, "status": "active"})
        _json_request("POST", f"/api/academy/batch-coach-assignments?batch_id={batch['id']}", {"coach_id": coach["id"], "assignment_role": "primary", "start_date": "2026-09-01"})
        _json_request("POST", f"/api/academy/batches/{batch['id']}/players", {"player_id": p1["id"], "joined_on": "2026-09-01"})
        _json_request("POST", f"/api/academy/batches/{batch['id']}/players", {"player_id": p2["id"], "joined_on": "2026-09-01"})
        generated = _json_request(
            "POST",
            f"/api/academy/batches/{batch['id']}/generate-sessions",
            {"start_date": "2026-09-07", "end_date": "2026-09-16", "weekdays": [0, 2], "start_time": "19:00", "duration_minutes": 60},
        )
        session_ids = [int(value) for value in generated["session_ids"]]
        assert len(session_ids) == 4

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1700, "height": 1250})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=attendance", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Attendance", exact=True)).to_be_visible(timeout=15000)
                expect(page.locator("#attendanceSessionSelect")).to_be_visible(timeout=15000)
                expect(page.get_by_text("Alert threshold", exact=True)).to_be_visible()

                # Session 1: batch attendance, make-up default, and coach attendance.
                _select_session(page, session_ids[0])
                page.get_by_role("button", name="Mark All Present").click()
                row2 = _player_row(page, p2["name"])
                row2.locator('[name="attendance_status"]').select_option("absent")
                row2.locator('[name="absence_reason"]').fill("Travel")
                expect(row2.locator('[name="make_up_eligible"]')).to_be_checked()
                page.locator('[name="coach_status"]').select_option("present")
                page.locator('[name="coach_notes"]').fill("On time")
                _save(page)

                row2 = _player_row(page, p2["name"])
                expect(row2.locator('[name="attendance_status"]')).to_have_value("absent")
                expect(row2.locator('[name="absence_reason"]')).to_have_value("Travel")
                expect(row2).to_contain_text("0% attendance")

                # Correct player and coach attendance; correction history remains visible.
                row1 = _player_row(page, p1["name"])
                row1.locator('[name="attendance_status"]').select_option("late")
                row1.locator('[name="attendance_notes"]').fill("Arrived 10 minutes late")
                page.locator('[name="coach_status"]').select_option("late")
                page.locator('[name="coach_notes"]').fill("Arrived 5 minutes late")
                _save(page)
                expect(page.locator(".academy-attendance-history")).to_contain_text("present → late", timeout=10000)

                # Session 2: second absence for Player 2.
                _select_session(page, session_ids[1])
                page.get_by_role("button", name="Mark All Present").click()
                row2 = _player_row(page, p2["name"])
                row2.locator('[name="attendance_status"]').select_option("absent")
                row2.locator('[name="absence_reason"]').fill("Sick")
                _save(page)

                # Session 3: Player 2 reaches threshold; alert must appear only once.
                _select_session(page, session_ids[2])
                page.get_by_role("button", name="Mark All Present").click()
                row1 = _player_row(page, p1["name"])
                row1.locator('[name="attendance_status"]').select_option("absent")
                row1.locator('[name="absence_reason"]').fill("School event")
                expect(row1.locator('[name="make_up_eligible"]')).to_be_checked()
                row2 = _player_row(page, p2["name"])
                row2.locator('[name="attendance_status"]').select_option("absent")
                row2.locator('[name="absence_reason"]').fill("Sick")
                _save(page)
                alert = page.locator(".academy-attendance-alert", has_text=p2["name"])
                expect(alert).to_be_visible(timeout=10000)
                expect(alert).to_contain_text("3 absences in 30 days")
                _save(page)
                expect(page.locator(".academy-attendance-alert", has_text=p2["name"])).to_have_count(1, timeout=10000)

                # Session 4: excused defaults to make-up eligible and is outside percentage denominator.
                _select_session(page, session_ids[3])
                page.get_by_role("button", name="Mark All Present").click()
                row1 = _player_row(page, p1["name"])
                row1.locator('[name="attendance_status"]').select_option("excused")
                row1.locator('[name="absence_reason"]').fill("Family commitment")
                expect(row1.locator('[name="make_up_eligible"]')).to_be_checked()
                _save(page)
                row1 = _player_row(page, p1["name"])
                expect(row1).to_contain_text("66.7% attendance", timeout=10000)
                expect(row1).to_contain_text("2 make-up eligible")

                # Correct the third Player 2 absence; the open alert resolves automatically.
                _select_session(page, session_ids[2])
                row2 = _player_row(page, p2["name"])
                row2.locator('[name="attendance_status"]').select_option("present")
                _save(page)
                expect(page.locator(".academy-attendance-alert", has_text=p2["name"])).to_have_count(0, timeout=10000)

                # Policy is configurable through the same screen.
                policy_form = page.locator("#attendancePolicyForm")
                policy_form.locator('[name="repeated_absence_threshold"]').fill("4")
                policy_form.locator('[name="absence_lookback_days"]').fill("45")
                with page.expect_response(
                    lambda response: response.url.endswith("/api/academy/attendance/policy")
                    and response.request.method == "PUT",
                    timeout=10000,
                ) as response_info:
                    page.get_by_role("button", name="Save Policy").click()
                assert response_info.value.ok
                expect(page.locator(".academy-stat", has_text="Alert threshold").locator("strong")).to_have_text("4", timeout=10000)

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-attendance-ui-failure.png", full_page=True)
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
