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
    raise RuntimeError(f"CrickAnalysis navigation cleanup server did not become ready: {last_error}")


def _button_labels(locator) -> list[str]:
    return [text.strip() for text in locator.all_text_contents()]


def _open_group(group) -> None:
    parent = group.locator(".nav-group-parent")
    if parent.get_attribute("aria-expanded") != "true":
        parent.click()
    expect(parent).to_have_attribute("aria-expanded", "true")


def test_sidebar_and_academy_report_navigation_are_cleaned_up():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-ui-nav-cleanup-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            try:
                page.goto(f"{BASE_URL}/#dashboard", wait_until="domcontentloaded")

                analysis_group = page.locator('.nav-group[data-nav-group="analysis"]')
                academy_group = page.locator('.nav-group[data-nav-group="academy"]')
                expect(analysis_group).to_be_visible(timeout=10000)
                expect(academy_group).to_be_visible(timeout=10000)

                # Dashboard is no longer a standalone item. It is Analysis > Overview.
                expect(page.locator('.sidebar .nav > button[data-route="dashboard"]')).to_have_count(0)
                analysis_labels = _button_labels(analysis_group.locator('.nav-group-submenu button'))
                assert analysis_labels == ["⌂Overview", "⇧Upload Video", "▣My Analyses", "⇄Comparisons"], analysis_labels

                # Players and Reports no longer appear in the Academy sidebar submenu.
                academy_labels = _button_labels(academy_group.locator('.nav-group-submenu button'))
                assert academy_labels == ["⌂Overview"], academy_labels
                expect(page.locator('.sidebar .nav > button[data-route="players"]')).to_have_count(0)
                expect(page.locator('.sidebar .nav > button[data-route="reports"]')).to_have_count(0)

                # Open Academy and confirm Reports lives beside Player Reviews in the Academy tabs.
                _open_group(academy_group)
                academy_overview = academy_group.locator('.nav-group-submenu button').filter(has_text="Overview")
                expect(academy_overview).to_be_visible()
                academy_overview.click()
                expect(page.locator('#academyWorkspace .academy-tabs')).to_be_visible(timeout=15000)
                reviews = page.locator('#academyWorkspace .academy-tabs button').filter(has_text="Player Reviews")
                reports = page.locator('#academyWorkspace .academy-tabs button').filter(has_text="Reports")
                expect(reviews).to_have_count(1)
                expect(reports).to_have_count(1)
                assert page.evaluate(
                    """() => {
                      const reviews=[...document.querySelectorAll('#academyWorkspace .academy-tabs button')]
                        .find(x => x.textContent.trim()==='Player Reviews');
                      const reports=[...document.querySelectorAll('#academyWorkspace .academy-tabs button')]
                        .find(x => x.textContent.trim()==='Reports');
                      return reviews && reports && reviews.nextElementSibling===reports;
                    }"""
                ) is True

                reports.click()
                expect(page).to_have_url(f"{BASE_URL}/#academy?tab=reports")
                expect(page.locator('.academy-reports-shell h1')).to_have_text("Reports", timeout=10000)

                # Analysis > Overview still routes to the existing analysis dashboard content.
                _open_group(analysis_group)
                analysis_overview = analysis_group.locator('.nav-group-submenu button').filter(has_text="Overview")
                expect(analysis_overview).to_be_visible()
                analysis_overview.click()
                expect(page).to_have_url(f"{BASE_URL}/#dashboard")
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
