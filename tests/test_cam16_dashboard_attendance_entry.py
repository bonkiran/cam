import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8786"


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
    raise RuntimeError(f"CAM-16 test server did not become ready: {last_error}")


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


def test_dashboard_sessions_expose_take_attendance_deep_link():
    dashboard = (ROOT / "app" / "static" / "cam_dashboard_v4.js").read_text(encoding="utf-8")
    attendance = (ROOT / "app" / "static" / "cam_attendance_v1.js").read_text(encoding="utf-8")
    assert "Take Attendance" in dashboard
    assert "cam?tab=attendance&session_id=" in dashboard
    assert "sessionIdFromHash" in attendance
    assert "['present','late','absent']" in attendance
    assert "['present','absent','late','excused']" not in attendance


def test_dashboard_take_attendance_opens_exact_session_and_moat_focus():
    data_dir = tempfile.mkdtemp(prefix="cam16-dashboard-attendance-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(ROOT)
    env["CAM_TEMP_ADMIN_MODE"] = "1"

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8786"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/cam/profile", {"name": "CAM-16 Test Academy", "timezone": "America/New_York"})
        program = _json_request("POST", "/api/cam/programs", {"name": "U13 CAM-16", "program_type": "group", "status": "active"})
        coach = _json_request("POST", "/api/cam/coaches", {"first_name": "Dashboard", "last_name": "Coach", "status": "active"})
        player = _json_request("POST", "/api/cam/players", {"name": "Dashboard Test Player", "status": "active"})
        batch = _json_request("POST", "/api/cam/batches", {"name": "CAM-16 Batch", "program_id": program["id"], "capacity": 16, "status": "active"})
        _json_request("POST", f"/api/cam/batch-coach-assignments?batch_id={batch['id']}", {"coach_id": coach["id"], "assignment_role": "primary", "start_date": date.today().isoformat()})
        _json_request("POST", f"/api/cam/batches/{batch['id']}/players", {"player_id": player["id"], "joined_on": date.today().isoformat()})
        today = date.today()
        generated = _json_request(
            "POST",
            f"/api/cam/batches/{batch['id']}/generate-sessions",
            {
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
                "weekdays": [today.weekday()],
                "start_time": "18:00",
                "duration_minutes": 90,
            },
        )
        assert generated["created_count"] == 1
        session_id = int(generated["session_ids"][0])

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            try:
                page.goto(f"{BASE_URL}/#cam", wait_until="domcontentloaded")
                button = page.locator(f'.c17-take-attendance[data-session-id="{session_id}"]')
                expect(button).to_be_visible(timeout=15000)
                button.click()
                expect(page).to_have_url(f"{BASE_URL}/#cam?tab=attendance&session_id={session_id}", timeout=10000)
                expect(page.get_by_role("heading", name="Attendance", exact=True)).to_be_visible(timeout=15000)
                expect(page.locator("#camAttendanceForm")).to_have_attribute("data-session-id", str(session_id), timeout=10000)
                expect(page.get_by_role("heading", name="Today's Development Focus", exact=True)).to_be_visible(timeout=10000)

                status_select = page.locator(".cam-attendance-player", has_text=player["name"]).locator('[name="attendance_status"]')
                values = status_select.locator("option").evaluate_all("els => els.map(e => e.value)")
                assert values == ["present", "late", "absent"]
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/cam16-dashboard-attendance-failure.png", full_page=True)
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
