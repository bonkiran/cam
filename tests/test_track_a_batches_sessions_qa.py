import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-track-a-batches-qa-")

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _reset_shared_postgres_state() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "session_attendance",
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


def _post(path: str, payload: dict, expected=(200, 201)):
    response = client.post(path, json=payload)
    assert response.status_code in expected, response.text
    return response.json() if response.content else None


def _coach_payload(first: str, last: str, status: str = "active") -> dict:
    return {
        "first_name": first,
        "last_name": last,
        "preferred_name": first,
        "email": f"{first.lower()}.{last.lower()}@tracka.example.test",
        "phone": "4045550123",
        "specialties": ["Batting"],
        "availability": "Weekday evenings",
        "certifications": "Track A QA",
        "joined_on": date.today().isoformat(),
        "status": status,
        "notes": "Track A batch/session QA",
    }


def test_track_a_coach_batch_roster_waitlist_and_future_session_lifecycle():
    _reset_shared_postgres_state()

    academy = client.put(
        "/api/academy/profile",
        json={"name": "Track A Batches Academy", "timezone": "America/New_York"},
    )
    assert academy.status_code == 200, academy.text

    program = _post(
        "/api/academy/programs",
        {"name": "Track A U13 Batch Program", "program_type": "group", "status": "active"},
    )
    primary = _post("/api/academy/coaches", _coach_payload("Primary", "Coach"))
    support = _post("/api/academy/coaches", _coach_payload("Support", "Coach"))

    players = [
        _post("/api/academy/players", {"name": f"Track A Batch Player {i}", "status": "active"})
        for i in range(1, 5)
    ]

    # QA-017: Coach lifecycle includes explicit deactivate and reactivate.
    primary_id = int(primary["id"])
    deactivated = client.put(
        f"/api/academy/coaches/{primary_id}",
        json=_coach_payload("Primary", "Coach", "inactive"),
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["status"] == "inactive"
    reactivated = client.put(
        f"/api/academy/coaches/{primary_id}",
        json=_coach_payload("Primary", "Coach", "active"),
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "active"

    # QA-018 / QA-019: create a capacity-two batch and later fill it exactly.
    batch = _post(
        "/api/academy/batches",
        {
            "name": "Track A Capacity Batch",
            "program_id": program["id"],
            "capacity": 2,
            "location": "Track A Indoor Center",
            "resource": "Net 2",
            "status": "active",
        },
    )
    batch_id = int(batch["id"])

    # QA-024: primary and support assignments coexist. The primary remains the
    # generated-session coach; support is retained as an active assignment.
    primary_assignment = _post(
        f"/api/academy/batch-coach-assignments?batch_id={batch_id}",
        {"coach_id": primary_id, "assignment_role": "primary", "start_date": date.today().isoformat()},
    )
    support_assignment = _post(
        f"/api/academy/batch-coach-assignments?batch_id={batch_id}",
        {"coach_id": support["id"], "assignment_role": "support", "start_date": date.today().isoformat()},
    )
    assert primary_assignment["assignment_role"] == "primary"
    assert support_assignment["assignment_role"] == "support"
    assignments = client.get(f"/api/academy/batch-coach-assignments?batch_id={batch_id}")
    assert assignments.status_code == 200, assignments.text
    active_roles = {row["assignment_role"] for row in assignments.json() if row["status"] == "active"}
    assert active_roles == {"primary", "support"}

    first_member = _post(
        f"/api/academy/batches/{batch_id}/players",
        {"player_id": players[0]["id"], "joined_on": date.today().isoformat()},
    )
    assert first_member["status"] == "active"

    # QA-025: create one future recurring session while only Player 1 is rostered.
    future = date.today() + timedelta(days=7)
    schedule = {
        "start_date": future.isoformat(),
        "end_date": future.isoformat(),
        "weekdays": [future.weekday()],
        "start_time": "18:30",
        "duration_minutes": 90,
    }
    generated = _post(f"/api/academy/batches/{batch_id}/generate-sessions", schedule)
    assert generated["created_count"] == 1
    session_id = int(generated["session_ids"][0])
    first_roster = client.get(f"/api/academy/sessions/{session_id}/players")
    assert first_roster.status_code == 200
    assert [int(row["player_id"]) for row in first_roster.json()] == [int(players[0]["id"])]

    # Adding Player 2 after sessions were generated must synchronize that player
    # into future scheduled session rosters. This closes the Track A defect found
    # during the permutation sweep.
    second_member = _post(
        f"/api/academy/batches/{batch_id}/players",
        {"player_id": players[1]["id"], "joined_on": date.today().isoformat()},
    )
    assert second_member["status"] == "active"
    synced_roster = client.get(f"/api/academy/sessions/{session_id}/players").json()
    assert {int(row["player_id"]) for row in synced_roster} == {int(players[0]["id"]), int(players[1]["id"])}

    # QA-021: duplicate current roster membership is rejected.
    duplicate = client.post(
        f"/api/academy/batches/{batch_id}/players",
        json={"player_id": players[1]["id"]},
    )
    assert duplicate.status_code == 409, duplicate.text

    batch_full = client.get(f"/api/academy/batches/{batch_id}").json()
    assert int(batch_full["active_player_count"]) == 2

    # QA-020: over-capacity addition rejects by default, then explicitly enters
    # the waitlist when requested. Waitlisted players do not enter sessions.
    over_capacity = client.post(
        f"/api/academy/batches/{batch_id}/players",
        json={"player_id": players[2]["id"]},
    )
    assert over_capacity.status_code == 409, over_capacity.text
    waitlisted = _post(
        f"/api/academy/batches/{batch_id}/players",
        {"player_id": players[2]["id"], "waitlist_if_full": True},
    )
    assert waitlisted["status"] == "waitlisted"
    assert int(waitlisted["player_id"]) == int(players[2]["id"])
    waitlist_roster = client.get(f"/api/academy/sessions/{session_id}/players").json()
    assert int(players[2]["id"]) not in {int(row["player_id"]) for row in waitlist_roster}

    # QA-026: identical recurring generation is idempotent at the session level.
    duplicate_generation = _post(f"/api/academy/batches/{batch_id}/generate-sessions", schedule)
    assert duplicate_generation["created_count"] == 0
    assert duplicate_generation["session_ids"] == []
    assert len(client.get(f"/api/academy/sessions?batch_id={batch_id}").json()) == 1

    # Promotion while the batch is still full is blocked.
    promote_while_full = client.post(
        f"/api/academy/batches/{batch_id}/players/{waitlisted['id']}/promote",
        json={},
    )
    assert promote_while_full.status_code == 409, promote_while_full.text

    # QA-022: ending Player 2 preserves membership history but removes the player
    # from today/future scheduled session rosters.
    ended = _post(
        f"/api/academy/batches/{batch_id}/players/{second_member['id']}/end",
        {},
    )
    assert ended["status"] == "inactive"
    assert ended["ended_on"] == date.today().isoformat()
    after_end_roster = client.get(f"/api/academy/sessions/{session_id}/players").json()
    assert {int(row["player_id"]) for row in after_end_roster} == {int(players[0]["id"])}

    # QA-023: vacancy opens -> promote the waitlisted player -> future session
    # roster is synchronized exactly once.
    promoted = _post(
        f"/api/academy/batches/{batch_id}/players/{waitlisted['id']}/promote",
        {},
    )
    assert promoted["status"] == "active"
    after_promote_roster = client.get(f"/api/academy/sessions/{session_id}/players").json()
    assert {int(row["player_id"]) for row in after_promote_roster} == {int(players[0]["id"]), int(players[2]["id"])}

    promoted_twice = client.post(
        f"/api/academy/batches/{batch_id}/players/{waitlisted['id']}/promote",
        json={},
    )
    assert promoted_twice.status_code == 409, promoted_twice.text

    final_batch = client.get(f"/api/academy/batches/{batch_id}").json()
    assert int(final_batch["active_player_count"]) == 2
    assert int(final_batch["waitlist_count"]) == 0

    # A waitlisted membership can also be ended without ever touching sessions.
    fourth_waitlist = _post(
        f"/api/academy/batches/{batch_id}/players",
        {"player_id": players[3]["id"], "waitlist_if_full": True},
    )
    assert fourth_waitlist["status"] == "waitlisted"
    ended_waitlist = _post(
        f"/api/academy/batches/{batch_id}/players/{fourth_waitlist['id']}/end",
        {},
    )
    assert ended_waitlist["status"] == "inactive"
    assert int(client.get(f"/api/academy/batches/{batch_id}").json()["waitlist_count"]) == 0

    # Session coach selection still uses the primary, not support, assignment.
    session = client.get(f"/api/academy/sessions/{session_id}").json()
    assert int(session["coach_id"]) == primary_id
