import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-track-a-attendance-qa-")
os.environ["CAM_BOOTSTRAP_TOKEN"] = "track-a-attendance-bootstrap"

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _reset_shared_postgres_state() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "attendance_change_history",
        "attendance_alerts",
        "coach_attendance",
        "player_attendance",
        "attendance_policies",
        "academy_auth_sessions",
        "academy_access_audit",
        "academy_users",
        "session_players",
        "academy_sessions",
        "batch_coach_assignments",
        "batch_players",
        "batches",
        "coach_player_assignments",
        "coaches",
        "enrollments",
        "programs",
        "player_guardians",
        "guardians",
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


def _post(path: str, payload: dict):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _bootstrap_owner() -> str:
    response = client.post(
        "/api/auth/bootstrap",
        json={
            "display_name": "Attendance Track A Owner",
            "email": "attendance.owner@example.test",
            "password": "AttendanceOwner!123",
        },
        headers={"X-CAM-Bootstrap": "track-a-attendance-bootstrap"},
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _create_user(owner_token: str, payload: dict) -> None:
    response = client.post("/api/cam/access/users", json=payload, headers=_auth(owner_token))
    assert response.status_code == 201, response.text


def _login(email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def test_track_a_attendance_statuses_correction_and_role_boundaries():
    _reset_shared_postgres_state()

    profile = client.put(
        "/api/cam/profile",
        json={"name": "Track A Attendance Academy", "timezone": "America/New_York"},
    )
    assert profile.status_code == 200, profile.text

    program = _post(
        "/api/cam/programs",
        {"name": "Track A Attendance U13", "program_type": "group", "status": "active"},
    )
    session_coach = _post(
        "/api/cam/coaches",
        {"first_name": "Assigned", "last_name": "Coach", "status": "active"},
    )
    other_coach = _post(
        "/api/cam/coaches",
        {"first_name": "Unassigned", "last_name": "Coach", "status": "active"},
    )

    players = []
    for index in range(4):
        guardian = {
            "first_name": f"Guardian{index + 1}",
            "last_name": "Attendance",
            "relationship": "Parent",
            "email": f"guardian{index + 1}.attendance@example.test",
            "is_primary": True,
            "billing_contact": True,
            "pickup_authorized": True,
        }
        players.append(
            _post(
                "/api/cam/players",
                {
                    "name": f"Attendance QA Player {index + 1}",
                    "status": "active",
                    "guardians": [guardian],
                },
            )
        )

    batch = _post(
        "/api/cam/batches",
        {
            "name": "Track A Attendance Batch",
            "program_id": program["id"],
            "capacity": 8,
            "status": "active",
        },
    )
    batch_id = int(batch["id"])
    _post(
        f"/api/cam/batch-coach-assignments?batch_id={batch_id}",
        {"coach_id": session_coach["id"], "assignment_role": "primary", "start_date": date.today().isoformat()},
    )
    for player in players:
        _post(f"/api/cam/batches/{batch_id}/players", {"player_id": player["id"]})

    session_day = date.today() + timedelta(days=7)
    generated = _post(
        f"/api/cam/batches/{batch_id}/generate-sessions",
        {
            "start_date": session_day.isoformat(),
            "end_date": session_day.isoformat(),
            "weekdays": [session_day.weekday()],
            "start_time": "18:00",
            "duration_minutes": 60,
        },
    )
    assert generated["created_count"] == 1
    session_id = int(generated["session_ids"][0])

    # QA-032..035: every supported attendance status is persisted in one
    # deterministic roster save. Absent/excused also exercise reason + default
    # make-up eligibility while present/late remain non-make-up by default.
    attendance_payload = {
        "players": [
            {"player_id": players[0]["id"], "status": "present"},
            {"player_id": players[1]["id"], "status": "absent", "absence_reason": "Illness"},
            {"player_id": players[2]["id"], "status": "late", "notes": "Arrived 12 minutes late"},
            {"player_id": players[3]["id"], "status": "excused", "absence_reason": "School event"},
        ],
        "coach_status": "present",
        "coach_notes": "Session coach present",
    }
    saved = client.put(f"/api/cam/sessions/{session_id}/attendance", json=attendance_payload)
    assert saved.status_code == 200, saved.text
    rows = {int(row["player_id"]): row for row in saved.json()["players"]}
    assert rows[int(players[0]["id"])]["attendance_status"] == "present"
    assert rows[int(players[0]["id"])]["make_up_eligible"] is False
    assert rows[int(players[1]["id"])]["attendance_status"] == "absent"
    assert rows[int(players[1]["id"])]["absence_reason"] == "Illness"
    assert rows[int(players[1]["id"])]["make_up_eligible"] is True
    assert rows[int(players[2]["id"])]["attendance_status"] == "late"
    assert rows[int(players[2]["id"])]["notes"] == "Arrived 12 minutes late"
    assert rows[int(players[3]["id"])]["attendance_status"] == "excused"
    assert rows[int(players[3]["id"])]["absence_reason"] == "School event"
    assert rows[int(players[3]["id"])]["make_up_eligible"] is True

    # Bootstrap access after the operational fixture exists. From this point the
    # generic attendance API must be Owner/Admin-only.
    owner_token = _bootstrap_owner()
    parent_guardian_id = int(players[0]["guardians"][0]["id"])

    _create_user(
        owner_token,
        {
            "display_name": "Unassigned Coach User",
            "email": "unassigned.coach.user@example.test",
            "password": "AttendanceCoach!123",
            "role": "coach",
            "coach_id": int(other_coach["id"]),
            "status": "active",
        },
    )
    _create_user(
        owner_token,
        {
            "display_name": "Attendance Parent User",
            "email": "attendance.parent@example.test",
            "password": "AttendanceParent!123",
            "role": "parent",
            "guardian_id": parent_guardian_id,
            "status": "active",
        },
    )

    coach_token = _login("unassigned.coach.user@example.test", "AttendanceCoach!123")
    parent_token = _login("attendance.parent@example.test", "AttendanceParent!123")

    # QA-037: a Coach who is not assigned to this session cannot use the generic
    # staff attendance endpoint. Future Coach Workspace APIs will need a second
    # assignment-aware check, but the current pilot boundary is secure by default.
    coach_attempt = client.put(
        f"/api/cam/sessions/{session_id}/attendance",
        json=attendance_payload,
        headers=_auth(coach_token),
    )
    assert coach_attempt.status_code == 403, coach_attempt.text

    # QA-038: Parent can never edit attendance through the generic management API,
    # even for a linked child.
    parent_attempt = client.put(
        f"/api/cam/sessions/{session_id}/attendance",
        json=attendance_payload,
        headers=_auth(parent_token),
    )
    assert parent_attempt.status_code == 403, parent_attempt.text

    # QA-036: Owner is permitted to correct a saved attendance record. The same
    # row is updated, history records before/after states, and no duplicate record
    # is introduced.
    corrected_payload = {
        "players": [
            {"player_id": players[0]["id"], "status": "late", "notes": "Corrected after coach review"},
            {"player_id": players[1]["id"], "status": "absent", "absence_reason": "Illness"},
            {"player_id": players[2]["id"], "status": "late", "notes": "Arrived 12 minutes late"},
            {"player_id": players[3]["id"], "status": "excused", "absence_reason": "School event"},
        ],
        "coach_status": "present",
    }
    corrected = client.put(
        f"/api/cam/sessions/{session_id}/attendance",
        json=corrected_payload,
        headers=_auth(owner_token),
    )
    assert corrected.status_code == 200, corrected.text
    corrected_row = next(
        row for row in corrected.json()["players"] if int(row["player_id"]) == int(players[0]["id"])
    )
    assert corrected_row["attendance_status"] == "late"
    assert corrected_row["notes"] == "Corrected after coach review"

    history = client.get(
        f"/api/cam/attendance/history?session_id={session_id}&entity_type=player&subject_id={players[0]['id']}",
        headers=_auth(owner_token),
    )
    assert history.status_code == 200, history.text
    assert len(history.json()) == 2
    latest = history.json()[0]
    assert latest["before"]["status"] == "present"
    assert latest["after"]["status"] == "late"

    attendance_after = client.get(
        f"/api/cam/sessions/{session_id}/attendance",
        headers=_auth(owner_token),
    )
    assert attendance_after.status_code == 200
    assert len(attendance_after.json()["players"]) == 4
