from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .academy_authz import require_parent_billing_user
from .academy_parent_billing_api import PAYMENT_MODE, _audit, _invoice_for_parent, _method_for_user
from .academy_payments_v2_api import PaymentAllocationPayload, PaymentPayload, payment_receipt, post_payment
from .database import connection

router = APIRouter(prefix="/api/academy/parent", tags=["academy-parent-billing-policy"])


class ParentFullInvoicePaymentPayload(BaseModel):
    payment_method_id: int = Field(gt=0)
    # Kept for API compatibility with the first Parent Portal version. If a
    # client sends an amount it must equal the full current balance.
    amount_cents: int | None = Field(default=None, gt=0, le=100_000_000)


@router.post("/invoices/{invoice_id}/pay")
def pay_parent_invoice_full_balance(
    invoice_id: int,
    payload: ParentFullInvoicePaymentPayload,
    user: dict = Depends(require_parent_billing_user),
):
    invoice = _invoice_for_parent(invoice_id, user)
    balance = int(invoice["balance_due_cents"])
    if balance <= 0:
        raise HTTPException(409, "Invoice has no balance due")
    if payload.amount_cents is not None and int(payload.amount_cents) != balance:
        raise HTTPException(409, "Parent Portal requires payment of the full invoice balance")

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
            amount_cents=balance,
            method="card",
            received_on=date.today().isoformat(),
            idempotency_key=f"parent-full-{user_id}-{uuid.uuid4().hex}",
            external_reference=str(method["provider_payment_method_ref"]),
            notes="Parent portal full-balance sandbox payment",
            allocations=[PaymentAllocationPayload(invoice_id=invoice_id, amount_cents=balance)],
        )
    )
    receipt = payment_receipt(int(result["id"]))
    with connection() as conn:
        _audit(
            conn,
            user_id,
            "parent_pay_invoice_full_balance",
            "invoice",
            invoice_id,
            f"payment_id={result['id']};amount_cents={balance};method_id={payload.payment_method_id}",
        )
    return {"payment": result, "receipt": receipt}
