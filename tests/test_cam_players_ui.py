import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8765"


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic only
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"CrickAnalysis test server did not become ready: {last_error}")


def test_cam_player_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            try:
                # Open the current CAM Players page directly.
                page.goto(f"{BASE_URL}/#cam?tab=players", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Players", exact=True)).to_be_visible(timeout=15000)
                expect(page.get_by_role("heading", name="Player Records", exact=True)).to_be_visible()

                # TC1: create a player with only the required display name and verify directory presence.
                player_name = "Automated UI Player"
                page.get_by_role("button", name="Add Player").click()
                expect(page.get_by_role("heading", name="Add Player")).to_be_visible()
                page.locator('#camPlayerForm [name="name"]').fill(player_name)
                page.get_by_role("button", name="Create Player").click()
                player_row = page.locator(".cam-player-row", has_text=player_name)
                expect(player_row).to_be_visible(timeout=10000)
                expect(player_row.locator(".cam-status")).to_have_text("active")

                # TC2: duplicate player display name must be rejected and no second directory row created.
                page.get_by_role("button", name="Add Player").click()
                page.locator('#camPlayerForm [name="name"]').fill(player_name)
                page.get_by_role("button", name="Create Player").click()
                expect(page.locator("#playerSaveStatus")).to_contain_text(
                    "A player with this name already exists", timeout=10000
                )
                expect(page.locator(".cam-player-row", has_text=player_name)).to_have_count(1)
                page.get_by_role("button", name="Cancel").click()

                # TC3: enrich player record and verify all values survive save/reopen.
                player_row.get_by_role("button", name="Edit").click()
                form = page.locator("#camPlayerForm")
                expect(form).to_be_visible()
                form.locator('[name="date_of_birth"]').fill("2012-08-17")
                form.locator('[name="batting_style"]').select_option(label="Right-handed")
                form.locator('[name="handedness"]').select_option(label="Right")
                form.locator('[name="skill_level"]').select_option(label="Intermediate")
                form.locator('[name="email"]').fill("ui-player@example.com")
                form.locator('[name="phone"]').fill("555-0111")
                form.locator('[name="emergency_contact_name"]').fill("Emergency Contact")
                form.locator('[name="emergency_contact_phone"]').fill("555-0999")
                page.get_by_role("button", name="Save Changes").click()
                player_row = page.locator(".cam-player-row", has_text=player_name)
                expect(player_row).to_contain_text("Intermediate · Right-handed", timeout=10000)

                player_row.get_by_role("button", name="Edit").click()
                form = page.locator("#camPlayerForm")
                expect(form.locator('[name="date_of_birth"]')).to_have_value("2012-08-17")
                expect(form.locator('[name="batting_style"]')).to_have_value("Right-handed")
                expect(form.locator('[name="handedness"]')).to_have_value("Right")
                expect(form.locator('[name="skill_level"]')).to_have_value("Intermediate")
                expect(form.locator('[name="email"]')).to_have_value("ui-player@example.com")
                expect(form.locator('[name="phone"]')).to_have_value("555-0111")
                expect(form.locator('[name="emergency_contact_name"]')).to_have_value("Emergency Contact")
                expect(form.locator('[name="emergency_contact_phone"]')).to_have_value("555-0999")

                # TC4: update skill level and confirm latest value persists after reopen.
                form.locator('[name="skill_level"]').select_option(label="Advanced")
                page.get_by_role("button", name="Save Changes").click()
                player_row = page.locator(".cam-player-row", has_text=player_name)
                expect(player_row).to_contain_text("Advanced · Right-handed", timeout=10000)
                player_row.get_by_role("button", name="Edit").click()
                form = page.locator("#camPlayerForm")
                expect(form.locator('[name="skill_level"]')).to_have_value("Advanced")

                # TC5: change Active -> Inactive; record stays visible and directory status changes.
                form.locator('[name="status"]').select_option(label="inactive")
                page.get_by_role("button", name="Save Changes").click()
                player_row = page.locator(".cam-player-row", has_text=player_name)
                expect(player_row).to_be_visible(timeout=10000)
                expect(player_row.locator(".cam-status")).to_have_text("inactive")

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/cam-player-ui-failure.png", full_page=True)
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
