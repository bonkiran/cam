import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-coaches-api-test-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def test_coach_profile_assignment_and_lifecycle():
    academy = client.put("/api/academy/profile", json={"name": "Coaches Test Academy"})
    assert academy.status_code == 200, academy.text

    player = client.post("/api/academy/players", json={"name": "Coach Assigned Player", "status": "active"})
    assert player.status_code == 201, player.text
    player_id = int(player.json()["id"])

    other_player = client.post("/api/academy/players", json={"name": "Coach Future Player", "status": "active"})
    assert other_player.status_code == 201, other_player.text
    other_player_id = int(other_player.json()["id"])

    created = client.post(
        "/api/academy/coaches",
        json={
            "first_name": "Anil",
            "last_name": "Sharma",
            "preferred_name": "Coach Anil",
            "email": "anil.coach@example.com",
            "phone": "555-0700",
            "specialties": ["Batting", "Spin Bowling"],
            "availability": "Mon/Wed 5-9 PM; Sat mornings",
            "certifications": "USA Cricket Level 1; CPR",
            "joined_on": "2026-08-01",
            "status": "active",
            "notes": "Senior development coach",
        },
    )
    assert created.status_code == 201, created.text
    coach = created.json()
    coach_id = int(coach["id"])
    assert coach["first_name"] == "Anil"
    assert coach["last_name"] == "Sharma"
    assert coach["specialties"] == ["Batting", "Spin Bowling"]
    assert coach["availability"] == "Mon/Wed 5-9 PM; Sat mornings"
    assert int(coach["assigned_player_count"]) == 0

    updated = client.put(
        f"/api/academy/coaches/{coach_id}",
        json={
            "first_name": "Anil",
            "last_name": "Sharma",
            "preferred_name": "Anil",
            "email": "anil.coach@example.com",
            "phone": "555-0800",
            "specialties": ["Batting", "Wicketkeeping"],
            "availability": "Tue/Thu 6-9 PM; Sat mornings",
            "certifications": "USA Cricket Level 1; CPR",
            "joined_on": "2026-08-01",
            "status": "active",
            "notes": "Updated availability",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["phone"] == "555-0800"
    assert updated.json()["specialties"] == ["Batting", "Wicketkeeping"]
    assert updated.json()["availability"] == "Tue/Thu 6-9 PM; Sat mornings"

    assigned = client.post(
        "/api/academy/coach-player-assignments",
        json={
            "coach_id": coach_id,
            "player_id": player_id,
            "assignment_role": "primary",
            "start_date": "2026-09-01",
            "notes": "Technique ownership",
        },
    )
    assert assigned.status_code == 201, assigned.text
    assignment = assigned.json()
    assignment_id = int(assignment["id"])
    assert assignment["coach_name"] == "Anil Sharma"
    assert assignment["player_name"] == "Coach Assigned Player"
    assert assignment["status"] == "active"

    duplicate = client.post(
        "/api/academy/coach-player-assignments",
        json={"coach_id": coach_id, "player_id": player_id, "assignment_role": "support"},
    )
    assert duplicate.status_code == 409

    detail = client.get(f"/api/academy/coaches/{coach_id}")
    assert detail.status_code == 200
    assert int(detail.json()["assigned_player_count"]) == 1

    # Deactivate the coach without deleting historical/current assignment records.
    deactivated = client.put(
        f"/api/academy/coaches/{coach_id}",
        json={
            "first_name": "Anil",
            "last_name": "Sharma",
            "preferred_name": "Anil",
            "email": "anil.coach@example.com",
            "phone": "555-0800",
            "specialties": ["Batting", "Wicketkeeping"],
            "availability": "Tue/Thu 6-9 PM; Sat mornings",
            "certifications": "USA Cricket Level 1; CPR",
            "joined_on": "2026-08-01",
            "status": "inactive",
            "notes": "Inactive but history retained",
        },
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["status"] == "inactive"

    history = client.get(f"/api/academy/coach-player-assignments?coach_id={coach_id}")
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["id"] == assignment_id

    blocked_new = client.post(
        "/api/academy/coach-player-assignments",
        json={"coach_id": coach_id, "player_id": other_player_id, "assignment_role": "primary"},
    )
    assert blocked_new.status_code == 409

    ended = client.post(f"/api/academy/coach-player-assignments/{assignment_id}/end?end_date=2026-10-15", json={})
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "inactive"
    assert ended.json()["end_date"] == "2026-10-15"

    history_after = client.get(f"/api/academy/coach-player-assignments?coach_id={coach_id}")
    assert history_after.status_code == 200
    assert len(history_after.json()) == 1
    assert history_after.json()[0]["status"] == "inactive"
