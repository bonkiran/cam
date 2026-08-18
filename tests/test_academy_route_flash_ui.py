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
          const result = { badVisibleFrames: 0, frames: 0, sawLoadingState: false };
          const isVisible = (el) => {
            if (!el) return false;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
          };
          const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
          location.hash = targetHash;
          for (let i = 0; i < 180; i++) {
            await frame();
            result.frames += 1;
            result.sawLoadingState = result.sawLoadingState || document.documentElement.classList.contains('academy-route-pending');
            const bad = [...document.querySelectorAll('.page-head,.panel')].some(el => {
              const text = el.textContent || '';
              return isVisible(el) && (
                text.includes('Not implemented yet') ||
                text.includes('This module is part of the real application shell') ||
                (text.trim().startsWith('Page') && text.includes('Core engineering'))
              );
            });
            if (bad) result.badVisibleFrames += 1;
            const workspace = document.querySelector('#academyWorkspace .academy-content');
            const pending = document.documentElement.classList.contains('academy-route-pending');
            if (workspace && !pending) break;
          }
          return result;
        }
        """,
        target_hash,
    )


def test_academy_routes_never_paint_generic_placeholder():
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
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            try:
                page.goto(f"{BASE_URL}/#dashboard", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Dashboard")).to_be_visible(timeout=15000)

                overview = _watch_transition(page, "academy")
                expect(page.locator("#academyWorkspace")).to_be_visible(timeout=15000)
                assert overview["badVisibleFrames"] == 0, overview

                players = _watch_transition(page, "academy?tab=players")
                expect(page.get_by_role("heading", name="Academy Players")).to_be_visible(timeout=15000)
                assert players["badVisibleFrames"] == 0, players

                back_overview = _watch_transition(page, "academy")
                expect(page.locator("#academyWorkspace")).to_be_visible(timeout=15000)
                assert back_overview["badVisibleFrames"] == 0, back_overview
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
