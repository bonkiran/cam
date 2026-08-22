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


def _registration_payload(player_last_name="TwoA", email_suffix="twoa"):
    return {
        "player_first_name": "Slice",
        "player_last_name": player_last_name,
        "player_date_of_birth": "2013-02-02",
        "player_gender": "Male",
        "cricket_role": "Batter",
        "batting_order": "TO",
        "bowling_type": "N/A",
        "wicketkeeping": False,
        "parent_first_name": "Ravi",
        "parent_last_name": "Kumar",
        "parent_relationship": "Father",
        "parent_email": f"slice2a.{email_suffix}@example.com",
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
                "email": f"priya.{email_suffix}@example.com",
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


def _submitted_registration(player_last_name="TwoA", email_suffix="twoa"):
    profile = client.put("/api/cam/profile", json={"name": "JKC"})
    assert profile.status_code == 200, profile.text
    created = client.post(
        "/api/cam/registration/invites",
        json={
            "parent_first_name": "Ravi",
            "parent_last_name": "Kumar",
            "parent_phone": "404-555-0134",
            "parent_email": f"slice2a.{email_suffix}@example.com",
        },
    )
    assert created.status_code == 201, created.text
    token = created.json()["registration_url"].rstrip("/").split("/")[-1]
    assert client.get(f"/api/public/registration/{token}").status_code == 200
    submitted = client.post(
        f"/api/public/registration/{token}/submit",
        json=_registration_payload(player_last_name, email_suffix),
    )
    assert submitted.status_code == 200, submitted.text
    return int(submitted.json()["application_id"])


def test_slice2a_approve_creates_secure_enrollment_and_tracks_status():
    application_id = _submitted_registration("TwoA", "twoa")

    approved = client.post(f"/api/cam/enrollments/from-registration/{application_id}", json={})
    assert approved.status_code == 200, approved.text
    enrollment = approved.json()
    assert enrollment["status"] == "created"
    assert enrollment["academy_name"] == "JKC"
    assert enrollment["player_name"] == "Slice TwoA"
    assert "/enroll/" in enrollment["enrollment_url"]

    enrollment_id = int(enrollment["id"])
    enrollment_token = enrollment["enrollment_url"].rstrip("/").split("/")[-1]

    marked_sent = client.post(
        f"/api/cam/enrollments/{enrollment_id}/sent",
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
    assert [step["label"] for step in body["steps"]] == [
        "Enrollment Summary",
        "Agreements & Documents",
        "Fees & Payment",
        "Complete",
    ]

    started = client.post(f"/api/public/enrollment/{enrollment_token}/start", json={})
    assert started.status_code == 200, started.text
    assert started.json() == {"status": "in_progress", "next_step": "agreements"}

    admin = client.get(f"/api/cam/enrollments/by-application/{application_id}")
    assert admin.status_code == 200, admin.text
    assert admin.json()["status"] == "in_progress"


def test_slice2b_test_documents_require_view_and_electronic_acceptance():
    application_id = _submitted_registration("TwoB", "twob")
    approved = client.post(f"/api/cam/enrollments/from-registration/{application_id}", json={})
    assert approved.status_code == 200, approved.text
    enrollment_token = approved.json()["enrollment_url"].rstrip("/").split("/")[-1]

    assert client.get(f"/api/public/enrollment/{enrollment_token}").status_code == 200
    started = client.post(f"/api/public/enrollment/{enrollment_token}/start", json={})
    assert started.status_code == 200, started.text

    documents_response = client.get(f"/api/public/enrollment/{enrollment_token}/documents")
    assert documents_response.status_code == 200, documents_response.text
    documents = documents_response.json()["documents"]
    assert len(documents) == 2
    assert all(item["required"] for item in documents)
    assert all(item["test_only"] for item in documents)
    assert all(item["available"] for item in documents)
    assert all(not item["accepted"] for item in documents)

    first, second = documents
    viewed_first = client.get(first["view_url"])
    assert viewed_first.status_code == 200, viewed_first.text
    assert viewed_first.headers["content-type"].startswith("application/pdf")

    missing_view = client.post(
        f"/api/public/enrollment/{enrollment_token}/agreements/accept",
        json={
            "document_ids": [first["id"], second["id"]],
            "signer_name": "Ravi Kumar",
            "electronic_signature_consent": True,
        },
    )
    assert missing_view.status_code == 422, missing_view.text
    assert "Open and review each required PDF" in missing_view.text

    viewed_second = client.get(second["view_url"])
    assert viewed_second.status_code == 200, viewed_second.text

    short_name = client.post(
        f"/api/public/enrollment/{enrollment_token}/agreements/accept",
        json={
            "document_ids": [first["id"], second["id"]],
            "signer_name": "Ravi",
            "electronic_signature_consent": True,
        },
    )
    assert short_name.status_code == 422, short_name.text

    no_consent = client.post(
        f"/api/public/enrollment/{enrollment_token}/agreements/accept",
        json={
            "document_ids": [first["id"], second["id"]],
            "signer_name": "Ravi Kumar",
            "electronic_signature_consent": False,
        },
    )
    assert no_consent.status_code == 422, no_consent.text

    accepted = client.post(
        f"/api/public/enrollment/{enrollment_token}/agreements/accept",
        json={
            "document_ids": [first["id"], second["id"]],
            "signer_name": "Ravi Kumar",
            "electronic_signature_consent": True,
        },
        headers={"user-agent": "CAM-Slice2B-Test"},
    )
    assert accepted.status_code == 200, accepted.text
    accepted_body = accepted.json()
    assert accepted_body["status"] == "documents_accepted"
    assert accepted_body["next_step"] == "payment"
    assert accepted_body["accepted_documents"] == 2
    assert accepted_body["signer_name"] == "Ravi Kumar"

    refreshed = client.get(f"/api/public/enrollment/{enrollment_token}")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["enrollment"]["status"] == "documents_accepted"
    assert [step["status"] for step in refreshed.json()["steps"]] == ["done", "done", "current", "later"]

    documents_after = client.get(f"/api/public/enrollment/{enrollment_token}/documents")
    assert documents_after.status_code == 200, documents_after.text
    assert all(item["viewed"] for item in documents_after.json()["documents"])
    assert all(item["accepted"] for item in documents_after.json()["documents"])
    assert all(item["signer_name"] == "Ravi Kumar" for item in documents_after.json()["documents"])


def test_slice2a_admin_ui_removes_request_information_and_uses_enrollment_action():
    js = (REPO_ROOT / "app" / "static" / "academy_enrollment_slice2a_v1.js").read_text(encoding="utf-8")
    html = (REPO_ROOT / "app" / "static" / "academy_enrollment_public_v1.html").read_text(encoding="utf-8")
    public_js = (REPO_ROOT / "app" / "static" / "academy_enrollment_public_v1.js").read_text(encoding="utf-8")

    assert "Approve & Send Enrollment Link" in js
    assert "[data-review-action=\"needs_information\"]" in js
    assert "/api/cam/enrollments/from-registration/" in js
    assert "navigator.clipboard.writeText(enrollment.enrollment_url)" in js
    assert "Start Enrollment" in html
    assert "Agreements &amp; Documents" in html
    assert "Continue to Agreements &amp; Documents" in html
    assert "TEST SAMPLES ONLY" in html
    assert "Agree &amp; Continue" in html
    assert "/documents" in public_js
    assert "/agreements/accept" in public_js
