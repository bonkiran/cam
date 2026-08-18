from __future__ import annotations

import os
import re
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .academy_authz import billing_account_ids_for_guardian, linked_player_ids_for_guardian, require_parent_billing_user
from .academy_payments_v2_api import PaymentAllocationPayload, PaymentPayload, payment_receipt, post_payment
from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy/parent", tags=["academy-parent-billing"])

PAYMENT_MODE = os.environ.get("CAM_PAYMENT_MODE", "disabled").strip().lower() or "disabled"

# CAM sandbox accepts only explicit test numbers. This prevents a real card from
# being accidentally entered into the local/test payment form.
SANDBOX_CARDS: dict[str, dict[str, str]] = {
    "4242424242424242": {"brand": "Visa", "behavior": "success", "label": "Successful payment"},
    "4000000000009995": {"brand": "Visa", "behavior": "insufficient_funds", "label": "Insufficient funds"},
    "4000000000000341": {"brand": "Visa", "behavior": "later_failure", "label": "Saved card fails on charge"},
    "4000002500003155": {"brand": "Visa", "behavior": "requires_setup_auth", "label": "Authentication required during setup"},
    "4000002760003184": {"brand": "Visa", "behavior": "requires_charge_auth", "label": "Authentication required for charge"},
}


class SandboxPaymentMethodPayload(BaseModel):
    card_number: str = Field(min_length=12, max_length=32)
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2026, le=2100)
    cvc: str = Field(min_length=3, max_length=4)
    make_default: bool = True


class ParentInvoicePaymentPayload(BaseModel):
    payment_method_id: int = Field(gt=0)
    amount_cents: int | None = Field(default=None, gt=0, le=100_000_000)


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_saved_payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id BIGINT NOT NULL,
            guardian_id BIGINT NOT NULL,
            provider TEXT NOT NULL,
            provider_payment_method_ref TEXT NOT NULL UNIQUE,
            brand TEXT NOT NULL,
            last4 TEXT NOT NULL,
            exp_month INTEGER NOT NULL,
            exp_year INTEGER NOT NULL,
            behavior TEXT NOT NULL DEFAULT 'success',
            is_default INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES academy_users(id) ON DELETE CASCADE,
            FOREIGN KEY(guardian_id) REFERENCES guardians(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_saved_payment_methods_user
          ON academy_saved_payment_methods(user_id,status);

        CREATE TABLE IF NOT EXISTS academy_billing_security_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id BIGINT,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id BIGINT,
            detail TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(actor_user_id) REFERENCES academy_users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_billing_security_audit_actor
          ON academy_billing_security_audit(actor_user_id,id DESC);
    """
    with connection() as conn:
        conn.executescript(schema)


def _audit(conn, user_id: int, action: str, target_type: str | None = None,
           target_id: int | None = None, detail: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO academy_billing_security_audit(actor_user_id,action,target_type,target_id,detail)
        VALUES(?,?,?,?,?)
        """,
        (user_id, action, target_type, target_id, detail),
    )


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _safe_method(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "provider": row["provider"],
        "brand": row["brand"],
        "last4": row["last4"],
        "exp_month": int(row["exp_month"]),
        "exp_year": int(row["exp_year"]),
        "is_default": bool(row["is_default"]),
        "status": row["status"],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _methods_for_user(user_id: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT * FROM academy_saved_payment_methods
        WHERE user_id=? AND status='active'
        ORDER BY is_default DESC,id DESC
        """,
        (user_id,),
    )
    return [_safe_method(row) for row in rows]


def _method_for_user(method_id: int, user_id: int) -> dict:
    row = fetch_one(
        "SELECT * FROM academy_saved_payment_methods WHERE id=? AND user_id=? AND status='active'",
        (method_id, user_id),
    )
    if not row:
        raise HTTPException(404, "Payment method not found")
    return row


def _parent_account_ids(user: dict) -> list[int]:
    guardian_id = int(user["guardian_id"])
    return billing_account_ids_for_guardian(guardian_id)


def _assert_parent_account(account_id: int, user: dict) -> None:
    if account_id not in set(_parent_account_ids(user)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This billing account is not linked to your parent account")


def _invoice_for_parent(invoice_id: int, user: dict) -> dict:
    row = fetch_one(
        """
        SELECT i.*,a.account_name
        FROM academy_invoices i
        JOIN academy_billing_accounts a ON a.id=i.account_id
        WHERE i.id=?
        """,
        (invoice_id,),
    )
    if not row:
        raise HTTPException(404, "Invoice not found")
    _assert_parent_account(int(row["account_id"]), user)
    row["balance_due_cents"] = max(
        0,
        int(row["total_cents"]) - int(row["amount_paid_cents"]) - int(row["credit_applied_cents"]),
    )
    return row


def _account_summary(account_id: int) -> dict:
    account = fetch_one(
        """
        SELECT a.*,g.first_name AS guardian_first_name,g.last_name AS guardian_last_name
        FROM academy_billing_accounts a
        LEFT JOIN guardians g ON g.id=a.primary_guardian_id
        WHERE a.id=?
        """,
        (account_id,),
    )
    if not account:
        raise HTTPException(404, "Billing account not found")
    account["players"] = fetch_all(
        """
        SELECT p.id,p.name,p.status
        FROM academy_billing_account_players bap
        JOIN players p ON p.id=bap.player_id
        WHERE bap.account_id=? AND bap.status='active'
        ORDER BY p.name COLLATE NOCASE
        """,
        (account_id,),
    )
    account["invoices"] = fetch_all(
        """
        SELECT i.*,
               CASE
                 WHEN i.total_cents-i.amount_paid_cents-i.credit_applied_cents > 0
                 THEN i.total_cents-i.amount_paid_cents-i.credit_applied_cents
                 ELSE 0
               END AS balance_due_cents
        FROM academy_invoices i
        WHERE i.account_id=? AND i.status<>'void'
        ORDER BY i.due_date DESC,i.id DESC
        """,
        (account_id,),
    )
    account["payments"] = fetch_all(
        """
        SELECT id,amount_cents,allocated_cents,unapplied_cents,refunded_cents,method,
               received_on,status,receipt_number,external_reference,created_at
        FROM academy_payments
        WHERE account_id=?
        ORDER BY received_on DESC,id DESC
        """,
        (account_id,),
    )
    account["balance_cents"] = sum(int(row.get("balance_due_cents") or 0) for row in account["invoices"])
    account["guardian_name"] = " ".join(
        value for value in [account.get("guardian_first_name"), account.get("guardian_last_name")] if value
    ).strip() or None
    account.pop("guardian_first_name", None)
    account.pop("guardian_last_name", None)
    return account


_ensure_tables()


@router.get("/billing")
def parent_billing_summary(user: dict = Depends(require_parent_billing_user)):
    guardian_id = int(user["guardian_id"])
    player_ids = linked_player_ids_for_guardian(guardian_id)
    players = []
    if player_ids:
        placeholders = ",".join("?" for _ in player_ids)
        players = fetch_all(
            f"SELECT id,name,status FROM players WHERE id IN ({placeholders}) ORDER BY name COLLATE NOCASE",
            player_ids,
        )
    account_ids = _parent_account_ids(user)
    accounts = [_account_summary(account_id) for account_id in account_ids]
    return {
        "user": {"id": user["id"], "display_name": user["display_name"], "role": user["role"]},
        "guardian_id": guardian_id,
        "players": players,
        "accounts": accounts,
        "payment_methods": _methods_for_user(int(user["id"])),
        "payment_mode": PAYMENT_MODE,
    }


@router.get("/payment-methods")
def parent_payment_methods(user: dict = Depends(require_parent_billing_user)):
    return {"payment_mode": PAYMENT_MODE, "payment_methods": _methods_for_user(int(user["id"]))}


@router.post("/payment-methods/sandbox", status_code=201)
def add_sandbox_payment_method(
    payload: SandboxPaymentMethodPayload,
    user: dict = Depends(require_parent_billing_user),
):
    if PAYMENT_MODE != "sandbox":
        raise HTTPException(503, "Sandbox payment methods are disabled. Set CAM_PAYMENT_MODE=sandbox only in a test environment")
    number = _digits(payload.card_number)
    test_card = SANDBOX_CARDS.get(number)
    if not test_card:
        raise HTTPException(422, "Sandbox accepts only CAM-approved test card numbers; do not enter a real card")
    if not payload.cvc.isdigit():
        raise HTTPException(422, "Sandbox CVC must contain only digits")
    if payload.exp_year < date.today().year:
        raise HTTPException(422, "Expiration year must be in the future")
    if test_card["behavior"] == "requires_setup_auth":
        raise HTTPException(409, "Sandbox authentication is required before this test card can be saved")

    user_id = int(user["id"])
    guardian_id = int(user["guardian_id"])
    provider_ref = f"sandbox_pm_{uuid.uuid4().hex}"
    with connection() as conn:
        if payload.make_default:
            conn.execute(
                "UPDATE academy_saved_payment_methods SET is_default=0,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND status='active'",
                (user_id,),
            )
        row = conn.execute(
            """
            INSERT INTO academy_saved_payment_methods(
                user_id,guardian_id,provider,provider_payment_method_ref,brand,last4,
                exp_month,exp_year,behavior,is_default,status
            ) VALUES(?,?, 'sandbox',?,?,?,?,?,?,?,'active') RETURNING id
            """,
            (
                user_id, guardian_id, provider_ref, test_card["brand"], number[-4:],
                payload.exp_month, payload.exp_year, test_card["behavior"], 1 if payload.make_default else 0,
            ),
        ).fetchone()
        method_id = int(row["id"])
        _audit(conn, user_id, "add_payment_method", "payment_method", method_id, f"sandbox;last4={number[-4:]}")
    return _safe_method(_method_for_user(method_id, user_id))


@router.put("/payment-methods/{method_id}/default")
def make_default_payment_method(method_id: int, user: dict = Depends(require_parent_billing_user)):
    user_id = int(user["id"])
    _method_for_user(method_id, user_id)
    with connection() as conn:
        conn.execute(
            "UPDATE academy_saved_payment_methods SET is_default=0,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND status='active'",
            (user_id,),
        )
        conn.execute(
            "UPDATE academy_saved_payment_methods SET is_default=1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (method_id, user_id),
        )
        _audit(conn, user_id, "set_default_payment_method", "payment_method", method_id)
    return _safe_method(_method_for_user(method_id, user_id))


@router.delete("/payment-methods/{method_id}", status_code=204)
def remove_payment_method(method_id: int, user: dict = Depends(require_parent_billing_user)):
    user_id = int(user["id"])
    current = _method_for_user(method_id, user_id)
    with connection() as conn:
        conn.execute(
            "UPDATE academy_saved_payment_methods SET status='removed',is_default=0,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
            (method_id, user_id),
        )
        if bool(current["is_default"]):
            replacement = conn.execute(
                "SELECT id FROM academy_saved_payment_methods WHERE user_id=? AND status='active' ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if replacement:
                conn.execute(
                    "UPDATE academy_saved_payment_methods SET is_default=1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (int(replacement["id"]),),
                )
        _audit(conn, user_id, "remove_payment_method", "payment_method", method_id)
    return None


@router.post("/invoices/{invoice_id}/pay")
def pay_parent_invoice(
    invoice_id: int,
    payload: ParentInvoicePaymentPayload,
    user: dict = Depends(require_parent_billing_user),
):
    invoice = _invoice_for_parent(invoice_id, user)
    balance = int(invoice["balance_due_cents"])
    if balance <= 0:
        raise HTTPException(409, "Invoice has no balance due")
    amount = int(payload.amount_cents or balance)
    if amount > balance:
        raise HTTPException(409, "Payment cannot exceed the current invoice balance")

    user_id = int(user["id"])
    method = _method_for_user(payload.payment_method_id, user_id)
    if method["provider"] != "sandbox" or PAYMENT_MODE != "sandbox":
        raise HTTPException(503, "The configured payment provider is not available for this payment method")

    behavior = str(method["behavior"])
    if behavior == "insufficient_funds":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Sandbox card declined: insufficient funds")
    if behavior == "later_failure":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Sandbox saved card was declined during payment")
    if behavior == "requires_charge_auth":
        raise HTTPException(409, "Sandbox card requires customer authentication before payment")
    if behavior != "success":
        raise HTTPException(409, "Sandbox payment method is not chargeable")

    result = post_payment(
        PaymentPayload(
            account_id=int(invoice["account_id"]),
            amount_cents=amount,
            method="card",
            received_on=date.today().isoformat(),
            idempotency_key=f"parent-{user_id}-{uuid.uuid4().hex}",
            external_reference=str(method["provider_payment_method_ref"]),
            notes="Parent portal sandbox payment",
            allocations=[PaymentAllocationPayload(invoice_id=invoice_id, amount_cents=amount)],
        )
    )
    receipt = payment_receipt(int(result["id"]))
    with connection() as conn:
        _audit(
            conn,
            user_id,
            "parent_invoice_payment",
            "invoice",
            invoice_id,
            f"amount_cents={amount};payment_id={result['id']};last4={method['last4']}",
        )
    return {"payment": result, "receipt": receipt, "invoice": _invoice_for_parent(invoice_id, user)}


@router.get("/receipts/{payment_id}")
def parent_receipt(payment_id: int, user: dict = Depends(require_parent_billing_user)):
    payment = fetch_one("SELECT id,account_id FROM academy_payments WHERE id=?", (payment_id,))
    if not payment:
        raise HTTPException(404, "Payment not found")
    _assert_parent_account(int(payment["account_id"]), user)
    return payment_receipt(payment_id)


@router.get("/billing-audit")
def parent_billing_audit(user: dict = Depends(require_parent_billing_user)):
    return fetch_all(
        """
        SELECT id,action,target_type,target_id,detail,created_at
        FROM academy_billing_security_audit
        WHERE actor_user_id=?
        ORDER BY id DESC LIMIT 100
        """,
        (int(user["id"]),),
    )
