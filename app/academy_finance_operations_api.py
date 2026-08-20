from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-finance-operations"])


class CoachRatePayload(BaseModel):
    coach_id: int = Field(gt=0)
    rate_type: Literal["hourly", "session"] = "hourly"
    rate_cents: int = Field(gt=0, le=10_000_000)
    effective_from: str
    effective_to: str | None = None
    status: Literal["active", "inactive"] = "active"
    external_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


class CoachPaymentPayload(BaseModel):
    coach_id: int = Field(gt=0)
    amount_cents: int = Field(gt=0, le=100_000_000)
    paid_on: str
    payment_method: Literal["card", "cash", "check", "bank", "other"] = "bank"
    hours_worked: float | None = Field(default=None, ge=0, le=1000)
    period_start: str | None = None
    period_end: str | None = None
    status: Literal["paid", "pending"] = "paid"
    external_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1500)


class ExpensePayload(BaseModel):
    expense_type: Literal["academy", "facility"]
    category: str = Field(min_length=2, max_length=120)
    vendor: str = Field(min_length=2, max_length=180)
    facility_name: str | None = Field(default=None, max_length=180)
    amount_cents: int = Field(gt=0, le=100_000_000)
    expense_date: str
    payment_method: Literal["card", "cash", "check", "bank", "other"] = "card"
    status: Literal["paid", "pending"] = "paid"
    recurring: bool = False
    external_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1500)


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


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_coach_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            coach_id BIGINT NOT NULL,
            rate_type TEXT NOT NULL DEFAULT 'hourly',
            rate_cents INTEGER NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            external_reference TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_academy_coach_rates_coach ON academy_coach_rates(coach_id);
        CREATE INDEX IF NOT EXISTS idx_academy_coach_rates_status ON academy_coach_rates(status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_academy_coach_rates_external_ref
            ON academy_coach_rates(external_reference);

        CREATE TABLE IF NOT EXISTS academy_coach_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            coach_id BIGINT NOT NULL,
            amount_cents INTEGER NOT NULL,
            paid_on TEXT NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'bank',
            hours_worked REAL,
            period_start TEXT,
            period_end TEXT,
            status TEXT NOT NULL DEFAULT 'paid',
            external_reference TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_academy_coach_payments_coach ON academy_coach_payments(coach_id);
        CREATE INDEX IF NOT EXISTS idx_academy_coach_payments_date ON academy_coach_payments(paid_on);
        CREATE INDEX IF NOT EXISTS idx_academy_coach_payments_status ON academy_coach_payments(status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_academy_coach_payments_external_ref
            ON academy_coach_payments(external_reference);

        CREATE TABLE IF NOT EXISTS academy_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            expense_type TEXT NOT NULL,
            category TEXT NOT NULL,
            vendor TEXT NOT NULL,
            facility_name TEXT,
            amount_cents INTEGER NOT NULL,
            expense_date TEXT NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'card',
            status TEXT NOT NULL DEFAULT 'paid',
            recurring INTEGER NOT NULL DEFAULT 0,
            external_reference TEXT,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_academy_expenses_type ON academy_expenses(expense_type);
        CREATE INDEX IF NOT EXISTS idx_academy_expenses_date ON academy_expenses(expense_date);
        CREATE INDEX IF NOT EXISTS idx_academy_expenses_status ON academy_expenses(status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_academy_expenses_external_ref
            ON academy_expenses(external_reference);
    """
    with connection() as conn:
        conn.executescript(schema)


def _coach_rate(rate_id: int) -> dict:
    row = fetch_one(
        """
        SELECT r.*,c.first_name AS coach_first_name,c.last_name AS coach_last_name,c.preferred_name AS coach_preferred_name
        FROM academy_coach_rates r
        JOIN coaches c ON c.id=r.coach_id
        WHERE r.id=?
        """,
        (rate_id,),
    )
    if not row:
        raise HTTPException(404, "Coach rate not found")
    row["coach_name"] = (
        row.get("coach_preferred_name")
        or f"{row.get('coach_first_name') or ''} {row.get('coach_last_name') or ''}".strip()
    )
    return row


def _coach_payment(payment_id: int) -> dict:
    row = fetch_one(
        """
        SELECT p.*,c.first_name AS coach_first_name,c.last_name AS coach_last_name,c.preferred_name AS coach_preferred_name
        FROM academy_coach_payments p
        JOIN coaches c ON c.id=p.coach_id
        WHERE p.id=?
        """,
        (payment_id,),
    )
    if not row:
        raise HTTPException(404, "Coach payment not found")
    row["coach_name"] = (
        row.get("coach_preferred_name")
        or f"{row.get('coach_first_name') or ''} {row.get('coach_last_name') or ''}".strip()
    )
    return row


def _expense(expense_id: int) -> dict:
    row = fetch_one("SELECT * FROM academy_expenses WHERE id=?", (expense_id,))
    if not row:
        raise HTTPException(404, "Expense not found")
    row["recurring"] = bool(row.get("recurring"))
    return row


def _month_bounds(month: str | None) -> tuple[str, str, str]:
    if month is None:
        today = date.today()
        month = today.strftime("%Y-%m")
    try:
        year_text, month_text = month.split("-", 1)
        year = int(year_text)
        month_number = int(month_text)
        start = date(year, month_number, 1)
    except Exception as exc:
        raise HTTPException(422, "month must be YYYY-MM") from exc
    if month_number == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month_number + 1, 1)
    return month, start.isoformat(), end.isoformat()


def operations_summary_for_month(month: str | None = None) -> dict:
    month, start, end = _month_bounds(month)
    academy_paid = fetch_one(
        """
        SELECT COALESCE(SUM(amount_cents),0) AS total,COUNT(*) AS count
        FROM academy_expenses
        WHERE expense_type='academy' AND status='paid' AND expense_date>=? AND expense_date<?
        """,
        (start, end),
    ) or {"total": 0, "count": 0}
    facility_paid = fetch_one(
        """
        SELECT COALESCE(SUM(amount_cents),0) AS total,COUNT(*) AS count
        FROM academy_expenses
        WHERE expense_type='facility' AND status='paid' AND expense_date>=? AND expense_date<?
        """,
        (start, end),
    ) or {"total": 0, "count": 0}
    coach_rates = fetch_one(
        "SELECT COUNT(DISTINCT coach_id) AS count FROM academy_coach_rates WHERE status='active'"
    ) or {"count": 0}
    coach_paid = fetch_one(
        """
        SELECT COALESCE(SUM(amount_cents),0) AS total,COUNT(*) AS count
        FROM academy_coach_payments
        WHERE status='paid' AND paid_on>=? AND paid_on<?
        """,
        (start, end),
    ) or {"total": 0, "count": 0}
    pending = fetch_one(
        """
        SELECT COALESCE(SUM(amount_cents),0) AS total,COUNT(*) AS count
        FROM academy_expenses
        WHERE status='pending' AND expense_date>=? AND expense_date<?
        """,
        (start, end),
    ) or {"total": 0, "count": 0}
    return {
        "month": month,
        "coach_rates_configured": int(coach_rates.get("count") or 0),
        "coach_salary_payment_count": int(coach_paid.get("count") or 0),
        "coach_salary_tracking_configured": int(coach_rates.get("count") or 0) > 0,
        "coach_salary_paid_mtd_cents": int(coach_paid.get("total") or 0),
        "academy_expense_count": int(academy_paid.get("count") or 0),
        "academy_expenses_mtd_cents": int(academy_paid.get("total") or 0),
        "facility_expense_count": int(facility_paid.get("count") or 0),
        "facility_payments_mtd_cents": int(facility_paid.get("total") or 0),
        "pending_expense_count": int(pending.get("count") or 0),
        "pending_expenses_cents": int(pending.get("total") or 0),
    }


_ensure_tables()


@router.get("/coach-rates")
def coach_rates(coach_id: int | None = None, status: str | None = None):
    sql = "SELECT id FROM academy_coach_rates WHERE 1=1"
    params: list[object] = []
    if coach_id is not None:
        sql += " AND coach_id=?"
        params.append(coach_id)
    if status is not None:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY effective_from DESC,id DESC"
    return [_coach_rate(int(row["id"])) for row in fetch_all(sql, params)]


@router.post("/coach-rates", status_code=201)
def create_coach_rate(payload: CoachRatePayload):
    _iso_date(payload.effective_from, "Effective from")
    if payload.effective_to:
        end = _iso_date(payload.effective_to, "Effective to")
        if end < _iso_date(payload.effective_from, "Effective from"):
            raise HTTPException(422, "Effective to cannot be before effective from")
    ref = _clean(payload.external_reference)
    if ref:
        existing = fetch_one("SELECT id FROM academy_coach_rates WHERE external_reference=?", (ref,))
        if existing:
            row = _coach_rate(int(existing["id"]))
            if (
                int(row["coach_id"]) == payload.coach_id
                and str(row["rate_type"]) == payload.rate_type
                and int(row["rate_cents"]) == payload.rate_cents
                and str(row["effective_from"]) == payload.effective_from
            ):
                return row
            raise HTTPException(409, "External reference is already used by a different coach rate")
    with connection() as conn:
        coach = conn.execute("SELECT id FROM coaches WHERE id=?", (payload.coach_id,)).fetchone()
        if not coach:
            raise HTTPException(404, "Coach not found")
        row = conn.execute(
            """
            INSERT INTO academy_coach_rates(
                academy_id,coach_id,rate_type,rate_cents,effective_from,effective_to,status,external_reference,notes
            ) VALUES(?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (
                _academy_id(conn), payload.coach_id, payload.rate_type, payload.rate_cents,
                payload.effective_from, _clean(payload.effective_to), payload.status, ref, _clean(payload.notes),
            ),
        ).fetchone()
        rate_id = int(row["id"])
    return _coach_rate(rate_id)


@router.get("/coach-payments")
def coach_payments(coach_id: int | None = None, month: str | None = None, status: str | None = None):
    sql = "SELECT id FROM academy_coach_payments WHERE 1=1"
    params: list[object] = []
    if coach_id is not None:
        sql += " AND coach_id=?"
        params.append(coach_id)
    if month is not None:
        _, start, end = _month_bounds(month)
        sql += " AND paid_on>=? AND paid_on<?"
        params.extend([start, end])
    if status is not None:
        if status not in {"paid", "pending"}:
            raise HTTPException(422, "status must be paid or pending")
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY paid_on DESC,id DESC"
    return [_coach_payment(int(row["id"])) for row in fetch_all(sql, params)]


@router.post("/coach-payments", status_code=201)
def create_coach_payment(payload: CoachPaymentPayload):
    _iso_date(payload.paid_on, "Paid on")
    if payload.period_start:
        _iso_date(payload.period_start, "Period start")
    if payload.period_end:
        _iso_date(payload.period_end, "Period end")
    if payload.period_start and payload.period_end:
        if _iso_date(payload.period_end, "Period end") < _iso_date(payload.period_start, "Period start"):
            raise HTTPException(422, "Period end cannot be before period start")
    ref = _clean(payload.external_reference)
    if ref:
        existing = fetch_one("SELECT id FROM academy_coach_payments WHERE external_reference=?", (ref,))
        if existing:
            row = _coach_payment(int(existing["id"]))
            if (
                int(row["coach_id"]) == payload.coach_id
                and int(row["amount_cents"]) == payload.amount_cents
                and str(row["paid_on"]) == payload.paid_on
            ):
                return row
            raise HTTPException(409, "External reference is already used by a different coach payment")
    with connection() as conn:
        coach = conn.execute("SELECT id FROM coaches WHERE id=?", (payload.coach_id,)).fetchone()
        if not coach:
            raise HTTPException(404, "Coach not found")
        row = conn.execute(
            """
            INSERT INTO academy_coach_payments(
                academy_id,coach_id,amount_cents,paid_on,payment_method,hours_worked,
                period_start,period_end,status,external_reference,notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (
                _academy_id(conn), payload.coach_id, payload.amount_cents, payload.paid_on,
                payload.payment_method, payload.hours_worked, _clean(payload.period_start),
                _clean(payload.period_end), payload.status, ref, _clean(payload.notes),
            ),
        ).fetchone()
        payment_id = int(row["id"])
    return _coach_payment(payment_id)


@router.get("/expenses")
def expenses(expense_type: str | None = None, month: str | None = None, status: str | None = None):
    sql = "SELECT id FROM academy_expenses WHERE 1=1"
    params: list[object] = []
    if expense_type is not None:
        if expense_type not in {"academy", "facility"}:
            raise HTTPException(422, "expense_type must be academy or facility")
        sql += " AND expense_type=?"
        params.append(expense_type)
    if month is not None:
        _, start, end = _month_bounds(month)
        sql += " AND expense_date>=? AND expense_date<?"
        params.extend([start, end])
    if status is not None:
        if status not in {"paid", "pending"}:
            raise HTTPException(422, "status must be paid or pending")
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY expense_date DESC,id DESC"
    return [_expense(int(row["id"])) for row in fetch_all(sql, params)]


@router.post("/expenses", status_code=201)
def create_expense(payload: ExpensePayload):
    _iso_date(payload.expense_date, "Expense date")
    ref = _clean(payload.external_reference)
    if ref:
        existing = fetch_one("SELECT id FROM academy_expenses WHERE external_reference=?", (ref,))
        if existing:
            row = _expense(int(existing["id"]))
            if (
                str(row["expense_type"]) == payload.expense_type
                and str(row["category"]) == payload.category
                and str(row["vendor"]) == payload.vendor
                and int(row["amount_cents"]) == payload.amount_cents
                and str(row["expense_date"]) == payload.expense_date
            ):
                return row
            raise HTTPException(409, "External reference is already used by a different expense")
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO academy_expenses(
                academy_id,expense_type,category,vendor,facility_name,amount_cents,expense_date,
                payment_method,status,recurring,external_reference,notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (
                _academy_id(conn), payload.expense_type, _clean(payload.category), _clean(payload.vendor),
                _clean(payload.facility_name), payload.amount_cents, payload.expense_date,
                payload.payment_method, payload.status, 1 if payload.recurring else 0, ref, _clean(payload.notes),
            ),
        ).fetchone()
        expense_id = int(row["id"])
    return _expense(expense_id)


@router.get("/finance/operations-summary")
def finance_operations_summary(month: str | None = None):
    return operations_summary_for_month(month)
