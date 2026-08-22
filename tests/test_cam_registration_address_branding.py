import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-registration-address-test-")
os.environ["CAM_TEMP_ADMIN_MODE"] = "1"
os.environ.setdefault("CAM_ADDRESS_VALIDATION_MODE", "stub")

from fastapi.testclient import TestClient

from run import app
from app import cam_registration_address_validation as address_validation


client = TestClient(app)


def _payload():
    return {
        "player_first_name": "Address",
        "player_last_name": "Tester",
        "player_date_of_birth": "2013-01-01",
        "player_gender": "Male",
        "cricket_role": "Batter",
        "batting_order": "TO",
        "bowling_type": "N/A",
        "wicketkeeping": False,
        "parent_first_name": "Ravi",
        "parent_last_name": "Kumar",
        "parent_relationship": "Father",
        "parent_email": "address.test@example.com",
        "parent_phone": "404-555-0101",
        "parent_address_line1": "123 Main Street",
        "parent_address_line2": None,
        "parent_city": "Johns Creek",
        "parent_state": "GA",
        "parent_postal_code": "30024",
        "parent_country": "United States",
        "emergency_contacts": [
            {
                "first_name": "Priya",
                "last_name": "Kumar",
                "relationship": "Mother",
                "phone": "404-555-0199",
                "email": "priya@example.com",
            }
        ],
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


def _new_token(suffix: str = "address") -> str:
    profile = client.put("/api/cam/profile", json={"name": "JKC"})
    assert profile.status_code == 200, profile.text
    created = client.post(
        "/api/cam/registration/invites",
        json={
            "parent_first_name": "Ravi",
            "parent_last_name": "Kumar",
            "parent_phone": "404-555-0101",
            "parent_email": f"{suffix}@example.com",
        },
    )
    assert created.status_code == 201, created.text
    token = created.json()["registration_url"].rstrip("/").split("/")[-1]
    opened = client.get(f"/api/public/registration/{token}")
    assert opened.status_code == 200, opened.text
    return token


def test_registration_rejects_address_that_cannot_be_verified(monkeypatch):
    token = _new_token("bad-address")
    monkeypatch.setattr(
        address_validation,
        "verify_us_address",
        lambda **_: {"verified": False, "source": "test", "matched_address": None},
    )
    submitted = client.post(f"/api/public/registration/{token}/submit", json=_payload())
    assert submitted.status_code == 422, submitted.text
    assert "address, city, state and ZIP could not be verified" in submitted.text


def test_registration_fails_closed_when_address_service_is_unavailable(monkeypatch):
    token = _new_token("address-unavailable")

    def unavailable(**_):
        raise address_validation.AddressVerificationUnavailable("temporary")

    monkeypatch.setattr(address_validation, "verify_us_address", unavailable)
    submitted = client.post(f"/api/public/registration/{token}/submit", json=_payload())
    assert submitted.status_code == 503, submitted.text
    assert "Address verification is temporarily unavailable" in submitted.text


def test_census_address_verifier_accepts_matching_state_and_zip(monkeypatch):
    monkeypatch.setenv("CAM_ADDRESS_VALIDATION_MODE", "census")
    monkeypatch.setattr(
        address_validation,
        "_fetch_json",
        lambda *_args, **_kwargs: {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 MAIN ST, JOHNS CREEK, GA, 30024",
                        "addressComponents": {
                            "city": "JOHNS CREEK",
                            "state": "GA",
                            "zip": "30024",
                        },
                    }
                ]
            }
        },
    )
    result = address_validation.verify_us_address(
        street="123 Main Street",
        city="Johns Creek",
        state="GA",
        zip_code="30024",
    )
    assert result["verified"] is True
    assert result["state"] == "GA"
    assert result["zip"] == "30024"


def test_census_address_verifier_rejects_mismatched_location(monkeypatch):
    monkeypatch.setenv("CAM_ADDRESS_VALIDATION_MODE", "census")
    monkeypatch.setattr(
        address_validation,
        "_fetch_json",
        lambda *_args, **_kwargs: {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 MAIN ST, ATLANTA, FL, 33101",
                        "addressComponents": {"city": "ATLANTA", "state": "FL", "zip": "33101"},
                    }
                ]
            }
        },
    )
    result = address_validation.verify_us_address(
        street="123 Main Street",
        city="Johns Creek",
        state="GA",
        zip_code="30024",
    )
    assert result["verified"] is False


def test_registration_branding_returns_academy_name_for_staff_and_parent():
    client.put("/api/cam/profile", json={"name": "JKC"})
    staff = client.get("/api/cam/registration/branding")
    assert staff.status_code == 200, staff.text
    assert staff.json()["academy_name"] == "JKC"

    token = _new_token("branding")
    public = client.get(f"/api/public/registration/{token}/branding")
    assert public.status_code == 200, public.text
    assert public.json()["academy_name"] == "JKC"


def test_registration_ui_uses_academy_name_in_message_and_form_title():
    staff_js = (REPO_ROOT / "app" / "static" / "academy_registration_v1.js").read_text(encoding="utf-8")
    public_js = (REPO_ROOT / "app" / "static" / "academy_registration_phone_validation_v1.js").read_text(encoding="utf-8")

    assert "/api/cam/registration/branding" in staff_js
    assert "please complete the ${camLabel()} player registration form" in staff_js
    assert "`${camLabel()} Player Registration`" in staff_js

    assert "/api/public/registration/${encodeURIComponent(token)}/branding" in public_js
    assert "`${camLabel(data?.academy_name)} Player Registration`" in public_js
    assert "document.title = `${title} · CrickAnalysis`" in public_js
