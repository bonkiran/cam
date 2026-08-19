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
          const buttons = [...document.querySelectorAll('#academyWorkspace .academy-tabs button')];
          const button = buttons.find(el => (el.textContent || '').trim() === label);
          if (!button) throw new Error(`Tab not found: ${label}`);

          const visible = (el) => {
            if (!el) return false;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && rect.width > 0 && rect.height > 0;
          };
          const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
          const result = {
            frames: 0,
            firstFrameActive: false,
            blankFrames: 0,
            snapshotFrames: 0,
            loadingPanelExposedFrames: 0,
            movingProgressVisibleFrames: 0,
            maxVisibleMainChildren: 0,
          };

          button.click();
          for (let i = 0; i < 300; i++) {
            await frame();
            result.frames += 1;
            const currentButtons = [...document.querySelectorAll('#academyWorkspace .academy-tabs button')];
            const currentButton = currentButtons.find(el => (el.textContent || '').trim() === label);
            if (i === 0) result.firstFrameActive = !!currentButton?.classList.contains('active');

            const snapshot = document.getElementById('academyTransitionSnapshot');
            const snapshotVisible = visible(snapshot);
            if (snapshotVisible) result.snapshotFrames += 1;

            const movingProgress = document.querySelector('#academyTransitionSnapshot .academy-transition-progress');
            if (visible(movingProgress)) result.movingProgressVisibleFrames += 1;

            const content = document.querySelector('#academyWorkspace .academy-content');
            const contentVisible = visible(content);
            const ready = !!document.querySelector(readySelector) && !document.querySelector(`${readySelector} .academy-loading`);
            if (!snapshotVisible && !contentVisible && !ready) result.blankFrames += 1;

            const exposedLoading = [...document.querySelectorAll('#academyWorkspace .academy-loading')].some(visible);
            if (exposedLoading && !snapshotVisible) result.loadingPanelExposedFrames += 1;

            const main = document.querySelector('#app .main');
            if (main) {
              const count = [...main.children].filter(el => !el.classList.contains('topbar') && visible(el)).length;
              result.maxVisibleMainChildren = Math.max(result.maxVisibleMainChildren, count);
            }

            if (ready && !snapshotVisible) break;
          }
          result.metrics = {...(window.__academyNavigationPerformance || {})};
          return result;
        }
        """,
        {"label": label, "readySelector": ready_selector},
    )


def _assert_stable_transition(result: dict, require_snapshot: bool = False) -> None:
    assert result["firstFrameActive"] is True, result
    assert result["blankFrames"] == 0, result
    assert result["loadingPanelExposedFrames"] == 0, result
    assert result["movingProgressVisibleFrames"] == 0, result
    if require_snapshot:
        assert result["snapshotFrames"] > 0, result


def test_academy_tab_clicks_are_immediate_and_visually_stable():
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
                expect(page.locator(".academy-hero")).to_be_visible(timeout=20000)

                players = _observe_click(page, "Players", ".academy-player-panel")
                _assert_stable_transition(players, require_snapshot=True)

                dashboard = _observe_click(page, "Dashboard", ".academy-hero")
                _assert_stable_transition(dashboard)

                programs = _observe_click(page, "Programs & Enrollment", "#openProgramForm")
                _assert_stable_transition(programs, require_snapshot=True)

                coaches = _observe_click(page, "Coaches", "#openCoachForm")
                _assert_stable_transition(coaches, require_snapshot=True)

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
