import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-programs-api-test-")

from fastapi.testclient import TestClient

from run import app

client = TestClient(app)


def _create_academy():
    response = client.put(
        "/api/academy/profile",
        json={"name": "Programs Test Academy", "timezone": "America/New_York"},
    )
    assert response.status_code == 200, response.text


def _create_player(name: str, status: str = "active") -> int:
    response = client.post("/api/academy/players", json={"name": name, "status": status})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_programs_and_enrollment_lifecycle_end_to_end():
    _create_academy()
    player_id = _create_player("Enrollment Player")
    trial_player_id = _create_player("Trial Player")
    inactive_player_id = _create_player("Inactive Player", status="inactive")

    create_program = client.post(
        "/api/academy/programs",
        json={
            "name": "U15 Advanced Batting",
            "code": "U15-AB",
            "description": "Advanced batting development program",
            "program_type": "group",
            "age_group": "U15",
            "skill_level": "Advanced",
            "start_date": "2026-09-01",
            "end_date": "2026-12-15",
            "status": "active",
        },
    )
    assert create_program.status_code == 201, create_program.text
    program = create_program.json()
    program_id = int(program["id"])
    assert program["name"] == "U15 Advanced Batting"
    assert int(program["current_enrollment_count"]) == 0

    duplicate_program = client.post(
        "/api/academy/programs",
        json={"name": "u15 advanced batting", "status": "active"},
    )
    assert duplicate_program.status_code == 409

    edit_program = client.put(
        f"/api/academy/programs/{program_id}",
        json={
            "name": "U15 Advanced Batting & Technique",
            "code": "U15-AB",
            "description": "Updated technique-focused program",
            "program_type": "group",
            "age_group": "U15",
            "skill_level": "Advanced",
            "start_date": "2026-09-01",
            "end_date": "2026-12-20",
            "status": "active",
        },
    )
    assert edit_program.status_code == 200, edit_program.text
    assert edit_program.json()["name"] == "U15 Advanced Batting & Technique"
    assert edit_program.json()["end_date"] == "2026-12-20"

    regular = client.post(
        "/api/academy/enrollments",
        json={
            "player_id": player_id,
            "program_id": program_id,
            "enrollment_type": "regular",
            "start_date": "2026-09-01",
            "notes": "First regular enrollment",
        },
    )
    assert regular.status_code == 201, regular.text
    regular_id = int(regular.json()["id"])
    assert regular.json()["status"] == "active"
    assert regular.json()["player_name"] == "Enrollment Player"

    duplicate_active = client.post(
        "/api/academy/enrollments",
        json={"player_id": player_id, "program_id": program_id, "enrollment_type": "regular"},
    )
    assert duplicate_active.status_code == 409

    inactive_attempt = client.post(
        "/api/academy/enrollments",
        json={"player_id": inactive_player_id, "program_id": program_id},
    )
    assert inactive_attempt.status_code == 409

    freeze = client.post(
        f"/api/academy/enrollments/{regular_id}/freeze",
        json={"effective_date": "2026-10-10"},
    )
    assert freeze.status_code == 200, freeze.text
    assert freeze.json()["status"] == "frozen"
    assert freeze.json()["frozen_on"] == "2026-10-10"

    duplicate_frozen = client.post(
        "/api/academy/enrollments",
        json={"player_id": player_id, "program_id": program_id},
    )
    assert duplicate_frozen.status_code == 409

    trial = client.post(
        "/api/academy/enrollments",
        json={
            "player_id": trial_player_id,
            "program_id": program_id,
            "enrollment_type": "trial",
            "start_date": "2026-09-05",
            "end_date": "2026-09-05",
        },
    )
    assert trial.status_code == 201, trial.text
    trial_id = int(trial.json()["id"])
    assert trial.json()["enrollment_type"] == "trial"
    assert trial.json()["status"] == "active"

    cancel = client.post(
        f"/api/academy/enrollments/{regular_id}/cancel",
        json={"effective_date": "2026-10-15", "reason": "Schedule conflict"},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"
    assert cancel.json()["cancellation_reason"] == "Schedule conflict"

    reenroll = client.post(
        "/api/academy/enrollments",
        json={
            "player_id": player_id,
            "program_id": program_id,
            "enrollment_type": "regular",
            "start_date": "2026-11-01",
        },
    )
    assert reenroll.status_code == 201, reenroll.text
    assert reenroll.json()["status"] == "active"

    history = client.get(f"/api/academy/enrollments?player_id={player_id}")
    assert history.status_code == 200
    history_rows = history.json()
    assert len(history_rows) == 2
    assert {row["status"] for row in history_rows} == {"cancelled", "active"}

    program_detail = client.get(f"/api/academy/programs/{program_id}")
    assert program_detail.status_code == 200
    assert int(program_detail.json()["current_enrollment_count"]) == 2  # regular re-enrollment + trial
    assert int(program_detail.json()["lifetime_enrollment_count"]) == 3

    trial_cancel = client.post(
        f"/api/academy/enrollments/{trial_id}/cancel",
        json={"effective_date": "2026-09-05", "reason": "Trial complete"},
    )
    assert trial_cancel.status_code == 200
