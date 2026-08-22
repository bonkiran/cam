from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from zoneinfo import ZoneInfo

BASE_URL = os.environ.get("CRICKANALYSIS_BASE_URL", "https://crickanalysis.onrender.com").rstrip("/")

PLAYER_NAMES = [
    ("Aarav", "Patel"), ("Maya", "Rao"), ("Rohan", "Singh"), ("Zoe", "Carter"),
    ("Arjun", "Mehta"), ("Anaya", "Iyer"), ("Vihaan", "Shah"), ("Aditi", "Nair"),
    ("Kabir", "Reddy"), ("Isha", "Kapoor"), ("Neel", "Joshi"), ("Riya", "Menon"),
    ("Dev", "Malhotra"), ("Tara", "Kulkarni"), ("Aryan", "Desai"), ("Saanvi", "Gupta"),
    ("Krish", "Verma"), ("Nisha", "Bhat"), ("Aditya", "Kumar"), ("Meera", "Pillai"),
    ("Ishaan", "Bose"), ("Kavya", "Jain"), ("Reyansh", "Sethi"), ("Siya", "Anand"),
    ("Dhruv", "Khanna"), ("Myra", "Chopra"), ("Arnav", "Saxena"), ("Kiara", "Fernandes"),
    ("Yash", "Chawla"), ("Diya", "Prasad"), ("Samar", "Banerjee"), ("Anika", "George"),
    ("Veer", "Narang"), ("Rhea", "Thomas"), ("Neil", "Mathew"), ("Aanya", "Das"),
    ("Kian", "Joseph"), ("Avni", "Varma"), ("Rishi", "Menon"), ("Leela", "Krishnan"),
    ("Ethan", "Miller"), ("Olivia", "Johnson"), ("Liam", "Davis"), ("Sophia", "Wilson"),
    ("Noah", "Brown"),
]

PARENT_FIRST_NAMES = [
    "Neha", "Anita", "Kiran", "Chris", "Raj", "Lakshmi", "Sameer", "Deepa", "Suresh", "Priya",
    "Vikram", "Anjali", "Manoj", "Kavita", "Rakesh", "Sunita", "Amit", "Pooja", "Naveen", "Rekha",
    "Sanjay", "Meena", "Arun", "Divya", "Rahul", "Nandini", "Vijay", "Shalini", "Mahesh", "Asha",
    "Ravi", "Geeta", "Ajay", "Latha", "Ramesh", "Seema", "Gopal", "Usha", "Vinod", "Radha",
    "Daniel", "Emma", "James", "Grace", "David",
]

SECONDARY_FIRST_NAMES = [
    "Arun", "Vijaya", "Manish", "Laura", "Karthik", "Suma", "Nitin", "Radhika", "Prakash", "Lalitha",
    "Sandeep", "Anu", "Mohan", "Shweta", "Dinesh",
]

COACHES = [
    {
        "first_name": "DEMO Priya", "last_name": "Shah", "preferred_name": "Coach Priya",
        "email": "demo.priya@example.com", "phone": "555-0201",
        "specialties": ["Batting", "Fielding"], "availability": "Mon/Wed evenings; Sat mornings",
        "certifications": "DEMO Level 2 Coaching Certification", "joined_on": "2026-07-15",
        "status": "active", "notes": "DEMO DATA — lead batting coach.", "rate_cents": 5500,
    },
    {
        "first_name": "DEMO Daniel", "last_name": "Brooks", "preferred_name": "Coach Daniel",
        "email": "demo.daniel@example.com", "phone": "555-0202",
        "specialties": ["Fast Bowling", "Fitness"], "availability": "Tue/Thu evenings; Sun mornings",
        "certifications": "DEMO Strength & Conditioning Certificate", "joined_on": "2026-07-20",
        "status": "active", "notes": "DEMO DATA — bowling and conditioning coach.", "rate_cents": 5000,
    },
    {
        "first_name": "DEMO Meera", "last_name": "Nair", "preferred_name": "Coach Meera",
        "email": "demo.meera.coach@example.com", "phone": "555-0203",
        "specialties": ["Spin Bowling", "Batting"], "availability": "Mon/Fri evenings; Sat afternoons",
        "certifications": "DEMO Youth Cricket Coaching Certificate", "joined_on": "2026-07-22",
        "status": "active", "notes": "DEMO DATA — spin and junior development coach.", "rate_cents": 4800,
    },
    {
        "first_name": "DEMO Arjun", "last_name": "Patel", "preferred_name": "Coach Arjun",
        "email": "demo.arjun.coach@example.com", "phone": "555-0204",
        "specialties": ["Advanced Batting", "Wicketkeeping"], "availability": "Wed/Fri evenings; weekends",
        "certifications": "DEMO Advanced Batting Coach", "joined_on": "2026-07-25",
        "status": "active", "notes": "DEMO DATA — advanced batting specialist.", "rate_cents": 6000,
    },
    {
        "first_name": "DEMO Michael", "last_name": "Reed", "preferred_name": "Coach Michael",
        "email": "demo.michael.coach@example.com", "phone": "555-0205",
        "specialties": ["Fielding", "Foundation Skills"], "availability": "Tue/Thu afternoons; Sat mornings",
        "certifications": "DEMO Foundation Coaching Certificate", "joined_on": "2026-07-28",
        "status": "active", "notes": "DEMO DATA — foundation and fielding coach.", "rate_cents": 4500,
    },
]

PROGRAMS = [
    {
        "name": "DEMO Junior Foundations", "code": "DEMO-JR-FND",
        "description": "DEMO DATA — U11/U12 foundation cricket skills.", "program_type": "group",
        "age_group": "U11", "skill_level": "Developing", "start_date": "2026-08-01",
        "end_date": "2026-12-15", "status": "active", "fee_name": "DEMO Monthly Junior Fee", "fee_cents": 12000,
    },
    {
        "name": "DEMO U13 Development", "code": "DEMO-U13-DEV",
        "description": "DEMO DATA — intermediate U13 development program.", "program_type": "group",
        "age_group": "U13", "skill_level": "Intermediate", "start_date": "2026-08-01",
        "end_date": "2026-12-15", "status": "active", "fee_name": "DEMO Monthly U13 Fee", "fee_cents": 16000,
    },
    {
        "name": "DEMO U15 Advanced Batting", "code": "DEMO-U15-AB",
        "description": "DEMO DATA — advanced U15 batting development program.", "program_type": "group",
        "age_group": "U15", "skill_level": "Advanced", "start_date": "2026-08-01",
        "end_date": "2026-12-15", "status": "active", "fee_name": "DEMO Monthly U15 Fee", "fee_cents": 20000,
    },
]

ACADEMY_EXPENSES = [
    ("Insurance", "Sports Academy Insurance", 42500, "bank", True),
    ("Software", "Academy Software Services", 18000, "card", True),
    ("Equipment", "Cricket Equipment Warehouse", 65000, "card", False),
    ("Marketing", "Local Sports Marketing", 30000, "card", False),
    ("Medical & Safety", "First Aid Supply Co", 8500, "card", False),
    ("Tournament Fees", "Regional Cricket League", 45000, "bank", False),
    ("Compliance", "Background Check Services", 12000, "card", False),
    ("Uniforms", "Team Print & Apparel", 24000, "card", False),
    ("Office Supplies", "Office Supply Store", 9500, "card", False),
    ("Refreshments", "Academy Water & Snacks", 14000, "card", False),
]

FACILITY_EXPENSES = [
    ("Facility Rental", "Johns Creek Indoor Cricket Center", "Main Indoor Center", 120000, "bank", True),
    ("Ground Rental", "North Fulton Parks", "Weekend Outdoor Ground", 45000, "check", False),
    ("Net Rental", "Cricket Training Center", "Practice Nets 1-3", 30000, "card", False),
    ("Field & Lights", "Sports Complex Operations", "Evening Match Field", 27500, "bank", False),
]


def request(method: str, path: str, payload=None, *, retries: int = 5):
    url = BASE_URL + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": "CrickAnalysis-Full-Demo-Seeder/1.0"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=40) as response:
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


def wait_for_service():
    for attempt in range(1, 61):
        try:
            storage = get("/api/system/storage")
            if storage and storage.get("database") == "postgresql":
                try:
                    summary = get("/api/cam/finance/operations-summary")
                    print(f"service ready on attempt {attempt}: storage={storage}, finance={summary}")
                    return
                except Exception as exc:
                    print(f"finance operations API not live yet on attempt {attempt}: {exc}")
            else:
                print(f"waiting for PostgreSQL on attempt {attempt}: {storage}")
        except Exception as exc:
            print(f"service readiness attempt {attempt}: {exc}")
        time.sleep(10)
    raise RuntimeError("CrickAnalysis service did not become ready with PostgreSQL + finance operations API within 10 minutes")


def find_by(items, key, value):
    wanted = str(value).casefold()
    for item in items or []:
        if str(item.get(key, "")).casefold() == wanted:
            return item
    return None


def guardian_payload(index: int, last_name: str, existing: list[dict] | None = None) -> list[dict]:
    existing = existing or []
    primary_first = PARENT_FIRST_NAMES[index]
    primary = {
        "first_name": primary_first,
        "last_name": last_name,
        "relationship": "Mother" if index % 2 == 0 else "Father",
        "email": f"demo.parent{index+1:02d}@example.com",
        "phone": f"555-{1000+index:04d}",
        "city": "Johns Creek",
        "state": "GA",
        "postal_code": "30024",
        "country": "United States",
        "is_primary": True,
        "billing_contact": True,
        "pickup_authorized": True,
    }
    if existing:
        primary["id"] = int(existing[0]["id"])
    guardians = [primary]
    if index % 3 == 0:
        secondary_index = index // 3
        secondary = {
            "first_name": SECONDARY_FIRST_NAMES[secondary_index],
            "last_name": last_name,
            "relationship": "Father" if index % 2 == 0 else "Mother",
            "email": f"demo.guardian{index+1:02d}@example.com",
            "phone": f"555-{2000+index:04d}",
            "city": "Johns Creek",
            "state": "GA",
            "postal_code": "30024",
            "country": "United States",
            "is_primary": False,
            "billing_contact": False,
            "pickup_authorized": True,
        }
        if len(existing) > 1:
            secondary["id"] = int(existing[1]["id"])
        guardians.append(secondary)
    return guardians


def player_payload(index: int, first: str, last: str, existing: dict | None = None) -> dict:
    group = index // 15
    birth_year = [2016, 2014, 2012][group]
    dob = f"{birth_year}-{(index % 12) + 1:02d}-{(index % 24) + 1:02d}"
    batting = "Left-handed" if index % 5 == 0 else "Right-handed"
    bowling_styles = ["Right-arm medium", "Right-arm off spin", "Right-arm leg spin", "Left-arm medium", "Right-arm fast"]
    skill = ["Developing", "Intermediate", "Advanced"][group]
    guardians = guardian_payload(index, last, (existing or {}).get("guardians") or [])
    return {
        "name": f"DEMO {first} {last}",
        "first_name": first,
        "last_name": last,
        "preferred_name": first,
        "date_of_birth": dob,
        "gender": "Female" if index % 2 else "Male",
        "batting_style": batting,
        "bowling_style": bowling_styles[index % len(bowling_styles)],
        "handedness": "Left" if batting.startswith("Left") else "Right",
        "skill_level": skill,
        "city": "Johns Creek",
        "state": "GA",
        "postal_code": "30024",
        "country": "United States",
        "emergency_contact_name": f"{guardians[0]['first_name']} {last}",
        "emergency_contact_phone": guardians[0]["phone"],
        "joined_on": f"2026-08-{(index % 18) + 1:02d}",
        "status": "active",
        "notes": f"DEMO DATA — player {index+1:02d} of 45 for repeatable academy manual testing.",
        "guardians": guardians,
    }


def ensure_players() -> list[dict]:
    current = get("/api/cam/players")
    by_name = {str(row.get("name") or "").casefold(): row for row in current}
    result = []
    for index, (first, last) in enumerate(PLAYER_NAMES):
        name = f"DEMO {first} {last}"
        existing = by_name.get(name.casefold())
        payload = player_payload(index, first, last, existing)
        if existing:
            saved = put(f"/api/cam/players/{existing['id']}", payload)
            print("updated player", saved["name"], saved["id"])
        else:
            saved = post("/api/cam/players", payload)
            print("created player", saved["name"], saved["id"])
        result.append(saved)
    return result


def ensure_coaches() -> list[dict]:
    current = get("/api/cam/coaches")
    result = []
    for spec in COACHES:
        found = next(
            (
                row for row in current
                if str(row.get("first_name") or "").casefold() == spec["first_name"].casefold()
                and str(row.get("last_name") or "").casefold() == spec["last_name"].casefold()
            ),
            None,
        )
        payload = {key: value for key, value in spec.items() if key != "rate_cents"}
        if found:
            saved = put(f"/api/cam/coaches/{found['id']}", payload)
            print("updated coach", saved.get("preferred_name"), saved["id"])
        else:
            saved = post("/api/cam/coaches", payload)
            print("created coach", saved.get("preferred_name"), saved["id"])
        result.append(saved)
    return result


def ensure_program(spec: dict) -> dict:
    programs = get("/api/cam/programs")
    found = find_by(programs, "name", spec["name"])
    payload = {key: value for key, value in spec.items() if key not in {"fee_name", "fee_cents"}}
    if found:
        return put(f"/api/cam/programs/{found['id']}", payload)
    return post("/api/cam/programs", payload)


def ensure_enrollment(player_id: int, program_id: int) -> dict:
    rows = get(f"/api/cam/enrollments?player_id={player_id}&program_id={program_id}")
    for row in rows:
        if str(row.get("status") or "") in {"active", "frozen"}:
            return row
    return post(
        "/api/cam/enrollments",
        {
            "player_id": player_id,
            "program_id": program_id,
            "enrollment_type": "regular",
            "start_date": "2026-08-01",
            "notes": "DEMO DATA — full academy test dataset enrollment.",
        },
    )


def ensure_fee_plan(spec: dict, program_id: int) -> dict:
    rows = get("/api/cam/fee-plans")
    found = find_by(rows, "name", spec["fee_name"])
    if found:
        if int(found.get("amount_cents") or 0) != int(spec["fee_cents"]):
            raise RuntimeError(f"Existing fee plan {spec['fee_name']} amount does not match expected test amount")
        return found
    return post(
        "/api/cam/fee-plans",
        {
            "name": spec["fee_name"],
            "amount_cents": spec["fee_cents"],
            "currency": "USD",
            "billing_frequency": "monthly",
            "due_day_of_month": 15,
            "program_id": program_id,
            "status": "active",
            "notes": "DEMO DATA — repeatable full-academy fee plan.",
        },
    )


def ensure_billing_config(enrollment_id: int, fee_plan_id: int) -> dict:
    return put(
        f"/api/cam/enrollments/{enrollment_id}/billing",
        {
            "fee_plan_id": fee_plan_id,
            "discount_type": "none",
            "discount_value": 0,
            "notes": "DEMO DATA — automated full-academy billing configuration.",
        },
    )


def ensure_family_account(player: dict, index: int) -> dict:
    rows = get("/api/cam/billing-accounts")
    account_name = f"DEMO Family {index+1:02d} - {player.get('last_name') or 'Family'}"
    found = find_by(rows, "account_name", account_name)
    if found:
        return found
    guardians = player.get("guardians") or []
    primary = next((row for row in guardians if row.get("is_primary")), guardians[0] if guardians else None)
    payload = {
        "account_name": account_name,
        "player_ids": [int(player["id"])],
        "overpayment_allowed": True,
        "status": "active",
        "notes": "DEMO DATA — family billing account for manual testing.",
    }
    if primary and primary.get("id"):
        payload["primary_guardian_id"] = int(primary["id"])
    return post("/api/cam/billing-accounts", payload)


def current_cycle_invoice_by_enrollment(month_start: date) -> dict[int, dict]:
    rows = get("/api/cam/invoices")
    result: dict[int, dict] = {}
    for row in rows:
        if str(row.get("source_type") or "") != "enrollment":
            continue
        if str(row.get("issue_date") or "") != month_start.isoformat():
            continue
        source_id = int(row.get("source_id") or 0)
        if source_id and source_id not in result:
            result[source_id] = row
    return result


def scenario_for(index: int) -> str:
    fixed = ["paid", "partial", "late", "pending"]
    if index < 4:
        return fixed[index]
    if index <= 22:
        return "paid"
    if index <= 31:
        return "partial"
    if index <= 38:
        return "late"
    return "pending"


def ensure_payment_for_scenario(account_id: int, invoice: dict, scenario: str, cycle: str, paid_on: str) -> None:
    total = int(invoice.get("total_cents") or 0)
    paid = int(invoice.get("amount_paid_cents") or 0)
    balance = int(invoice.get("balance_due_cents") or max(0, total - paid))
    if scenario == "paid" and balance > 0:
        post(
            "/api/cam/payments",
            {
                "account_id": account_id,
                "amount_cents": balance,
                "method": "card",
                "received_on": paid_on,
                "idempotency_key": f"full-demo-{cycle}-{invoice['id']}-paid",
                "notes": "DEMO DATA — fully paid monthly academy fee.",
                "allocations": [{"invoice_id": int(invoice["id"]), "amount_cents": balance}],
            },
        )
    elif scenario == "partial" and paid == 0:
        partial = max(1, (total * 40) // 100)
        post(
            "/api/cam/payments",
            {
                "account_id": account_id,
                "amount_cents": partial,
                "method": "cash",
                "received_on": paid_on,
                "idempotency_key": f"full-demo-{cycle}-{invoice['id']}-partial",
                "notes": "DEMO DATA — 40% partial payment for manual testing.",
                "allocations": [{"invoice_id": int(invoice["id"]), "amount_cents": partial}],
            },
        )


def ensure_coach_assignments(players: list[dict], coaches: list[dict]) -> None:
    existing = get("/api/cam/coach-player-assignments")
    active_pairs = {
        (int(row.get("coach_id") or 0), int(row.get("player_id") or 0))
        for row in existing if str(row.get("status") or "") == "active"
    }
    for index, player in enumerate(players):
        coach = coaches[index % len(coaches)]
        pair = (int(coach["id"]), int(player["id"]))
        if pair in active_pairs:
            continue
        post(
            "/api/cam/coach-player-assignments",
            {
                "coach_id": pair[0],
                "player_id": pair[1],
                "assignment_role": "primary",
                "start_date": "2026-08-01",
                "notes": "DEMO DATA — balanced 9-player primary coach assignment.",
            },
        )
        active_pairs.add(pair)


def ensure_coach_rates(coaches: list[dict]) -> None:
    for coach, spec in zip(coaches, COACHES):
        post(
            "/api/cam/coach-rates",
            {
                "coach_id": int(coach["id"]),
                "rate_type": "hourly",
                "rate_cents": int(spec["rate_cents"]),
                "effective_from": "2026-08-01",
                "status": "active",
                "external_reference": f"DEMO-COACH-RATE-{int(coach['id'])}",
                "notes": "DEMO DATA — active hourly coach rate for payroll testing.",
            },
        )


def ensure_expenses(today: date) -> None:
    cycle = today.strftime("%Y-%m")
    for index, (category, vendor, amount, method, recurring) in enumerate(ACADEMY_EXPENSES, start=1):
        expense_date = today.replace(day=min(index + 1, 18)).isoformat()
        post(
            "/api/cam/expenses",
            {
                "expense_type": "cam",
                "category": category,
                "vendor": vendor,
                "amount_cents": amount,
                "expense_date": expense_date,
                "payment_method": method,
                "status": "paid",
                "recurring": recurring,
                "external_reference": f"DEMO-{cycle}-ACADEMY-{index:02d}",
                "notes": "DEMO DATA — academy operating expense for manual testing.",
            },
        )
    for index, (category, vendor, facility, amount, method, recurring) in enumerate(FACILITY_EXPENSES, start=1):
        expense_date = today.replace(day=min(index + 4, 18)).isoformat()
        post(
            "/api/cam/expenses",
            {
                "expense_type": "facility",
                "category": category,
                "vendor": vendor,
                "facility_name": facility,
                "amount_cents": amount,
                "expense_date": expense_date,
                "payment_method": method,
                "status": "paid",
                "recurring": recurring,
                "external_reference": f"DEMO-{cycle}-FACILITY-{index:02d}",
                "notes": "DEMO DATA — facility expense for manual testing.",
            },
        )


def main():
    wait_for_service()
    today = __import__("datetime").datetime.now(ZoneInfo("America/New_York")).date()
    cycle = today.strftime("%Y-%m")
    month_start = today.replace(day=1)
    paid_on = max(month_start, today - timedelta(days=2)).isoformat()
    future_due = (today + timedelta(days=10)).isoformat()
    late_due = (today - timedelta(days=5)).isoformat()

    players = ensure_players()
    if len(players) != 45:
        raise RuntimeError(f"Expected 45 seeded players, got {len(players)}")

    coaches = ensure_coaches()
    if len(coaches) != 5:
        raise RuntimeError(f"Expected 5 seeded coaches, got {len(coaches)}")

    program_rows = [ensure_program(spec) for spec in PROGRAMS]
    fee_plans = [ensure_fee_plan(spec, int(program["id"])) for spec, program in zip(PROGRAMS, program_rows)]

    enrollments = []
    accounts = []
    for index, player in enumerate(players):
        program_index = index // 15
        enrollment = ensure_enrollment(int(player["id"]), int(program_rows[program_index]["id"]))
        ensure_billing_config(int(enrollment["id"]), int(fee_plans[program_index]["id"]))
        enrollments.append(enrollment)
        accounts.append(None)

    existing_invoice_map = current_cycle_invoice_by_enrollment(month_start)
    all_accounts = get("/api/cam/billing-accounts")

    for index, (player, enrollment) in enumerate(zip(players, enrollments)):
        existing_invoice = existing_invoice_map.get(int(enrollment["id"]))
        if existing_invoice:
            account = next(
                (row for row in all_accounts if int(row.get("id") or 0) == int(existing_invoice.get("account_id") or 0)),
                None,
            )
            if not account:
                raise RuntimeError(f"Invoice {existing_invoice.get('id')} references missing billing account")
            accounts[index] = account
            invoice = existing_invoice
        else:
            account = ensure_family_account(player, index)
            accounts[index] = account
            scenario = scenario_for(index)
            due_date = late_due if scenario == "late" else future_due
            invoice = post(
                "/api/cam/invoices/from-enrollment",
                {
                    "account_id": int(account["id"]),
                    "enrollment_id": int(enrollment["id"]),
                    "issue_date": month_start.isoformat(),
                    "due_date": due_date,
                    "description": f"DEMO FULL DATASET {cycle} — {scenario}",
                },
            )
            existing_invoice_map[int(enrollment["id"])] = invoice

        scenario = scenario_for(index)
        # Refresh invoice so payment state reflects any previous seeding/manual changes.
        invoice = get(f"/api/cam/invoices/{invoice['id']}")
        ensure_payment_for_scenario(int(accounts[index]["id"]), invoice, scenario, cycle, paid_on)

    ensure_coach_assignments(players, coaches)
    ensure_coach_rates(coaches)
    ensure_expenses(today)

    refreshed_players = get("/api/cam/players")
    target_names = {f"DEMO {first} {last}" for first, last in PLAYER_NAMES}
    target_players = [row for row in refreshed_players if row.get("name") in target_names]
    guardian_links = sum(len(row.get("guardians") or []) for row in target_players)
    target_coach_names = {(spec["first_name"], spec["last_name"]) for spec in COACHES}
    target_coaches = [
        row for row in get("/api/cam/coaches")
        if (row.get("first_name"), row.get("last_name")) in target_coach_names
    ]
    rates = get("/api/cam/coach-rates?status=active")
    target_coach_ids = {int(row["id"]) for row in target_coaches}
    target_rates = [row for row in rates if int(row.get("coach_id") or 0) in target_coach_ids]
    academy_expenses = get(f"/api/cam/expenses?expense_type=academy&month={cycle}")
    facility_expenses = get(f"/api/cam/expenses?expense_type=facility&month={cycle}")
    target_academy_expenses = [row for row in academy_expenses if str(row.get("external_reference") or "").startswith(f"DEMO-{cycle}-ACADEMY-")]
    target_facility_expenses = [row for row in facility_expenses if str(row.get("external_reference") or "").startswith(f"DEMO-{cycle}-FACILITY-")]

    scenario_counts = {name: 0 for name in ("paid", "partial", "late", "pending")}
    for index in range(45):
        scenario_counts[scenario_for(index)] += 1

    if len(target_players) != 45:
        raise RuntimeError(f"Verification failed: expected 45 target players, got {len(target_players)}")
    if guardian_links != 60:
        raise RuntimeError(f"Verification failed: expected 60 linked parent/guardian records, got {guardian_links}")
    if len(target_coaches) != 5:
        raise RuntimeError(f"Verification failed: expected 5 target coaches, got {len(target_coaches)}")
    if len(target_rates) < 5:
        raise RuntimeError(f"Verification failed: expected at least 5 active target coach rates, got {len(target_rates)}")
    if len(target_academy_expenses) != 10:
        raise RuntimeError(f"Verification failed: expected 10 academy expenses, got {len(target_academy_expenses)}")
    if len(target_facility_expenses) != 4:
        raise RuntimeError(f"Verification failed: expected 4 facility expenses, got {len(target_facility_expenses)}")

    summary = get(f"/api/cam/finance/operations-summary?month={cycle}")
    print("FULL_ACADEMY_DEMO_SEED_COMPLETE")
    print(json.dumps({
        "base_url": BASE_URL,
        "cycle": cycle,
        "players": len(target_players),
        "linked_parents_guardians": guardian_links,
        "coaches": len(target_coaches),
        "coach_rates": len(target_rates),
        "fee_plans": [
            {"name": plan["name"], "amount_cents": int(plan["amount_cents"])} for plan in fee_plans
        ],
        "finance_scenarios": scenario_counts,
        "academy_expenses": len(target_academy_expenses),
        "facility_expenses": len(target_facility_expenses),
        "operations_summary": summary,
        "coach_rate_values": {
            spec["preferred_name"]: spec["rate_cents"] for spec in COACHES
        },
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FULL_ACADEMY_DEMO_SEED_FAILED: {exc}", file=sys.stderr)
        raise
