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
BASE_URL = "http://127.0.0.1:8773"


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
    raise RuntimeError(f"CrickAnalysis workload test server did not become ready: {last_error}")


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


def test_coach_workload_is_visible_on_coaches_page():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-workload-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8773"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/academy/profile", {"name": "Workload UI Academy", "timezone": "America/New_York"})
        program = _json_request("POST", "/api/academy/programs", {"name": "Workload Program", "program_type": "group", "status": "active"})
        coach = _json_request("POST", "/api/academy/coaches", {"first_name": "Workload", "last_name": "Coach", "specialties": ["Batting"], "status": "active"})
        player = _json_request("POST", "/api/academy/players", {"name": "Workload Player", "status": "active"})
        batch = _json_request("POST", "/api/academy/batches", {"name": "Workload Batch", "program_id": program["id"], "capacity": 5, "status": "active"})
        _json_request("POST", f"/api/academy/batch-coach-assignments?batch_id={batch['id']}", {"coach_id": coach["id"], "assignment_role": "primary", "start_date": "2026-09-01"})
        _json_request("POST", f"/api/academy/batches/{batch['id']}/players", {"player_id": player["id"], "joined_on": "2026-09-01"})
        generated = _json_request(
            "POST",
            f"/api/academy/batches/{batch['id']}/generate-sessions",
            {"start_date": "2026-09-07", "end_date": "2026-09-09", "weekdays": [0, 2], "start_time": "19:00", "duration_minutes": 60},
        )
        assert generated["created_count"] == 2

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            try:
                page.goto(f"{BASE_URL}/#academy?tab=coaches", wait_until="domcontentloaded")
                coach_row = page.locator(".academy-coach-row", has_text="Workload Coach")
                expect(coach_row).to_be_visible(timeout=15000)
                expect(coach_row).to_contain_text("2 sessions · 2h", timeout=10000)
                workload_stat = page.locator(".academy-stat", has_text="Session workload")
                expect(workload_stat.locator("strong")).to_have_text("2", timeout=10000)
                expect(workload_stat.locator("small")).to_contain_text("2h scheduled coaching time")
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-coach-workload-ui-failure.png", full_page=True)
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
