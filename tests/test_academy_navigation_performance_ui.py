import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8776"


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
    raise RuntimeError(f"CrickAnalysis navigation test server did not become ready: {last_error}")


def _observe_click(page, label: str, ready_selector: str) -> dict:
    return page.evaluate(
        """
        async ({label, readySelector}) => {
          const visible = (el) => {
            if (!el) return false;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return !el.hidden && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && rect.width > 0 && rect.height > 0;
          };
          const buttons = [...document.querySelectorAll('.c17-sidebar-nav [data-c17-target]')];
          const button = buttons.find(el => (el.textContent || '').trim() === label && visible(el));
          if (!button) throw new Error(`Visible C17 nav item not found: ${label}`);

          const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
          const result = {
            frames: 0,
            firstFrameActive: false,
            blankFrames: 0,
            firstPaintFrames: 0,
            legacyOverviewFrames: 0,
            loadingPanelExposedFrames: 0,
            maxVisibleMainChildren: 0,
            finalHash: null,
          };

          button.click();
          for (let i = 0; i < 300; i++) {
            await frame();
            result.frames += 1;
            result.finalHash = location.hash;
            const currentButtons = [...document.querySelectorAll('.c17-sidebar-nav [data-c17-target]')];
            const currentButton = currentButtons.find(el => (el.textContent || '').trim() === label && visible(el));
            if (i === 0) result.firstFrameActive = !!currentButton?.classList.contains('active');

            const content = document.querySelector('#academyWorkspace .academy-content');
            const contentVisible = visible(content);
            const readyNode = document.querySelector(readySelector);
            const ready = !!readyNode && visible(readyNode) && !readyNode.querySelector?.('.academy-loading');
            const firstPaintVisible = visible(document.getElementById('c17DashboardFirstPaint'));
            if (firstPaintVisible) result.firstPaintFrames += 1;
            if (!contentVisible && !ready && !firstPaintVisible) result.blankFrames += 1;

            const exposedLoading = [...document.querySelectorAll('#academyWorkspace .academy-loading')].some(visible);
            if (exposedLoading) result.loadingPanelExposedFrames += 1;

            const legacy = [...document.querySelectorAll(
              '#academyWorkspace .academy-hero, #academyWorkspace .academy-stats, #academyWorkspace .academy-dashboard-grid, .page-head + .stats'
            )];
            if (legacy.some(visible)) result.legacyOverviewFrames += 1;

            const main = document.querySelector('#app .main');
            if (main) {
              const count = [...main.children].filter(el => !el.classList.contains('topbar') && visible(el)).length;
              result.maxVisibleMainChildren = Math.max(result.maxVisibleMainChildren, count);
            }

            if (ready) break;
          }
          result.metrics = {...(window.__academyNavigationPerformance || {})};
          return result;
        }
        """,
        {"label": label, "readySelector": ready_selector},
    )


def _assert_stable_transition(result: dict) -> None:
    assert result["firstFrameActive"] is True, result
    assert result["blankFrames"] == 0, result
    assert result["loadingPanelExposedFrames"] == 0, result


def test_c17_left_navigation_clicks_are_immediate_and_visually_stable():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-nav-performance-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8776"],
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
            page = browser.new_page(viewport={"width": 1778, "height": 950})

            # Add visible latency so a transition regression cannot hide behind a fast local DB.
            def delay_academy_get(route):
                request = route.request
                if request.method == "GET" and ("/api/academy/" in request.url or request.url.endswith("/api/dashboard")):
                    time.sleep(0.25)
                route.continue_()

            page.route("**/api/**", delay_academy_get)
            try:
                page.goto(f"{BASE_URL}/#academy", wait_until="domcontentloaded")
                expect(page.locator("#academyWorkspace")).to_be_visible(timeout=20000)
                expect(page.locator('#academyWorkspace .academy-content[data-dashboard-v4="1"]')).to_be_visible(timeout=30000)
                expect(page.locator('.c17-sidebar-nav [data-c17-target="academy"]')).to_have_attribute('aria-current', 'page')
                expect(page.locator('.c17-sidebar-nav b', has_text='Academy')).to_have_count(0)

                players = _observe_click(page, "Players", ".academy-player-panel")
                _assert_stable_transition(players)

                dashboard = _observe_click(page, "Dashboard", '.academy-content[data-dashboard-v4="1"]')
                _assert_stable_transition(dashboard)
                assert dashboard["finalHash"] == "#academy", dashboard
                assert dashboard["legacyOverviewFrames"] == 0, dashboard
                assert dashboard["firstPaintFrames"] > 0, dashboard

                programs = _observe_click(page, "Programs", "#openProgramForm")
                _assert_stable_transition(programs)

                coaches = _observe_click(page, "Coaches", "#openCoachForm")
                _assert_stable_transition(coaches)

                # Returning through recently-used data should exercise the short-lived GET cache.
                back_players = _observe_click(page, "Players", ".academy-player-panel")
                _assert_stable_transition(back_players)
                metrics = back_players["metrics"]
                assert metrics.get("version") == "1", metrics
                assert metrics.get("cacheHits", 0) + metrics.get("deduplicatedRequests", 0) > 0, metrics
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
