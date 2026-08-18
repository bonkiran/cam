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
            badPlaceholderDomFrames: 0,
            frames: 0,
            sawLoadingState: false,
            guardVersion: null,
            baseRouterBypassed: false,
          };
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
            result.baseRouterBypassed = window.__academyBaseRouterBypassed === true;
            const pending = document.documentElement.classList.contains('academy-route-pending');
            result.sawLoadingState = result.sawLoadingState || pending;

            const genericTextNodes = [...document.querySelectorAll('#app .main *')].filter(el => {
              const text = (el.textContent || '').trim();
              return text.includes('Not implemented yet') ||
                     text.includes('This module is part of the real application shell') ||
                     (text.startsWith('Page') && text.includes('Core engineering'));
            });
            if (genericTextNodes.length) result.badPlaceholderDomFrames += 1;
            if (genericTextNodes.some(isVisible)) result.badPlaceholderFrames += 1;

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
    assert result["guardVersion"] == "2", result
    assert result["baseRouterBypassed"] is True, result
    assert result["badPlaceholderDomFrames"] == 0, result
    assert result["badPlaceholderFrames"] == 0, result
    assert result["badInterimVisibleFrames"] == 0, result


def test_academy_routes_never_paint_or_create_generic_placeholder():
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
                page.goto(f"{BASE_URL}/#dashboard", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=15000)

                overview = _watch_transition(page, "academy")
                expect(page.locator("#academyWorkspace")).to_be_visible(timeout=15000)
                _assert_clean(overview)

                players = _watch_transition(page, "academy?tab=players")
                expect(page.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)
                _assert_clean(players)

                back_overview = _watch_transition(page, "academy")
                expect(page.locator("#academyWorkspace")).to_be_visible(timeout=15000)
                _assert_clean(back_overview)

                # Direct-load path: app.js would have created the placeholder before
                # Academy loaded in v1. The bridge must remove/bypass it before paint.
                direct = browser.new_page(viewport={"width": 1778, "height": 832})
                direct.goto(f"{BASE_URL}/#academy?tab=players", wait_until="domcontentloaded")
                expect(direct.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)
                assert direct.evaluate("window.__academyBaseRouterBypassed === true") is True
                assert direct.locator("text=Not implemented yet").count() == 0
                direct.close()
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
