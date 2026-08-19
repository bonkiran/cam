import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-post-track-a-api-")
os.environ["CAM_BOOTSTRAP_TOKEN"] = "post-track-a-bootstrap"
os.environ["CAM_PAYMENT_MODE"] = "sandbox"
os.environ.pop("WEATHER_COM_API_KEY", None)

from fastapi.testclient import TestClient
from app.database import connection, fetch_one
from run import app

client = TestClient(app)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def post(path: str, payload: dict, token: str | None = None, expected=(200, 201)):
    response = client.post(path, json=payload, headers=auth(token) if token else {})
    assert response.status_code in expected, response.text
    return response.json() if response.content else None


def put(path: str, payload: dict, token: str | None = None, expected=(200,)):
    response = client.put(path, json=payload, headers=auth(token) if token else {})
    assert response.status_code in expected, response.text
    return response.json() if response.content else None


def setup_owner_and_family():
    profile = client.put(
        "/api/academy/profile",
        json={
            "name": "CAM Manual Fix Academy",
            "email": "academy@example.test",
            "city": "Johns Creek",
            "state": "GA",
            "postal_code": "30097",
            "country": "United States",
            "timezone": "America/New_York",
        },
    )
    assert profile.status_code == 200, profile.text

    bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"display_name": "Gayatri Owner", "email": "owner@example.test", "password": "OwnerPassword123!"},
        headers={"X-CAM-Bootstrap": "post-track-a-bootstrap"},
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_token = bootstrap.json()["token"]

    player = post(
        "/api/academy/players",
        {
            "name": "Dashboard Player",
            "status": "active",
            "guardians": [
                {
                    "first_name": "Dashboard",
                    "last_name": "Parent",
                    "relationship": "Parent",
                    "email": "parent@example.test",
                    "phone": "4045550100",
                    "is_primary": True,
                    "billing_contact": True,
                    "pickup_authorized": True,
                }
            ],
        },
        owner_token,
    )
    guardian_id = int(player["guardians"][0]["id"])
    program = post(
        "/api/academy/programs",
        {"name": "Dashboard Program", "program_type": "group", "status": "active"},
        owner_token,
    )
    enrollment = post(
        "/api/academy/enrollments",
        {
            "player_id": player["id"],
            "program_id": program["id"],
            "enrollment_type": "regular",
            "start_date": date.today().isoformat(),
        },
        owner_token,
    )
    fee_plan = post(
        "/api/academy/fee-plans",
        {
            "name": "Dashboard Monthly",
            "amount_cents": 17500,
            "currency": "USD",
            "billing_frequency": "monthly",
            "due_day_of_month": 1,
            "program_id": program["id"],
            "status": "active",
        },
        owner_token,
    )
    account = post(
        "/api/academy/billing-accounts",
        {
            "account_name": "Dashboard Family",
            "player_ids": [player["id"]],
            "primary_guardian_id": guardian_id,
            "overpayment_allowed": True,
            "status": "active",
        },
        owner_token,
    )
    put(
        f"/api/academy/enrollments/{enrollment['id']}/billing",
        {"fee_plan_id": fee_plan["id"], "discount_type": "none", "discount_value": 0},
        owner_token,
    )
    today = date.today()
    invoice = post(
        "/api/academy/invoices/from-enrollment",
        {
            "account_id": account["id"],
            "enrollment_id": enrollment["id"],
            "issue_date": today.isoformat(),
            "due_date": (today + timedelta(days=10)).isoformat(),
            "description": "Parent full-payment policy invoice",
        },
        owner_token,
    )
    parent_user = post(
        "/api/academy/access/users",
        {
            "display_name": "Dashboard Parent",
            "email": "parent.login@example.test",
            "password": "ParentPassword123!",
            "role": "parent",
            "guardian_id": guardian_id,
            "status": "active",
        },
        owner_token,
    )
    login = post(
        "/api/auth/login",
        {"email": "parent.login@example.test", "password": "ParentPassword123!"},
    )
    parent_token = login["token"]
    method = post(
        "/api/academy/parent/payment-methods/sandbox",
        {"card_number": "4242424242424242", "exp_month": 12, "exp_year": 2034, "cvc": "123", "make_default": True},
        parent_token,
    )
    coach = post(
        "/api/academy/coaches",
        {"first_name": "Smoke", "last_name": "Coach", "status": "active", "specialties": ["Batting"]},
        owner_token,
    )
    return {
        "owner_token": owner_token,
        "parent_token": parent_token,
        "player": player,
        "guardian_id": guardian_id,
        "program": program,
        "account": account,
        "invoice": invoice,
        "method": method,
        "coach": coach,
        "parent_user": parent_user,
    }


def seed_dashboard_operations(data: dict, as_of: date):
    yesterday = as_of - timedelta(days=1)
    upcoming = as_of + timedelta(days=2)
    with connection() as conn:
        academy_id = int(conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()["id"])
        batch = conn.execute(
            "INSERT INTO batches(academy_id,program_id,name,capacity,status) VALUES(?,?,?,12,'active') RETURNING id",
            (academy_id, int(data["program"]["id"]), "Dashboard Batch"),
        ).fetchone()
        batch_id = int(batch["id"])
        group_session = conn.execute(
            """
            INSERT INTO academy_sessions(academy_id,batch_id,coach_id,session_kind,session_date,start_time,duration_minutes,timezone,status,location)
            VALUES(?,?,?,'batch',?,'18:00',90,'America/New_York','scheduled','Main Nets') RETURNING id
            """,
            (academy_id, batch_id, int(data["coach"]["id"]), as_of.isoformat()),
        ).fetchone()
        private_session = conn.execute(
            """
            INSERT INTO academy_sessions(academy_id,coach_id,session_kind,session_date,start_time,duration_minutes,timezone,status,location)
            VALUES(?,?,'private',?,'16:00',60,'America/New_York','scheduled','Private Net') RETURNING id
            """,
            (academy_id, int(data["coach"]["id"]), as_of.isoformat()),
        ).fetchone()
        yesterday_session = conn.execute(
            """
            INSERT INTO academy_sessions(academy_id,batch_id,coach_id,session_kind,session_date,start_time,duration_minutes,timezone,status,location)
            VALUES(?,?,?,'batch',?,'18:00',90,'America/New_York','scheduled','Main Nets') RETURNING id
            """,
            (academy_id, batch_id, int(data["coach"]["id"]), yesterday.isoformat()),
        ).fetchone()
        for session_id in (int(group_session["id"]), int(private_session["id"]), int(yesterday_session["id"])):
            conn.execute(
                "INSERT INTO session_players(session_id,player_id,participation_type) VALUES(?,?,'roster')",
                (session_id, int(data["player"]["id"])),
            )
        conn.execute(
            """
            INSERT INTO player_attendance(academy_id,session_id,player_id,status,make_up_eligible)
            VALUES(?,?,?,'late',0)
            """,
            (academy_id, int(yesterday_session["id"]), int(data["player"]["id"])),
        )
        conn.execute(
            "INSERT INTO coach_attendance(academy_id,session_id,coach_id,status) VALUES(?,?,?,'present')",
            (academy_id, int(yesterday_session["id"]), int(data["coach"]["id"])),
        )
        team = conn.execute(
            "INSERT INTO academy_teams(academy_id,name,status) VALUES(?,'Dashboard XI','active') RETURNING id",
            (academy_id,),
        ).fetchone()
        match = conn.execute(
            """
            INSERT INTO academy_matches(academy_id,team_id,opponent,match_date,start_time,venue,status)
            VALUES(?,?,?,?,'09:00','Central Ground','scheduled') RETURNING id
            """,
            (academy_id, int(team["id"]), "Weekend CC", upcoming.isoformat()),
        ).fetchone()
        conn.execute(
            "INSERT INTO academy_match_squad(match_id,player_id,is_captain,is_wicketkeeper) VALUES(?,?,0,0)",
            (int(match["id"]), int(data["player"]["id"])),
        )
        conn.execute(
            """
            INSERT INTO academy_invoices(academy_id,account_id,invoice_number,issue_date,due_date,status,subtotal_cents,total_cents)
            VALUES(?,?,?,? ,?,'open',10000,10000)
            """,
            (academy_id, int(data["account"]["id"]), "INV-DASH-PENDING", as_of.isoformat(), (as_of + timedelta(days=3)).isoformat()),
        )
        conn.execute(
            """
            INSERT INTO academy_invoices(academy_id,account_id,invoice_number,issue_date,due_date,status,subtotal_cents,total_cents)
            VALUES(?,?,?,? ,?,'open',5000,5000)
            """,
            (academy_id, int(data["account"]["id"]), "INV-DASH-LATE", (as_of - timedelta(days=10)).isoformat(), yesterday.isoformat()),
        )
    return int(match["id"])


def test_parent_partial_payment_is_rejected_and_full_payment_succeeds():
    data = setup_owner_and_family()
    partial = client.post(
        f"/api/academy/parent/invoices/{data['invoice']['id']}/pay",
        json={"payment_method_id": data["method"]["id"], "amount_cents": 5000},
        headers=auth(data["parent_token"]),
    )
    assert partial.status_code == 409, partial.text
    assert "full invoice balance" in partial.text
    unchanged = client.get(
        "/api/academy/parent/billing",
        headers=auth(data["parent_token"]),
    )
    assert unchanged.status_code == 200, unchanged.text
    invoice = unchanged.json()["accounts"][0]["invoices"][0]
    assert int(invoice["balance_due_cents"]) == 17500

    full = client.post(
        f"/api/academy/parent/invoices/{data['invoice']['id']}/pay",
        json={"payment_method_id": data["method"]["id"]},
        headers=auth(data["parent_token"]),
    )
    assert full.status_code == 200, full.text
    assert int(full.json()["payment"]["amount_cents"]) == 17500
    paid = client.get("/api/academy/parent/billing", headers=auth(data["parent_token"])).json()
    assert int(paid["accounts"][0]["invoices"][0]["balance_due_cents"]) == 0

    first_dashboard = client.get("/api/academy/dashboard/operations", headers=auth(data["owner_token"]))
    assert first_dashboard.status_code == 200, first_dashboard.text
    as_of = date.fromisoformat(first_dashboard.json()["as_of"])
    match_id = seed_dashboard_operations(data, as_of)

    dashboard = client.get("/api/academy/dashboard/operations", headers=auth(data["owner_token"]))
    assert dashboard.status_code == 200, dashboard.text
    body = dashboard.json()
    assert body["user"]["display_name"] == "Gayatri Owner"
    assert body["academy"]["name"] == "CAM Manual Fix Academy"
    assert body["metrics"]["fee_received_mtd_cents"] >= 17500
    assert body["metrics"]["fee_pending_cents"] == 10000
    assert body["metrics"]["fee_late_cents"] == 5000
    assert len(body["today_sessions"]["group"]) == 1
    assert len(body["today_sessions"]["private"]) == 1
    yesterday = body["yesterday_attendance"]["sessions"]
    assert len(yesterday) == 1
    assert yesterday[0]["late"] == 1
    assert yesterday[0]["coach_status"] == "present"
    assert body["weather"]["provider"] == "The Weather Company / weather.com"
    assert body["weather"]["status"] == "api_key_required"
    assert body["upcoming_matches"][0]["awaiting"] == 1
    assert body["upcoming_matches"][0]["confirmed"] == 0

    confirmation = client.put(
        f"/api/academy/matches/{match_id}/confirmations/{data['player']['id']}",
        json={"status": "confirmed"},
        headers=auth(data["owner_token"]),
    )
    assert confirmation.status_code == 200, confirmation.text
    assert confirmation.json()["summary"]["confirmed"] == 1
    assert confirmation.json()["summary"]["awaiting"] == 0

    refreshed = client.get("/api/academy/dashboard/operations", headers=auth(data["owner_token"])).json()
    assert refreshed["upcoming_matches"][0]["confirmed"] == 1
    assert refreshed["upcoming_matches"][0]["awaiting"] == 0
