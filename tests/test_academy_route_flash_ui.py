import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8775"


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
    raise RuntimeError(f"CrickAnalysis route-flash test server did not become ready: {last_error}")


def _watch_transition(page, target_hash: str) -> dict:
    return page.evaluate(
        """
        async (targetHash) => {
          const result = {
            badPlaceholderFrames: 0,
            badInterimVisibleFrames: 0,
            legacyOverviewFrames: 0,
            workspaceMissingFrames: 0,
            frames: 0,
            sawLoadingState: false,
            guardVersion: null,
            adapterVersion: null,
          };
          const hadWorkspace = !!document.querySelector('#academyWorkspace');
          const isVisible = (el) => {
            if (!el) return false;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' && style.opacity !== '0' && rect.width > 0 && rect.height > 0;
          };
          const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
          location.hash = targetHash;
          for (let i = 0; i < 180; i++) {
            await frame();
            result.frames += 1;
            result.guardVersion = document.documentElement.dataset.academyRouteGuard || null;
            result.adapterVersion = document.documentElement.dataset.academyRouterAdapter || null;
            const pending = document.documentElement.classList.contains('academy-route-pending');
            result.sawLoadingState = result.sawLoadingState || pending;

            if (hadWorkspace && !document.querySelector('#academyWorkspace')) {
              result.workspaceMissingFrames += 1;
            }

            const genericTextNodes = [...document.querySelectorAll('#app .main *')].filter(el => {
              const text = (el.textContent || '').trim();
              return text.includes('Not implemented yet') ||
                     text.includes('This module is part of the real application shell') ||
                     (text.startsWith('Page') && text.includes('Core engineering'));
            });
            if (genericTextNodes.some(isVisible)) result.badPlaceholderFrames += 1;

            // The retired Academy overview must never become a painted transition state.
            // This is the exact view that appeared for several seconds in the production video.
            const legacyHero = document.querySelector('#academyWorkspace .academy-content > .academy-hero');
            if (isVisible(legacyHero) && (legacyHero.textContent || '').includes('ACADEMY + PERFORMANCE INTELLIGENCE')) {
              result.legacyOverviewFrames += 1;
            }

            if (pending) {
              const main = document.querySelector('#app .main');
              if (main) {
                const visibleInterim = [...main.children]
                  .filter(el => !el.classList.contains('topbar'))
                  .some(isVisible);
                if (visibleInterim) result.badInterimVisibleFrames += 1;
              }
            }

            const workspace = document.querySelector('#academyWorkspace .academy-content');
            if (workspace && !pending) break;
          }
          return result;
        }
        """,
        target_hash,
    )


def _assert_clean(result: dict) -> None:
    assert result["guardVersion"] == "3", result
    assert result["adapterVersion"] == "1", result
    assert result["badPlaceholderFrames"] == 0, result
    assert result["badInterimVisibleFrames"] == 0, result
    assert result["legacyOverviewFrames"] == 0, result
    assert result["workspaceMissingFrames"] == 0, result


def test_academy_routes_never_paint_generic_placeholder_or_reload_between_tabs():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-route-flash-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8775"],
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
            page = browser.new_page(viewport={"width": 1778, "height": 832})
            try:
                # Analysis is intentionally parked during Academy pilot work, so
                # Academy is now the stable initial workspace for this regression.
                # The separate paused-Analysis regression verifies stale Analysis
                # URLs redirect here before any video API request can leave the page.
                page.goto(f"{BASE_URL}/#academy", wait_until="domcontentloaded")
                expect(page.locator("#academyWorkspace")).to_be_visible(timeout=15000)
                expect(page.locator("#academyWorkspace .academy-content")).to_be_visible(timeout=15000)
                assert page.evaluate("document.documentElement.dataset.academyRouteGuard") == "3"
                assert page.evaluate("document.documentElement.dataset.academyRouterAdapter") == "1"

                # The legacy dashboard is retired from the visible Academy overview.
                expect(page.locator("#academyWorkspace .academy-content > .academy-hero")).to_have_count(0)

                # Academy -> Academy navigation must preserve the mounted workspace
                # and must never re-enable the full-page Loading Academy overlay.
                players = _watch_transition(page, "academy?tab=players")
                expect(page.get_by_role("heading", name="Players", exact=True)).to_be_visible(timeout=15000)
                _assert_clean(players)
                assert players["sawLoadingState"] is False, players

                back_overview = _watch_transition(page, "academy")
                expect(page.locator("#academyWorkspace")).to_be_visible(timeout=15000)
                _assert_clean(back_overview)
                assert back_overview["sawLoadingState"] is False, back_overview
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
