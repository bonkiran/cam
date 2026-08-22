import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="crickanalysis-enrollment-payment-test-")
os.environ["CAM_TEMP_ADMIN_MODE"] = "1"
os.environ["CAM_ADDRESS_VALIDATION_MODE"] = "stub"
os.environ["CAM_ENROLLMENT_MONTHLY_FEE_CENTS"] = "20000"
os.environ["CAM_ENROLLMENT_FIRST_CHARGE_DATE"] = "2026-09-01"

from fastapi.testclient import TestClient

# Import run first so app.main creates the core schema (academies, players, etc.)
# before enrollment/payment modules create tables with foreign keys to it.
from run import app
from app import cam_enrollment_payment_api as enrollment_payment_api
from app.database import connection, fetch_one
from app.payment_providers import ProviderDescriptor

client = TestClient(app)


class FakeStripeProvider:
    provider = "stripe"
    display_name = "Stripe"

    def descriptor(self):
        return ProviderDescriptor(
            provider="stripe",
            display_name="Stripe",
            configured=True,
            environment="sandbox",
            capabilities=("sandbox", "save_payment_method_without_charge", "off_session_charge"),
            client_config={"integration_mode": "stripe_elements_setup_intent", "publishable_key": "pk_test_cam"},
            configuration_notes=(),
        )

    def create_customer(self, **kwargs):
        assert kwargs["cam_parent_reference"].startswith("cam-enrollment-")
        return {"provider": "stripe", "customer_id": "cus_cam_test"}

    def begin_payment_method_setup(self, **kwargs):
        assert kwargs["customer_id"] == "cus_cam_test"
        return {
            "provider": "stripe",
            "mode": "stripe_elements_setup_intent",
            "customer_id": "cus_cam_test",
            "setup_session_id": "seti_cam_test",
            "client_secret": "seti_cam_test_secret_123",
            "client_config": {"publishable_key": "pk_test_cam"},
        }

    def complete_payment_method_setup(self, **kwargs):
        assert kwargs["setup_payload"]["setup_session_id"] == "seti_cam_test"
        return {
            "provider": "stripe",
            "customer_id": "cus_cam_test",
            "payment_method_id": "pm_cam_test",
            "card_brand": "visa",
            "card_last4": "4242",
            "card_exp_month": 12,
            "card_exp_year": 2030,
            "setup_status": "succeeded",
        }


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
        "parent_email": "ravi.slice2c@example.com",
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
                "email": "priya.slice2c@example.com",
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


def _create_documents_accepted_enrollment():
    profile = client.put(
        "/api/cam/profile",
        json={"name": "Slice 2C Test Academy", "city": "Johns Creek", "state": "GA", "postal_code": "30024"},
    )
    assert profile.status_code == 200, profile.text

    invite = client.post(
        "/api/cam/registration/invites",
        json={
            "parent_first_name": "Ravi",
            "parent_last_name": "Kumar",
            "parent_phone": "404-555-1212",
            "parent_email": "ravi.slice2c@example.com",
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

    enrollment = client.post(f"/api/cam/enrollments/from-registration/{application_id}")
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
    assert accepted.json()["status"] == "documents_accepted"
    return enrollment_token, enrollment_id


def test_slice2c_stripe_save_now_charge_later_flow(monkeypatch):
    enrollment_token, enrollment_id = _create_documents_accepted_enrollment()
    academy_id = int(fetch_one("SELECT id FROM academies ORDER BY id LIMIT 1")["id"])

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO academy_payment_provider_connections(
                academy_id,provider,environment,provider_merchant_id,status,credential_source,
                last_tested_at,last_test_status,selected
            ) VALUES(?,'stripe','sandbox','acct_cam_test','connected','environment',CURRENT_TIMESTAMP,'success',1)
            ON CONFLICT(academy_id,provider) DO UPDATE SET status='connected',selected=1
            """,
            (academy_id,),
        )

    fake = FakeStripeProvider()
    monkeypatch.setattr(enrollment_payment_api, "get_payment_provider", lambda provider_name: fake)

    summary = client.get(f"/api/public/enrollment/{enrollment_token}/payment")
    assert summary.status_code == 200, summary.text
    summary_json = summary.json()
    assert summary_json["provider"]["name"] == "stripe"
    assert summary_json["provider"]["environment"] == "sandbox"
    assert summary_json["plan"]["monthly_amount_cents"] == 20000
    assert summary_json["plan"]["due_today_cents"] == 0
    assert summary_json["plan"]["billing_start_date"] == "2026-09-01"
    assert summary_json["raw_card_data_stored_by_cam"] is False

    missing_consent = client.post(
        f"/api/public/enrollment/{enrollment_token}/payment/setup",
        json={"recurring_consent": False, "use_parent_address": True},
    )
    assert missing_consent.status_code == 422

    setup = client.post(
        f"/api/public/enrollment/{enrollment_token}/payment/setup",
        json={"recurring_consent": True, "use_parent_address": True},
    )
    assert setup.status_code == 200, setup.text
    setup_json = setup.json()
    assert setup_json["provider"] == "stripe"
    assert setup_json["setup_session_id"] == "seti_cam_test"
    assert setup_json["client_secret"] == "seti_cam_test_secret_123"
    assert setup_json["plan"]["due_today_cents"] == 0

    authorization = fetch_one(
        "SELECT * FROM academy_enrollment_payment_authorizations WHERE enrollment_id=?",
        (enrollment_id,),
    )
    assert authorization is not None
    assert authorization["provider_customer_id"] == "cus_cam_test"
    assert authorization["provider_payment_method_id"] is None
    assert authorization["setup_status"] == "pending"
    assert authorization["billing_start_date"] == "2026-09-01"
    assert authorization["billing_address_source"] == "parent_registration_address"
    assert int(authorization["billing_address_verified"]) == 1
    assert authorization["recurring_consent_version"] == "cam-recurring-tuition-v1"

    completed = client.post(
        f"/api/public/enrollment/{enrollment_token}/payment/complete",
        json={"setup_payload": {"setup_session_id": "seti_cam_test"}},
    )
    assert completed.status_code == 200, completed.text
    completed_json = completed.json()
    assert completed_json["payment_setup_complete"] is True
    assert completed_json["next_step"] == "complete"
    assert completed_json["authorization"]["setup_status"] == "succeeded"
    assert completed_json["authorization"]["card_brand"] == "visa"
    assert completed_json["authorization"]["card_last4"] == "4242"

    stored = fetch_one(
        "SELECT * FROM academy_enrollment_payment_authorizations WHERE enrollment_id=?",
        (enrollment_id,),
    )
    assert stored["provider_payment_method_id"] == "pm_cam_test"
    assert stored["card_last4"] == "4242"
    assert stored["setup_status"] == "succeeded"


def test_slice2c_parent_ui_uses_provider_secure_element_not_raw_card_fields():
    html = (REPO_ROOT / "app" / "static" / "academy_enrollment_public_v1.html").read_text(encoding="utf-8")
    js = (REPO_ROOT / "app" / "static" / "academy_enrollment_public_v1.js").read_text(encoding="utf-8")

    assert "Fees &amp; Payment" in html
    assert "id=\"paymentElement\"" in html
    assert "id=\"recurringPaymentConsent\"" in html
    assert "id=\"useParentBillingAddress\"" in html
    assert "https://js.stripe.com/v3/" in js
    assert "stripe.elements({clientSecret:data.client_secret})" in js
    assert "stripe.confirmSetup" in js
    assert "/payment/setup" in js
    assert "/payment/complete" in js

    lowered = html.lower()
    assert 'name="card_number"' not in lowered
    assert 'id="cardnumber"' not in lowered
    assert 'id="cvc"' not in lowered
