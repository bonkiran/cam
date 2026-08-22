import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam14-player-development-api-test-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _post(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _put(path, payload):
    response = client.put(path, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _setup_session():
    _put("/api/academy/profile", {"name": "CAM-14 Test Academy", "timezone": "America/New_York"})
    program = _post("/api/academy/programs", {"name": "U13 Development", "program_type": "group", "status": "active"})
    coach = _post("/api/academy/coaches", {"first_name": "Moat", "last_name": "Coach", "status": "active"})
    players = [
        _post("/api/academy/players", {"name": f"CAM14 Player {index}", "status": "active"})
        for index in (1, 2, 3)
    ]
    batch = _post(
        "/api/academy/batches",
        {"name": "U13 CAM-14", "program_id": program["id"], "capacity": 16, "status": "active"},
    )
    _post(
        f"/api/academy/batch-coach-assignments?batch_id={batch['id']}",
        {"coach_id": coach["id"], "assignment_role": "primary", "start_date": "2026-08-01"},
    )
    for player in players:
        _post(
            f"/api/academy/batches/{batch['id']}/players",
            {"player_id": player["id"], "joined_on": "2026-08-01"},
        )
    generated = _post(
        f"/api/academy/batches/{batch['id']}/generate-sessions",
        {
            "start_date": "2026-08-24",
            "end_date": "2026-08-24",
            "weekdays": [0],
            "start_time": "18:00",
            "duration_minutes": 60,
        },
    )
    assert generated["created_count"] == 1
    return int(generated["session_ids"][0]), players


def test_cam14_passive_practice_evidence_tracks_focus_and_attendance_without_claiming_improvement():
    session_id, players = _setup_session()
    p1, p2, p3 = players

    skills = client.get("/api/academy/development/skills")
    assert skills.status_code == 200, skills.text
    skill_keys = {row["skill_key"] for row in skills.json()}
    assert {"front_foot_movement", "cover_drive", "running_between_wickets"}.issubset(skill_keys)

    focus = _put(
        f"/api/academy/sessions/{session_id}/development-focus",
        {"skill_keys": ["front_foot_movement", "cover_drive", "running_between_wickets"]},
    )
    assert focus["evidence_label"] == "Practiced / Exposed"
    assert focus["claim_level"] == "training_exposure_only"
    assert focus["generated_evidence_count"] == 0

    attendance = _put(
        f"/api/academy/sessions/{session_id}/attendance",
        {
            "players": [
                {"player_id": p1["id"], "status": "present"},
                {"player_id": p2["id"], "status": "late"},
                {"player_id": p3["id"], "status": "absent", "absence_reason": "School"},
            ],
            "coach_status": "present",
        },
    )
    assert attendance["development"]["generated_evidence_count"] == 6

    for attended_player in (p1, p2):
        history_response = client.get(f"/api/academy/players/{attended_player['id']}/development-history")
        assert history_response.status_code == 200, history_response.text
        history = history_response.json()["evidence"]
        assert len(history) == 3
        assert {row["skill_key"] for row in history} == {
            "front_foot_movement",
            "cover_drive",
            "running_between_wickets",
        }
        assert all(row["evidence_type"] == "practiced" for row in history)
        assert all(row["evidence_label"] == "Practiced / Exposed" for row in history)
        assert all(row["claim_level"] == "training_exposure_only" for row in history)
        assert all(row["improvement_claimed"] is False for row in history)
        assert all(int(row["exposure_minutes"]) == 60 for row in history)

    absent_history = client.get(f"/api/academy/players/{p3['id']}/development-history")
    assert absent_history.status_code == 200
    assert absent_history.json()["evidence"] == []

    # Attendance correction removes passive evidence immediately. Excused is not
    # treated as development exposure because the player did not attend.
    corrected = _put(
        f"/api/academy/sessions/{session_id}/attendance",
        {
            "players": [
                {"player_id": p1["id"], "status": "present"},
                {"player_id": p2["id"], "status": "excused", "absence_reason": "Family commitment"},
                {"player_id": p3["id"], "status": "absent", "absence_reason": "School"},
            ],
            "coach_status": "present",
        },
    )
    assert corrected["development"]["generated_evidence_count"] == 3
    assert client.get(f"/api/academy/players/{p2['id']}/development-history").json()["evidence"] == []

    # Editing session focus reconciles the historical evidence instead of
    # leaving stale skill rows behind.
    narrowed = _put(
        f"/api/academy/sessions/{session_id}/development-focus",
        {"skill_keys": ["cover_drive"]},
    )
    assert narrowed["generated_evidence_count"] == 1
    p1_history = client.get(f"/api/academy/players/{p1['id']}/development-history").json()["evidence"]
    assert len(p1_history) == 1
    assert p1_history[0]["skill_key"] == "cover_drive"

    summary = client.get(f"/api/academy/players/{p1['id']}/development-summary")
    assert summary.status_code == 200, summary.text
    summary_data = summary.json()
    assert summary_data["improvement_claimed"] is False
    assert summary_data["claim_level"] == "training_exposure_only"
    assert len(summary_data["skills"]) == 1
    assert summary_data["skills"][0]["skill_key"] == "cover_drive"
    assert int(summary_data["skills"][0]["practiced_sessions"]) == 1
    assert int(summary_data["skills"][0]["exposure_minutes"]) == 60

    # Re-saving the same attendance is idempotent: no duplicate evidence.
    _put(
        f"/api/academy/sessions/{session_id}/attendance",
        {
            "players": [
                {"player_id": p1["id"], "status": "present"},
                {"player_id": p2["id"], "status": "excused", "absence_reason": "Family commitment"},
                {"player_id": p3["id"], "status": "absent", "absence_reason": "School"},
            ],
            "coach_status": "present",
        },
    )
    assert len(client.get(f"/api/academy/players/{p1['id']}/development-history").json()["evidence"]) == 1

    cleared = _put(f"/api/academy/sessions/{session_id}/development-focus", {"skill_keys": []})
    assert cleared["generated_evidence_count"] == 0
    assert client.get(f"/api/academy/players/{p1['id']}/development-history").json()["evidence"] == []


def test_cam14_rejects_unknown_development_skill():
    session_id, _players = _setup_session()
    response = client.put(
        f"/api/academy/sessions/{session_id}/development-focus",
        json={"skill_keys": ["made_up_skill"]},
    )
    assert response.status_code == 422
    assert "Unknown development skill" in response.text
