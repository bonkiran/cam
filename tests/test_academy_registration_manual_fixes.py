import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-registration-fixes-test-")
os.environ["CAM_TEMP_ADMIN_MODE"] = "1"

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _payload(emergency_contacts=None):
    return {
        "player_first_name": "Optional",
        "player_last_name": "Contacts",
        "player_date_of_birth": "2013-01-01",
        "player_gender": "Male",
        "cricket_role": "Batter",
        "batting_order": "TO",
        "bowling_type": "N/A",
        "wicketkeeping": False,
        "parent_first_name": "Ravi",
        "parent_last_name": "Kumar",
        "parent_relationship": "Father",
        "parent_email": "optional.contacts@example.com",
        "parent_phone": "404-555-0101",
        "parent_address_line1": "1 Main Street",
        "parent_address_line2": None,
        "parent_city": "Johns Creek",
        "parent_state": "GA",
        "parent_postal_code": "30024",
        "parent_country": "United States",
        "emergency_contacts": emergency_contacts or [],
        "guardian_same_as_parent": True,
        "guardian": None,
        "injuries": None,
        "surgeries": None,
        "medical_considerations": None,
        "allergies": None,
        "physical_restrictions": None,
        "additional_notes": None,
        "consent_confirmed": True,
    }


def _new_token():
    client.put("/api/academy/profile", json={"name": "Registration Fix Test Academy"})
    created = client.post(
        "/api/academy/registration/invites",
        json={
            "parent_first_name": "Ravi",
            "parent_last_name": "Kumar",
            "parent_phone": "404-555-0101",
            "parent_email": "optional.contacts@example.com",
        },
    )
    assert created.status_code == 201, created.text
    invite = created.json()
    token = invite["registration_url"].rstrip("/").split("/")[-1]
    opened = client.get(f"/api/public/registration/{token}")
    assert opened.status_code == 200, opened.text
    return int(invite["id"]), token


def test_registration_can_submit_without_emergency_contacts():
    invite_id, token = _new_token()
    submitted = client.post(f"/api/public/registration/{token}/submit", json=_payload([]))
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    tracked = client.get("/api/academy/registration/invites").json()
    invite = next(row for row in tracked if int(row["id"]) == invite_id)
    assert invite["status"] == "submitted"


def test_partially_entered_emergency_contact_must_be_complete():
    _, token = _new_token()
    partial = _payload([
        {
            "first_name": "Priya",
            "last_name": None,
            "relationship": "Mother",
            "phone": None,
            "email": None,
        }
    ])
    submitted = client.post(f"/api/public/registration/{token}/submit", json=partial)
    assert submitted.status_code == 422, submitted.text
    assert "Emergency contact 1 name, relationship and phone" in submitted.text


def test_copy_link_fix_is_loaded_and_does_not_call_sent_api():
    index = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    patch = (REPO_ROOT / "app" / "static" / "academy_registration_copy_link_fix_v1.js").read_text(encoding="utf-8")
    public_html = (REPO_ROOT / "app" / "static" / "academy_registration_public_v1.html").read_text(encoding="utf-8")

    assert "academy_registration_copy_link_fix_v1.js" in index
    assert "data-share=\"copy\"" in patch
    assert "/sent" not in patch
    assert "Emergency Contact 1 *" not in public_html
    assert "Emergency Contact 2 *" not in public_html
    assert "Optional: provide up to two additional people" in public_html
