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


def _is_analysis_network(url: str) -> bool:
    return "/api/videos" in url or "/api/biomechanics" in url or "/api/events" in url


def test_analysis_is_paused_without_video_api_traffic_and_academy_stays_operational():
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
            requests: list[str] = []
            page.on("request", lambda request: requests.append(request.url))
            try:
                # A stale Analysis URL must be neutralized before app.js can call
                # /api/videos/{id}, event or biomechanics endpoints. Academy may still
                # call the shared /api/dashboard aggregate for its Dashboard metrics.
                page.goto(f"{BASE_URL}/#analysis?id=1", wait_until="domcontentloaded")
                expect(page).to_have_url(f"{BASE_URL}/#academy", timeout=10000)
                expect(page.locator('#academyWorkspace .academy-tabs')).to_be_visible(timeout=15000)

                forbidden_network = [url for url in requests if _is_analysis_network(url)]
                assert forbidden_network == [], forbidden_network

                # Analysis remains visible as a parked workspace, but is disabled so
                # users cannot accidentally restart video traffic while Academy is active.
                analysis_button = page.locator('.sidebar .nav > button[data-workspace-nav="analysis"]')
                expect(analysis_button).to_be_visible(timeout=10000)
                expect(analysis_button).to_have_text("◈Analysis")
                expect(analysis_button).to_be_disabled()
                expect(analysis_button).to_have_attribute("aria-disabled", "true")
                expect(analysis_button).to_have_attribute(
                    "title", "Analysis is temporarily paused while Academy pilot work is active."
                )
                expect(page.locator('#analysisWorkspaceTabs')).to_have_count(0)
                expect(page.locator('.nav-group[data-nav-group="analysis"]')).to_have_count(0)

                # Programmatic attempts to enter every Analysis route are redirected
                # back to Academy before the legacy router runs.
                for route in ["dashboard", "upload", "analyses", "comparisons", "analysis?id=99"]:
                    before = len(requests)
                    page.evaluate("route => { location.hash = route; }", route)
                    expect(page).to_have_url(f"{BASE_URL}/#academy", timeout=10000)
                    page.wait_for_timeout(150)
                    new_requests = requests[before:]
                    assert not any(_is_analysis_network(url) for url in new_requests), new_requests

                # Academy keeps its direct sidebar entry and horizontal workspace tabs.
                academy_button = page.locator('.sidebar .nav > button[data-workspace-nav="academy"]')
                expect(academy_button).to_be_visible(timeout=10000)
                expect(academy_button).to_have_text("▦Academy")
                expect(academy_button).to_have_class("active")
                expect(page.locator('.nav-group[data-nav-group="academy"]')).to_have_count(0)
                expect(page.locator('.sidebar .nav > button[data-route="players"]')).to_have_count(0)
                expect(page.locator('.sidebar .nav > button[data-route="reports"]')).to_have_count(0)
                expect(page.locator('#academyWorkspace .academy-tabs button').filter(has_text="Dashboard")).to_have_count(1)

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
                expect(academy_button).to_have_class("active")
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
