from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .academy_registration_api import _require_admin
from .database import connection, fetch_all, fetch_one
from .payment_providers import (
    PaymentProviderError,
    SUPPORTED_PAYMENT_PROVIDERS,
    get_payment_provider,
    payment_provider_catalog,
)

router = APIRouter(prefix="/api/academy/payment-providers", tags=["academy-payment-providers"])


class ProviderSelectionPayload(BaseModel):
    provider: Literal["stripe", "square"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_payment_provider_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            provider TEXT NOT NULL,
            environment TEXT NOT NULL DEFAULT 'sandbox',
            provider_merchant_id TEXT,
            provider_location_id TEXT,
            status TEXT NOT NULL DEFAULT 'not_configured',
            credential_source TEXT NOT NULL DEFAULT 'environment',
            last_tested_at TEXT,
            last_test_status TEXT,
            selected INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE(academy_id, provider),
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_payment_provider_connections_academy
            ON academy_payment_provider_connections(academy_id,selected,provider);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy_id(user: dict) -> int | None:
    user_academy_id = int(user.get("academy_id") or 0)
    if user_academy_id:
        return user_academy_id
    row = fetch_one("SELECT id FROM academies ORDER BY id LIMIT 1")
    return int(row["id"]) if row else None


def _connection(academy_id: int | None, provider: str) -> dict | None:
    if academy_id is None:
        return None
    return fetch_one(
        "SELECT * FROM academy_payment_provider_connections WHERE academy_id=? AND provider=?",
        (academy_id, provider),
    )


def _provider_response(provider_name: str, academy_id: int | None) -> dict:
    descriptor = get_payment_provider(provider_name).descriptor().as_dict()
    existing = _connection(academy_id, provider_name)
    descriptor["connection"] = existing
    descriptor["selected"] = bool(existing and existing.get("selected"))
    return descriptor


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


_ensure_tables()


@router.get("")
def provider_catalog(user: dict = Depends(_require_admin)):
    academy_id = _academy_id(user)
    catalog = payment_provider_catalog()
    for item in catalog:
        provider_name = str(item["provider"])
        existing = _connection(academy_id, provider_name)
        item["connection"] = existing
        item["selected"] = bool(existing and existing.get("selected"))
    return {
        "providers": catalog,
        "supported": list(SUPPORTED_PAYMENT_PROVIDERS),
        "architecture": "provider_neutral",
        "secrets_stored_in_cam_database": False,
    }


@router.get("/{provider_name}")
def provider_details(provider_name: str, user: dict = Depends(_require_admin)):
    provider_name = provider_name.strip().lower()
    if provider_name not in SUPPORTED_PAYMENT_PROVIDERS:
        raise HTTPException(404, "Unsupported payment provider")
    return _provider_response(provider_name, _academy_id(user))


@router.post("/{provider_name}/test-connection")
def test_provider_connection(provider_name: str, user: dict = Depends(_require_admin)):
    provider_name = provider_name.strip().lower()
    if provider_name not in SUPPORTED_PAYMENT_PROVIDERS:
        raise HTTPException(404, "Unsupported payment provider")
    academy_id = _academy_id(user)
    if academy_id is None:
        raise HTTPException(409, "Academy profile must exist before configuring payments")

    provider = get_payment_provider(provider_name)
    descriptor = provider.descriptor()
    now = _now_iso()
    try:
        result = provider.test_connection()
        status_value = "connected"
        test_status = "success"
    except PaymentProviderError as exc:
        status_value = "not_configured" if exc.code == "not_configured" else "error"
        test_status = str(exc.code or "error")
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO academy_payment_provider_connections(
                    academy_id,provider,environment,status,credential_source,last_tested_at,last_test_status,selected
                ) VALUES(?,?,?,?,?,?,?,0)
                ON CONFLICT(academy_id,provider) DO UPDATE SET
                    environment=excluded.environment,status=excluded.status,last_tested_at=excluded.last_tested_at,
                    last_test_status=excluded.last_test_status,updated_at=CURRENT_TIMESTAMP
                """,
                (
                    academy_id,
                    provider_name,
                    descriptor.environment,
                    status_value,
                    "environment",
                    now,
                    test_status,
                ),
            )
        raise _translate_provider_error(exc)

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO academy_payment_provider_connections(
                academy_id,provider,environment,provider_merchant_id,provider_location_id,status,
                credential_source,last_tested_at,last_test_status,selected
            ) VALUES(?,?,?,?,?,'connected','environment',?,'success',0)
            ON CONFLICT(academy_id,provider) DO UPDATE SET
                environment=excluded.environment,provider_merchant_id=excluded.provider_merchant_id,
                provider_location_id=excluded.provider_location_id,status='connected',credential_source='environment',
                last_tested_at=excluded.last_tested_at,last_test_status='success',updated_at=CURRENT_TIMESTAMP
            """,
            (
                academy_id,
                provider_name,
                descriptor.environment,
                result.get("provider_merchant_id"),
                result.get("provider_location_id"),
                now,
            ),
        )
    return {**result, "connection": _connection(academy_id, provider_name)}


@router.post("/select")
def select_provider(payload: ProviderSelectionPayload, user: dict = Depends(_require_admin)):
    academy_id = _academy_id(user)
    if academy_id is None:
        raise HTTPException(409, "Academy profile must exist before configuring payments")
    selected = _connection(academy_id, payload.provider)
    if not selected or str(selected.get("status")) != "connected":
        raise HTTPException(409, "Test and connect this provider before selecting it")
    with connection() as conn:
        conn.execute(
            "UPDATE academy_payment_provider_connections SET selected=0,updated_at=CURRENT_TIMESTAMP WHERE academy_id=?",
            (academy_id,),
        )
        conn.execute(
            "UPDATE academy_payment_provider_connections SET selected=1,updated_at=CURRENT_TIMESTAMP WHERE academy_id=? AND provider=?",
            (academy_id, payload.provider),
        )
    return {
        "selected_provider": payload.provider,
        "connection": _connection(academy_id, payload.provider),
    }


@router.get("/connection/selected")
def selected_provider(user: dict = Depends(_require_admin)):
    academy_id = _academy_id(user)
    if academy_id is None:
        return {"selected_provider": None, "connection": None}
    row = fetch_one(
        "SELECT * FROM academy_payment_provider_connections WHERE academy_id=? AND selected=1 ORDER BY id LIMIT 1",
        (academy_id,),
    )
    return {"selected_provider": row.get("provider") if row else None, "connection": row}
