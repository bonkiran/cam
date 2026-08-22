import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8792"


def _reset_shared_postgres_state() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "academy_tournament_entries",
        "academy_tournaments",
        "academy_match_player_stats",
        "academy_match_squad",
        "academy_matches",
        "academy_team_roster",
        "academy_teams",
        "academy_auth_sessions",
        "academy_access_audit",
        "academy_users",
        "players",
        "academies",
    ]
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            existing = []
            for table in candidates:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cursor.fetchone()[0] is not None:
                    existing.append(table)
            if existing:
                cursor.execute(f"TRUNCATE TABLE {', '.join(existing)} RESTART IDENTITY CASCADE")
        conn.commit()


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
    raise RuntimeError(f"Tournament type UI server did not become ready: {last_error}")


def _request(method: str, path: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw) if raw else None
        except Exception:
            body = raw
        return exc.code, body


def test_tournament_type_is_selectable_and_saved_in_browser():
    _reset_shared_postgres_state()

    data_dir = tempfile.mkdtemp(prefix="cam-track-a-tournament-ui-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8792"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        status, _ = _request("PUT", "/api/cam/profile", {"name": "Track A Tournament UI Academy"})
        assert status == 200

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            try:
                page.goto(f"{BASE_URL}/#cam?tab=tournaments", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Tournaments")).to_be_visible(timeout=15000)
                page.get_by_role("button", name="Add Tournament").click()
                expect(page.get_by_role("heading", name="Create Tournament")).to_be_visible(timeout=10000)

                type_select = page.locator('#camTournamentForm [name="tournament_type"]')
                expect(type_select).to_be_visible(timeout=10000)
                expect(type_select).to_have_value("external")
                type_select.select_option("internal")

                page.locator('#camTournamentForm [name="name"]').fill("Track A Browser Internal Cup")
                page.locator('#camTournamentForm [name="organizer"]').fill("Track A Tournament UI Academy")
                page.locator('#camTournamentForm [name="location"]').fill("Academy Ground")
                page.locator('#camTournamentForm [name="start_date"]').fill("2026-09-19")
                page.locator('#camTournamentForm [name="end_date"]').fill("2026-09-20")
                page.get_by_role("button", name="Create Tournament").click()

                expect(page.locator("#toast")).to_contain_text("Tournament created", timeout=10000)
                expect(page.locator(".cam-tournament-row", has_text="Track A Browser Internal Cup")).to_be_visible(timeout=10000)

                status, tournaments = _request("GET", "/api/cam/tournaments")
                assert status == 200
                created = next(row for row in tournaments if row["name"] == "Track A Browser Internal Cup")
                assert created["tournament_type"] == "internal"

                # Edit form must reload the persisted classification, not fall back
                # to the new-tournament default.
                page.locator(".cam-tournament-row", has_text="Track A Browser Internal Cup").get_by_role("button", name="Edit").click()
                edit_type = page.locator('#camTournamentForm [name="tournament_type"]')
                expect(edit_type).to_have_value("internal", timeout=10000)
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
