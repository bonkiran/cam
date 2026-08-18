import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-tournaments-api-test-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _post(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_tournament_team_registration_and_history():
    profile = client.put("/api/academy/profile", json={"name": "Tournament Test Academy"})
    assert profile.status_code == 200, profile.text

    team = _post("/api/academy/teams", {"name": "Tournament U15 XI", "age_group": "U15", "status": "active"})

    invalid_dates = client.post(
        "/api/academy/tournaments",
        json={"name": "Invalid Tournament", "start_date": "2026-10-10", "end_date": "2026-10-09", "status": "planned"},
    )
    assert invalid_dates.status_code == 422

    tournament = _post(
        "/api/academy/tournaments",
        {
            "name": "Southeast Junior Cup",
            "organizer": "Regional Cricket Association",
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "location": "Atlanta Cricket Complex",
            "status": "open",
            "notes": "Three-day junior tournament",
        },
    )
    tournament_id = int(tournament["id"])
    assert tournament["name"] == "Southeast Junior Cup"
    assert int(tournament["registered_team_count"]) == 0

    duplicate_tournament = client.post(
        "/api/academy/tournaments",
        json={"name": "Southeast Junior Cup", "start_date": "2026-10-10", "end_date": "2026-10-12", "status": "planned"},
    )
    assert duplicate_tournament.status_code == 409

    entry = _post(
        f"/api/academy/tournaments/{tournament_id}/entries",
        {"team_id": team["id"], "registered_on": "2026-08-18", "notes": "Academy first team"},
    )
    assert entry["team_name"] == "Tournament U15 XI"
    assert entry["status"] == "registered"

    tournament_after = client.get(f"/api/academy/tournaments/{tournament_id}")
    assert tournament_after.status_code == 200
    assert int(tournament_after.json()["registered_team_count"]) == 1

    duplicate_entry = client.post(
        f"/api/academy/tournaments/{tournament_id}/entries",
        json={"team_id": team["id"], "registered_on": "2026-08-18"},
    )
    assert duplicate_entry.status_code == 409

    entries = client.get(f"/api/academy/tournaments/{tournament_id}/entries")
    assert entries.status_code == 200
    assert len(entries.json()) == 1
    assert entries.json()[0]["team_name"] == "Tournament U15 XI"

    withdrawn = client.put(
        f"/api/academy/tournament-entries/{entry['id']}",
        json={"status": "withdrawn", "notes": "Schedule conflict"},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "withdrawn"
    assert withdrawn.json()["notes"] == "Schedule conflict"

    history = client.get(f"/api/academy/tournaments/{tournament_id}/entries").json()
    assert len(history) == 1
    assert history[0]["status"] == "withdrawn"
    tournament_final = client.get(f"/api/academy/tournaments/{tournament_id}").json()
    assert int(tournament_final["registered_team_count"]) == 0

    completed = client.put(
        f"/api/academy/tournaments/{tournament_id}",
        json={
            "name": "Southeast Junior Cup",
            "organizer": "Regional Cricket Association",
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "location": "Atlanta Cricket Complex",
            "status": "completed",
        },
    )
    assert completed.status_code == 200

    blocked_registration = client.post(
        f"/api/academy/tournaments/{tournament_id}/entries",
        json={"team_id": team["id"], "registered_on": "2026-08-19"},
    )
    assert blocked_registration.status_code == 409
