from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE_URL = os.environ.get("CRICKANALYSIS_BASE_URL", "https://crickanalysis.onrender.com").rstrip("/")


def request(method: str, path: str, payload=None, *, retries: int = 4):
    url = BASE_URL + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": "CrickAnalysis-Finance-Demo-Seeder/1.0"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last = RuntimeError(f"{method} {path} -> HTTP {exc.code}: {body}")
            if exc.code < 500:
                raise last
        except Exception as exc:
            last = exc
        if attempt < retries:
            time.sleep(3 * attempt)
    raise RuntimeError(f"{method} {path} failed after {retries} attempts: {last}")


def get(path: str):
    return request("GET", path)


def post(path: str, payload):
    return request("POST", path, payload)


def put(path: str, payload):
    return request("PUT", path, payload)


def wait_for_postgres():
    for attempt in range(1, 31):
        try:
            state = get("/api/system/storage")
            print(f"storage attempt {attempt}: {state}")
            if state and state.get("database") == "postgresql":
                return
        except Exception as exc:
            print(f"storage attempt {attempt}: {exc}")
        time.sleep(10)
    raise RuntimeError("Live service did not report PostgreSQL within 5 minutes")


def find_by(items, key, value):
    wanted = str(value).casefold()
    for item in items or []:
        if str(item.get(key, "")).casefold() == wanted:
            return item
    return None


def require_named(items, key, value, label):
    found = find_by(items, key, value)
    if not found:
        raise RuntimeError(
            f"Missing {label} {value!r}. Run scripts/seed_live_demo.py first, then rerun this finance seeder."
        )
    return found


def current_enrollment(player_id: int, program_id: int):
    rows = get(f"/api/academy/enrollments?player_id={player_id}&program_id={program_id}")
    for row in rows:
        if str(row.get("status") or "") in {"active", "frozen"}:
            return row
    raise RuntimeError(
        f"No active/frozen enrollment for player_id={player_id}, program_id={program_id}. "
        "Run scripts/seed_live_demo.py first."
    )


def ensure_fee_plan(name: str, amount_cents: int, program_id: int):
    rows = get("/api/academy/fee-plans")
    found = find_by(rows, "name", name)
    if found:
        print("reuse fee plan", found["name"], found["id"])
        return found
    created = post(
        "/api/academy/fee-plans",
        {
            "name": name,
            "amount_cents": amount_cents,
            "currency": "USD",
            "billing_frequency": "monthly",
            "due_day_of_month": 15,
            "program_id": program_id,
            "status": "active",
            "notes": "DEMO DATA — repeatable manual finance testing.",
        },
    )
    print("created fee plan", created["name"], created["id"])
    return created


def ensure_billing_account(name: str, player_ids: list[int]):
    rows = get("/api/academy/billing-accounts")
    found = find_by(rows, "account_name", name)
    if found:
        existing_ids = {int(row["player_id"]) for row in found.get("players", [])}
        if not set(player_ids).issubset(existing_ids):
            raise RuntimeError(
                f"Existing billing account {name!r} does not contain all DEMO players. "
                "Use a new DEMO account name before rerunning."
            )
        print("reuse billing account", found["account_name"], found["id"])
        return found
    created = post(
        "/api/academy/billing-accounts",
        {
            "account_name": name,
            "player_ids": player_ids,
            "overpayment_allowed": True,
            "status": "active",
            "notes": "DEMO DATA — finance scenarios for manual testing.",
        },
    )
    print("created billing account", created["account_name"], created["id"])
    return created


def configure_billing(enrollment_id: int, fee_plan_id: int):
    configured = put(
        f"/api/academy/enrollments/{enrollment_id}/billing",
        {
            "fee_plan_id": fee_plan_id,
            "discount_type": "none",
            "discount_value": 0,
            "notes": "DEMO DATA — automated finance fixture.",
        },
    )
    print("configured enrollment billing", enrollment_id, "-> fee plan", fee_plan_id)
    return configured


def ensure_invoice(account_id: int, enrollment_id: int, issue_date: str, due_date: str, description: str):
    rows = get(f"/api/academy/invoices?account_id={account_id}")
    for row in rows:
        if (
            str(row.get("source_type") or "") == "enrollment"
            and int(row.get("source_id") or 0) == enrollment_id
            and str(row.get("issue_date") or "") == issue_date
        ):
            print("reuse invoice", row.get("invoice_number"), row.get("id"), description)
            return row
    created = post(
        "/api/academy/invoices/from-enrollment",
        {
            "account_id": account_id,
            "enrollment_id": enrollment_id,
            "issue_date": issue_date,
            "due_date": due_date,
            "description": description,
        },
    )
    print("created invoice", created.get("invoice_number"), created.get("id"), description)
    return created


def ensure_payment(account_id: int, invoice: dict, amount_cents: int, method: str, received_on: str, key: str, notes: str):
    payment = post(
        "/api/academy/payments",
        {
            "account_id": account_id,
            "amount_cents": amount_cents,
            "method": method,
            "received_on": received_on,
            "idempotency_key": key,
            "notes": notes,
            "allocations": [{"invoice_id": int(invoice["id"]), "amount_cents": amount_cents}],
        },
    )
    print("ensured payment", payment.get("receipt_number"), payment.get("id"), amount_cents, method)
    return payment


def roll_forward_old_demo_balances(account_id: int, demo_enrollment_ids: set[int], month_start: date):
    previous_period_date = month_start - timedelta(days=1)
    rows = get(f"/api/academy/invoices?account_id={account_id}")
    settled = []
    for invoice in rows:
        if str(invoice.get("source_type") or "") != "enrollment":
            continue
        if int(invoice.get("source_id") or 0) not in demo_enrollment_ids:
            continue
        try:
            issued = date.fromisoformat(str(invoice.get("issue_date")))
        except Exception:
            continue
        if issued >= month_start:
            continue
        balance = int(invoice.get("balance_due_cents") or 0)
        if balance <= 0:
            continue
        payment = ensure_payment(
            account_id,
            invoice,
            balance,
            "other",
            previous_period_date.isoformat(),
            f"demo-finance-rollforward-{invoice['id']}",
            "DEMO DATA — closes prior-period manual-test balance before creating the current test cycle.",
        )
        settled.append(payment)
    return settled


def main():
    wait_for_postgres()

    today = date.today()
    cycle = today.strftime("%Y-%m")
    month_start = today.replace(day=1)
    paid_on = max(month_start, today - timedelta(days=4))
    partial_on = max(month_start, today - timedelta(days=3))
    future_due = today + timedelta(days=10)
    future_due_2 = today + timedelta(days=14)

    if today.day >= 7:
        late_issue = month_start
        late_due = today - timedelta(days=5)
    else:
        late_issue = today - timedelta(days=20)
        late_due = today - timedelta(days=5)

    players = get("/api/academy/players")
    programs = get("/api/academy/programs")

    aarav = require_named(players, "name", "DEMO Aarav Patel", "player")
    maya = require_named(players, "name", "DEMO Maya Rao", "player")
    rohan = require_named(players, "name", "DEMO Rohan Singh", "player")
    zoe = require_named(players, "name", "DEMO Zoe Carter", "player")

    advanced = require_named(programs, "name", "DEMO U15 Advanced Batting", "program")
    foundation = require_named(programs, "name", "DEMO Junior Foundations", "program")

    enrollments = {
        "aarav": current_enrollment(int(aarav["id"]), int(advanced["id"])),
        "maya": current_enrollment(int(maya["id"]), int(advanced["id"])),
        "rohan": current_enrollment(int(rohan["id"]), int(advanced["id"])),
        "zoe": current_enrollment(int(zoe["id"]), int(foundation["id"])),
    }

    advanced_plan = ensure_fee_plan("DEMO Monthly U15 Fee", 20000, int(advanced["id"]))
    foundation_plan = ensure_fee_plan("DEMO Monthly Junior Fee", 12000, int(foundation["id"]))

    for key in ("aarav", "maya", "rohan"):
        configure_billing(int(enrollments[key]["id"]), int(advanced_plan["id"]))
    configure_billing(int(enrollments["zoe"]["id"]), int(foundation_plan["id"]))

    account = ensure_billing_account(
        "DEMO Finance Test Family",
        [int(aarav["id"]), int(maya["id"]), int(rohan["id"]), int(zoe["id"])],
    )
    account_id = int(account["id"])

    demo_enrollment_ids = {int(value["id"]) for value in enrollments.values()}
    roll_forward_old_demo_balances(account_id, demo_enrollment_ids, month_start)

    paid_invoice = ensure_invoice(
        account_id,
        int(enrollments["aarav"]["id"]),
        month_start.isoformat(),
        future_due.isoformat(),
        f"DEMO FINANCE {cycle} — paid in full",
    )
    partial_invoice = ensure_invoice(
        account_id,
        int(enrollments["maya"]["id"]),
        month_start.isoformat(),
        future_due.isoformat(),
        f"DEMO FINANCE {cycle} — partial payment",
    )
    late_invoice = ensure_invoice(
        account_id,
        int(enrollments["rohan"]["id"]),
        late_issue.isoformat(),
        late_due.isoformat(),
        f"DEMO FINANCE {cycle} — overdue unpaid",
    )
    pending_invoice = ensure_invoice(
        account_id,
        int(enrollments["zoe"]["id"]),
        month_start.isoformat(),
        future_due_2.isoformat(),
        f"DEMO FINANCE {cycle} — open not yet due",
    )

    ensure_payment(
        account_id,
        paid_invoice,
        20000,
        "card",
        paid_on.isoformat(),
        f"demo-finance-paid-{cycle}-{paid_invoice['id']}",
        "DEMO DATA — fully paid invoice.",
    )
    ensure_payment(
        account_id,
        partial_invoice,
        8000,
        "cash",
        partial_on.isoformat(),
        f"demo-finance-partial-{cycle}-{partial_invoice['id']}",
        "DEMO DATA — partial payment leaves $120 outstanding.",
    )

    final_invoices = get(f"/api/academy/invoices?account_id={account_id}")
    by_id = {int(row["id"]): row for row in final_invoices}
    scenario_rows = [
        ("paid_in_full", by_id[int(paid_invoice["id"])]),
        ("partial_payment", by_id[int(partial_invoice["id"])]),
        ("late_unpaid", by_id[int(late_invoice["id"])]),
        ("pending_unpaid", by_id[int(pending_invoice["id"])]),
    ]

    summary = {
        "base_url": BASE_URL,
        "cycle": cycle,
        "billing_account": account.get("account_name"),
        "scenarios": [
            {
                "scenario": name,
                "invoice_number": row.get("invoice_number"),
                "status": row.get("status"),
                "total_cents": int(row.get("total_cents") or 0),
                "paid_cents": int(row.get("amount_paid_cents") or 0),
                "balance_due_cents": int(row.get("balance_due_cents") or 0),
                "due_date": row.get("due_date"),
            }
            for name, row in scenario_rows
        ],
        "seeded_dashboard_contribution": {
            "fee_received_mtd_cents": 28000,
            "fee_pending_cents": 24000,
            "fee_late_cents": 20000,
        },
        "manual_test_notes": [
            "Aarav: $200 invoice fully paid by card.",
            "Maya: $200 invoice with $80 cash partial payment; $120 remains.",
            "Rohan: $200 invoice overdue and unpaid.",
            "Zoe: $120 invoice open and not yet due.",
        ],
    }
    print("FINANCE_DEMO_SEED_COMPLETE")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FINANCE_DEMO_SEED_FAILED: {exc}", file=sys.stderr)
        raise
