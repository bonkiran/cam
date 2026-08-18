import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-rbac-enforcement-api-test-")
os.environ["CAM_BOOTSTRAP_TOKEN"] = "rbac-enforcement-bootstrap"
os.environ["CAM_PAYMENT_MODE"] = "sandbox"

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _reset_shared_postgres_state() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    import psycopg

    candidates = [
        "academy_billing_security_audit",
        "academy_saved_payment_methods",
        "academy_review_actions",
        "academy_player_reviews",
        "academy_refunds",
        "academy_payment_allocations",
        "academy_payments",
        "academy_invoice_items",
        "academy_invoices",
        "academy_enrollment_billing",
        "academy_billing_account_players",
        "academy_billing_accounts",
        "academy_fee_plans",
        "academy_auth_sessions",
        "academy_access_audit",
        "academy_users",
        "session_attendance",
        "session_players",
        "academy_sessions",
        "batch_coach_assignments",
        "batch_players",
        "batches",
        "coaches",
        "enrollments",
        "programs",
        "player_guardians",
        "guardians",
        "players",
        "academies",
    ]
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            existing = []
            for table in candidates:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cursor.fetchone()[0] is not None:
                    existing.append(table)
            if existing:
                cursor.execute(f"TRUNCATE TABLE {', '.join(existing)} RESTART IDENTITY CASCADE")
        conn.commit()


def _post(path: str, payload: dict, token: str | None = None, expected=(200, 201)):
    response = client.post(path, json=payload, headers=_auth(token) if token else {})
    assert response.status_code in expected, response.text
    return response.json() if response.content else None


def _login(email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _create_user(owner_token: str, **payload):
    response = client.post("/api/academy/access/users", json=payload, headers=_auth(owner_token))
    assert response.status_code == 201, response.text
    return response.json()


def test_legacy_management_is_owner_admin_only_after_bootstrap():
    _reset_shared_postgres_state()

    # Migration/setup compatibility: before the first access user exists, the
    # Academy can establish its profile and seed core records.
    profile = client.put("/api/academy/profile", json={"name": "RBAC Test Academy"})
    assert profile.status_code == 200, profile.text
    player = _post(
        "/api/academy/players",
        {
            "name": "RBAC Aarav Patel",
            "status": "active",
            "guardians": [
                {
                    "first_name": "Priya",
                    "last_name": "Patel",
                    "relationship": "Mother",
                    "email": "priya.rbac@example.test",
                    "phone": "4045550199",
                    "is_primary": True,
                    "billing_contact": True,
                }
            ],
        },
    )
    guardian_id = int(player["guardians"][0]["id"])

    bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"display_name": "RBAC Owner", "email": "owner.rbac@example.test", "password": "OwnerRBAC!123"},
        headers={"X-CAM-Bootstrap": "rbac-enforcement-bootstrap"},
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_token = bootstrap.json()["token"]

    # After bootstrap, anonymous access to generic Academy management is closed.
    anonymous_players = client.get("/api/academy/players")
    assert anonymous_players.status_code == 401, anonymous_players.text
    anonymous_program = client.post(
        "/api/academy/programs",
        json={"name": "Anonymous Program", "program_type": "group", "status": "active"},
    )
    assert anonymous_program.status_code == 401, anonymous_program.text

    # Owner remains fully operational through the generic management surface.
    owner_players = client.get("/api/academy/players", headers=_auth(owner_token))
    assert owner_players.status_code == 200, owner_players.text
    assert any(int(row["id"]) == int(player["id"]) for row in owner_players.json())
    owner_program = client.post(
        "/api/academy/programs",
        json={"name": "Owner U13 Program", "program_type": "group", "status": "active"},
        headers=_auth(owner_token),
    )
    assert owner_program.status_code == 201, owner_program.text

    # Create the reference records needed for role-linked users using Owner auth.
    coach = client.post(
        "/api/academy/coaches",
        json={"first_name": "Maya", "last_name": "Coach", "email": "maya.rbac@example.test", "status": "active"},
        headers=_auth(owner_token),
    )
    assert coach.status_code == 201, coach.text
    coach_id = int(coach.json()["id"])

    _create_user(
        owner_token,
        display_name="RBAC Admin",
        email="admin.rbac@example.test",
        password="AdminRBAC!123",
        role="admin",
        status="active",
    )
    _create_user(
        owner_token,
        display_name="RBAC Coach",
        email="coach.rbac@example.test",
        password="CoachRBAC!123",
        role="coach",
        coach_id=coach_id,
        status="active",
    )
    _create_user(
        owner_token,
        display_name="Priya Patel",
        email="parent.rbac@example.test",
        password="ParentRBAC!123",
        role="parent",
        guardian_id=guardian_id,
        status="active",
    )
    _create_user(
        owner_token,
        display_name="Aarav Patel",
        email="player.rbac@example.test",
        password="PlayerRBAC!123",
        role="player",
        player_id=int(player["id"]),
        status="active",
    )

    admin_token = _login("admin.rbac@example.test", "AdminRBAC!123")
    coach_token = _login("coach.rbac@example.test", "CoachRBAC!123")
    parent_token = _login("parent.rbac@example.test", "ParentRBAC!123")
    player_token = _login("player.rbac@example.test", "PlayerRBAC!123")

    # Admin has the same generic management boundary as Owner.
    admin_programs = client.get("/api/academy/programs", headers=_auth(admin_token))
    assert admin_programs.status_code == 200, admin_programs.text

    # Non-management roles cannot use generic management endpoints even though
    # their sessions are valid.
    for role_token in (coach_token, parent_token, player_token):
        denied_players = client.get("/api/academy/players", headers=_auth(role_token))
        assert denied_players.status_code == 403, denied_players.text
        denied_fees = client.get("/api/academy/fee-plans", headers=_auth(role_token))
        assert denied_fees.status_code == 403, denied_fees.text

    # Dedicated role-aware surfaces remain reachable and enforce their own scope.
    parent_billing = client.get("/api/academy/parent/billing", headers=_auth(parent_token))
    assert parent_billing.status_code == 200, parent_billing.text
    assert [int(row["id"]) for row in parent_billing.json()["players"]] == [int(player["id"])]

    parent_reviews = client.get("/api/academy/reviews", headers=_auth(parent_token))
    assert parent_reviews.status_code == 200, parent_reviews.text
    assert parent_reviews.json() == []

    access_roles = client.get("/api/academy/access/roles", headers=_auth(owner_token))
    assert access_roles.status_code == 200, access_roles.text
    parent_access_roles = client.get("/api/academy/access/roles", headers=_auth(parent_token))
    assert parent_access_roles.status_code == 403, parent_access_roles.text
