import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["CRICKANALYSIS_DATA_DIR"] = tempfile.mkdtemp(prefix="cam-auth-api-test-")
os.environ["CAM_BOOTSTRAP_TOKEN"] = "test-bootstrap-key"

from fastapi.testclient import TestClient
from run import app

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _post(path: str, payload: dict, token: str | None = None, expected=(200, 201)):
    response = client.post(path, json=payload, headers=_auth(token) if token else {})
    assert response.status_code in expected, response.text
    return response.json() if response.content else None


def test_academy_roles_security_end_to_end():
    status_response = client.get("/api/auth/bootstrap-status")
    assert status_response.status_code == 200
    status_json = status_response.json()
    assert status_json["has_users"] is False
    assert status_json["bootstrap_configured"] is True
    assert set(status_json["roles"]) == {"owner", "admin", "coach", "parent", "player"}

    wrong_key = client.post(
        "/api/auth/bootstrap",
        json={"display_name": "Academy Owner", "email": "owner@example.test", "password": "StrongPass!123"},
        headers={"X-CAM-Bootstrap": "wrong-key"},
    )
    assert wrong_key.status_code == 403

    bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"display_name": "Academy Owner", "email": "OWNER@example.test", "password": "StrongPass!123"},
        headers={"X-CAM-Bootstrap": "test-bootstrap-key"},
    )
    assert bootstrap.status_code == 201, bootstrap.text
    bootstrap_json = bootstrap.json()
    owner_token = bootstrap_json["token"]
    owner = bootstrap_json["user"]
    assert owner["role"] == "owner"
    assert owner["email"] == "owner@example.test"
    assert "users.manage" in owner["permissions"]
    assert bootstrap_json["expires_at"]

    second_bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"display_name": "Second Owner", "email": "second@example.test", "password": "AnotherPass!123"},
        headers={"X-CAM-Bootstrap": "test-bootstrap-key"},
    )
    assert second_bootstrap.status_code == 409

    me = client.get("/api/auth/me", headers=_auth(owner_token))
    assert me.status_code == 200
    assert me.json()["id"] == owner["id"]

    no_auth_users = client.get("/api/academy/access/users")
    assert no_auth_users.status_code == 401

    # Create real Academy identities that can be linked to role accounts.
    profile = client.put("/api/academy/profile", json={"name": "Security Test Academy"})
    assert profile.status_code == 200, profile.text
    coach = _post(
        "/api/academy/coaches",
        {"first_name": "Anita", "last_name": "Coach", "email": "anita@example.test", "status": "active"},
    )
    player = _post(
        "/api/academy/players",
        {
            "name": "Security Aarav Patel",
            "status": "active",
            "guardians": [
                {
                    "first_name": "Priya",
                    "last_name": "Patel",
                    "relationship": "Mother",
                    "email": "priya@example.test",
                    "is_primary": True,
                    "billing_contact": True,
                    "pickup_authorized": True,
                }
            ],
        },
    )
    guardian_id = int(player["guardians"][0]["id"])

    reference = client.get("/api/academy/access/reference", headers=_auth(owner_token))
    assert reference.status_code == 200
    reference_json = reference.json()
    assert any(int(row["id"]) == int(coach["id"]) for row in reference_json["coaches"])
    assert any(int(row["id"]) == guardian_id for row in reference_json["guardians"])
    assert any(int(row["id"]) == int(player["id"]) for row in reference_json["players"])

    roles = client.get("/api/academy/access/roles", headers=_auth(owner_token))
    assert roles.status_code == 200
    role_map = {row["role"]: row["permissions"] for row in roles.json()}
    assert "users.manage" in role_map["admin"]
    assert "reviews.manage" in role_map["coach"]
    assert "billing.view" in role_map["parent"]
    assert "self.view" in role_map["player"]

    coach_user = _post(
        "/api/academy/access/users",
        {
            "display_name": "Coach Anita",
            "email": "coach@example.test",
            "password": "CoachPass!123",
            "role": "coach",
            "coach_id": coach["id"],
            "status": "active",
        },
        owner_token,
    )
    assert coach_user["role"] == "coach"
    assert int(coach_user["coach_id"]) == int(coach["id"])
    assert coach_user["linked_name"] == "Anita Coach"

    parent_user = _post(
        "/api/academy/access/users",
        {
            "display_name": "Priya Patel",
            "email": "parent@example.test",
            "password": "ParentPass!123",
            "role": "parent",
            "guardian_id": guardian_id,
            "status": "active",
        },
        owner_token,
    )
    assert parent_user["linked_name"] == "Priya Patel"

    player_user = _post(
        "/api/academy/access/users",
        {
            "display_name": "Aarav Patel",
            "email": "player@example.test",
            "password": "PlayerPass!123",
            "role": "player",
            "player_id": player["id"],
            "status": "active",
        },
        owner_token,
    )
    assert player_user["linked_name"] == "Security Aarav Patel"

    admin_user = _post(
        "/api/academy/access/users",
        {
            "display_name": "Operations Admin",
            "email": "admin@example.test",
            "password": "AdminPass!123",
            "role": "admin",
            "status": "active",
        },
        owner_token,
    )
    assert "users.manage" in admin_user["permissions"]

    duplicate = client.post(
        "/api/academy/access/users",
        json={
            "display_name": "Duplicate",
            "email": "COACH@example.test",
            "password": "Duplicate!123",
            "role": "coach",
            "coach_id": coach["id"],
        },
        headers=_auth(owner_token),
    )
    assert duplicate.status_code == 409

    invalid_link = client.post(
        "/api/academy/access/users",
        json={
            "display_name": "Bad Parent",
            "email": "badparent@example.test",
            "password": "BadParent!123",
            "role": "parent",
            "coach_id": coach["id"],
        },
        headers=_auth(owner_token),
    )
    assert invalid_link.status_code == 422

    users = client.get("/api/academy/access/users", headers=_auth(owner_token))
    assert users.status_code == 200
    assert {row["role"] for row in users.json()} >= {"owner", "admin", "coach", "parent", "player"}

    bad_login = client.post("/api/auth/login", json={"email": "coach@example.test", "password": "wrong-password"})
    assert bad_login.status_code == 401

    coach_login = _post("/api/auth/login", {"email": "coach@example.test", "password": "CoachPass!123"})
    coach_token = coach_login["token"]
    assert coach_login["user"]["role"] == "coach"
    forbidden = client.get("/api/academy/access/users", headers=_auth(coach_token))
    assert forbidden.status_code == 403

    admin_login = _post("/api/auth/login", {"email": "admin@example.test", "password": "AdminPass!123"})
    admin_token = admin_login["token"]
    admin_can_list = client.get("/api/academy/access/users", headers=_auth(admin_token))
    assert admin_can_list.status_code == 200

    disable_coach = client.put(
        f"/api/academy/access/users/{coach_user['id']}",
        json={
            "display_name": "Coach Anita",
            "email": "coach@example.test",
            "role": "coach",
            "coach_id": coach["id"],
            "status": "disabled",
        },
        headers=_auth(owner_token),
    )
    assert disable_coach.status_code == 200
    assert disable_coach.json()["status"] == "disabled"
    revoked = client.get("/api/auth/me", headers=_auth(coach_token))
    assert revoked.status_code == 401

    reenable = client.put(
        f"/api/academy/access/users/{coach_user['id']}",
        json={
            "display_name": "Coach Anita",
            "email": "coach@example.test",
            "role": "coach",
            "coach_id": coach["id"],
            "status": "active",
        },
        headers=_auth(owner_token),
    )
    assert reenable.status_code == 200

    reset = client.post(
        f"/api/academy/access/users/{coach_user['id']}/password",
        json={"password": "CoachNewPass!456"},
        headers=_auth(owner_token),
    )
    assert reset.status_code == 204
    old_password = client.post("/api/auth/login", json={"email": "coach@example.test", "password": "CoachPass!123"})
    assert old_password.status_code == 401
    new_login = _post("/api/auth/login", {"email": "coach@example.test", "password": "CoachNewPass!456"})
    assert new_login["user"]["role"] == "coach"

    audit = client.get("/api/academy/access/audit?limit=100", headers=_auth(owner_token))
    assert audit.status_code == 200
    actions = {row["action"] for row in audit.json()}
    assert {"bootstrap_owner", "create_user", "login", "update_user", "reset_password"}.issubset(actions)

    logout = client.post("/api/auth/logout", headers=_auth(new_login["token"]))
    assert logout.status_code == 204
    after_logout = client.get("/api/auth/me", headers=_auth(new_login["token"]))
    assert after_logout.status_code == 401
