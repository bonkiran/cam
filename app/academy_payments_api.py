from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-payments"])


class PaymentAllocationPayload(BaseModel):
    invoice_id: int = Field(gt=0)
    amount_cents: int = Field(gt=0, le=100_000_000)


class PaymentPayload(BaseModel):
    account_id: int = Field(gt=0)
    amount_cents: int = Field(gt=0, le=100_000_000)
    method: Literal["card", "cash", "check", "bank", "other"]
    received_on: str
    idempotency_key: str = Field(min_length=8, max_length=120)
    external_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)
    allocations: list[PaymentAllocationPayload] = Field(default_factory=list, max_length=50)


class RefundPayload(BaseModel):
    amount_cents: int = Field(gt=0, le=100_000_000)
    refunded_on: str
    reason: str = Field(min_length=2, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=120)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _iso_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except Exception as exc:
        raise HTTPException(422, f"{label} must be YYYY-MM-DD") from exc


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            account_id BIGINT NOT NULL,
            amount_cents INTEGER NOT NULL,
            allocated_cents INTEGER NOT NULL DEFAULT 0,
            unapplied_cents INTEGER NOT NULL DEFAULT 0,
            refunded_cents INTEGER NOT NULL DEFAULT 0,
            method TEXT NOT NULL,
            received_on TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'posted',
            receipt_number TEXT UNIQUE,
            idempotency_key TEXT NOT NULL UNIQUE,
            external_reference TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(account_id) REFERENCES academy_billing_accounts(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_academy_payments_account ON academy_payments(account_id);
        CREATE INDEX IF NOT EXISTS idx_academy_payments_received ON academy_payments(received_on);

        CREATE TABLE IF NOT EXISTS academy_payment_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id BIGINT NOT NULL,
            invoice_id BIGINT NOT NULL,
            amount_cents INTEGER NOT NULL,
            refunded_cents INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(payment_id) REFERENCES academy_payments(id) ON DELETE CASCADE,
            FOREIGN KEY(invoice_id) REFERENCES academy_invoices(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_payment_allocations_payment ON academy_payment_allocations(payment_id);
        CREATE INDEX IF NOT EXISTS idx_payment_allocations_invoice ON academy_payment_allocations(invoice_id);

        CREATE TABLE IF NOT EXISTS academy_refunds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id BIGINT NOT NULL,
            amount_cents INTEGER NOT NULL,
            refunded_on TEXT NOT NULL,
            reason TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(payment_id) REFERENCES academy_payments(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_academy_refunds_payment ON academy_refunds(payment_id);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _invoice_balance(row) -> int:
    return max(0, int(row["total_cents"]) - int(row["amount_paid_cents"]) - int(row["credit_applied_cents"]))


def _update_invoice_status(conn, invoice_id: int) -> None:
    row = conn.execute(
        "SELECT id,total_cents,amount_paid_cents,credit_applied_cents,status FROM academy_invoices WHERE id=?",
        (invoice_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Invoice not found")
    if str(row["status"]) == "void":
        return
    balance = _invoice_balance(row)
    paid = int(row["amount_paid_cents"])
    if balance == 0:
        status = "paid"
    elif paid > 0:
        status = "partially_paid"
    else:
        status = "open"
    conn.execute("UPDATE academy_invoices SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, invoice_id))


def _payment(payment_id: int) -> dict:
    row = fetch_one(
        """
        SELECT p.*,a.account_name FROM academy_payments p
        JOIN academy_billing_accounts a ON a.id=p.account_id WHERE p.id=?
        """,
        (payment_id,),
    )
    if not row:
        raise HTTPException(404, "Payment not found")
    row["allocations"] = fetch_all(
        """
        SELECT pa.*,i.invoice_number,i.total_cents,i.amount_paid_cents,i.status AS invoice_status
        FROM academy_payment_allocations pa JOIN academy_invoices i ON i.id=pa.invoice_id
        WHERE pa.payment_id=? ORDER BY pa.id
        """,
        (payment_id,),
    )
    row["refunds"] = fetch_all("SELECT * FROM academy_refunds WHERE payment_id=? ORDER BY id", (payment_id,))
    row["available_credit_cents"] = int(row["unapplied_cents"])
    return row


def _same_retry(existing: dict, payload: PaymentPayload) -> bool:
    if int(existing["account_id"]) != payload.account_id or int(existing["amount_cents"]) != payload.amount_cents:
        return False
    if str(existing["method"]) != payload.method or str(existing["received_on"]) != payload.received_on:
        return False
    expected = sorted((x.invoice_id, x.amount_cents) for x in payload.allocations)
    actual = sorted((int(x["invoice_id"]), int(x["amount_cents"])) for x in existing.get("allocations", []))
    return expected == actual


def _account(account_id: int) -> dict:
    row = fetch_one("SELECT * FROM academy_billing_accounts WHERE id=?", (account_id,))
    if not row:
        raise HTTPException(404, "Billing account not found")
    return row


_ensure_tables()


@router.get("/payments")
def payments(account_id: int | None = None):
    sql = "SELECT id FROM academy_payments WHERE 1=1"
    params: list[object] = []
    if account_id is not None:
        sql += " AND account_id=?"
        params.append(account_id)
    sql += " ORDER BY received_on DESC,id DESC"
    return [_payment(int(row["id"])) for row in fetch_all(sql, params)]


@router.get("/payments/{payment_id}")
def payment(payment_id: int):
    return _payment(payment_id)


@router.post("/payments", status_code=201)
def post_payment(payload: PaymentPayload):
    _iso_date(payload.received_on, "Received date")
    account = _account(payload.account_id)
    if str(account["status"]) != "active":
        raise HTTPException(409, "Payment requires an active billing account")

    existing_id = fetch_one("SELECT id FROM academy_payments WHERE idempotency_key=?", (payload.idempotency_key,))
    if existing_id:
        existing = _payment(int(existing_id["id"]))
        if not _same_retry(existing, payload):
            raise HTTPException(409, "Idempotency key was already used for a different payment")
        return existing

    allocation_pairs = [(x.invoice_id, x.amount_cents) for x in payload.allocations]
    if len(allocation_pairs) != len({invoice_id for invoice_id, _ in allocation_pairs}):
        raise HTTPException(422, "Each invoice can appear only once in a payment")
    requested_allocation = sum(amount for _, amount in allocation_pairs)
    if requested_allocation > payload.amount_cents:
        raise HTTPException(422, "Invoice allocations cannot exceed payment amount")
    unapplied = payload.amount_cents - requested_allocation
    if unapplied > 0 and not bool(account["overpayment_allowed"]):
        raise HTTPException(409, "This billing account does not allow unapplied overpayment credit")

    with connection() as conn:
        invoice_rows = {}
        for invoice_id, amount in allocation_pairs:
            invoice = conn.execute(
                "SELECT id,account_id,total_cents,amount_paid_cents,credit_applied_cents,status FROM academy_invoices WHERE id=?",
                (invoice_id,),
            ).fetchone()
            if not invoice:
                raise HTTPException(404, f"Invoice {invoice_id} not found")
            if int(invoice["account_id"]) != payload.account_id:
                raise HTTPException(409, "Payment allocations must belong to the same billing account")
            if str(invoice["status"]) == "void":
                raise HTTPException(409, "Cannot pay a void invoice")
            balance = _invoice_balance(invoice)
            if amount > balance:
                raise HTTPException(409, "Payment allocation exceeds invoice balance")
            invoice_rows[invoice_id] = invoice

        row = conn.execute(
            """
            INSERT INTO academy_payments(
                academy_id,account_id,amount_cents,allocated_cents,unapplied_cents,refunded_cents,
                method,received_on,status,idempotency_key,external_reference,notes
            ) VALUES(?,?,?,?,?,0,?,?,'posted',?,?,?) RETURNING id
            """,
            (_academy_id(conn),payload.account_id,payload.amount_cents,requested_allocation,unapplied,
             payload.method,payload.received_on,payload.idempotency_key,_clean(payload.external_reference),_clean(payload.notes)),
        ).fetchone()
        payment_id = int(row["id"])
        receipt_number = f"RCT-{payment_id:06d}"
        conn.execute("UPDATE academy_payments SET receipt_number=? WHERE id=?", (receipt_number,payment_id))

        for invoice_id, amount in allocation_pairs:
            conn.execute(
                "INSERT INTO academy_payment_allocations(payment_id,invoice_id,amount_cents,refunded_cents) VALUES(?,?,?,0)",
                (payment_id,invoice_id,amount),
            )
            conn.execute(
                "UPDATE academy_invoices SET amount_paid_cents=amount_paid_cents+?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (amount,invoice_id),
            )
            _update_invoice_status(conn,invoice_id)

    return _payment(payment_id)


@router.post("/payments/{payment_id}/refunds", status_code=201)
def refund_payment(payment_id: int, payload: RefundPayload):
    _iso_date(payload.refunded_on, "Refund date")
    current = _payment(payment_id)
    existing = fetch_one("SELECT id,payment_id,amount_cents,refunded_on,reason FROM academy_refunds WHERE idempotency_key=?", (payload.idempotency_key,))
    if existing:
        if int(existing["payment_id"]) != payment_id or int(existing["amount_cents"]) != payload.amount_cents or str(existing["refunded_on"]) != payload.refunded_on:
            raise HTTPException(409, "Idempotency key was already used for a different refund")
        return {"refund": existing, "payment": current}

    remaining_refundable = int(current["amount_cents"]) - int(current["refunded_cents"])
    if payload.amount_cents > remaining_refundable:
        raise HTTPException(409, "Refund amount exceeds remaining refundable payment")

    with connection() as conn:
        payment_row = conn.execute(
            "SELECT id,amount_cents,allocated_cents,unapplied_cents,refunded_cents FROM academy_payments WHERE id=?",
            (payment_id,),
        ).fetchone()
        amount_left = payload.amount_cents

        # Refund unused family credit first because it is not tied to an invoice.
        credit_refund = min(amount_left, int(payment_row["unapplied_cents"]))
        if credit_refund:
            conn.execute(
                "UPDATE academy_payments SET unapplied_cents=unapplied_cents-?,refunded_cents=refunded_cents+?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (credit_refund,credit_refund,payment_id),
            )
            amount_left -= credit_refund

        # Then reverse active allocations newest-first while preserving original allocation evidence.
        if amount_left:
            allocations = conn.execute(
                "SELECT id,invoice_id,amount_cents,refunded_cents FROM academy_payment_allocations WHERE payment_id=? ORDER BY id DESC",
                (payment_id,),
            ).fetchall()
            for allocation in allocations:
                available = int(allocation["amount_cents"]) - int(allocation["refunded_cents"])
                reversal = min(amount_left,available)
                if reversal <= 0:
                    continue
                conn.execute(
                    "UPDATE academy_payment_allocations SET refunded_cents=refunded_cents+?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (reversal,int(allocation["id"])),
                )
                conn.execute(
                    "UPDATE academy_invoices SET amount_paid_cents=MAX(0,amount_paid_cents-?),updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (reversal,int(allocation["invoice_id"])),
                )
                conn.execute(
                    "UPDATE academy_payments SET allocated_cents=MAX(0,allocated_cents-?),refunded_cents=refunded_cents+?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (reversal,reversal,payment_id),
                )
                _update_invoice_status(conn,int(allocation["invoice_id"]))
                amount_left -= reversal
                if amount_left == 0:
                    break

        if amount_left:
            raise HTTPException(409, "Refund could not be reconciled to payment credit or invoice allocations")

        refund_row = conn.execute(
            """
            INSERT INTO academy_refunds(payment_id,amount_cents,refunded_on,reason,idempotency_key)
            VALUES(?,?,?,?,?) RETURNING id
            """,
            (payment_id,payload.amount_cents,payload.refunded_on,_clean(payload.reason),payload.idempotency_key),
        ).fetchone()
        updated = conn.execute("SELECT amount_cents,refunded_cents FROM academy_payments WHERE id=?", (payment_id,)).fetchone()
        status = "refunded" if int(updated["refunded_cents"]) >= int(updated["amount_cents"]) else "partially_refunded"
        conn.execute("UPDATE academy_payments SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (status,payment_id))
        refund_id = int(refund_row["id"])

    refund = fetch_one("SELECT * FROM academy_refunds WHERE id=?", (refund_id,))
    return {"refund": refund, "payment": _payment(payment_id)}


@router.get("/payments/{payment_id}/receipt")
def payment_receipt(payment_id: int):
    p = _payment(payment_id)
    account = _account(int(p["account_id"]))
    allocations = fetch_all(
        """
        SELECT pa.invoice_id,pa.amount_cents,pa.refunded_cents,i.invoice_number,i.source_type,i.source_id,
               CASE WHEN i.source_type='enrollment' THEN pl.name ELSE NULL END AS player_name
        FROM academy_payment_allocations pa
        JOIN academy_invoices i ON i.id=pa.invoice_id
        LEFT JOIN enrollments e ON i.source_type='enrollment' AND e.id=i.source_id
        LEFT JOIN players pl ON pl.id=e.player_id
        WHERE pa.payment_id=? ORDER BY pa.id
        """,
        (payment_id,),
    )
    return {
        "receipt_number": p["receipt_number"],
        "payment_id": p["id"],
        "account_id": p["account_id"],
        "account_name": p["account_name"],
        "amount_cents": p["amount_cents"],
        "method": p["method"],
        "received_on": p["received_on"],
        "external_reference": p["external_reference"],
        "status": p["status"],
        "allocations": allocations,
        "unapplied_credit_cents": p["unapplied_cents"],
        "refunded_cents": p["refunded_cents"],
        "overpayment_allowed": bool(account["overpayment_allowed"]),
    }


@router.get("/billing-accounts/{account_id}/ledger")
def billing_account_ledger(account_id: int):
    account = _account(account_id)
    invoices = fetch_all(
        """
        SELECT id,invoice_number,issue_date,due_date,status,total_cents,amount_paid_cents,credit_applied_cents,
               MAX(0,total_cents-amount_paid_cents-credit_applied_cents) AS balance_due_cents
        FROM academy_invoices WHERE account_id=? AND status<>'void' ORDER BY issue_date,id
        """,
        (account_id,),
    )
    payment_rows = payments(account_id)
    outstanding = sum(int(row["balance_due_cents"]) for row in invoices)
    credit = sum(int(row["unapplied_cents"]) for row in payment_rows)
    return {
        "account": account,
        "invoices": invoices,
        "payments": payment_rows,
        "outstanding_cents": outstanding,
        "credit_cents": credit,
        "net_balance_cents": outstanding-credit,
    }
