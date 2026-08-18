from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-fees"])


class FeePlanPayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    amount_cents: int = Field(ge=0, le=100_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    billing_frequency: Literal["one_time", "monthly", "session", "tournament"] = "monthly"
    program_id: int | None = Field(default=None, gt=0)
    status: Literal["active", "inactive"] = "active"
    notes: str | None = Field(default=None, max_length=1500)


class BillingAccountPayload(BaseModel):
    account_name: str = Field(min_length=2, max_length=180)
    player_ids: list[int] = Field(min_length=1, max_length=20)
    primary_guardian_id: int | None = Field(default=None, gt=0)
    status: Literal["active", "inactive"] = "active"
    overpayment_allowed: bool = True
    notes: str | None = Field(default=None, max_length=1500)


class EnrollmentBillingPayload(BaseModel):
    fee_plan_id: int = Field(gt=0)
    discount_type: Literal["none", "fixed", "percent"] = "none"
    discount_value: int = Field(default=0, ge=0, le=100_000_000)
    notes: str | None = Field(default=None, max_length=1000)


class EnrollmentInvoicePayload(BaseModel):
    account_id: int = Field(gt=0)
    issue_date: str
    due_date: str
    description: str | None = Field(default=None, max_length=240)


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
        CREATE TABLE IF NOT EXISTS academy_fee_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            program_id BIGINT,
            name TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            billing_frequency TEXT NOT NULL DEFAULT 'monthly',
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_academy_fee_plans_program ON academy_fee_plans(program_id);
        CREATE INDEX IF NOT EXISTS idx_academy_fee_plans_status ON academy_fee_plans(status);

        CREATE TABLE IF NOT EXISTS academy_billing_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            account_name TEXT NOT NULL,
            primary_guardian_id BIGINT,
            status TEXT NOT NULL DEFAULT 'active',
            overpayment_allowed INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(primary_guardian_id) REFERENCES guardians(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_academy_billing_accounts_status ON academy_billing_accounts(status);

        CREATE TABLE IF NOT EXISTS academy_billing_account_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id BIGINT NOT NULL,
            player_id BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES academy_billing_accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_billing_account_players_account ON academy_billing_account_players(account_id);
        CREATE INDEX IF NOT EXISTS idx_billing_account_players_player ON academy_billing_account_players(player_id);

        CREATE TABLE IF NOT EXISTS academy_enrollment_billing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id BIGINT NOT NULL,
            fee_plan_id BIGINT NOT NULL,
            discount_type TEXT NOT NULL DEFAULT 'none',
            discount_value INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE,
            FOREIGN KEY(fee_plan_id) REFERENCES academy_fee_plans(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_enrollment_billing_enrollment ON academy_enrollment_billing(enrollment_id);

        CREATE TABLE IF NOT EXISTS academy_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            account_id BIGINT NOT NULL,
            invoice_number TEXT UNIQUE,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            subtotal_cents INTEGER NOT NULL DEFAULT 0,
            discount_cents INTEGER NOT NULL DEFAULT 0,
            total_cents INTEGER NOT NULL DEFAULT 0,
            amount_paid_cents INTEGER NOT NULL DEFAULT 0,
            credit_applied_cents INTEGER NOT NULL DEFAULT 0,
            source_type TEXT,
            source_id BIGINT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(account_id) REFERENCES academy_billing_accounts(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_academy_invoices_account ON academy_invoices(account_id);
        CREATE INDEX IF NOT EXISTS idx_academy_invoices_status ON academy_invoices(status);
        CREATE INDEX IF NOT EXISTS idx_academy_invoices_source ON academy_invoices(source_type,source_id);

        CREATE TABLE IF NOT EXISTS academy_invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id BIGINT NOT NULL,
            fee_plan_id BIGINT,
            description TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_amount_cents INTEGER NOT NULL DEFAULT 0,
            discount_cents INTEGER NOT NULL DEFAULT 0,
            line_total_cents INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(invoice_id) REFERENCES academy_invoices(id) ON DELETE CASCADE,
            FOREIGN KEY(fee_plan_id) REFERENCES academy_fee_plans(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON academy_invoice_items(invoice_id);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _fee_plan(fee_plan_id: int) -> dict:
    row = fetch_one(
        """
        SELECT fp.*,p.name AS program_name
        FROM academy_fee_plans fp LEFT JOIN programs p ON p.id=fp.program_id
        WHERE fp.id=?
        """,
        (fee_plan_id,),
    )
    if not row:
        raise HTTPException(404, "Fee plan not found")
    return row


def _billing_account(account_id: int) -> dict:
    row = fetch_one(
        """
        SELECT a.*,g.first_name AS guardian_first_name,g.last_name AS guardian_last_name,
               COALESCE((SELECT SUM(i.total_cents-i.amount_paid_cents-i.credit_applied_cents) FROM academy_invoices i WHERE i.account_id=a.id AND i.status<>'void'),0) AS balance_cents,
               COALESCE((SELECT SUM(i.total_cents) FROM academy_invoices i WHERE i.account_id=a.id AND i.status<>'void'),0) AS invoiced_cents
        FROM academy_billing_accounts a LEFT JOIN guardians g ON g.id=a.primary_guardian_id
        WHERE a.id=?
        """,
        (account_id,),
    )
    if not row:
        raise HTTPException(404, "Billing account not found")
    row["players"] = fetch_all(
        """
        SELECT bap.*,p.name AS player_name FROM academy_billing_account_players bap
        JOIN players p ON p.id=bap.player_id WHERE bap.account_id=? AND bap.status='active'
        ORDER BY p.name COLLATE NOCASE
        """,
        (account_id,),
    )
    row["guardian_name"] = f"{row.get('guardian_first_name') or ''} {row.get('guardian_last_name') or ''}".strip() or None
    return row


def _enrollment_billing(enrollment_id: int) -> dict:
    row = fetch_one(
        """
        SELECT eb.*,fp.name AS fee_plan_name,fp.amount_cents,fp.currency,fp.billing_frequency,fp.program_id AS fee_plan_program_id,
               e.player_id,e.program_id,p.name AS player_name,pr.name AS program_name
        FROM academy_enrollment_billing eb
        JOIN academy_fee_plans fp ON fp.id=eb.fee_plan_id
        JOIN enrollments e ON e.id=eb.enrollment_id
        JOIN players p ON p.id=e.player_id
        JOIN programs pr ON pr.id=e.program_id
        WHERE eb.enrollment_id=?
        """,
        (enrollment_id,),
    )
    if not row:
        raise HTTPException(404, "Enrollment billing is not configured")
    return row


def _invoice(invoice_id: int) -> dict:
    row = fetch_one(
        """
        SELECT i.*,a.account_name FROM academy_invoices i
        JOIN academy_billing_accounts a ON a.id=i.account_id WHERE i.id=?
        """,
        (invoice_id,),
    )
    if not row:
        raise HTTPException(404, "Invoice not found")
    row["items"] = fetch_all("SELECT * FROM academy_invoice_items WHERE invoice_id=? ORDER BY id", (invoice_id,))
    row["balance_due_cents"] = max(0, int(row["total_cents"]) - int(row["amount_paid_cents"]) - int(row["credit_applied_cents"]))
    return row


def _discount_cents(amount_cents: int, discount_type: str, discount_value: int) -> int:
    if discount_type == "none":
        if discount_value != 0:
            raise HTTPException(422, "Discount value must be zero when discount type is none")
        return 0
    if discount_type == "fixed":
        return min(amount_cents, discount_value)
    if discount_type == "percent":
        if discount_value > 10_000:
            raise HTTPException(422, "Percent discount uses basis points and cannot exceed 10000")
        return min(amount_cents, (amount_cents * discount_value + 5_000) // 10_000)
    raise HTTPException(422, "Unsupported discount type")


def _validate_account_player(conn, account_id: int, player_id: int) -> None:
    row = conn.execute(
        "SELECT id FROM academy_billing_account_players WHERE account_id=? AND player_id=? AND status='active'",
        (account_id, player_id),
    ).fetchone()
    if not row:
        raise HTTPException(409, "Enrollment player must belong to the billing account")


_ensure_tables()


@router.get("/fee-plans")
def fee_plans():
    return fetch_all(
        """
        SELECT fp.*,p.name AS program_name FROM academy_fee_plans fp
        LEFT JOIN programs p ON p.id=fp.program_id
        ORDER BY CASE WHEN fp.status='active' THEN 0 ELSE 1 END,fp.name COLLATE NOCASE
        """
    )


@router.post("/fee-plans", status_code=201)
def create_fee_plan(payload: FeePlanPayload):
    name = _clean(payload.name) or ""
    currency = payload.currency.upper()
    with connection() as conn:
        if payload.program_id is not None:
            program = conn.execute("SELECT id FROM programs WHERE id=?", (payload.program_id,)).fetchone()
            if not program:
                raise HTTPException(404, "Program not found")
        duplicate = conn.execute("SELECT id FROM academy_fee_plans WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if duplicate:
            raise HTTPException(409, "A fee plan with this name already exists")
        row = conn.execute(
            """
            INSERT INTO academy_fee_plans(academy_id,program_id,name,amount_cents,currency,billing_frequency,status,notes)
            VALUES(?,?,?,?,?,?,?,?) RETURNING id
            """,
            (_academy_id(conn),payload.program_id,name,payload.amount_cents,currency,payload.billing_frequency,payload.status,_clean(payload.notes)),
        ).fetchone()
        fee_plan_id = int(row["id"])
    return _fee_plan(fee_plan_id)


@router.get("/billing-accounts")
def billing_accounts():
    rows = fetch_all("SELECT id FROM academy_billing_accounts ORDER BY account_name COLLATE NOCASE")
    return [_billing_account(int(row["id"])) for row in rows]


@router.get("/billing-accounts/{account_id}")
def billing_account(account_id: int):
    return _billing_account(account_id)


@router.post("/billing-accounts", status_code=201)
def create_billing_account(payload: BillingAccountPayload):
    player_ids = list(dict.fromkeys(payload.player_ids))
    with connection() as conn:
        players = conn.execute(
            f"SELECT id FROM players WHERE id IN ({','.join('?' for _ in player_ids)})",
            player_ids,
        ).fetchall()
        if len(players) != len(player_ids):
            raise HTTPException(404, "One or more billing-account players were not found")
        if payload.primary_guardian_id is not None:
            guardian = conn.execute("SELECT id FROM guardians WHERE id=?", (payload.primary_guardian_id,)).fetchone()
            if not guardian:
                raise HTTPException(404, "Guardian not found")
            linked = conn.execute(
                f"SELECT id FROM player_guardians WHERE guardian_id=? AND player_id IN ({','.join('?' for _ in player_ids)}) LIMIT 1",
                (payload.primary_guardian_id,*player_ids),
            ).fetchone()
            if not linked:
                raise HTTPException(409, "Primary guardian must be linked to a player on the billing account")
        row = conn.execute(
            """
            INSERT INTO academy_billing_accounts(academy_id,account_name,primary_guardian_id,status,overpayment_allowed,notes)
            VALUES(?,?,?,?,?,?) RETURNING id
            """,
            (_academy_id(conn),_clean(payload.account_name),payload.primary_guardian_id,payload.status,1 if payload.overpayment_allowed else 0,_clean(payload.notes)),
        ).fetchone()
        account_id = int(row["id"])
        for player_id in player_ids:
            conn.execute(
                "INSERT INTO academy_billing_account_players(account_id,player_id,status) VALUES(?,?,'active')",
                (account_id,player_id),
            )
    return _billing_account(account_id)


@router.put("/enrollments/{enrollment_id}/billing")
def configure_enrollment_billing(enrollment_id: int, payload: EnrollmentBillingPayload):
    with connection() as conn:
        enrollment = conn.execute("SELECT id,program_id FROM enrollments WHERE id=?", (enrollment_id,)).fetchone()
        if not enrollment:
            raise HTTPException(404, "Enrollment not found")
        fee_plan = conn.execute("SELECT id,program_id,status,amount_cents FROM academy_fee_plans WHERE id=?", (payload.fee_plan_id,)).fetchone()
        if not fee_plan:
            raise HTTPException(404, "Fee plan not found")
        if str(fee_plan["status"]) != "active":
            raise HTTPException(409, "Only an active fee plan can be assigned")
        if fee_plan["program_id"] is not None and int(fee_plan["program_id"]) != int(enrollment["program_id"]):
            raise HTTPException(409, "Fee plan program does not match the enrollment program")
        _discount_cents(int(fee_plan["amount_cents"]), payload.discount_type, payload.discount_value)
        existing = conn.execute("SELECT id FROM academy_enrollment_billing WHERE enrollment_id=?", (enrollment_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE academy_enrollment_billing SET fee_plan_id=?,discount_type=?,discount_value=?,notes=?,updated_at=CURRENT_TIMESTAMP
                WHERE enrollment_id=?
                """,
                (payload.fee_plan_id,payload.discount_type,payload.discount_value,_clean(payload.notes),enrollment_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO academy_enrollment_billing(enrollment_id,fee_plan_id,discount_type,discount_value,notes)
                VALUES(?,?,?,?,?)
                """,
                (enrollment_id,payload.fee_plan_id,payload.discount_type,payload.discount_value,_clean(payload.notes)),
            )
    return _enrollment_billing(enrollment_id)


@router.get("/enrollments/{enrollment_id}/billing")
def enrollment_billing(enrollment_id: int):
    return _enrollment_billing(enrollment_id)


@router.post("/invoices/from-enrollment", status_code=201)
def invoice_from_enrollment(payload: EnrollmentInvoicePayload):
    issue = _iso_date(payload.issue_date, "Issue date")
    due = _iso_date(payload.due_date, "Due date")
    if due < issue:
        raise HTTPException(422, "Due date must be on or after issue date")
    billing = _enrollment_billing(payload.enrollment_id)
    amount = int(billing["amount_cents"])
    discount = _discount_cents(amount, str(billing["discount_type"]), int(billing["discount_value"]))
    total = amount - discount
    description = _clean(payload.description) or f"{billing['program_name']} — {billing['fee_plan_name']}"

    with connection() as conn:
        account = conn.execute("SELECT id,status FROM academy_billing_accounts WHERE id=?", (payload.account_id,)).fetchone()
        if not account:
            raise HTTPException(404, "Billing account not found")
        if str(account["status"]) != "active":
            raise HTTPException(409, "Invoice requires an active billing account")
        _validate_account_player(conn,payload.account_id,int(billing["player_id"]))
        row = conn.execute(
            """
            INSERT INTO academy_invoices(academy_id,account_id,issue_date,due_date,status,subtotal_cents,discount_cents,total_cents,source_type,source_id)
            VALUES(?,?,?,?,'open',?,?,?,'enrollment',?) RETURNING id
            """,
            (_academy_id(conn),payload.account_id,payload.issue_date,payload.due_date,amount,discount,total,payload.enrollment_id),
        ).fetchone()
        invoice_id = int(row["id"])
        invoice_number = f"INV-{invoice_id:06d}"
        conn.execute("UPDATE academy_invoices SET invoice_number=? WHERE id=?", (invoice_number,invoice_id))
        conn.execute(
            """
            INSERT INTO academy_invoice_items(invoice_id,fee_plan_id,description,quantity,unit_amount_cents,discount_cents,line_total_cents)
            VALUES(?,?,?,1,?,?,?)
            """,
            (invoice_id,int(billing["fee_plan_id"]),description,amount,discount,total),
        )
    return _invoice(invoice_id)


@router.get("/invoices")
def invoices(account_id: int | None = None):
    sql = "SELECT id FROM academy_invoices WHERE 1=1"
    params: list[object] = []
    if account_id is not None:
        sql += " AND account_id=?"
        params.append(account_id)
    sql += " ORDER BY id DESC"
    rows = fetch_all(sql,params)
    return [_invoice(int(row["id"])) for row in rows]


@router.get("/invoices/{invoice_id}")
def invoice(invoice_id: int):
    return _invoice(invoice_id)
