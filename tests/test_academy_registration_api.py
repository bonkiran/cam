import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-registration-test-")
os.environ["CAM_TEMP_ADMIN_MODE"] = "1"

from fastapi.testclient import TestClient
from run import app
from app.database import fetch_all, fetch_one

client = TestClient(app)


def _application_payload():
    return {
        "player_first_name": "Aarav",
        "player_last_name": "Patel",
        "player_date_of_birth": "2012-04-15",
        "player_gender": "Male",
        "cricket_role": "All-Rounder",
        "batting_order": "TO",
        "bowling_type": "Spin",
        "wicketkeeping": False,
        "parent_first_name": "Ravi",
        "parent_last_name": "Patel",
        "parent_relationship": "Father",
        "parent_email": "ravi.registration@example.com",
        "parent_phone": "404-555-1212",
        "parent_address_line1": "101 Cricket Lane",
        "parent_address_line2": None,
        "parent_city": "Johns Creek",
        "parent_state": "GA",
        "parent_postal_code": "30024",
        "parent_country": "United States",
        "emergency_contacts": [
            {"first_name": "Priya", "last_name": "Patel", "relationship": "Mother", "phone": "404-555-2222", "email": "priya@example.com"},
            {"first_name": "Anil", "last_name": "Patel", "relationship": "Uncle", "phone": "404-555-3333", "email": "anil@example.com"},
        ],
        "guardian_same_as_parent": False,
        "guardian": {
            "first_name": "Priya",
            "last_name": "Patel",
            "relationship": "Mother",
            "phone": "404-555-2222",
            "email": "priya@example.com",
            "address_line1": "101 Cricket Lane",
            "city": "Johns Creek",
            "state": "GA",
            "postal_code": "30024",
            "country": "United States",
            "pickup_authorized": True,
        },
        "injuries": "Prior ankle sprain; fully recovered.",
        "surgeries": None,
        "medical_considerations": None,
        "allergies": "None known",
        "physical_restrictions": None,
        "additional_notes": "Interested in weekend sessions.",
        "consent_confirmed": True,
    }


def test_registration_invite_tracking_submission_review_and_approval():
    profile = client.put("/api/academy/profile", json={"name": "Registration Test Academy", "city": "Johns Creek", "state": "GA", "postal_code": "30024"})
    assert profile.status_code == 200, profile.text

    created = client.post(
        "/api/academy/registration/invites",
        json={
            "parent_first_name": "Ravi",
            "parent_last_name": "Patel",
            "parent_phone": "404-555-1212",
            "parent_email": "ravi.registration@example.com",
        },
    )
    assert created.status_code == 201, created.text
    invite = created.json()
    invite_id = int(invite["id"])
    registration_url = invite["registration_url"]
    assert "/register/" in registration_url
    token = registration_url.rstrip("/").split("/")[-1]
    assert invite["status"] == "created"
    assert invite["sent_by_name"] == "Admin"

    sent = client.post(f"/api/academy/registration/invites/{invite_id}/sent", json={"channel": "sms"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    assert sent.json()["last_channel"] == "sms"

    public_page = client.get(f"/register/{token}")
    assert public_page.status_code == 200
    assert "Academy Player Registration" in public_page.text

    opened = client.get(f"/api/public/registration/{token}")
    assert opened.status_code == 200, opened.text
    opened_json = opened.json()
    assert opened_json["invite"]["status"] == "opened"
    application_id = int(opened_json["application"]["id"])
    assert opened_json["application"]["parent_first_name"] == "Ravi"

    draft_payload = _application_payload()
    draft_payload["consent_confirmed"] = False
    draft = client.put(f"/api/public/registration/{token}/draft", json=draft_payload)
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "draft"
    tracked = client.get("/api/academy/registration/invites").json()
    tracked_invite = next(row for row in tracked if int(row["id"]) == invite_id)
    assert tracked_invite["status"] == "in_progress"
    assert tracked_invite["application_id"] == application_id

    invalid_submit = client.post(f"/api/public/registration/{token}/submit", json=draft_payload)
    assert invalid_submit.status_code == 422
    assert "Registration confirmation" in invalid_submit.text

    submitted_payload = _application_payload()
    submitted = client.post(f"/api/public/registration/{token}/submit", json=submitted_payload)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    summary = client.get("/api/academy/registration/summary")
    assert summary.status_code == 200, summary.text
    assert int(summary.json()["submitted"]) == 1

    application = client.get(f"/api/academy/registration/applications/{application_id}")
    assert application.status_code == 200, application.text
    app_json = application.json()
    assert app_json["cricket_role"] == "All-Rounder"
    assert len(app_json["emergency_contacts"]) == 2
    assert app_json["guardian"]["first_name"] == "Priya"

    needs_info = client.post(
        f"/api/academy/registration/applications/{application_id}/review",
        json={"action": "needs_information", "note": "Please confirm the allergy information."},
    )
    assert needs_info.status_code == 200, needs_info.text
    assert needs_info.json()["status"] == "needs_information"

    parent_reopen = client.get(f"/api/public/registration/{token}")
    assert parent_reopen.status_code == 200, parent_reopen.text
    assert parent_reopen.json()["application"]["review_note"] == "Please confirm the allergy information."

    resubmit_payload = _application_payload()
    resubmit_payload["allergies"] = "No allergies"
    resubmit = client.post(f"/api/public/registration/{token}/submit", json=resubmit_payload)
    assert resubmit.status_code == 200, resubmit.text

    approved = client.post(
        f"/api/academy/registration/applications/{application_id}/review",
        json={"action": "approve", "note": "Reviewed and approved."},
    )
    assert approved.status_code == 200, approved.text
    approved_json = approved.json()
    player_id = int(approved_json["approved_player_id"])
    assert approved_json["status"] == "approved"

    player = client.get(f"/api/academy/players/{player_id}")
    assert player.status_code == 200, player.text
    player_json = player.json()
    assert player_json["name"] == "Aarav Patel"
    assert player_json["status"] == "active"
    assert len(player_json["guardians"]) == 2
    assert player_json["emergency_contact_phone"] == "404-555-2222"

    profile_row = fetch_one("SELECT * FROM academy_player_registration_profiles WHERE player_id=?", (player_id,))
    assert profile_row is not None
    assert profile_row["cricket_role"] == "All-Rounder"
    assert profile_row["batting_order"] == "TO"
    assert profile_row["bowling_type"] == "Spin"
    assert int(profile_row["wicketkeeping"]) == 0

    emergency_rows = fetch_all("SELECT * FROM academy_player_emergency_contacts WHERE player_id=? ORDER BY sequence_no", (player_id,))
    assert len(emergency_rows) == 2
    medical = fetch_one("SELECT * FROM academy_player_medical_profiles WHERE player_id=?", (player_id,))
    assert medical is not None
    assert medical["allergies"] == "No allergies"

    final_summary = client.get("/api/academy/registration/summary").json()
    assert int(final_summary["approved"]) == 1
    assert int(final_summary["submitted"]) == 0
