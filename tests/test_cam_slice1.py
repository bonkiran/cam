import os
import sys
import tempfile
from pathlib import Path

# Make the repository root importable when pytest is launched from GitHub Actions.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Must be set before app.database is imported by run.py.
os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-test-")

from fastapi.testclient import TestClient

from run import app

client = TestClient(app)


def test_academy_player_guardian_end_to_end():
    academy_payload = {
        "name": "Test Cricket Academy",
        "email": "admin@example.com",
        "phone": "555-0100",
        "city": "Alpharetta",
        "state": "GA",
        "postal_code": "30005",
        "country": "United States",
        "timezone": "America/New_York",
    }
    academy_response = client.put("/api/cam/profile", json=academy_payload)
    assert academy_response.status_code == 200
    assert academy_response.json()["profile"]["name"] == "Test Cricket Academy"

    profile_response = client.get("/api/cam/profile")
    assert profile_response.status_code == 200
    assert profile_response.json()["configured"] is True

    player_payload = {
        "name": "Test Player",
        "first_name": "Test",
        "last_name": "Player",
        "date_of_birth": "2012-08-17",
        "batting_style": "Right-handed",
        "handedness": "Right",
        "skill_level": "Intermediate",
        "status": "active",
        "guardians": [
            {
                "first_name": "Parent",
                "last_name": "Player",
                "relationship": "Mother",
                "email": "parent@example.com",
                "phone": "555-0200",
                "is_primary": True,
                "billing_contact": True,
                "pickup_authorized": True,
            }
        ],
    }
    create_response = client.post("/api/cam/players", json=player_payload)
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    player_id = created["id"]
    assert created["name"] == "Test Player"
    assert len(created["guardians"]) == 1
    assert created["guardians"][0]["billing_contact"] == 1

    detail_response = client.get(f"/api/cam/players/{player_id}")
    assert detail_response.status_code == 200
    player = detail_response.json()
    guardian = player["guardians"][0]

    player_payload["preferred_name"] = "TP"
    player_payload["skill_level"] = "Advanced"
    player_payload["guardians"][0]["id"] = guardian["id"]
    player_payload["guardians"][0]["phone"] = "555-0300"

    update_response = client.put(f"/api/cam/players/{player_id}", json=player_payload)
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["preferred_name"] == "TP"
    assert updated["skill_level"] == "Advanced"
    assert updated["guardians"][0]["phone"] == "555-0300"

    directory_response = client.get("/api/cam/players")
    assert directory_response.status_code == 200
    assert any(row["id"] == player_id for row in directory_response.json())

    legacy_players_response = client.get("/api/players")
    assert legacy_players_response.status_code == 200
    assert any(row["id"] == player_id and row["name"] == "Test Player" for row in legacy_players_response.json())
