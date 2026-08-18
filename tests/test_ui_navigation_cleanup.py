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


def test_analysis_uses_horizontal_tabs_and_academy_navigation_stays_clean():
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

                # Analysis is one top-level sidebar workspace, with no fly-out submenu.
                analysis_button = page.locator('.sidebar .nav > button[data-workspace-nav="analysis"]')
                expect(analysis_button).to_be_visible(timeout=10000)
                expect(analysis_button).to_have_text("◈Analysis")
                expect(analysis_button).to_have_class("active")
                expect(page.locator('.nav-group[data-nav-group="analysis"]')).to_have_count(0)
                expect(page.locator('.sidebar .nav > button[data-route="upload"]')).to_have_count(0)
                expect(page.locator('.sidebar .nav > button[data-route="analyses"]')).to_have_count(0)
                expect(page.locator('.sidebar .nav > button[data-route="comparisons"]')).to_have_count(0)

                # Analysis navigation is horizontal, matching the Academy workspace pattern.
                analysis_tabs = page.locator('#analysisWorkspaceTabs')
                expect(analysis_tabs).to_be_visible(timeout=10000)
                assert _button_labels(analysis_tabs.locator('button')) == [
                    "Overview", "Upload Video", "My Analyses", "Comparisons"
                ]
                expect(analysis_tabs.locator('button[data-analysis-route="dashboard"]')).to_have_class("active")

                analysis_tabs.locator('button[data-analysis-route="upload"]').click()
                expect(page).to_have_url(f"{BASE_URL}/#upload")
                expect(page.locator('#analysisWorkspaceTabs button[data-analysis-route="upload"]')).to_have_class("active")

                page.locator('#analysisWorkspaceTabs button[data-analysis-route="analyses"]').click()
                expect(page).to_have_url(f"{BASE_URL}/#analyses")
                expect(page.locator('#analysisWorkspaceTabs button[data-analysis-route="analyses"]')).to_have_class("active")

                page.locator('#analysisWorkspaceTabs button[data-analysis-route="comparisons"]').click()
                expect(page).to_have_url(f"{BASE_URL}/#comparisons")
                expect(page.locator('#analysisWorkspaceTabs button[data-analysis-route="comparisons"]')).to_have_class("active")

                # Academy remains a separate workspace and Analysis tabs disappear there.
                academy_group = page.locator('.nav-group[data-nav-group="academy"]')
                expect(academy_group).to_be_visible(timeout=10000)
                academy_labels = _button_labels(academy_group.locator('.nav-group-submenu button'))
                assert academy_labels == ["⌂Overview"], academy_labels
                expect(page.locator('.sidebar .nav > button[data-route="players"]')).to_have_count(0)
                expect(page.locator('.sidebar .nav > button[data-route="reports"]')).to_have_count(0)

                _open_group(academy_group)
                academy_overview = academy_group.locator('.nav-group-submenu button').filter(has_text="Overview")
                expect(academy_overview).to_be_visible()
                academy_overview.click()
                expect(page.locator('#academyWorkspace .academy-tabs')).to_be_visible(timeout=15000)
                expect(page.locator('#analysisWorkspaceTabs')).to_have_count(0)

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

                # One click on Analysis returns to Analysis Overview and restores the horizontal tabs.
                page.locator('.sidebar .nav > button[data-workspace-nav="analysis"]').click()
                expect(page).to_have_url(f"{BASE_URL}/#dashboard")
                expect(page.locator('#analysisWorkspaceTabs')).to_be_visible(timeout=10000)
                expect(page.locator('#analysisWorkspaceTabs button[data-analysis-route="dashboard"]')).to_have_class("active")
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
