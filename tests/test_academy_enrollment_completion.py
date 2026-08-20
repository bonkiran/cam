import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-enrollment-completion-test-")
os.environ["CAM_TEMP_ADMIN_MODE"] = "1"
os.environ["CAM_ADDRESS_VALIDATION_MODE"] = "stub"

from fastapi.testclient import TestClient

from app.database import connection, fetch_one
from run import app

client = TestClient(app)


def _registration_payload():
    return {
        "player_first_name": "Hari",
        "player_last_name": "Kumar",
        "player_date_of_birth": "2012-04-15",
        "player_gender": "Male",
        "cricket_role": "Batter",
        "batting_order": "TO",
        "bowling_type": "N/A",
        "wicketkeeping": False,
        "parent_first_name": "Ravi",
        "parent_last_name": "Kumar",
        "parent_relationship": "Father",
        "parent_email": "ravi.slice2d@example.com",
        "parent_phone": "404-555-1212",
        "parent_address_line1": "101 Cricket Lane",
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
                "phone": "404-555-2222",
                "email": "priya.slice2d@example.com",
            }
        ],
        "guardian_same_as_parent": True,
        "guardian": None,
        "injuries": None,
        "surgeries": None,
        "medical_considerations": None,
        "allergies": "None",
        "physical_restrictions": None,
        "additional_notes": None,
        "consent_confirmed": True,
    }


def _create_payment_ready_enrollment():
    profile = client.put(
        "/api/academy/profile",
        json={"name": "Slice 2D Test Academy", "city": "Johns Creek", "state": "GA", "postal_code": "30024"},
    )
    assert profile.status_code == 200, profile.text

    invite = client.post(
        "/api/academy/registration/invites",
        json={
            "parent_first_name": "Ravi",
            "parent_last_name": "Kumar",
            "parent_phone": "404-555-1212",
            "parent_email": "ravi.slice2d@example.com",
        },
    )
    assert invite.status_code == 201, invite.text
    registration_token = invite.json()["registration_url"].rstrip("/").split("/")[-1]
    opened = client.get(f"/api/public/registration/{registration_token}")
    assert opened.status_code == 200, opened.text
    application_id = int(opened.json()["application"]["id"])

    submitted = client.post(
        f"/api/public/registration/{registration_token}/submit",
        json=_registration_payload(),
    )
    assert submitted.status_code == 200, submitted.text

    enrollment = client.post(f"/api/academy/enrollments/from-registration/{application_id}")
    assert enrollment.status_code == 200, enrollment.text
    enrollment_json = enrollment.json()
    enrollment_token = enrollment_json["enrollment_url"].rstrip("/").split("/")[-1]
    enrollment_id = int(enrollment_json["id"])

    started = client.post(f"/api/public/enrollment/{enrollment_token}/start", json={})
    assert started.status_code == 200, started.text
    docs = client.get(f"/api/public/enrollment/{enrollment_token}/documents")
    assert docs.status_code == 200, docs.text
    required = [doc for doc in docs.json()["documents"] if doc["required"]]
    assert len(required) == 2
    for doc in required:
        viewed = client.get(f"/api/public/enrollment/{enrollment_token}/documents/{doc['id']}/view")
        assert viewed.status_code == 200, viewed.text

    accepted = client.post(
        f"/api/public/enrollment/{enrollment_token}/agreements/accept",
        json={
            "document_ids": [doc["id"] for doc in required],
            "signer_name": "Ravi Kumar",
            "electronic_signature_consent": True,
        },
    )
    assert accepted.status_code == 200, accepted.text

    enrollment_row = fetch_one("SELECT * FROM academy_enrollment_invites WHERE id=?", (enrollment_id,))
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO academy_enrollment_payment_authorizations(
                enrollment_id,academy_id,provider,provider_customer_id,provider_payment_method_id,
                provider_setup_session_id,fee_plan_name,monthly_amount_cents,currency,billing_frequency,
                billing_start_date,due_today_cents,recurring_consent_version,recurring_consent_text,
                recurring_consent_sha256,recurring_consent_accepted_at,billing_address_source,
                billing_address_verified,card_brand,card_last4,card_exp_month,card_exp_year,
                setup_status,payment_method_added_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """,
            (
                enrollment_id,
                enrollment_row.get("academy_id"),
                "stripe",
                "cus_slice2d",
                "pm_slice2d",
                "seti_slice2d",
                "Academy Monthly Tuition",
                20000,
                "USD",
                "monthly",
                "2026-09-01",
                0,
                "cam-recurring-tuition-v1",
                "Authorize monthly tuition.",
                "a" * 64,
                "2026-08-20T21:54:00+00:00",
                "parent_registration_address",
                1,
                "visa",
                "4242",
                12,
                2030,
                "succeeded",
            ),
        )
    return enrollment_token, enrollment_id


def test_slice2d_completion_finalizes_enrollment_and_builds_secure_package():
    enrollment_token, enrollment_id = _create_payment_ready_enrollment()

    ready = client.get(f"/api/public/enrollment/{enrollment_token}/completion")
    assert ready.status_code == 200, ready.text
    ready_json = ready.json()
    assert ready_json["status"] == "payment_method_added"
    assert ready_json["completion_ready"] is True
    assert ready_json["placement_ready"] is False
    assert ready_json["payment"]["card_last4"] == "4242"
    assert len(ready_json["documents"]) == 2

    completed = client.post(f"/api/public/enrollment/{enrollment_token}/complete", json={})
    assert completed.status_code == 200, completed.text
    completed_json = completed.json()
    assert completed_json["status"] == "completed"
    assert completed_json["placement_ready"] is True
    assert completed_json["next_operational_step"] == "program_batch_assignment"
    assert completed_json["package_url"].endswith("/completion/package")

    enrollment = client.get(f"/api/public/enrollment/{enrollment_token}")
    assert enrollment.status_code == 200, enrollment.text
    assert enrollment.json()["enrollment"]["status"] == "completed"
    assert all(step["status"] == "done" for step in enrollment.json()["steps"])

    stored = fetch_one("SELECT * FROM academy_enrollment_completions WHERE enrollment_id=?", (enrollment_id,))
    assert stored is not None
    assert stored["completion_version"] == "cam-enrollment-complete-v1"
    assert stored["confirmation_delivery_status"] == "secure_portal_ready"

    package = client.get(f"/api/public/enrollment/{enrollment_token}/completion/package")
    assert package.status_code == 200, package.text
    assert package.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        names = archive.namelist()
        assert "CAM Enrollment Confirmation.txt" in names
        assert "CAM Acceptance Summary.txt" in names
        assert len([name for name in names if name.lower().endswith(".pdf")]) == 2
        confirmation = archive.read("CAM Enrollment Confirmation.txt").decode("utf-8")
        assert "Hari Kumar" in confirmation
        assert "Sep" not in confirmation or "2026-09-01" in confirmation
        assert "Program / Batch Assignment" in confirmation
        acceptance = archive.read("CAM Acceptance Summary.txt").decode("utf-8")
        assert "Ravi Kumar" in acceptance
        assert "4242" in acceptance

    completed_again = client.post(f"/api/public/enrollment/{enrollment_token}/complete", json={})
    assert completed_again.status_code == 200, completed_again.text
    assert completed_again.json()["completed_at"] == completed_json["completed_at"]

    admin_ready = client.get("/api/academy/enrollments/completed")
    assert admin_ready.status_code == 200, admin_ready.text
    row = next(item for item in admin_ready.json() if int(item["enrollment_id"]) == enrollment_id)
    assert row["placement_ready"] is True
    assert row["next_operational_step"] == "program_batch_assignment"


def test_slice2d_parent_ui_exposes_explicit_completion_and_secure_package():
    html = (REPO_ROOT / "app" / "static" / "academy_enrollment_public_v1.html").read_text(encoding="utf-8")
    js = (REPO_ROOT / "app" / "static" / "academy_enrollment_complete_v1.js").read_text(encoding="utf-8")

    assert "academy_enrollment_complete_v1.js" in html
    assert "Complete Enrollment" in js
    assert "/complete`" in js
    assert "/completion/package" in js
    assert "Program / Batch Assignment" in js
    assert "No Program or Batch is assigned automatically" in js
