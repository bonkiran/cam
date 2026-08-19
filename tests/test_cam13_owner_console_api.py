import os
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _reset_postgres_if_needed() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


os.environ.setdefault("CRICKANALYSIS_DATA_DIR", tempfile.mkdtemp(prefix="cam13-owner-api-"))
os.environ["CAM_BOOTSTRAP_TOKEN"] = "cam13-owner-bootstrap"
os.environ["CAM_PAYMENT_MODE"] = "sandbox"
_reset_postgres_if_needed()

from fastapi.testclient import TestClient

from run import app

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_owner_console_directory_player360_and_notification_event():
    profile = client.put(
        "/api/academy/profile",
        json={"name": "CAM-13 Academy", "timezone": "America/New_York"},
    )
    assert profile.status_code == 200, profile.text

    bootstrap = client.post(
        "/api/auth/bootstrap",
        headers={"X-CAM-Bootstrap": "cam13-owner-bootstrap"},
        json={
            "display_name": "CAM Owner",
            "email": "owner.cam13@example.test",
            "password": "OwnerCam13!123",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    token = bootstrap.json()["token"]
    headers = _auth(token)

    player = client.post(
        "/api/academy/players",
        headers=headers,
        json={
            "name": "Aarav CAM13",
            "first_name": "Aarav",
            "last_name": "Patel",
            "joined_on": date.today().isoformat(),
            "status": "active",
            "guardians": [
                {
                    "first_name": "Priya",
                    "last_name": "Patel",
                    "relationship": "Mother",
                    "phone": "+1-404-555-0101",
                    "email": "priya.cam13@example.test",
                    "is_primary": True,
                    "billing_contact": True,
                    "pickup_authorized": True,
                }
            ],
        },
    )
    assert player.status_code == 201, player.text
    player_id = player.json()["id"]

    coach = client.post(
        "/api/academy/coaches",
        headers=headers,
        json={
            "first_name": "Ravi",
            "last_name": "Coach",
            "phone": "+1-404-555-0202",
            "email": "ravi.cam13@example.test",
            "status": "active",
        },
    )
    assert coach.status_code == 201, coach.text
    coach_id = coach.json()["id"]

    program = client.post(
        "/api/academy/programs",
        headers=headers,
        json={"name": "CAM13 U15", "program_type": "group", "status": "active"},
    )
    assert program.status_code == 201, program.text

    batch = client.post(
        "/api/academy/batches",
        headers=headers,
        json={
            "name": "CAM13 U15 Batch A",
            "program_id": program.json()["id"],
            "capacity": 16,
            "status": "active",
        },
    )
    assert batch.status_code == 201, batch.text
    batch_id = batch.json()["id"]

    membership = client.post(
        f"/api/academy/batches/{batch_id}/players",
        headers=headers,
        json={"player_id": player_id, "waitlist_if_full": False, "joined_on": date.today().isoformat()},
    )
    assert membership.status_code == 201, membership.text

    assignment = client.post(
        f"/api/academy/coach-player-assignments",
        headers=headers,
        json={
            "coach_id": coach_id,
            "player_id": player_id,
            "assignment_role": "primary",
            "start_date": date.today().isoformat(),
        },
    )
    assert assignment.status_code == 201, assignment.text

    private_session = client.post(
        "/api/academy/sessions/private",
        headers=headers,
        json={
            "player_id": player_id,
            "coach_id": coach_id,
            "session_date": date.today().isoformat(),
            "start_time": "18:00",
            "duration_minutes": 60,
            "location": "Indoor Center",
        },
    )
    assert private_session.status_code == 201, private_session.text
    session_id = private_session.json()["id"]

    directory = client.get("/api/academy/owner-console/players", headers=headers)
    assert directory.status_code == 200, directory.text
    row = next(item for item in directory.json() if item["id"] == player_id)
    assert row["batches"][0]["name"] == "CAM13 U15 Batch A"
    assert row["guardians"][0]["name"] == "Priya Patel"
    assert row["cricclubs"]["status"] == "not_connected"

    summary = client.get(f"/api/academy/owner-console/players/{player_id}/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["player"]["name"] == "Aarav CAM13"
    assert payload["batches"][0]["batch_name"] == "CAM13 U15 Batch A"
    assert payload["coaches"][0]["coach_id"] == coach_id
    assert payload["guardians"][0]["email"] == "priya.cam13@example.test"

    event = client.post(
        "/api/academy/owner-console/notification-events",
        headers=headers,
        json={
            "event_type": "session_rescheduled",
            "entity_type": "session",
            "entity_id": session_id,
            "channels": ["push", "whatsapp"],
            "message": "Session rescheduled for CAM-13 test.",
            "metadata": {"source": "dashboard"},
        },
    )
    assert event.status_code == 201, event.text
    event_payload = event.json()
    assert event_payload["status"] == "awaiting_provider"
    assert event_payload["payload"]["dispatch_attempted"] is False
    assert event_payload["payload"]["provider_configured"] is False
    assert set(event_payload["channels"]) == {"push", "whatsapp"}
    assert event_payload["recipient_count"] == 2

    events = client.get("/api/academy/owner-console/notification-events", headers=headers)
    assert events.status_code == 200, events.text
    assert events.json()[0]["id"] == event_payload["id"]


def test_owner_console_is_owner_admin_only():
    # The owner token from the prior test remains valid in this module-level test app.
    login = client.post(
        "/api/auth/login",
        json={"email": "owner.cam13@example.test", "password": "OwnerCam13!123"},
    )
    assert login.status_code == 200, login.text
    owner_headers = _auth(login.json()["token"])

    users = client.get("/api/academy/access/reference", headers=owner_headers)
    assert users.status_code == 200, users.text
    guardian_id = users.json()["guardians"][0]["id"]

    parent = client.post(
        "/api/academy/access/users",
        headers=owner_headers,
        json={
            "display_name": "CAM13 Parent",
            "email": "parent.cam13@example.test",
            "password": "ParentCam13!123",
            "role": "parent",
            "guardian_id": guardian_id,
            "status": "active",
        },
    )
    assert parent.status_code == 201, parent.text

    parent_login = client.post(
        "/api/auth/login",
        json={"email": "parent.cam13@example.test", "password": "ParentCam13!123"},
    )
    assert parent_login.status_code == 200, parent_login.text
    parent_headers = _auth(parent_login.json()["token"])

    forbidden = client.get("/api/academy/owner-console/players", headers=parent_headers)
    assert forbidden.status_code == 403, forbidden.text
