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


def _primary_emergency(phone="404-555-0199"):
    return {
        "first_name": "Priya",
        "last_name": "Kumar",
        "relationship": "Mother",
        "phone": phone,
        "email": "priya.kumar@example.com",
    }


def _payload(emergency_contacts=None, *, player_first_name="Policy", player_last_name="Tester"):
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
        {"first_name": "Anil", "last_name": None, "relationship": "Uncle", "phone": None, "email": None},
    ]
    submitted = client.post(f"/api/public/registration/{token}/submit", json=_payload(contacts))
    assert submitted.status_code == 422, submitted.text
    assert "Emergency contact 2 name, relationship and phone" in submitted.text


def test_parent_phone_rejects_text_and_too_few_digits():
    _, token = _new_token("invalid-parent-phone")
    payload = _payload()
    payload["parent_phone"] = "call-me-now"
    submitted = client.post(f"/api/public/registration/{token}/submit", json=payload)
    assert submitted.status_code == 422, submitted.text
    assert "Parent phone must contain 9-15 digits and no letters" in submitted.text

    payload["parent_phone"] = "12345678"
    submitted = client.post(f"/api/public/registration/{token}/submit", json=payload)
    assert submitted.status_code == 422, submitted.text


def test_nine_digit_phone_is_accepted():
    _, token = _new_token("nine-digit-phone")
    payload = _payload([_primary_emergency("123-456-789")])
    payload["parent_phone"] = "123-456-789"
    submitted = client.post(f"/api/public/registration/{token}/submit", json=payload)
    assert submitted.status_code == 200, submitted.text


def test_emergency_contact_phone_rejects_text():
    _, token = _new_token("invalid-emergency-phone")
    submitted = client.post(
        f"/api/public/registration/{token}/submit",
        json=_payload([_primary_emergency("abc-123456789")]),
    )
    assert submitted.status_code == 422, submitted.text
    assert "Emergency contact 1 phone must contain 9-15 digits and no letters" in submitted.text


def test_state_rejects_invalid_text_and_accepts_full_name():
    _, token = _new_token("invalid-state")
    payload = _payload()
    payload["parent_state"] = "Atlantis"
    submitted = client.post(f"/api/public/registration/{token}/submit", json=payload)
    assert submitted.status_code == 422, submitted.text
    assert "Parent state must be a valid US state name or 2-letter abbreviation" in submitted.text

    _, token = _new_token("full-state")
    payload = _payload(player_first_name="FullState")
    payload["parent_state"] = "Georgia"
    submitted = client.post(f"/api/public/registration/{token}/submit", json=payload)
    assert submitted.status_code == 200, submitted.text
    application_id = int(submitted.json()["application_id"])
    application = client.get(f"/api/academy/registration/applications/{application_id}")
    assert application.status_code == 200, application.text
    assert application.json()["parent_state"] == "GA"


def test_zip_requires_exactly_five_digits_and_preserves_leading_zero():
    _, token = _new_token("invalid-zip")
    payload = _payload()
    payload["parent_postal_code"] = "30O24"
    submitted = client.post(f"/api/public/registration/{token}/submit", json=payload)
    assert submitted.status_code == 422, submitted.text
    assert "Parent ZIP must be a valid 5-digit US ZIP code" in submitted.text

    _, token = _new_token("leading-zero-zip")
    payload = _payload(player_first_name="LeadingZero")
    payload["parent_postal_code"] = "02108"
    submitted = client.post(f"/api/public/registration/{token}/submit", json=payload)
    assert submitted.status_code == 200, submitted.text
    application_id = int(submitted.json()["application_id"])
    application = client.get(f"/api/academy/registration/applications/{application_id}")
    assert application.json()["parent_postal_code"] == "02108"


def test_copy_link_and_public_form_ui_match_current_policy():
    index = (REPO_ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    copy_patch = (REPO_ROOT / "app" / "static" / "academy_registration_copy_link_fix_v1.js").read_text(encoding="utf-8")
    review_patch = (REPO_ROOT / "app" / "static" / "academy_registration_review_policy_v2.js").read_text(encoding="utf-8")
    public_html = (REPO_ROOT / "app" / "static" / "academy_registration_public_v1.html").read_text(encoding="utf-8")
    validation = (REPO_ROOT / "app" / "static" / "academy_registration_phone_validation_v1.js").read_text(encoding="utf-8")

    assert "academy_registration_copy_link_fix_v1.js" in index
    assert "data-share=\"copy\"" in copy_patch
    assert "/sent" not in copy_patch

    assert "Emergency Contact 1 *" in public_html
    assert "Emergency Contact 2 *" not in public_html
    assert "Please provide one emergency contact. A second contact is optional." in public_html
    assert "<h2>Guardian</h2>" not in public_html

    assert 'name="parent_phone" type="tel"' in public_html
    assert 'data-contact="phone" type="tel"' in public_html
    assert "academy_registration_phone_validation_v1.js" in public_html
    assert "digits.length >= 9 && digits.length <= 15" in validation
    assert "STATE_MESSAGE" in validation
    assert "ZIP_MESSAGE" in validation
    assert "^[0-9]{5}$" in validation
    assert "label.remove()" in validation

    assert "academy_registration_review_policy_v2.js" in index
    assert "Emergency Contacts" in review_patch
    assert "Pickup Authorized" not in review_patch


# Verification-only touch so PR CI validates the exact code currently on main.
