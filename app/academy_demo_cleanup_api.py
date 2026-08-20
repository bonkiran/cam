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
    """Remove finance records that belong to the repeatable DEMO fixture only.

    Safety rules:
    - Billing accounts are removable only when every actively linked player name
      starts with ``DEMO ``.
    - Coach rates/payments and operating/facility expenses are removable only
      when their explicit external reference starts with ``DEMO-``.
    - Players, guardians, enrollments, programs, sessions and any non-DEMO finance
      records are never deleted here.
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
        "coach_payments": 0,
        "coach_rates": 0,
        "academy_expenses": 0,
    }

    with connection() as conn:
        # Remove only explicitly tagged DEMO operating-finance records so the
        # monthly dashboard can be rebuilt predictably while preserving real data.
        cursor = conn.execute(
            "DELETE FROM academy_coach_payments WHERE external_reference LIKE 'DEMO-%'"
        )
        deleted["coach_payments"] = max(0, int(cursor.rowcount or 0))

        cursor = conn.execute(
            "DELETE FROM academy_coach_rates WHERE external_reference LIKE 'DEMO-%'"
        )
        deleted["coach_rates"] = max(0, int(cursor.rowcount or 0))

        cursor = conn.execute(
            "DELETE FROM academy_expenses WHERE external_reference LIKE 'DEMO-%'"
        )
        deleted["academy_expenses"] = max(0, int(cursor.rowcount or 0))

        # Only accounts whose actively linked players are ALL DEMO players are
        # eligible. This includes current DEMO Family xx accounts and older test
        # accounts that were linked exclusively to DEMO players.
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

        if account_ids:
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
        "safety": (
            "Only DEMO-tagged operating records and billing accounts linked "
            "exclusively to DEMO players were removed."
        ),
    }
