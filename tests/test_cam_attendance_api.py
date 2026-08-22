import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-attendance-api-test-")

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


def test_attendance_statuses_corrections_metrics_makeup_coach_and_alerts():
    _put("/api/cam/profile", {"name": "Attendance Test Academy", "timezone": "America/New_York"})

    policy = client.get("/api/cam/attendance/policy")
    assert policy.status_code == 200, policy.text
    assert policy.json()["repeated_absence_threshold"] == 3
    assert policy.json()["absence_lookback_days"] == 30

    program = _post("/api/cam/programs", {"name": "Attendance Program", "program_type": "group", "status": "active"})
    coach = _post("/api/cam/coaches", {"first_name": "Attendance", "last_name": "Coach", "status": "active"})
    player1 = _post("/api/cam/players", {"name": "Attendance Player One", "status": "active"})
    player2 = _post("/api/cam/players", {"name": "Attendance Player Two", "status": "active"})
    batch = _post(
        "/api/cam/batches",
        {"name": "Attendance Batch", "program_id": program["id"], "capacity": 5, "status": "active"},
    )
    batch_id = int(batch["id"])
    _post(
        f"/api/cam/batch-coach-assignments?batch_id={batch_id}",
        {"coach_id": coach["id"], "assignment_role": "primary", "start_date": "2026-09-01"},
    )
    _post(f"/api/cam/batches/{batch_id}/players", {"player_id": player1["id"], "joined_on": "2026-09-01"})
    _post(f"/api/cam/batches/{batch_id}/players", {"player_id": player2["id"], "joined_on": "2026-09-01"})

    generated = _post(
        f"/api/cam/batches/{batch_id}/generate-sessions",
        {
            "start_date": "2026-09-07",
            "end_date": "2026-09-16",
            "weekdays": [0, 2],
            "start_time": "19:00",
            "duration_minutes": 60,
        },
    )
    assert generated["created_count"] == 4
    session_ids = [int(x) for x in generated["session_ids"]]

    # Session 1: regular batch attendance plus coach attendance.
    first = _put(
        f"/api/cam/sessions/{session_ids[0]}/attendance",
        {
            "players": [
                {"player_id": player1["id"], "status": "present"},
                {"player_id": player2["id"], "status": "absent", "absence_reason": "Travel"},
            ],
            "coach_status": "present",
            "coach_notes": "On time",
        },
    )
    p2_first = next(row for row in first["players"] if int(row["player_id"]) == int(player2["id"]))
    assert p2_first["attendance_status"] == "absent"
    assert p2_first["absence_reason"] == "Travel"
    assert p2_first["make_up_eligible"] is True
    assert first["coach_attendance"]["status"] == "present"

    # Correct Player 1 after save; correction must be auditable.
    corrected = _put(
        f"/api/cam/sessions/{session_ids[0]}/attendance",
        {
            "players": [
                {"player_id": player1["id"], "status": "late", "notes": "Arrived 10 minutes late"},
                {"player_id": player2["id"], "status": "absent", "absence_reason": "Travel"},
            ],
            "coach_status": "late",
            "coach_notes": "Arrived 5 minutes late",
        },
    )
    p1_corrected = next(row for row in corrected["players"] if int(row["player_id"]) == int(player1["id"]))
    assert p1_corrected["attendance_status"] == "late"
    assert p1_corrected["notes"] == "Arrived 10 minutes late"
    history = client.get(
        f"/api/cam/attendance/history?session_id={session_ids[0]}&entity_type=player&subject_id={player1['id']}"
    )
    assert history.status_code == 200, history.text
    assert len(history.json()) >= 2  # initial mark + correction
    assert history.json()[0]["before"]["status"] == "present"
    assert history.json()[0]["after"]["status"] == "late"

    # Sessions 2-4 exercise the three supported player statuses and repeated absence alerting.
    _put(
        f"/api/cam/sessions/{session_ids[1]}/attendance",
        {
            "players": [
                {"player_id": player1["id"], "status": "present"},
                {"player_id": player2["id"], "status": "absent", "absence_reason": "Sick"},
            ],
            "coach_status": "present",
        },
    )
    _put(
        f"/api/cam/sessions/{session_ids[2]}/attendance",
        {
            "players": [
                {"player_id": player1["id"], "status": "absent", "absence_reason": "School event"},
                {"player_id": player2["id"], "status": "absent", "absence_reason": "Sick"},
            ],
            "coach_status": "present",
        },
    )

    alerts = client.get(f"/api/cam/attendance/alerts?player_id={player2['id']}")
    assert alerts.status_code == 200, alerts.text
    assert len(alerts.json()) == 1
    alert = alerts.json()[0]
    assert alert["alert_type"] == "repeated_absence"
    assert int(alert["occurrence_count"]) == 3
    assert int(alert["threshold"]) == 3
    assert alert["status"] == "open"

    # Saving the same third absence again must update, not duplicate, the open alert.
    _put(
        f"/api/cam/sessions/{session_ids[2]}/attendance",
        {
            "players": [
                {"player_id": player1["id"], "status": "absent", "absence_reason": "School event"},
                {"player_id": player2["id"], "status": "absent", "absence_reason": "Sick"},
            ],
            "coach_status": "present",
        },
    )
    assert len(client.get(f"/api/cam/attendance/alerts?player_id={player2['id']}").json()) == 1

    _put(
        f"/api/cam/sessions/{session_ids[3]}/attendance",
        {
            "players": [
                {"player_id": player1["id"], "status": "absent", "absence_reason": "Family commitment"},
                {"player_id": player2["id"], "status": "present"},
            ],
            "coach_status": "present",
        },
    )

    summary = client.get(f"/api/cam/players/{player1['id']}/attendance-summary")
    assert summary.status_code == 200, summary.text
    summary_data = summary.json()
    assert summary_data["recorded_sessions"] == 4
    assert summary_data["present"] == 1
    assert summary_data["late"] == 1
    assert summary_data["absent"] == 2
    assert "excused" not in summary_data
    assert summary_data["attendance_denominator"] == 4
    assert summary_data["attendance_percentage"] == 50.0
    assert summary_data["make_up_eligible_count"] == 2
    assert summary_data["calculation_rule"] == "present + late count as attended; absent counts against percentage"

    # Correcting Player 2's third absence below the threshold automatically resolves the alert.
    _put(
        f"/api/cam/sessions/{session_ids[2]}/attendance",
        {
            "players": [
                {"player_id": player1["id"], "status": "absent", "absence_reason": "School event"},
                {"player_id": player2["id"], "status": "present"},
            ],
            "coach_status": "present",
        },
    )
    assert client.get(f"/api/cam/attendance/alerts?player_id={player2['id']}").json() == []
    resolved = client.get(f"/api/cam/attendance/alerts?status=resolved&player_id={player2['id']}")
    assert resolved.status_code == 200
    assert len(resolved.json()) == 1
    assert resolved.json()[0]["status"] == "resolved"
