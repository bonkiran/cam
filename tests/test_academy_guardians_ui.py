import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8766"


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


def _create_player(page, name: str):
    page.get_by_role("button", name="Add Player").click()
    form = page.locator("#academyPlayerForm")
    expect(form).to_be_visible(timeout=10000)
    form.locator('[name="name"]').fill(name)
    page.get_by_role("button", name="Create Player").click()
    expect(page.locator("#academyPlayerForm")).to_have_count(0, timeout=10000)
    row = page.locator(".academy-player-row", has_text=name)
    expect(row).to_be_visible(timeout=10000)
    return row


def _open_player_editor(page, row):
    edit = row.get_by_role("button", name="Edit")
    expect(edit).to_be_visible(timeout=10000)
    page.wait_for_function(
        "el => typeof el.onclick === 'function'",
        arg=edit.element_handle(),
        timeout=10000,
    )
    edit.click()
    form = page.locator("#academyPlayerForm")
    expect(form).to_be_visible(timeout=10000)
    return form


def _wait_for_save(page):
    """A successful Academy player save rerenders the workspace and removes the editor."""
    expect(page.locator("#academyPlayerForm")).to_have_count(0, timeout=10000)


def _guardian_card(page, index: int):
    return page.locator("[data-guardian-card]").nth(index)


def test_academy_guardian_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-guardian-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8766"],
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
                page.goto(f"{BASE_URL}/#academy?tab=players", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)

                player_a = "Guardian Test Player A"
                row_a = _create_player(page, player_a)
                _open_player_editor(page, row_a)
                page.get_by_role("button", name="Add Guardian").click()
                card1 = _guardian_card(page, 0)

                pickup1 = card1.locator('[name="guardian_pickup_authorized"]')
                expect(pickup1).to_be_checked()

                card1.locator('[name="guardian_last_name"]').fill("Parent")
                page.get_by_role("button", name="Save Changes").click()
                first_name = card1.locator('[name="guardian_first_name"]')
                assert first_name.evaluate("el => el.validity.valueMissing") is True
                expect(page.locator("#academyPlayerForm")).to_be_visible()

                first_name.fill("Primary")
                email1 = card1.locator('[name="guardian_email"]')
                email1.fill("parent@@example")
                page.get_by_role("button", name="Save Changes").click()
                assert email1.evaluate("el => el.validity.typeMismatch") is True

                email1.fill("primary.parent@example.com")
                card1.locator('[name="guardian_relationship"]').fill("Mother")
                card1.locator('[name="guardian_phone"]').fill("555-0200")
                card1.locator('[name="guardian_is_primary"]').check()
                card1.locator('[name="guardian_billing_contact"]').check()
                page.get_by_role("button", name="Save Changes").click()
                _wait_for_save(page)

                row_a = page.locator(".academy-player-row", has_text=player_a)
                expect(row_a).to_contain_text("Guardian: Primary Parent · 555-0200", timeout=10000)

                _open_player_editor(page, row_a)
                card1 = _guardian_card(page, 0)
                expect(card1.locator('[name="guardian_first_name"]')).to_have_value("Primary")
                expect(card1.locator('[name="guardian_last_name"]')).to_have_value("Parent")
                expect(card1.locator('[name="guardian_relationship"]')).to_have_value("Mother")
                expect(card1.locator('[name="guardian_email"]')).to_have_value("primary.parent@example.com")
                expect(card1.locator('[name="guardian_phone"]')).to_have_value("555-0200")
                expect(card1.locator('[name="guardian_is_primary"]')).to_be_checked()
                expect(card1.locator('[name="guardian_billing_contact"]')).to_be_checked()
                expect(card1.locator('[name="guardian_pickup_authorized"]')).to_be_checked()

                page.get_by_role("button", name="Add Guardian").click()
                card2 = _guardian_card(page, 1)
                card2.locator('[name="guardian_first_name"]').fill("Second")
                card2.locator('[name="guardian_last_name"]').fill("Parent")
                card2.locator('[name="guardian_relationship"]').fill("Father")
                card2.locator('[name="guardian_email"]').fill("second.parent@example.com")
                card2.locator('[name="guardian_phone"]').fill("555-0400")
                page.get_by_role("button", name="Save Changes").click()
                _wait_for_save(page)

                row_a = page.locator(".academy-player-row", has_text=player_a)
                expect(row_a).to_be_visible(timeout=10000)
                _open_player_editor(page, row_a)
                expect(page.locator("[data-guardian-card]")).to_have_count(2, timeout=10000)

                card1 = _guardian_card(page, 0)
                card1.locator('[name="guardian_phone"]').fill("555-0300")
                card1.locator('[name="guardian_pickup_authorized"]').uncheck()
                page.get_by_role("button", name="Save Changes").click()
                _wait_for_save(page)
                row_a = page.locator(".academy-player-row", has_text=player_a)
                expect(row_a).to_contain_text("Guardian: Primary Parent · 555-0300", timeout=10000)

                _open_player_editor(page, row_a)
                card1 = _guardian_card(page, 0)
                expect(card1.locator('[name="guardian_phone"]')).to_have_value("555-0300")
                expect(card1.locator('[name="guardian_pickup_authorized"]')).not_to_be_checked()
                expect(card1.locator('[name="guardian_is_primary"]')).to_be_checked()
                expect(card1.locator('[name="guardian_billing_contact"]')).to_be_checked()

                _guardian_card(page, 1).get_by_role("button", name="Remove").click()
                expect(page.locator("[data-guardian-card]")).to_have_count(1)
                page.get_by_role("button", name="Save Changes").click()
                _wait_for_save(page)
                row_a = page.locator(".academy-player-row", has_text=player_a)
                expect(row_a).to_be_visible(timeout=10000)
                _open_player_editor(page, row_a)
                expect(page.locator("[data-guardian-card]")).to_have_count(1, timeout=10000)
                page.get_by_role("button", name="Cancel").click()

                player_b = "Guardian Test Player B"
                row_b = _create_player(page, player_b)
                _open_player_editor(page, row_b)
                page.get_by_role("button", name="Add Guardian").click()
                bcard = _guardian_card(page, 0)
                bcard.locator('[name="guardian_first_name"]').fill("Other")
                bcard.locator('[name="guardian_last_name"]').fill("Family")
                bcard.locator('[name="guardian_phone"]').fill("555-0500")
                bcard.locator('[name="guardian_is_primary"]').check()
                page.get_by_role("button", name="Save Changes").click()
                _wait_for_save(page)
                row_b = page.locator(".academy-player-row", has_text=player_b)
                expect(row_b).to_contain_text("Guardian: Other Family · 555-0500", timeout=10000)

                row_a = page.locator(".academy-player-row", has_text=player_a)
                _open_player_editor(page, row_a)
                card1 = _guardian_card(page, 0)
                card1.locator('[name="guardian_phone"]').fill("555-0311")
                page.get_by_role("button", name="Save Changes").click()
                _wait_for_save(page)

                row_b = page.locator(".academy-player-row", has_text=player_b)
                expect(row_b).to_contain_text("Guardian: Other Family · 555-0500")
                _open_player_editor(page, row_b)
                bcard = _guardian_card(page, 0)
                expect(bcard.locator('[name="guardian_first_name"]')).to_have_value("Other")
                expect(bcard.locator('[name="guardian_last_name"]')).to_have_value("Family")
                expect(bcard.locator('[name="guardian_phone"]')).to_have_value("555-0500")

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/academy-guardian-ui-failure.png", full_page=True)
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
