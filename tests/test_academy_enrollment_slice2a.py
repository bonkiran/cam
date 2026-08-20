import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-enrollment-slice2a-")
os.environ["CAM_TEMP_ADMIN_MODE"] = "1"
os.environ.setdefault("CAM_ADDRESS_VALIDATION_MODE", "stub")

from fastapi.testclient import TestClient

from run import app

client = TestClient(app)


def _registration_payload():
    return {
        "player_first_name": "Slice",
        "player_last_name": "TwoA",
        "player_date_of_birth": "2013-02-02",
        "player_gender": "Male",
        "cricket_role": "Batter",
        "batting_order": "TO",
        "bowling_type": "N/A",
        "wicketkeeping": False,
        "parent_first_name": "Ravi",
        "parent_last_name": "Kumar",
        "parent_relationship": "Father",
        "parent_email": "slice2a.parent@example.com",
        "parent_phone": "404-555-0134",
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
                "phone": "404-555-0198",
                "email": "priya.slice2a@example.com",
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


def _submitted_registration():
    profile = client.put("/api/academy/profile", json={"name": "JKC"})
    assert profile.status_code == 200, profile.text
    created = client.post(
        "/api/academy/registration/invites",
        json={
            "parent_first_name": "Ravi",
            "parent_last_name": "Kumar",
            "parent_phone": "404-555-0134",
            "parent_email": "slice2a.parent@example.com",
        },
    )
    assert created.status_code == 201, created.text
    token = created.json()["registration_url"].rstrip("/").split("/")[-1]
    assert client.get(f"/api/public/registration/{token}").status_code == 200
    submitted = client.post(f"/api/public/registration/{token}/submit", json=_registration_payload())
    assert submitted.status_code == 200, submitted.text
    return int(submitted.json()["application_id"])


def test_slice2a_approve_creates_secure_enrollment_and_tracks_status():
    application_id = _submitted_registration()

    approved = client.post(f"/api/academy/enrollments/from-registration/{application_id}", json={})
    assert approved.status_code == 200, approved.text
    enrollment = approved.json()
    assert enrollment["status"] == "created"
    assert enrollment["academy_name"] == "JKC"
    assert enrollment["player_name"] == "Slice TwoA"
    assert "/enroll/" in enrollment["enrollment_url"]

    enrollment_id = int(enrollment["id"])
    enrollment_token = enrollment["enrollment_url"].rstrip("/").split("/")[-1]

    marked_sent = client.post(
        f"/api/academy/enrollments/{enrollment_id}/sent",
        json={"channel": "sms"},
    )
    assert marked_sent.status_code == 200, marked_sent.text
    assert marked_sent.json()["status"] == "sent"

    opened = client.get(f"/api/public/enrollment/{enrollment_token}")
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["enrollment"]["status"] == "opened"
    assert body["enrollment"]["academy_name"] == "JKC"
    assert body["enrollment"]["player_name"] == "Slice TwoA"
    assert [step["key"] for step in body["steps"]] == ["summary", "agreements", "payment", "complete"]

    started = client.post(f"/api/public/enrollment/{enrollment_token}/start", json={})
    assert started.status_code == 200, started.text
    assert started.json() == {"status": "in_progress", "next_step": "agreements"}

    admin = client.get(f"/api/academy/enrollments/by-application/{application_id}")
    assert admin.status_code == 200, admin.text
    assert admin.json()["status"] == "in_progress"


def test_slice2a_admin_ui_removes_request_information_and_uses_enrollment_action():
    js = (REPO_ROOT / "app" / "static" / "academy_enrollment_slice2a_v1.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "academy_enrollment_public_v1.html").read_text(encoding="utf-8")

    assert "Approve & Send Enrollment Link" in js
    assert "[data-review-action=\"needs_information\"]" in js
    assert "/api/academy/enrollments/from-registration/" in js
    assert "navigator.clipboard.writeText(enrollment.enrollment_url)" in js
    assert "Start Enrollment" in html
    assert "Agreements & Documents" in html
    assert "Fees & Payment" in html
