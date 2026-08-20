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
from app.database import fetch_one

client = TestClient(app)


def _primary_emergency():
    return {
        "first_name": "Priya",
        "last_name": "Kumar",
        "relationship": "Mother",
        "phone": "404-555-0199",
        "email": "priya.kumar@example.com",
    }


def _payload(emergency_contacts=None, *, pickup_authorized=True, player_first_name="Policy", player_last_name="Tester"):
    return {
        "player_first_name": player_first_name,
        "player_last_name": player_last_name,
        "player_date_of_birth": "2013-01-01",
        "player_gender": "Male",
        "cricket_role": "Batter",
        "batting_order": "TO",
        "bowling_type": "N/A",
        "wicketkeeping": False,
        "parent_first_name": "Ravi",
        "parent_last_name": "Kumar",
        "parent_relationship": "Father",
        "parent_email": "registration.policy@example.com",
        "parent_phone": "404-555-0101",
        "parent_address_line1": "1 Main Street",
        "parent_address_line2": None,
        "parent_city": "Johns Creek",
        "parent_state": "GA",
        "parent_postal_code": "30024",
        "parent_country": "United States",
        "emergency_contacts": emergency_contacts if emergency_contacts is not None else [_primary_emergency()],
        # Current public-form policy reuses this legacy boolean as the primary
        # parent's pickup authorization while the separate Guardian UI is retired.
        "guardian_same_as_parent": pickup_authorized,
        "guardian": None,
        "injuries": None,
        "surgeries": None,
        "medical_considerations": None,
        "allergies": None,
        "physical_restrictions": None,
        "additional_notes": None,
        "consent_confirmed": True,
    }


def _new_token(parent_suffix="policy"):
    client.put("/api/academy/profile", json={"name": "Registration Fix Test Academy"})
    created = client.post(
        "/api/academy/registration/invites",
        json={
            "parent_first_name": "Ravi",
            "parent_last_name": "Kumar",
            "parent_phone": "404-555-0101",
            "parent_email": f"{parent_suffix}@example.com",
        },
    )
    assert created.status_code == 201, created.text
    invite = created.json()
    token = invite["registration_url"].rstrip("/").split("/")[-1]
    opened = client.get(f"/api/public/registration/{token}")
    assert opened.status_code == 200, opened.text
    return int(invite["id"]), token


def test_registration_requires_emergency_contact_1():
    _, token = _new_token("missing-emergency")
    submitted = client.post(f"/api/public/registration/{token}/submit", json=_payload([]))
    assert submitted.status_code == 422, submitted.text
    assert "Emergency contact 1 name, relationship and phone" in submitted.text


def test_registration_accepts_one_emergency_contact_without_contact_2():
    invite_id, token = _new_token("one-emergency")
    submitted = client.post(
        f"/api/public/registration/{token}/submit",
        json=_payload([_primary_emergency()]),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    tracked = client.get("/api/academy/registration/invites").json()
    invite = next(row for row in tracked if int(row["id"]) == invite_id)
    assert invite["status"] == "submitted"


def test_optional_second_emergency_contact_must_be_complete_when_started():
    _, token = _new_token("partial-second")
    contacts = [
        _primary_emergency(),
        {
            "first_name": "Anil",
            "last_name": None,
            "relationship": "Uncle",
            "phone": None,
            "email": None,
        },
    ]
    submitted = client.post(f"/api/public/registration/{token}/submit", json=_payload(contacts))
    assert submitted.status_code == 422, submitted.text
    assert "Emergency contact 2 name, relationship and phone" in submitted.text


def test_parent_pickup_authorization_is_applied_on_approval():
    _, token = _new_token("pickup-policy")
    submitted = client.post(
        f"/api/public/registration/{token}/submit",
        json=_payload(
            [_primary_emergency()],
            pickup_authorized=False,
            player_first_name="Pickup",
            player_last_name="Policy",
        ),
    )
    assert submitted.status_code == 200, submitted.text
    application_id = int(submitted.json()["application_id"])

    approved = client.post(
        f"/api/academy/registration/applications/{application_id}/review",
        json={"action": "approve", "note": "Pickup policy test"},
    )
    assert approved.status_code == 200, approved.text
    player_id = int(approved.json()["approved_player_id"])

    primary_link = fetch_one(
        "SELECT pickup_authorized FROM player_guardians WHERE player_id=? AND is_primary=1",
        (player_id,),
    )
    assert primary_link is not None
    assert int(primary_link["pickup_authorized"]) == 0


def test_copy_link_and_public_form_ui_match_current_policy():
    index = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    copy_patch = (REPO_ROOT / "app" / "static" / "academy_registration_copy_link_fix_v1.js").read_text(encoding="utf-8")
    review_patch = (REPO_ROOT / "app" / "static" / "academy_registration_review_policy_v2.js").read_text(encoding="utf-8")
    public_html = (REPO_ROOT / "app" / "static" / "academy_registration_public_v1.html").read_text(encoding="utf-8")

    assert "academy_registration_copy_link_fix_v1.js" in index
    assert "data-share=\"copy\"" in copy_patch
    assert "/sent" not in copy_patch

    assert '<span class="active">Player</span><span>Parent</span><span>Medical</span><span>Review</span>' in public_html
    assert "1 · Player" not in public_html
    assert "3 · Safety" not in public_html
    assert "Emergency Contact 1 *" in public_html
    assert "Emergency Contact 2 *" not in public_html
    assert "Please provide one emergency contact. A second contact is optional." in public_html
    assert 'name="parent_pickup_authorized"' in public_html
    assert "Authorized to pick up player" in public_html
    assert "<h2>Guardian</h2>" not in public_html

    assert "academy_registration_review_policy_v2.js" in index
    assert "Emergency Contacts" in review_patch
    assert "Pickup Authorized" in review_patch
