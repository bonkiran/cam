from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .academy_auth_api import require_access_admin
from .database import connection

router = APIRouter(prefix="/api/academy", tags=["academy-demo-cleanup"])


class DemoFinanceCleanupPayload(BaseModel):
    confirm: str


@router.post("/demo-data/cleanup-finance")
def cleanup_demo_finance(
    payload: DemoFinanceCleanupPayload,
    _: dict = Depends(require_access_admin),
):
    """Remove finance records belonging only to DEMO players.

    This is deliberately narrow. It never deletes players, guardians, enrollments,
    programs, coach data, academy expenses, facility expenses, or any billing
    account that contains a non-DEMO player. It exists only to keep the repeatable
    manual-test finance fixture deterministic.
    """
    if payload.confirm != "RESET_DEMO_FINANCE":
        raise HTTPException(422, "Exact cleanup confirmation is required")

    deleted = {
        "refunds": 0,
        "payment_allocations": 0,
        "payments": 0,
        "invoice_items": 0,
        "invoices": 0,
        "billing_account_players": 0,
        "billing_accounts": 0,
    }

    with connection() as conn:
        # Only accounts whose linked players are ALL DEMO players are eligible.
        # This safely catches both the current DEMO Family xx accounts and older
        # test accounts such as "Patel Family" that were linked only to DEMO players.
        account_rows = conn.execute(
            """
            SELECT bap.account_id
            FROM academy_billing_account_players bap
            JOIN players p ON p.id=bap.player_id
            WHERE bap.status='active'
            GROUP BY bap.account_id
            HAVING COUNT(*) > 0
               AND SUM(CASE WHEN p.name LIKE 'DEMO %' THEN 0 ELSE 1 END) = 0
            """
        ).fetchall()
        account_ids = [int(row["account_id"]) for row in account_rows]

        if not account_ids:
            return {"status": "ok", "demo_account_count": 0, "deleted": deleted}

        account_marks = ",".join("?" for _ in account_ids)
        invoice_rows = conn.execute(
            f"SELECT id FROM academy_invoices WHERE account_id IN ({account_marks})",
            account_ids,
        ).fetchall()
        invoice_ids = [int(row["id"]) for row in invoice_rows]

        payment_rows = conn.execute(
            f"SELECT id FROM academy_payments WHERE account_id IN ({account_marks})",
            account_ids,
        ).fetchall()
        payment_ids = [int(row["id"]) for row in payment_rows]

        if payment_ids:
            payment_marks = ",".join("?" for _ in payment_ids)
            cursor = conn.execute(
                f"DELETE FROM academy_refunds WHERE payment_id IN ({payment_marks})",
                payment_ids,
            )
            deleted["refunds"] = max(0, int(cursor.rowcount or 0))
            cursor = conn.execute(
                f"DELETE FROM academy_payment_allocations WHERE payment_id IN ({payment_marks})",
                payment_ids,
            )
            deleted["payment_allocations"] = max(0, int(cursor.rowcount or 0))
            cursor = conn.execute(
                f"DELETE FROM academy_payments WHERE id IN ({payment_marks})",
                payment_ids,
            )
            deleted["payments"] = max(0, int(cursor.rowcount or 0))

        if invoice_ids:
            invoice_marks = ",".join("?" for _ in invoice_ids)
            cursor = conn.execute(
                f"DELETE FROM academy_invoice_items WHERE invoice_id IN ({invoice_marks})",
                invoice_ids,
            )
            deleted["invoice_items"] = max(0, int(cursor.rowcount or 0))
            cursor = conn.execute(
                f"DELETE FROM academy_invoices WHERE id IN ({invoice_marks})",
                invoice_ids,
            )
            deleted["invoices"] = max(0, int(cursor.rowcount or 0))

        cursor = conn.execute(
            f"DELETE FROM academy_billing_account_players WHERE account_id IN ({account_marks})",
            account_ids,
        )
        deleted["billing_account_players"] = max(0, int(cursor.rowcount or 0))
        cursor = conn.execute(
            f"DELETE FROM academy_billing_accounts WHERE id IN ({account_marks})",
            account_ids,
        )
        deleted["billing_accounts"] = max(0, int(cursor.rowcount or 0))

    return {
        "status": "ok",
        "demo_account_count": len(account_ids),
        "deleted": deleted,
        "safety": "Only billing accounts linked exclusively to DEMO players were removed.",
    }
