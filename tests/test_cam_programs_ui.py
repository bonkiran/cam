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


def test_cam_programs_ui_end_to_end():
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

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1500, "height": 1100})
            try:
                page.goto(f"{BASE_URL}/#cam?tab=programs", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Programs", exact=True).first).to_be_visible(timeout=15000)
                expect(page.get_by_role("heading", name="Program Operations", exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Create Program")).to_be_visible()

                # Enrollment is intentionally a separate primary CAM workflow now.
                expect(page.get_by_role("button", name="Enrollment", exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Enroll Player")).to_have_count(0)

                # Create a program from the current Programs operations page.
                page.get_by_role("button", name="Create Program").click()
                program_form = page.locator("#camProgramForm")
                expect(program_form).to_be_visible(timeout=10000)
                program_form.locator('[name="name"]').fill("UI U13 Development")
                program_form.locator('[name="code"]').fill("UI-U13")
                program_form.locator('[name="program_type"]').select_option("group")
                program_form.locator('[name="age_group"]').fill("U13")
                program_form.locator('[name="skill_level"]').fill("Developing")
                program_form.locator('[name="start_date"]').fill("2026-09-01")
                program_form.locator('[name="end_date"]').fill("2026-12-01")
                program_form.locator('[name="description"]').fill("UI-created development program")
                page.get_by_role("button", name="Create Program").last.click()
                program_row = page.locator(".cam-program-row", has_text="UI U13 Development")
                expect(program_row).to_be_visible(timeout=10000)
                expect(program_row).to_contain_text("0 current")

                # Edit the program and confirm the current row updates.
                program_row.get_by_role("button", name="Edit").click()
                program_form = page.locator("#camProgramForm")
                expect(program_form).to_be_visible()
                program_form.locator('[name="name"]').fill("UI U13 Development Plus")
                program_form.locator('[name="end_date"]').fill("2026-12-15")
                page.get_by_role("button", name="Save Program").click()
                program_row = page.locator(".cam-program-row", has_text="UI U13 Development Plus")
                expect(program_row).to_be_visible(timeout=10000)
                expect(program_row).to_contain_text("U13")

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
