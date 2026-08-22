import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-track-a-core-qa-")
os.environ["CAM_BOOTSTRAP_TOKEN"] = "track-a-bootstrap-token"
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


def _bootstrap_owner() -> str:
    response = client.post(
        "/api/auth/bootstrap",
        json={
            "display_name": "Track A Owner",
            "email": "owner.tracka@example.test",
            "password": "TrackAOwner!123",
        },
        headers={"X-CAM-Bootstrap": "track-a-bootstrap-token"},
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _create_access_user(owner_token: str, **payload):
    response = client.post(
        "/api/cam/access/users",
        json=payload,
        headers=_auth(owner_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def test_track_a_setup_players_guardians_programs_and_rbac_permutations():
    """Track A P0 core QA tranche.

    Explicitly covers the highest-risk gaps in the living QA matrix for
    Academy Setup, Players/Guardians, Programs and the generic RBAC boundary.
    Existing focused suites continue to cover the deeper enrollment and parent
    billing lifecycle permutations and are run beside this test in Track A CI.
    """

    _reset_shared_postgres_state()

    # QA-001 / Setup: create the first valid Academy profile.
    profile = client.put(
        "/api/cam/profile",
        json={
            "name": "Track A Cricket Academy",
            "email": "office.tracka@example.test",
            "city": "Alpharetta",
            "state": "GA",
            "country": "United States",
            "timezone": "America/New_York",
        },
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["configured"] is True
    assert profile.json()["profile"]["name"] == "Track A Cricket Academy"

    # Validation: Academy name shorter than the model minimum is rejected and
    # the existing profile remains unchanged.
    invalid_profile = client.put("/api/cam/profile", json={"name": "A"})
    assert invalid_profile.status_code == 422, invalid_profile.text
    assert client.get("/api/cam/profile").json()["profile"]["name"] == "Track A Cricket Academy"

    # QA-003 / QA-007 / QA-008: create a complete player with two guardians and
    # distinct primary/billing/pickup flags.
    player_payload = {
        "name": "Track A Aarav Patel",
        "first_name": "Aarav",
        "last_name": "Patel",
        "date_of_birth": "2012-04-12",
        "batting_style": "Right-handed",
        "handedness": "Right",
        "skill_level": "Intermediate",
        "status": "active",
        "guardians": [
            {
                "first_name": "Priya",
                "last_name": "Patel",
                "relationship": "Mother",
                "email": "priya.tracka@example.test",
                "phone": "4045550101",
                "is_primary": True,
                "billing_contact": True,
                "pickup_authorized": True,
            },
            {
                "first_name": "Ravi",
                "last_name": "Patel",
                "relationship": "Father",
                "email": "ravi.tracka@example.test",
                "phone": "4045550102",
                "is_primary": False,
                "billing_contact": False,
                "pickup_authorized": False,
            },
        ],
    }
    player_response = client.post("/api/cam/players", json=player_payload)
    assert player_response.status_code == 201, player_response.text
    player = player_response.json()
    player_id = int(player["id"])
    assert len(player["guardians"]) == 2

    priya = next(g for g in player["guardians"] if g["first_name"] == "Priya")
    ravi = next(g for g in player["guardians"] if g["first_name"] == "Ravi")
    assert int(priya["is_primary"]) == 1
    assert int(priya["billing_contact"]) == 1
    assert int(priya["pickup_authorized"]) == 1
    assert int(ravi["is_primary"]) == 0
    assert int(ravi["billing_contact"]) == 0
    assert int(ravi["pickup_authorized"]) == 0

    # QA-004: missing required player display name is rejected without creating
    # a partial player row.
    before_invalid = client.get("/api/cam/players").json()
    invalid_player = client.post(
        "/api/cam/players",
        json={"first_name": "No", "last_name": "Display Name", "status": "active"},
    )
    assert invalid_player.status_code == 422, invalid_player.text
    after_invalid = client.get("/api/cam/players").json()
    assert len(after_invalid) == len(before_invalid)

    # Duplicate names are case-insensitive and must not create a second master
    # player identity.
    duplicate_player = client.post(
        "/api/cam/players",
        json={"name": "track a aarav patel", "status": "active"},
    )
    assert duplicate_player.status_code == 409, duplicate_player.text
    assert len(client.get("/api/cam/players").json()) == len(before_invalid)

    # QA-005: Active -> inactive -> active lifecycle changes preserve the same
    # player ID and the existing guardian relationships.
    inactive = client.put(
        f"/api/cam/players/{player_id}",
        json={"name": player_payload["name"], "status": "inactive"},
    )
    assert inactive.status_code == 200, inactive.text
    assert inactive.json()["status"] == "inactive"
    assert len(inactive.json()["guardians"]) == 2

    reactivated = client.put(
        f"/api/cam/players/{player_id}",
        json={"name": player_payload["name"], "status": "active"},
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "active"
    assert len(reactivated.json()["guardians"]) == 2

    guardian_id = int(priya["id"])

    # Bootstrap closes generic Academy management to anonymous users.
    owner_token = _bootstrap_owner()

    # QA-002: anonymous profile mutation after bootstrap is rejected and does
    # not change the Academy profile.
    anonymous_profile_update = client.put(
        "/api/cam/profile",
        json={"name": "Unauthorized Academy Rename"},
    )
    assert anonymous_profile_update.status_code == 401, anonymous_profile_update.text
    current_profile = client.get("/api/cam/profile", headers=_auth(owner_token))
    assert current_profile.status_code == 200, current_profile.text
    assert current_profile.json()["profile"]["name"] == "Track A Cricket Academy"

    # Owner can update the same protected management record.
    owner_profile_update = client.put(
        "/api/cam/profile",
        json={"name": "Track A Cricket Academy Updated"},
        headers=_auth(owner_token),
    )
    assert owner_profile_update.status_code == 200, owner_profile_update.text

    # Create Admin, Parent and Player identities for explicit role permutations.
    _create_access_user(
        owner_token,
        display_name="Track A Admin",
        email="admin.tracka@example.test",
        password="TrackAAdmin!123",
        role="admin",
        status="active",
    )
    _create_access_user(
        owner_token,
        display_name="Priya Patel",
        email="parent.tracka@example.test",
        password="TrackAParent!123",
        role="parent",
        guardian_id=guardian_id,
        status="active",
    )
    _create_access_user(
        owner_token,
        display_name="Aarav Patel",
        email="player.tracka@example.test",
        password="TrackAPlayer!123",
        role="player",
        player_id=player_id,
        status="active",
    )

    admin_token = _login("admin.tracka@example.test", "TrackAAdmin!123")
    parent_token = _login("parent.tracka@example.test", "TrackAParent!123")
    player_token = _login("player.tracka@example.test", "TrackAPlayer!123")

    # Admin has generic management access; Parent and Player do not.
    assert client.get("/api/cam/players", headers=_auth(admin_token)).status_code == 200
    assert client.get("/api/cam/players", headers=_auth(parent_token)).status_code == 403
    assert client.get("/api/cam/players", headers=_auth(player_token)).status_code == 403
    assert client.get("/api/cam/players").status_code == 401

    # Parent cannot mutate Academy setup either.
    parent_profile_update = client.put(
        "/api/cam/profile",
        json={"name": "Parent Unauthorized Rename"},
        headers=_auth(parent_token),
    )
    assert parent_profile_update.status_code == 403, parent_profile_update.text

    # QA-010 / QA-011: create multiple distinct Programs under Owner access and
    # reject a case-insensitive duplicate.
    program_payloads = [
        {"name": "Track A U11 Beginners", "program_type": "group", "age_group": "U11", "status": "active"},
        {"name": "Track A U13 Development", "program_type": "group", "age_group": "U13", "status": "active"},
        {"name": "Track A Beginners", "program_type": "group", "skill_level": "Beginner", "status": "active"},
    ]
    created_program_ids = []
    for payload in program_payloads:
        response = client.post("/api/cam/programs", json=payload, headers=_auth(owner_token))
        assert response.status_code == 201, response.text
        created_program_ids.append(int(response.json()["id"]))

    programs = client.get("/api/cam/programs", headers=_auth(owner_token))
    assert programs.status_code == 200, programs.text
    assert set(created_program_ids).issubset({int(row["id"]) for row in programs.json()})

    duplicate_program = client.post(
        "/api/cam/programs",
        json={"name": "track a u13 development", "program_type": "group", "status": "active"},
        headers=_auth(owner_token),
    )
    assert duplicate_program.status_code == 409, duplicate_program.text

    # Parent dedicated billing surface remains reachable while generic
    # management stays closed; the linked player must be in family scope.
    parent_billing = client.get("/api/cam/parent/billing", headers=_auth(parent_token))
    assert parent_billing.status_code == 200, parent_billing.text
    assert player_id in {int(row["id"]) for row in parent_billing.json()["players"]}
