import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-batches-api-test-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _post(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_batches_sessions_capacity_schedule_conflicts_and_workload():
    academy = client.put("/api/cam/profile", json={"name": "Batches Test Academy", "timezone": "America/New_York"})
    assert academy.status_code == 200, academy.text

    program = _post("/api/cam/programs", {"name": "U15 Batch Program", "program_type": "group", "status": "active"})
    coach1 = _post("/api/cam/coaches", {"first_name": "Batch", "last_name": "Coach", "specialties": ["Batting"], "status": "active"})
    coach2 = _post("/api/cam/coaches", {"first_name": "Private", "last_name": "Coach", "specialties": ["Bowling"], "status": "active"})
    p1 = _post("/api/cam/players", {"name": "Batch Player One", "status": "active"})
    p2 = _post("/api/cam/players", {"name": "Batch Player Two", "status": "active"})
    p3 = _post("/api/cam/players", {"name": "Batch Player Three", "status": "active"})

    batch = _post(
        "/api/cam/batches",
        {
            "name": "U15 Mon Wed",
            "code": "U15-MW",
            "program_id": program["id"],
            "capacity": 2,
            "location": "Main Indoor Center",
            "resource": "Net 3",
            "start_date": "2026-09-01",
            "end_date": "2026-12-15",
            "status": "active",
        },
    )
    batch_id = int(batch["id"])
    assert batch["program_name"] == "U15 Batch Program"
    assert int(batch["capacity"]) == 2

    assigned_coach = _post(
        f"/api/cam/batch-coach-assignments?batch_id={batch_id}",
        {"coach_id": coach1["id"], "assignment_role": "primary", "start_date": "2026-09-01"},
    )
    assert assigned_coach["coach_name"] == "Batch Coach"
    batch = client.get(f"/api/cam/batches/{batch_id}").json()
    assert int(batch["primary_coach_id"]) == int(coach1["id"])

    m1 = _post(f"/api/cam/batches/{batch_id}/players", {"player_id": p1["id"], "joined_on": "2026-09-01"})
    m2 = _post(f"/api/cam/batches/{batch_id}/players", {"player_id": p2["id"], "joined_on": "2026-09-01"})
    assert m1["status"] == "active" and m2["status"] == "active"

    over_capacity = client.post(f"/api/cam/batches/{batch_id}/players", json={"player_id": p3["id"]})
    assert over_capacity.status_code == 409
    assert "capacity" in over_capacity.json()["detail"].lower()

    waitlisted = _post(
        f"/api/cam/batches/{batch_id}/players",
        {"player_id": p3["id"], "waitlist_if_full": True, "joined_on": "2026-09-01"},
    )
    assert waitlisted["status"] == "waitlisted"
    batch = client.get(f"/api/cam/batches/{batch_id}").json()
    assert int(batch["active_player_count"]) == 2
    assert int(batch["waitlist_count"]) == 1

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
    assert generated["timezone"] == "America/New_York"

    sessions = client.get(f"/api/cam/sessions?batch_id={batch_id}")
    assert sessions.status_code == 200
    rows = sessions.json()
    assert len(rows) == 4
    assert all(row["timezone"] == "America/New_York" for row in rows)
    assert all(row["location"] == "Main Indoor Center" for row in rows)
    assert all(row["resource"] == "Net 3" for row in rows)
    assert all(int(row["player_count"]) == 2 for row in rows)

    first_id = int(rows[0]["id"])
    second_id = int(rows[1]["id"])
    first_date = rows[0]["session_date"]

    updated = client.put(
        f"/api/cam/sessions/{first_id}",
        json={
            "session_date": first_date,
            "start_time": "20:15",
            "duration_minutes": 60,
            "coach_id": coach1["id"],
            "location": "Main Indoor Center",
            "resource": "Net 4",
            "notes": "Single occurrence moved",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["start_time"] == "20:15"
    assert updated.json()["resource"] == "Net 4"

    cancelled = client.post(f"/api/cam/sessions/{second_id}/cancel", json={"reason": "Facility closure"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancellation_reason"] == "Facility closure"

    makeup = _post(
        f"/api/cam/sessions/{second_id}/makeup",
        {"session_date": "2026-09-10", "start_time": "18:00", "notes": "Replacement for closure"},
    )
    assert makeup["session_kind"] == "makeup"
    assert int(makeup["original_session_id"]) == second_id
    makeup_players = client.get(f"/api/cam/sessions/{makeup['id']}/players").json()
    assert len(makeup_players) == 2

    private_session = _post(
        "/api/cam/sessions/private",
        {
            "player_id": p1["id"],
            "coach_id": coach2["id"],
            "session_date": "2026-09-08",
            "start_time": "18:00",
            "duration_minutes": 60,
            "location": "Main Indoor Center",
            "resource": "Lane 1",
            "notes": "Private lesson",
        },
    )
    assert private_session["session_kind"] == "private"
    assert private_session["batch_id"] is None
    assert private_session["timezone"] == "America/New_York"

    private_conflict = client.post(
        "/api/cam/sessions/private",
        json={
            "player_id": p2["id"],
            "coach_id": coach2["id"],
            "session_date": "2026-09-08",
            "start_time": "18:30",
            "duration_minutes": 60,
        },
    )
    assert private_conflict.status_code == 409
    assert "conflicting" in private_conflict.json()["detail"].lower()

    batch_conflict = client.post(
        "/api/cam/sessions/private",
        json={
            "player_id": p3["id"],
            "coach_id": coach1["id"],
            "session_date": "2026-09-14",
            "start_time": "19:30",
            "duration_minutes": 30,
        },
    )
    assert batch_conflict.status_code == 409

    workload = client.get(f"/api/cam/coaches/{coach1['id']}/workload")
    assert workload.status_code == 200, workload.text
    workload_data = workload.json()
    assert workload_data["coach_name"] == "Batch Coach"
    assert workload_data["session_count"] == 4  # 3 non-cancelled originals + 1 makeup
    assert workload_data["total_minutes"] == 240
