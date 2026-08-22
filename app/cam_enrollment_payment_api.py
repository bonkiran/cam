from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .cam_enrollment_api import _enrollment_for_token
from .cam_registration_address_validation import AddressVerificationUnavailable, verify_us_address
from .cam_registration_validation_policy import _normalize_us_state, _valid_us_zip
from .database import connection, fetch_one
from .payment_providers import PaymentProviderError, get_payment_provider

router = APIRouter(tags=["cam-enrollment-payment"])

RECURRING_CONSENT_VERSION = "cam-recurring-tuition-v1"


class BillingAddressPayload(BaseModel):
    address_line1: str = Field(min_length=2, max_length=240)
    address_line2: str | None = Field(default=None, max_length=240)
    city: str = Field(min_length=2, max_length=120)
    state: str = Field(min_length=2, max_length=120)
    postal_code: str = Field(min_length=5, max_length=30)
    country: str = Field(default="United States", min_length=2, max_length=120)


class PaymentSetupStartPayload(BaseModel):
    recurring_consent: bool
    use_parent_address: bool = True
    billing_address: BillingAddressPayload | None = None


class PaymentSetupCompletePayload(BaseModel):
    setup_payload: dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_enrollment_payment_authorizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id BIGINT NOT NULL UNIQUE,
            academy_id BIGINT,
            provider TEXT NOT NULL,
            provider_customer_id TEXT,
            provider_payment_method_id TEXT,
            provider_setup_session_id TEXT,
            fee_plan_name TEXT NOT NULL,
            monthly_amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            billing_frequency TEXT NOT NULL DEFAULT 'monthly',
            billing_start_date TEXT NOT NULL,
            due_today_cents INTEGER NOT NULL DEFAULT 0,
            recurring_consent_version TEXT NOT NULL,
            recurring_consent_text TEXT NOT NULL,
            recurring_consent_sha256 TEXT NOT NULL,
            recurring_consent_accepted_at TEXT,
            consent_ip_address TEXT,
            consent_user_agent TEXT,
            billing_address_line1 TEXT,
            billing_address_line2 TEXT,
            billing_city TEXT,
            billing_state TEXT,
            billing_postal_code TEXT,
            billing_country TEXT,
            billing_address_source TEXT,
            billing_address_verified INTEGER NOT NULL DEFAULT 0,
            billing_address_verification_source TEXT,
            card_brand TEXT,
            card_last4 TEXT,
            card_exp_month INTEGER,
            card_exp_year INTEGER,
            setup_status TEXT NOT NULL DEFAULT 'not_started',
            payment_method_added_at TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(enrollment_id) REFERENCES academy_enrollment_invites(id) ON DELETE CASCADE,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enrollment_payment_authorizations_provider
            ON academy_enrollment_payment_authorizations(provider,setup_status);
    """
    with connection() as conn:
        conn.executescript(schema)


def _billing_plan() -> dict[str, Any]:
    amount_cents = int(os.environ.get("CAM_ENROLLMENT_MONTHLY_FEE_CENTS", "20000"))
    first_charge = os.environ.get("CAM_ENROLLMENT_FIRST_CHARGE_DATE", "2026-09-01").strip()
    try:
        parsed = date.fromisoformat(first_charge)
    except ValueError as exc:
        raise HTTPException(500, "CAM enrollment first-charge date is not configured correctly") from exc
    return {
        "fee_plan_name": os.environ.get("CAM_ENROLLMENT_FEE_PLAN_NAME", "Academy Monthly Tuition").strip() or "Academy Monthly Tuition",
        "monthly_amount_cents": amount_cents,
        "currency": os.environ.get("CAM_ENROLLMENT_CURRENCY", "USD").strip().upper() or "USD",
        "billing_frequency": "monthly",
        "billing_start_date": parsed.isoformat(),
        "billing_day": parsed.day,
        "due_today_cents": 0,
        "source": "slice2c_configurable_enrollment_plan",
    }


def _consent_text(enrollment: dict, plan: dict[str, Any]) -> str:
    amount = plan["monthly_amount_cents"] / 100
    return (
        f"I authorize {enrollment.get('academy_name') or 'the academy'} to charge my saved payment method "
        f"${amount:,.2f} {plan['currency']} monthly for {enrollment.get('player_name') or 'the enrolled player'}, "
        f"beginning {plan['billing_start_date']}. Variable tournament, match, camp, travel and equipment charges "
        "are not included in this recurring authorization and require separate parent approval."
    )


def _application_address(enrollment: dict) -> dict[str, str | None]:
    row = fetch_one(
        """
        SELECT parent_address_line1,parent_address_line2,parent_city,parent_state,parent_postal_code,parent_country
        FROM academy_registration_applications
        WHERE id=?
        """,
        (int(enrollment["application_id"]),),
    ) or {}
    return {
        "address_line1": row.get("parent_address_line1"),
        "address_line2": row.get("parent_address_line2"),
        "city": row.get("parent_city"),
        "state": row.get("parent_state"),
        "postal_code": row.get("parent_postal_code"),
        "country": row.get("parent_country") or "United States",
    }


def _selected_provider(enrollment: dict) -> tuple[str, dict, Any]:
    academy_id = int(enrollment.get("academy_id") or 0) or None
    if academy_id is None:
        raise HTTPException(409, "Academy payment provider is not configured")
    row = fetch_one(
        """
        SELECT * FROM academy_payment_provider_connections
        WHERE academy_id=? AND selected=1 AND status='connected'
        ORDER BY id LIMIT 1
        """,
        (academy_id,),
    )
    if not row:
        raise HTTPException(409, "Select and connect a payment provider before collecting parent payment details")
    provider_name = str(row.get("provider") or "").strip().lower()
    provider = get_payment_provider(provider_name)
    return provider_name, row, provider


def _authorization(enrollment_id: int) -> dict | None:
    return fetch_one(
        "SELECT * FROM academy_enrollment_payment_authorizations WHERE enrollment_id=?",
        (enrollment_id,),
    )


def _normalized_address(payload: PaymentSetupStartPayload, enrollment: dict) -> tuple[dict[str, str | None], str, dict]:
    if payload.use_parent_address:
        address = _application_address(enrollment)
        source = "parent_registration_address"
    else:
        if payload.billing_address is None:
            raise HTTPException(422, "Enter the billing address or use the parent registration address")
        address = payload.billing_address.model_dump()
        source = "alternate_billing_address"

    required = [address.get("address_line1"), address.get("city"), address.get("state"), address.get("postal_code")]
    if not all(str(value or "").strip() for value in required):
        raise HTTPException(422, "A complete billing street, city, state and ZIP are required")

    state_code = _normalize_us_state(str(address.get("state") or ""))
    if not state_code:
        raise HTTPException(422, "Billing state must be a valid US state name or 2-letter abbreviation")
    postal_code = str(address.get("postal_code") or "").strip()
    if not _valid_us_zip(postal_code):
        raise HTTPException(422, "Billing ZIP must be a valid 5-digit US ZIP code")

    country = str(address.get("country") or "United States").strip()
    if country.lower() not in {"united states", "united states of america", "usa", "us", "u.s.", "u.s.a."}:
        raise HTTPException(422, "CAM Slice 2C billing address must be in the United States")

    try:
        verification = verify_us_address(
            street=str(address["address_line1"]),
            city=str(address["city"]),
            state=state_code,
            zip_code=postal_code,
        )
    except AddressVerificationUnavailable as exc:
        raise HTTPException(503, "Billing address verification is temporarily unavailable. Please try again shortly.") from exc
    if not bool(verification.get("verified")):
        raise HTTPException(422, "Billing street, city, state and ZIP could not be verified as one valid US address")

    normalized = {
        "address_line1": str(address.get("address_line1") or "").strip(),
        "address_line2": str(address.get("address_line2") or "").strip() or None,
        "city": str(address.get("city") or "").strip(),
        "state": state_code,
        "postal_code": postal_code,
        "country": "United States",
    }
    return normalized, source, verification


def _translate_provider_error(exc: PaymentProviderError) -> HTTPException:
    return HTTPException(
        exc.http_status,
        {
            "provider": exc.provider,
            "code": exc.code,
            "message": str(exc),
            "retryable": exc.retryable,
        },
    )


def _public_response(enrollment: dict) -> dict[str, Any]:
    provider_name, connection_row, provider = _selected_provider(enrollment)
    plan = _billing_plan()
    authorization = _authorization(int(enrollment["id"]))
    descriptor = provider.descriptor().as_dict()
    return {
        "status": str(enrollment.get("status") or ""),
        "plan": plan,
        "provider": {
            "name": provider_name,
            "display_name": descriptor.get("display_name"),
            "environment": descriptor.get("environment"),
            "client_config": descriptor.get("client_config") or {},
            "connection_status": connection_row.get("status"),
        },
        "parent_address": _application_address(enrollment),
        "authorization": {
            "setup_status": authorization.get("setup_status"),
            "provider": authorization.get("provider"),
            "card_brand": authorization.get("card_brand"),
            "card_last4": authorization.get("card_last4"),
            "card_exp_month": authorization.get("card_exp_month"),
            "card_exp_year": authorization.get("card_exp_year"),
            "payment_method_added_at": authorization.get("payment_method_added_at"),
            "billing_start_date": authorization.get("billing_start_date"),
            "monthly_amount_cents": authorization.get("monthly_amount_cents"),
        } if authorization else None,
        "recurring_consent_version": RECURRING_CONSENT_VERSION,
        "recurring_consent_text": _consent_text(enrollment, plan),
        "raw_card_data_stored_by_cam": False,
    }


_ensure_tables()


@router.get("/api/public/enrollment/{token}/payment")
def public_enrollment_payment(token: str):
    enrollment = _enrollment_for_token(token)
    if str(enrollment.get("status") or "") not in {"documents_accepted", "completed"}:
        raise HTTPException(409, "Accept enrollment documents before setting up payment")
    return _public_response(enrollment)


@router.post("/api/public/enrollment/{token}/payment/setup")
def start_public_payment_setup(token: str, payload: PaymentSetupStartPayload, request: Request):
    enrollment = _enrollment_for_token(token)
    if str(enrollment.get("status") or "") != "documents_accepted":
        raise HTTPException(409, "Payment setup is available after enrollment documents are accepted")
    if not payload.recurring_consent:
        raise HTTPException(422, "Recurring monthly payment authorization is required")

    provider_name, _, provider = _selected_provider(enrollment)
    existing = _authorization(int(enrollment["id"]))
    if existing and str(existing.get("setup_status")) == "succeeded":
        return {"already_configured": True, **_public_response(enrollment)}

    address, address_source, verification = _normalized_address(payload, enrollment)
    plan = _billing_plan()
    consent_text = _consent_text(enrollment, plan)
    consent_sha = hashlib.sha256(consent_text.encode("utf-8")).hexdigest()
    parent_name = " ".join(
        part for part in [str(enrollment.get("parent_first_name") or "").strip(), str(enrollment.get("parent_last_name") or "").strip()] if part
    ) or "CAM Parent"
    parent_reference = f"cam-enrollment-{int(enrollment['id'])}-parent"

    try:
        if existing and str(existing.get("provider")) == provider_name and existing.get("provider_customer_id"):
            customer_id = str(existing["provider_customer_id"])
        else:
            customer = provider.create_customer(
                idempotency_key=f"cam-enrollment-{int(enrollment['id'])}-{provider_name}-customer-v1",
                name=parent_name,
                email=str(enrollment.get("parent_email") or "").strip() or None,
                cam_parent_reference=parent_reference,
            )
            customer_id = str(customer["customer_id"])

        setup = provider.begin_payment_method_setup(
            customer_id=customer_id,
            idempotency_key=f"cam-enrollment-{int(enrollment['id'])}-{provider_name}-setup-v1",
        )
    except PaymentProviderError as exc:
        raise _translate_provider_error(exc)

    now = _now_iso()
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    setup_session_id = str(setup.get("setup_session_id") or "") or None

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO academy_enrollment_payment_authorizations(
                enrollment_id,academy_id,provider,provider_customer_id,provider_setup_session_id,
                fee_plan_name,monthly_amount_cents,currency,billing_frequency,billing_start_date,due_today_cents,
                recurring_consent_version,recurring_consent_text,recurring_consent_sha256,recurring_consent_accepted_at,
                consent_ip_address,consent_user_agent,billing_address_line1,billing_address_line2,billing_city,billing_state,
                billing_postal_code,billing_country,billing_address_source,billing_address_verified,
                billing_address_verification_source,setup_status
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')
            ON CONFLICT(enrollment_id) DO UPDATE SET
                provider=excluded.provider,provider_customer_id=excluded.provider_customer_id,
                provider_setup_session_id=excluded.provider_setup_session_id,fee_plan_name=excluded.fee_plan_name,
                monthly_amount_cents=excluded.monthly_amount_cents,currency=excluded.currency,
                billing_frequency=excluded.billing_frequency,billing_start_date=excluded.billing_start_date,
                due_today_cents=excluded.due_today_cents,recurring_consent_version=excluded.recurring_consent_version,
                recurring_consent_text=excluded.recurring_consent_text,recurring_consent_sha256=excluded.recurring_consent_sha256,
                recurring_consent_accepted_at=excluded.recurring_consent_accepted_at,consent_ip_address=excluded.consent_ip_address,
                consent_user_agent=excluded.consent_user_agent,billing_address_line1=excluded.billing_address_line1,
                billing_address_line2=excluded.billing_address_line2,billing_city=excluded.billing_city,
                billing_state=excluded.billing_state,billing_postal_code=excluded.billing_postal_code,
                billing_country=excluded.billing_country,billing_address_source=excluded.billing_address_source,
                billing_address_verified=excluded.billing_address_verified,
                billing_address_verification_source=excluded.billing_address_verification_source,
                setup_status='pending',updated_at=CURRENT_TIMESTAMP
            """,
            (
                int(enrollment["id"]),
                int(enrollment.get("academy_id") or 0) or None,
                provider_name,
                customer_id,
                setup_session_id,
                plan["fee_plan_name"],
                int(plan["monthly_amount_cents"]),
                plan["currency"],
                plan["billing_frequency"],
                plan["billing_start_date"],
                int(plan["due_today_cents"]),
                RECURRING_CONSENT_VERSION,
                consent_text,
                consent_sha,
                now,
                ip_address,
                user_agent,
                address["address_line1"],
                address["address_line2"],
                address["city"],
                address["state"],
                address["postal_code"],
                address["country"],
                address_source,
                1,
                str(verification.get("source") or ""),
            ),
        )

    return {
        "provider": provider_name,
        "mode": setup.get("mode"),
        "customer_id": customer_id,
        "setup_session_id": setup_session_id,
        "client_secret": setup.get("client_secret"),
        "client_config": setup.get("client_config") or {},
        "plan": plan,
        "billing_address": address,
        "recurring_consent_version": RECURRING_CONSENT_VERSION,
        "setup_status": "pending",
    }


@router.post("/api/public/enrollment/{token}/payment/complete")
def complete_public_payment_setup(token: str, payload: PaymentSetupCompletePayload):
    enrollment = _enrollment_for_token(token)
    if str(enrollment.get("status") or "") != "documents_accepted":
        raise HTTPException(409, "Payment setup is available after enrollment documents are accepted")
    authorization = _authorization(int(enrollment["id"]))
    if not authorization:
        raise HTTPException(409, "Start payment setup before completing it")
    if str(authorization.get("setup_status")) == "succeeded":
        return _public_response(enrollment)

    provider_name, _, provider = _selected_provider(enrollment)
    if str(authorization.get("provider")) != provider_name:
        raise HTTPException(409, "The selected payment provider changed. Restart payment setup.")

    setup_payload = dict(payload.setup_payload or {})
    expected_session = str(authorization.get("provider_setup_session_id") or "")
    provided_session = str(setup_payload.get("setup_session_id") or "")
    if expected_session and expected_session != provided_session:
        raise HTTPException(409, "Payment setup session does not match this enrollment")

    try:
        result = provider.complete_payment_method_setup(
            customer_id=str(authorization["provider_customer_id"]),
            setup_payload=setup_payload,
            idempotency_key=f"cam-enrollment-{int(enrollment['id'])}-{provider_name}-complete-v1",
        )
    except PaymentProviderError as exc:
        raise _translate_provider_error(exc)

    now = _now_iso()
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_enrollment_payment_authorizations
            SET provider_payment_method_id=?,card_brand=?,card_last4=?,card_exp_month=?,card_exp_year=?,
                setup_status='succeeded',payment_method_added_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE enrollment_id=?
            """,
            (
                result.get("payment_method_id"),
                result.get("card_brand"),
                result.get("card_last4"),
                result.get("card_exp_month"),
                result.get("card_exp_year"),
                now,
                int(enrollment["id"]),
            ),
        )
        conn.execute(
            "UPDATE academy_enrollment_invites SET last_activity_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (now, int(enrollment["id"])),
        )

    response = _public_response(enrollment)
    response["payment_setup_complete"] = True
    response["next_step"] = "complete"
    return response
