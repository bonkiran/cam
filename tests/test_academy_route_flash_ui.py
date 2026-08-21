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
            prototypeFirstPaintFrames: 0,
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
          const targetRaw = targetHash.replace(/^#/, '');
          const [targetPage, targetQuery = ''] = targetRaw.split('?');
          const targetTab = targetPage === 'academy' ? (new URLSearchParams(targetQuery).get('tab') || 'overview') : null;
          const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
          location.hash = targetHash;
          for (let i = 0; i < 1200; i++) {
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

            const legacy = [
              ...document.querySelectorAll('#academyWorkspace .academy-hero, #academyWorkspace .academy-stats, #academyWorkspace .academy-dashboard-grid')
            ];
            if (legacy.some(isVisible)) result.legacyOverviewFrames += 1;

            const firstPaint = document.querySelector('#c17DashboardFirstPaint');
            if (isVisible(firstPaint)) result.prototypeFirstPaintFrames += 1;

            if (pending) {
              const main = document.querySelector('#app .main');
              if (main) {
                const visibleInterim = [...main.children]
                  .filter(el => !el.classList.contains('topbar'))
                  .filter(el => el.id !== 'c17DashboardFirstPaint')
                  .some(isVisible);
                if (visibleInterim) result.badInterimVisibleFrames += 1;
              }
            }

            const workspace = document.querySelector('#academyWorkspace .academy-content');
            if (targetTab === 'overview') {
              // The flash regression validates renderer ownership, not production data
              // availability. Dashboard v4 marks the content after either its normal
              // prototype render or its own error state; neither may expose legacy UI.
              if (workspace?.dataset.dashboardV4 === '1' && isVisible(workspace)) break;
            } else if (workspace && !pending && isVisible(workspace)) {
              break;
            }
          }
          return result;
        }
        """,
        target_hash,
    )


def _assert_clean(result: dict) -> None:
    assert result["guardVersion"] == "4", result
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
                page.goto(f"{BASE_URL}/#academy", wait_until="domcontentloaded")

                # The approved C17 layout owns first paint. Generic loading and legacy
                # Academy overview cards must never become visible while v4 loads.
                expect(page.locator("#c17DashboardFirstPaint")).to_be_visible(timeout=5000)
                assert page.evaluate("document.documentElement.dataset.academyRouteGuard") == "4"
                assert page.evaluate("document.documentElement.dataset.academyRouterAdapter") == "1"
                assert page.evaluate("document.documentElement.classList.contains('academy-route-pending')") is False
                expect(page.locator("#academyWorkspace .academy-hero")).to_be_hidden(timeout=5000)
                expect(page.locator("#academyWorkspace .academy-stats")).to_be_hidden(timeout=5000)

                # Dashboard v4 explicitly claims the workspace before the first-paint
                # shell is removed. Local CI may use a sparse temp DB, so this test does
                # not require successful production dashboard data; it requires that the
                # ownership handoff never reveals the legacy overview.
                owned = page.locator('#academyWorkspace .academy-content[data-dashboard-v4="1"]')
                expect(owned).to_be_visible(timeout=30000)
                expect(page.locator("#c17DashboardFirstPaint")).to_be_hidden(timeout=5000)
                expect(page.locator("#academyWorkspace .academy-hero")).to_be_hidden(timeout=5000)

                players = _watch_transition(page, "academy?tab=players")
                expect(page.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)
                _assert_clean(players)
                assert players["sawLoadingState"] is False, players

                back_overview = _watch_transition(page, "academy")
                expect(page.locator('#academyWorkspace .academy-content[data-dashboard-v4="1"]')).to_be_visible(timeout=30000)
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
