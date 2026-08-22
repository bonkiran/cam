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
BASE_URL = "http://127.0.0.1:8778"


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
    raise RuntimeError(f"CrickAnalysis tournament test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_tournament_registration_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-tournaments-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8778"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/cam/profile", {"name": "Tournament UI Academy"})
        team = _json_request("POST", "/api/cam/teams", {"name": "UI Tournament U15 XI", "age_group": "U15", "status": "active"})
        assert team["name"] == "UI Tournament U15 XI"

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            try:
                page.goto(f"{BASE_URL}/#cam?tab=tournaments", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Tournaments")).to_be_visible(timeout=15000)
                expect(page.locator("#openTournamentForm")).to_be_visible()

                page.get_by_role("button", name="Add Tournament").click()
                form = page.locator("#camTournamentForm")
                expect(form).to_be_visible()
                form.locator('[name="name"]').fill("UI Southeast Junior Cup")
                form.locator('[name="organizer"]').fill("UI Regional Association")
                form.locator('[name="location"]').fill("UI Cricket Complex")
                form.locator('[name="start_date"]').fill("2026-10-10")
                form.locator('[name="end_date"]').fill("2026-10-12")
                form.locator('[name="status"]').select_option("open")
                form.locator('[name="notes"]').fill("UI tournament test")
                page.get_by_role("button", name="Create Tournament").click()

                tournament_row = page.locator(".cam-tournament-row", has_text="UI Southeast Junior Cup")
                expect(tournament_row).to_be_visible(timeout=10000)
                expect(tournament_row).to_contain_text("UI Regional Association")
                expect(tournament_row).to_contain_text("0 registered teams")

                page.get_by_role("button", name="Register Team").click()
                entry_form = page.locator("#camTournamentEntryForm")
                expect(entry_form).to_be_visible()
                entry_form.locator('[name="tournament_id"]').select_option(label="UI Southeast Junior Cup")
                entry_form.locator('[name="team_id"]').select_option(label="UI Tournament U15 XI")
                entry_form.locator('[name="registered_on"]').fill("2026-08-18")
                entry_form.locator('[name="notes"]').fill("UI registration")
                entry_form.get_by_role("button", name="Register Team").click()

                tournament_row = page.locator(".cam-tournament-row", has_text="UI Southeast Junior Cup")
                expect(tournament_row).to_contain_text("1 registered team", timeout=10000)
                expect(tournament_row).to_contain_text("UI Tournament U15 XI")
                entry_row = page.locator(".cam-tournament-entry-row", has_text="UI Tournament U15 XI")
                expect(entry_row).to_be_visible()
                expect(entry_row).to_contain_text("registered")
                expect(entry_row).to_contain_text("UI registration")

                entry_row.get_by_role("button", name="Withdraw").click()
                entry_row = page.locator(".cam-tournament-entry-row", has_text="UI Tournament U15 XI")
                expect(entry_row).to_contain_text("withdrawn", timeout=10000)
                tournament_row = page.locator(".cam-tournament-row", has_text="UI Southeast Junior Cup")
                expect(tournament_row).to_contain_text("0 registered teams")

                # Financial linkage is intentionally not fabricated before Fees & Payments.
                expect(page.locator(".cam-programs-note")).to_contain_text("Fee linkage deferred")
            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/cam-tournaments-ui-failure.png", full_page=True)
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
