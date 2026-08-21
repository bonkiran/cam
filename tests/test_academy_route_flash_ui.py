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
            finalHash: null,
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
          for (let i = 0; i < 1200; i++) {
            await frame();
            result.frames += 1;
            result.finalHash = location.hash;
            result.guardVersion = document.documentElement.dataset.academyRouteGuard || null;
            result.adapterVersion = document.documentElement.dataset.academyRouterAdapter || null;
            const pending = document.documentElement.classList.contains('academy-route-pending');
            result.sawLoadingState = result.sawLoadingState || pending;

            if (hadWorkspace && !document.querySelector('#academyWorkspace')) result.workspaceMissingFrames += 1;

            const genericTextNodes = [...document.querySelectorAll('#app .main *')].filter(el => {
              const text = (el.textContent || '').trim();
              return text.includes('Not implemented yet') ||
                     text.includes('This module is part of the real application shell') ||
                     (text.startsWith('Page') && text.includes('Core engineering'));
            });
            if (genericTextNodes.some(isVisible)) result.badPlaceholderFrames += 1;

            const legacy = [...document.querySelectorAll(
              '#academyWorkspace .academy-hero, #academyWorkspace .academy-stats, #academyWorkspace .academy-dashboard-grid, .page-head + .stats'
            )];
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
            const raw = location.hash.replace(/^#/, '');
            const [pageName, query = ''] = raw.split('?');
            const tab = pageName === 'academy' ? (new URLSearchParams(query).get('tab') || 'overview') : null;
            if (tab === 'overview') {
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


def test_dashboard_is_canonical_academy_overview_without_legacy_flash():
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
                # Legacy/default Dashboard entry is normalized before app.js can paint
                # the old video-analysis dashboard.
                page.goto(f"{BASE_URL}/#dashboard", wait_until="domcontentloaded")
                expect(page).to_have_url(f"{BASE_URL}/#academy", timeout=5000)
                assert page.evaluate("document.documentElement.dataset.academyRouteGuard") == "4"
                assert page.evaluate("document.documentElement.dataset.academyRouterAdapter") == "1"
                expect(page.locator("#academyWorkspace .academy-hero")).to_be_hidden(timeout=5000)
                expect(page.locator("#academyWorkspace .academy-stats")).to_be_hidden(timeout=5000)
                expect(page.locator("#academyWorkspace .academy-dashboard-grid")).to_be_hidden(timeout=5000)

                owned = page.locator('#academyWorkspace .academy-content[data-dashboard-v4="1"]')
                expect(owned).to_be_visible(timeout=30000)

                # The C17 menu exposes one Dashboard concept; there is no separate
                # Academy menu item competing for the selected state.
                expect(page.locator('.c17-sidebar-nav [data-c17-target="academy"]')).to_have_count(1)
                expect(page.locator('.c17-sidebar-nav [data-c17-target="academy"] b')).to_have_text('Dashboard')
                expect(page.locator('.c17-sidebar-nav b', has_text='Academy')).to_have_count(0)
                expect(page.locator('.c17-sidebar-nav [data-c17-target="academy"]')).to_have_attribute('aria-current', 'page')

                # Players -> Dashboard must return directly to the prototype.
                players = _watch_transition(page, "academy?tab=players")
                expect(page.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)
                _assert_clean(players)

                back = _watch_transition(page, "dashboard")
                _assert_clean(back)
                assert back["finalHash"] == "#academy", back
                expect(page.locator('#academyWorkspace .academy-content[data-dashboard-v4="1"]')).to_be_visible(timeout=30000)

                # Clicking Dashboard again while already on Dashboard must not replay
                # the legacy dashboard or disturb the selected state.
                repeated = _watch_transition(page, "dashboard")
                _assert_clean(repeated)
                assert repeated["finalHash"] == "#academy", repeated
                expect(page.locator('.c17-sidebar-nav [data-c17-target="academy"]')).to_have_attribute('aria-current', 'page')
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
