import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-matches-api-test-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _post(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_teams_fixtures_squad_result_and_player_statistics():
    academy = client.put("/api/cam/profile", json={"name": "Matches Test Academy", "timezone": "America/New_York"})
    assert academy.status_code == 200, academy.text

    p1 = _post("/api/cam/players", {"name": "Match Player One", "status": "active"})
    p2 = _post("/api/cam/players", {"name": "Match Player Two", "status": "active"})
    p3 = _post("/api/cam/players", {"name": "Match Player Three", "status": "active"})
    outsider = _post("/api/cam/players", {"name": "Match Outsider", "status": "active"})

    team = _post(
        "/api/cam/teams",
        {"name": "U15 Match XI", "code": "U15-XI", "age_group": "U15", "status": "active", "notes": "Weekend team"},
    )
    team_id = int(team["id"])
    assert team["name"] == "U15 Match XI"
    assert int(team["roster_count"]) == 0

    for index, player in enumerate((p1, p2, p3), start=1):
        roster = _post(
            f"/api/cam/teams/{team_id}/roster",
            {"player_id": player["id"], "role": "player", "jersey_number": str(index), "joined_on": "2026-09-01"},
        )
        assert int(roster["player_id"]) == int(player["id"])
        assert roster["status"] == "active"

    duplicate = client.post(
        f"/api/cam/teams/{team_id}/roster",
        json={"player_id": p1["id"]},
    )
    assert duplicate.status_code == 409

    team_after = client.get(f"/api/cam/teams/{team_id}")
    assert team_after.status_code == 200
    assert int(team_after.json()["roster_count"]) == 3

    fixture = _post(
        "/api/cam/matches",
        {
            "team_id": team_id,
            "opponent": "North Atlanta Juniors",
            "match_date": "2026-09-20",
            "start_time": "10:00",
            "venue": "Academy Ground 1",
            "competition": "Fall League",
            "match_format": "T20",
            "notes": "League fixture",
        },
    )
    match_id = int(fixture["id"])
    assert fixture["team_name"] == "U15 Match XI"
    assert fixture["opponent"] == "North Atlanta Juniors"
    assert fixture["status"] == "scheduled"

    outsider_squad = client.put(
        f"/api/cam/matches/{match_id}/squad",
        json={"player_ids": [p1["id"], outsider["id"]]},
    )
    assert outsider_squad.status_code == 409
    assert "roster" in outsider_squad.json()["detail"].lower()

    squad = client.put(
        f"/api/cam/matches/{match_id}/squad",
        json={
            "player_ids": [p1["id"], p2["id"], p3["id"]],
            "captain_id": p1["id"],
            "wicketkeeper_id": p2["id"],
        },
    )
    assert squad.status_code == 200, squad.text
    squad_rows = squad.json()
    assert len(squad_rows) == 3
    assert sum(int(row["is_captain"]) for row in squad_rows) == 1
    assert sum(int(row["is_wicketkeeper"]) for row in squad_rows) == 1

    result = client.put(
        f"/api/cam/matches/{match_id}/result",
        json={
            "outcome": "win",
            "our_score": "146/5",
            "opponent_score": "131/8",
            "result_summary": "Won by 15 runs",
            "player_stats": [
                {
                    "player_id": p1["id"],
                    "runs": 62,
                    "balls_faced": 41,
                    "fours": 7,
                    "sixes": 2,
                    "balls_bowled": 0,
                    "runs_conceded": 0,
                    "wickets": 0,
                    "catches": 1,
                },
                {
                    "player_id": p2["id"],
                    "runs": 28,
                    "balls_faced": 24,
                    "fours": 3,
                    "sixes": 0,
                    "balls_bowled": 24,
                    "runs_conceded": 22,
                    "wickets": 2,
                    "stumpings": 1,
                },
                {
                    "player_id": p3["id"],
                    "runs": 11,
                    "balls_faced": 8,
                    "fours": 1,
                    "sixes": 0,
                    "balls_bowled": 24,
                    "runs_conceded": 19,
                    "wickets": 3,
                    "catches": 1,
                },
            ],
        },
    )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["match"]["status"] == "completed"
    assert payload["match"]["outcome"] == "win"
    assert payload["match"]["result_summary"] == "Won by 15 runs"
    assert len(payload["stats"]) == 3

    stats = {row["player_name"]: row for row in payload["stats"]}
    assert int(stats["Match Player One"]["runs"]) == 62
    assert int(stats["Match Player Two"]["wickets"]) == 2
    assert int(stats["Match Player Three"]["wickets"]) == 3

    completed = client.get(f"/api/cam/matches/{match_id}")
    assert completed.status_code == 200
    completed_json = completed.json()
    assert int(completed_json["squad_count"]) == 3
    assert int(completed_json["stat_count"]) == 3
