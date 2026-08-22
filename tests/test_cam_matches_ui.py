import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8777"


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
    raise RuntimeError(f"CrickAnalysis matches test server did not become ready: {last_error}")


def _json_request(method: str, path: str, payload: dict):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_teams_matches_ui_end_to_end():
    data_dir = tempfile.mkdtemp(prefix="crickanalysis-matches-ui-test-")
    env = os.environ.copy()
    env["CRICKANALYSIS_DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(REPO_ROOT)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "run:app", "--host", "127.0.0.1", "--port", "8777"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(f"{BASE_URL}/api/health")
        _json_request("PUT", "/api/cam/profile", {"name": "Matches UI Academy"})
        p1 = _json_request("POST", "/api/cam/players", {"name": "UI Match Aarav", "status": "active"})
        p2 = _json_request("POST", "/api/cam/players", {"name": "UI Match Maya", "status": "active"})
        p3 = _json_request("POST", "/api/cam/players", {"name": "UI Match Rohan", "status": "active"})

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1100})
            try:
                page.goto(f"{BASE_URL}/#cam?tab=teams", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Teams & Matches")).to_be_visible(timeout=15000)
                expect(page.locator("#openTeamForm")).to_be_visible()

                # AM-MAT-001: create team and build a real player roster.
                page.get_by_role("button", name="Add Team").click()
                form = page.locator("#camTeamForm")
                expect(form).to_be_visible()
                form.locator('[name="name"]').fill("UI U15 Match XI")
                form.locator('[name="code"]').fill("UI-U15")
                form.locator('[name="age_group"]').fill("U15")
                form.locator('[name="notes"]').fill("UI competition team")
                page.get_by_role("button", name="Create Team").click()
                team_row = page.locator(".cam-match-team-row", has_text="UI U15 Match XI")
                expect(team_row).to_be_visible(timeout=10000)
                expect(team_row).to_contain_text("0 players")

                for player in (p1, p2, p3):
                    page.get_by_role("button", name="Roster Player").click()
                    roster_form = page.locator("#camTeamRosterForm")
                    expect(roster_form).to_be_visible()
                    roster_form.locator('[name="team_id"]').select_option(label="UI U15 Match XI")
                    roster_form.locator('[name="player_id"]').select_option(label=player["name"])
                    roster_form.locator('[name="role"]').fill("player")
                    page.get_by_role("button", name="Add to Roster").click()
                    expect(page.locator("#camTeamRosterForm")).to_have_count(0, timeout=10000)

                team_row = page.locator(".cam-match-team-row", has_text="UI U15 Match XI")
                expect(team_row).to_contain_text("3 players", timeout=10000)
                expect(team_row).to_contain_text("UI Match Aarav")
                expect(team_row).to_contain_text("UI Match Maya")
                expect(team_row).to_contain_text("UI Match Rohan")

                # AM-MAT-002: create fixture.
                page.get_by_role("button", name="Fixture").click()
                fixture_form = page.locator("#camFixtureForm")
                expect(fixture_form).to_be_visible()
                fixture_form.locator('[name="team_id"]').select_option(label="UI U15 Match XI")
                fixture_form.locator('[name="opponent"]').fill("UI North Atlanta Juniors")
                fixture_form.locator('[name="match_date"]').fill("2026-09-20")
                fixture_form.locator('[name="start_time"]').fill("10:00")
                fixture_form.locator('[name="venue"]').fill("UI Ground 1")
                fixture_form.locator('[name="competition"]').fill("UI Fall League")
                fixture_form.locator('[name="match_format"]').fill("T20")
                page.get_by_role("button", name="Create Fixture").click()
                match_row = page.locator(".cam-match-row", has_text="UI North Atlanta Juniors")
                expect(match_row).to_be_visible(timeout=10000)
                expect(match_row).to_contain_text("UI Fall League")
                expect(match_row).to_contain_text("scheduled")

                # AM-MAT-003: select match squad from team roster.
                match_row.get_by_role("button", name="Squad").click()
                squad_form = page.locator("#camSquadForm")
                expect(squad_form).to_be_visible()
                for player in (p1, p2, p3):
                    squad_form.locator(f'input[name="squad_player"][value="{player["id"]}"]').check()
                squad_form.locator('[name="captain_id"]').select_option(str(p1["id"]))
                squad_form.locator('[name="wicketkeeper_id"]').select_option(str(p2["id"]))
                page.get_by_role("button", name="Save Squad").click()
                match_row = page.locator(".cam-match-row", has_text="UI North Atlanta Juniors")
                expect(match_row).to_contain_text("3 squad", timeout=10000)

                # AM-MAT-004: record result and player-level match statistics.
                match_row.get_by_role("button", name="Result").click()
                result_form = page.locator("#camMatchResultForm")
                expect(result_form).to_be_visible()
                result_form.locator('[name="outcome"]').select_option("win")
                result_form.locator('[name="our_score"]').fill("146/5")
                result_form.locator('[name="opponent_score"]').fill("131/8")
                result_form.locator('[name="result_summary"]').fill("Won by 15 runs")

                aarav = result_form.locator(f'[data-player-stat="{p1["id"]}"]')
                aarav.locator('[name="runs"]').fill("62")
                aarav.locator('[name="balls_faced"]').fill("41")
                aarav.locator('[name="fours"]').fill("7")
                aarav.locator('[name="sixes"]').fill("2")
                aarav.locator('[name="catches"]').fill("1")

                maya = result_form.locator(f'[data-player-stat="{p2["id"]}"]')
                maya.locator('[name="runs"]').fill("28")
                maya.locator('[name="balls_faced"]').fill("24")
                maya.locator('[name="balls_bowled"]').fill("24")
                maya.locator('[name="runs_conceded"]').fill("22")
                maya.locator('[name="wickets"]').fill("2")
                maya.locator('[name="stumpings"]').fill("1")

                rohan = result_form.locator(f'[data-player-stat="{p3["id"]}"]')
                rohan.locator('[name="runs"]').fill("11")
                rohan.locator('[name="balls_bowled"]').fill("24")
                rohan.locator('[name="runs_conceded"]').fill("19")
                rohan.locator('[name="wickets"]').fill("3")

                page.get_by_role("button", name="Save Result & Stats").click()
                match_row = page.locator(".cam-match-row", has_text="UI North Atlanta Juniors")
                expect(match_row).to_contain_text("completed", timeout=10000)
                expect(match_row).to_contain_text("win")
                expect(match_row).to_contain_text("Won by 15 runs")
                expect(match_row).to_contain_text("146/5")
                expect(match_row).to_contain_text("131/8")

                # Verify persisted statistics via API from the same Chromium context.
                match_id = page.evaluate("""
                    async () => {
                      const matches = await (await fetch('/api/cam/matches')).json();
                      return matches.find(m => m.opponent === 'UI North Atlanta Juniors')?.id;
                    }
                """)
                assert match_id
                persisted = page.evaluate("""
                    async (id) => await (await fetch(`/api/cam/matches/${id}/stats`)).json()
                """, match_id)
                stats = {row["player_name"]: row for row in persisted}
                assert int(stats["UI Match Aarav"]["runs"]) == 62
                assert int(stats["UI Match Maya"]["wickets"]) == 2
                assert int(stats["UI Match Rohan"]["wickets"]) == 3

            except Exception:
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/cam-matches-ui-failure.png", full_page=True)
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
