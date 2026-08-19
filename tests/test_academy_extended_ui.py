import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8767"


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
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
    raise RuntimeError(f"CrickAnalysis test server did not become ready: {last_error}")


def test_academy_setup_and_player_extended_ui():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-extended-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8767"],
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
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            try:
                # ----- Academy Setup extended cases -----
                page.goto(f"{BASE_URL}/#academy?tab=setup", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Academy Setup")).to_be_visible(timeout=15000)
                form = page.locator("#academyProfileForm")

                # Timezone remains an internal/default scheduling value but is no
                # longer exposed as an Academy Setup field.
                timezone = form.locator('[name="timezone"]')
                expect(timezone).to_have_value("America/New_York")
                expect(timezone).to_be_hidden()

                # One-character academy name should be rejected by form validation.
                name = form.locator('[name="name"]')
                name.fill("A")
                page.get_by_role("button", name="Save Academy Profile").click()
                assert name.evaluate("el => el.validity.tooShort") is True

                # Malformed academy email should be rejected by browser validation.
                name.fill("Extended Test Academy")
                email = form.locator('[name="email"]')
                email.fill("admin@@academy")
                page.get_by_role("button", name="Save Academy Profile").click()
                assert email.evaluate("el => el.validity.typeMismatch") is True

                # Save primary location while the internal timezone remains unchanged.
                email.fill("admin@example.com")
                form.locator('[name="phone"]').fill("555-0100")
                form.locator('[name="address_line1"]').fill("2345 Hello Dr")
                form.locator('[name="address_line2"]').fill("Suite 10")
                form.locator('[name="city"]').fill("Atlanta")
                form.locator('[name="state"]').fill("GA")
                form.locator('[name="postal_code"]').fill("30005")
                form.locator('[name="country"]').fill("United States")
                page.get_by_role("button", name="Save Academy Profile").click()
                expect(page.get_by_role("heading", name="Academy Setup")).to_be_visible(timeout=10000)
                form = page.locator("#academyProfileForm")
                expect(form.locator('[name="address_line1"]')).to_have_value("2345 Hello Dr")
                expect(form.locator('[name="address_line2"]')).to_have_value("Suite 10")
                expect(form.locator('[name="city"]')).to_have_value("Atlanta")
                expect(form.locator('[name="state"]')).to_have_value("GA")
                expect(form.locator('[name="postal_code"]')).to_have_value("30005")
                expect(form.locator('[name="country"]')).to_have_value("United States")
                expect(form.locator('[name="timezone"]')).to_have_value("America/New_York")
                expect(form.locator('[name="timezone"]')).to_be_hidden()

                # ----- Player extended cases -----
                page.goto(f"{BASE_URL}/#academy?tab=players", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)

                # Required display name.
                page.get_by_role("button", name="Add Player").click()
                pform = page.locator("#academyPlayerForm")
                player_name = pform.locator('[name="name"]')
                page.get_by_role("button", name="Create Player").click()
                assert player_name.evaluate("el => el.validity.valueMissing") is True

                # One-character player name rejected by form validation.
                player_name.fill("A")
                page.get_by_role("button", name="Create Player").click()
                assert player_name.evaluate("el => el.validity.tooShort") is True

                # Complete identity/demographics/cricket/contact/address/notes and create.
                player_name.fill("Extended Test Player")
                pform.locator('[name="first_name"]').fill("Extended")
                pform.locator('[name="last_name"]').fill("Player")
                pform.locator('[name="preferred_name"]').fill("EP")
                pform.locator('[name="gender"]').select_option(label="Female")
                pform.locator('[name="bowling_style"]').fill("Right-arm leg spin")
                pform.locator('[name="status"]').select_option(label="waitlisted")
                pform.locator('[name="address_line1"]').fill("100 Player Way")
                pform.locator('[name="address_line2"]').fill("Unit 2")
                pform.locator('[name="city"]').fill("Johns Creek")
                pform.locator('[name="state"]').fill("GA")
                pform.locator('[name="postal_code"]').fill("30097")
                pform.locator('[name="country"]').fill("United States")
                pform.locator('[name="notes"]').fill("Internal coaching note.\nSecond line retained.")

                # Malformed player email blocks save.
                pemail = pform.locator('[name="email"]')
                pemail.fill("player@@example")
                page.get_by_role("button", name="Create Player").click()
                assert pemail.evaluate("el => el.validity.typeMismatch") is True
                pemail.fill("extended.player@example.com")
                page.get_by_role("button", name="Create Player").click()

                prow = page.locator(".academy-player-row", has_text="Extended Test Player")
                expect(prow).to_be_visible(timeout=10000)
                expect(prow.locator(".academy-status")).to_have_text("waitlisted")

                # Reopen and verify all extended fields persist.
                prow.get_by_role("button", name="Edit").click()
                pform = page.locator("#academyPlayerForm")
                expect(pform.locator('[name="first_name"]')).to_have_value("Extended")
                expect(pform.locator('[name="last_name"]')).to_have_value("Player")
                expect(pform.locator('[name="preferred_name"]')).to_have_value("EP")
                expect(pform.locator('[name="gender"]')).to_have_value("Female")
                expect(pform.locator('[name="bowling_style"]')).to_have_value("Right-arm leg spin")
                expect(pform.locator('[name="status"]')).to_have_value("waitlisted")
                expect(pform.locator('[name="address_line1"]')).to_have_value("100 Player Way")
                expect(pform.locator('[name="address_line2"]')).to_have_value("Unit 2")
                expect(pform.locator('[name="city"]')).to_have_value("Johns Creek")
                expect(pform.locator('[name="state"]')).to_have_value("GA")
                expect(pform.locator('[name="postal_code"]')).to_have_value("30097")
                expect(pform.locator('[name="country"]')).to_have_value("United States")
                expect(pform.locator('[name="notes"]')).to_have_value("Internal coaching note.\nSecond line retained.")
                page.get_by_role("button", name="Cancel").click()

                # Special-character player name supports apostrophe and hyphen.
                page.get_by_role("button", name="Add Player").click()
                pform = page.locator("#academyPlayerForm")
                special_name = "D'Arcy O-Neill"
                pform.locator('[name="name"]').fill(special_name)
                page.get_by_role("button", name="Create Player").click()
                expect(page.locator(".academy-player-row", has_text=special_name)).to_be_visible(timeout=10000)

                # Simulate legacy/video-created player through the existing upload API.
                # The dummy bytes may fail media analysis later, but player identity is created by the same upload route.
                legacy_name = "Legacy Video Player"
                upload = httpx.post(
                    f"{BASE_URL}/api/videos",
                    data={"player_name": legacy_name, "analysis_mode": "quick"},
                    files={"file": ("legacy.mp4", b"not-a-real-video", "video/mp4")},
                    timeout=20.0,
                )
                assert upload.status_code == 201, upload.text

                # Reload Academy Players: legacy upload-created player is present and editable, not duplicated.
                page.reload(wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)
                legacy_row = page.locator(".academy-player-row", has_text=legacy_name)
                expect(legacy_row).to_have_count(1)
                expect(legacy_row).to_be_visible()
                legacy_row.get_by_role("button", name="Edit").click()
                pform = page.locator("#academyPlayerForm")
                pform.locator('[name="skill_level"]').select_option(label="Developing")
                page.get_by_role("button", name="Save Changes").click()
                legacy_row = page.locator(".academy-player-row", has_text=legacy_name)
                expect(legacy_row).to_contain_text("Developing", timeout=10000)
                expect(legacy_row).to_have_count(1)

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-extended-ui-failure.png", full_page=True)
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