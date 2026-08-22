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
                # video, event or biomechanics endpoints. The current C17 Academy
                # shell is now the only visible navigation surface.
                page.goto(f"{BASE_URL}/#analysis?id=1", wait_until="domcontentloaded")
                expect(page).to_have_url(f"{BASE_URL}/#cam", timeout=10000)

                c17_nav = page.locator('.c17-sidebar-nav')
                expect(c17_nav).to_be_visible(timeout=15000)
                dashboard_button = c17_nav.locator('[data-c17-target="cam"]')
                expect(dashboard_button).to_be_visible(timeout=10000)
                expect(dashboard_button).to_have_text("Dashboard")
                expect(dashboard_button).to_have_class("active")
                expect(dashboard_button).to_have_attribute("aria-current", "page")

                # The retired horizontal Academy tabs and legacy Academy workspace-nav
                # button must not be the user-facing navigation contract anymore.
                expect(page.locator('#camWorkspace .cam-tabs')).not_to_be_visible(timeout=10000)
                expect(page.locator('.sidebar .nav > button[data-workspace-nav="cam"]')).to_have_count(0)

                forbidden_network = [url for url in requests if _is_analysis_network(url)]
                assert forbidden_network == [], forbidden_network

                # Programmatic attempts to enter every parked Analysis route are redirected
                # back to Academy before the legacy router can issue video API traffic.
                for route in ["dashboard", "upload", "analyses", "comparisons", "analysis?id=99"]:
                    before = len(requests)
                    page.evaluate("route => { location.hash = route; }", route)
                    expect(page).to_have_url(f"{BASE_URL}/#cam", timeout=10000)
                    page.wait_for_timeout(150)
                    new_requests = requests[before:]
                    assert not any(_is_analysis_network(url) for url in new_requests), new_requests

                # The approved C17 sidebar remains operational after the redirects.
                reports = c17_nav.locator('[data-c17-target="cam?tab=reports"]')
                expect(reports).to_be_visible(timeout=10000)
                expect(reports).to_have_text("Reports")
                reports.click()
                expect(page).to_have_url(f"{BASE_URL}/#cam?tab=reports")
                expect(page.locator('.cam-reports-shell h1')).to_have_text("Reports", timeout=10000)
                expect(reports).to_have_class("active")
                expect(reports).to_have_attribute("aria-current", "page")

                # Returning to Dashboard must use the C17 Academy overview route.
                dashboard_button.click()
                expect(page).to_have_url(f"{BASE_URL}/#cam")
                expect(dashboard_button).to_have_class("active")
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
