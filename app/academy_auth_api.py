from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from .database import IntegrityErrors, connection, fetch_all, fetch_one

router = APIRouter(tags=["academy-access"])

Role = Literal["owner", "admin", "coach", "parent", "player"]
UserStatus = Literal["active", "disabled"]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": [
        "academy.manage", "users.manage", "players.manage", "coaches.manage",
        "sessions.manage", "attendance.manage", "teams.manage", "tournaments.manage",
        "billing.manage", "reviews.manage", "video.manage", "reports.view",
    ],
    "admin": [
        "academy.manage", "users.manage", "players.manage", "coaches.manage",
        "sessions.manage", "attendance.manage", "teams.manage", "tournaments.manage",
        "billing.manage", "reviews.manage", "video.manage", "reports.view",
    ],
    "coach": [
        "players.view", "sessions.view", "attendance.manage", "reviews.manage",
        "video.view", "reports.view",
    ],
    "parent": [
        "linked_players.view", "attendance.view", "billing.view", "reviews.view",
        "video.view", "reports.view",
    ],
    "player": [
        "self.view", "attendance.view", "reviews.view", "video.view", "reports.view",
    ],
}

PASSWORD_ITERATIONS = 310_000
SESSION_HOURS = 12


class BootstrapPayload(BaseModel):
    display_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=240)
    password: str = Field(min_length=10, max_length=256)


class LoginPayload(BaseModel):
    email: str = Field(min_length=5, max_length=240)
    password: str = Field(min_length=1, max_length=256)


class AccessUserCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=240)
    password: str = Field(min_length=10, max_length=256)
    role: Role
    coach_id: int | None = Field(default=None, gt=0)
    guardian_id: int | None = Field(default=None, gt=0)
    player_id: int | None = Field(default=None, gt=0)
    status: UserStatus = "active"


class AccessUserUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=240)
    role: Role
    coach_id: int | None = Field(default=None, gt=0)
    guardian_id: int | None = Field(default=None, gt=0)
    player_id: int | None = Field(default=None, gt=0)
    status: UserStatus = "active"


class PasswordResetPayload(BaseModel):
    password: str = Field(min_length=10, max_length=256)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(422, "Enter a valid email address")
    return normalized


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return salt.hex(), digest.hex()


def _verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return hmac.compare_digest(candidate, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            email TEXT NOT NULL,
            display_name TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            coach_id BIGINT,
            guardian_id BIGINT,
            player_id BIGINT,
            status TEXT NOT NULL DEFAULT 'active',
            last_login_at TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE SET NULL,
            FOREIGN KEY(guardian_id) REFERENCES guardians(id) ON DELETE SET NULL,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE SET NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_academy_users_email_nocase ON academy_users(LOWER(email));
        CREATE INDEX IF NOT EXISTS idx_academy_users_role ON academy_users(role);
        CREATE INDEX IF NOT EXISTS idx_academy_users_status ON academy_users(status);

        CREATE TABLE IF NOT EXISTS academy_auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT,
            FOREIGN KEY(user_id) REFERENCES academy_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_academy_auth_sessions_user ON academy_auth_sessions(user_id);

        CREATE TABLE IF NOT EXISTS academy_access_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id BIGINT,
            action TEXT NOT NULL,
            target_user_id BIGINT,
            detail TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(actor_user_id) REFERENCES academy_users(id) ON DELETE SET NULL,
            FOREIGN KEY(target_user_id) REFERENCES academy_users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_academy_access_audit_actor ON academy_access_audit(actor_user_id);
        CREATE INDEX IF NOT EXISTS idx_academy_access_audit_target ON academy_access_audit(target_user_id);
    """
    with connection() as conn:
        conn.executescript(schema)


def _audit(conn, action: str, actor_user_id: int | None = None,
           target_user_id: int | None = None, detail: str | None = None) -> None:
    conn.execute(
        "INSERT INTO academy_access_audit(actor_user_id,action,target_user_id,detail) VALUES(?,?,?,?)",
        (actor_user_id, action, target_user_id, detail),
    )


def _linked_name(row: dict) -> str | None:
    role = row.get("role")
    if role == "coach":
        return " ".join(x for x in [row.get("coach_first_name"), row.get("coach_last_name")] if x).strip() or None
    if role == "parent":
        return " ".join(x for x in [row.get("guardian_first_name"), row.get("guardian_last_name")] if x).strip() or None
    if role == "player":
        return row.get("player_name")
    return None


def _user_row(user_id: int) -> dict:
    row = fetch_one(
        """
        SELECT u.id,u.academy_id,u.email,u.display_name,u.role,u.coach_id,u.guardian_id,u.player_id,
               u.status,u.last_login_at,u.created_at,u.updated_at,
               c.first_name AS coach_first_name,c.last_name AS coach_last_name,
               g.first_name AS guardian_first_name,g.last_name AS guardian_last_name,
               p.name AS player_name
        FROM academy_users u
        LEFT JOIN coaches c ON c.id=u.coach_id
        LEFT JOIN guardians g ON g.id=u.guardian_id
        LEFT JOIN players p ON p.id=u.player_id
        WHERE u.id=?
        """,
        (user_id,),
    )
    if not row:
        raise HTTPException(404, "Access user not found")
    row["permissions"] = ROLE_PERMISSIONS.get(str(row.get("role")), [])
    row["linked_name"] = _linked_name(row)
    for key in ("coach_first_name", "coach_last_name", "guardian_first_name", "guardian_last_name", "player_name"):
        row.pop(key, None)
    return row


def _validate_link(conn, role: str, coach_id: int | None,
                   guardian_id: int | None, player_id: int | None) -> None:
    supplied = [x for x in (coach_id, guardian_id, player_id) if x is not None]
    if len(supplied) > 1:
        raise HTTPException(422, "A user can be linked to only one coach, guardian, or player identity")
    if coach_id is not None:
        if role != "coach":
            raise HTTPException(422, "coach_id can only be used with the coach role")
        if not conn.execute("SELECT id FROM coaches WHERE id=?", (coach_id,)).fetchone():
            raise HTTPException(422, "Linked coach was not found")
    if guardian_id is not None:
        if role != "parent":
            raise HTTPException(422, "guardian_id can only be used with the parent role")
        if not conn.execute("SELECT id FROM guardians WHERE id=?", (guardian_id,)).fetchone():
            raise HTTPException(422, "Linked guardian was not found")
    if player_id is not None:
        if role != "player":
            raise HTTPException(422, "player_id can only be used with the player role")
        if not conn.execute("SELECT id FROM players WHERE id=?", (player_id,)).fetchone():
            raise HTTPException(422, "Linked player was not found")


def _issue_session(conn, user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(hours=SESSION_HOURS)
    conn.execute(
        "INSERT INTO academy_auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
        (_token_hash(token), user_id, _iso(expires_at)),
    )
    return token, _iso(expires_at)


def _extract_token(authorization: str | None, session_header: str | None) -> str | None:
    if authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    return _clean(session_header)


def current_access_user(
    authorization: str | None = Header(default=None),
    x_cam_session: str | None = Header(default=None, alias="X-CAM-Session"),
) -> dict:
    token = _extract_token(authorization, x_cam_session)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    row = fetch_one(
        """
        SELECT s.token_hash,s.expires_at,s.revoked_at,u.id AS user_id,u.status
        FROM academy_auth_sessions s
        JOIN academy_users u ON u.id=s.user_id
        WHERE s.token_hash=?
        """,
        (_token_hash(token),),
    )
    if not row or row.get("revoked_at") or row.get("status") != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is not valid")
    try:
        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is not valid") from exc
    if expires_at <= _now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has expired")
    return _user_row(int(row["user_id"]))


def require_access_admin(user: dict = Depends(current_access_user)) -> dict:
    if user.get("role") not in ("owner", "admin") or "users.manage" not in user.get("permissions", []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner or admin access is required")
    return user


_ensure_tables()


@router.get("/api/auth/bootstrap-status")
def bootstrap_status():
    row = fetch_one("SELECT COUNT(*) AS count FROM academy_users") or {"count": 0}
    return {
        "has_users": int(row.get("count") or 0) > 0,
        "bootstrap_configured": bool(os.environ.get("CAM_BOOTSTRAP_TOKEN", "").strip()),
        "roles": list(ROLE_PERMISSIONS),
    }


@router.post("/api/auth/bootstrap", status_code=201)
def bootstrap_owner(payload: BootstrapPayload, x_cam_bootstrap: str | None = Header(default=None, alias="X-CAM-Bootstrap")):
    expected = os.environ.get("CAM_BOOTSTRAP_TOKEN", "").strip()
    if not expected:
        raise HTTPException(503, "CAM_BOOTSTRAP_TOKEN is not configured")
    if not x_cam_bootstrap or not hmac.compare_digest(x_cam_bootstrap, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid bootstrap token")
    email = _email(payload.email)
    salt, digest = _hash_password(payload.password)
    try:
        with connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS count FROM academy_users").fetchone()
            if int(existing["count"] or 0) > 0:
                raise HTTPException(409, "Academy access has already been bootstrapped")
            academy_id = _academy_id(conn)
            row = conn.execute(
                """
                INSERT INTO academy_users(academy_id,email,display_name,password_salt,password_hash,role,status)
                VALUES(?,?,?,?,?,'owner','active') RETURNING id
                """,
                (academy_id, email, payload.display_name.strip(), salt, digest),
            ).fetchone()
            user_id = int(row["id"])
            token, expires_at = _issue_session(conn, user_id)
            _audit(conn, "bootstrap_owner", actor_user_id=user_id, target_user_id=user_id)
    except IntegrityErrors as exc:
        raise HTTPException(409, "A user with this email already exists") from exc
    return {"token": token, "expires_at": expires_at, "user": _user_row(user_id)}


@router.post("/api/auth/login")
def login(payload: LoginPayload):
    email = _email(payload.email)
    row = fetch_one(
        "SELECT id,password_salt,password_hash,status FROM academy_users WHERE LOWER(email)=LOWER(?)",
        (email,),
    )
    if not row or row.get("status") != "active" or not _verify_password(payload.password, row["password_salt"], row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    user_id = int(row["id"])
    with connection() as conn:
        conn.execute("UPDATE academy_users SET last_login_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (_iso(_now()), user_id))
        token, expires_at = _issue_session(conn, user_id)
        _audit(conn, "login", actor_user_id=user_id, target_user_id=user_id)
    return {"token": token, "expires_at": expires_at, "user": _user_row(user_id)}


@router.get("/api/auth/me")
def auth_me(user: dict = Depends(current_access_user)):
    return user


@router.post("/api/auth/logout", status_code=204)
def logout(
    user: dict = Depends(current_access_user),
    authorization: str | None = Header(default=None),
    x_cam_session: str | None = Header(default=None, alias="X-CAM-Session"),
):
    token = _extract_token(authorization, x_cam_session)
    with connection() as conn:
        conn.execute("UPDATE academy_auth_sessions SET revoked_at=? WHERE token_hash=?", (_iso(_now()), _token_hash(token or "")))
        _audit(conn, "logout", actor_user_id=int(user["id"]), target_user_id=int(user["id"]))
    return None


@router.get("/api/academy/access/roles")
def access_roles(_: dict = Depends(require_access_admin)):
    return [{"role": role, "permissions": permissions} for role, permissions in ROLE_PERMISSIONS.items()]


@router.get("/api/academy/access/reference")
def access_reference(_: dict = Depends(require_access_admin)):
    coaches = fetch_all("SELECT id,first_name,last_name,status FROM coaches ORDER BY last_name COLLATE NOCASE,first_name COLLATE NOCASE")
    guardians = fetch_all("SELECT id,first_name,last_name,email,phone FROM guardians ORDER BY last_name COLLATE NOCASE,first_name COLLATE NOCASE")
    players = fetch_all("SELECT id,name,status FROM players ORDER BY name COLLATE NOCASE")
    return {"coaches": coaches, "guardians": guardians, "players": players}


@router.get("/api/academy/access/users")
def access_users(_: dict = Depends(require_access_admin)):
    ids = [int(row["id"]) for row in fetch_all("SELECT id FROM academy_users ORDER BY display_name COLLATE NOCASE,email COLLATE NOCASE")]
    return [_user_row(user_id) for user_id in ids]


@router.post("/api/academy/access/users", status_code=201)
def create_access_user(payload: AccessUserCreate, actor: dict = Depends(require_access_admin)):
    email = _email(payload.email)
    salt, digest = _hash_password(payload.password)
    try:
        with connection() as conn:
            _validate_link(conn, payload.role, payload.coach_id, payload.guardian_id, payload.player_id)
            academy_id = _academy_id(conn)
            row = conn.execute(
                """
                INSERT INTO academy_users(academy_id,email,display_name,password_salt,password_hash,role,coach_id,guardian_id,player_id,status)
                VALUES(?,?,?,?,?,?,?,?,?,?) RETURNING id
                """,
                (
                    academy_id, email, payload.display_name.strip(), salt, digest, payload.role,
                    payload.coach_id, payload.guardian_id, payload.player_id, payload.status,
                ),
            ).fetchone()
            user_id = int(row["id"])
            _audit(conn, "create_user", int(actor["id"]), user_id, f"role={payload.role}")
    except IntegrityErrors as exc:
        raise HTTPException(409, "A user with this email already exists") from exc
    return _user_row(user_id)


@router.put("/api/academy/access/users/{user_id}")
def update_access_user(user_id: int, payload: AccessUserUpdate, actor: dict = Depends(require_access_admin)):
    email = _email(payload.email)
    with connection() as conn:
        existing = conn.execute("SELECT id,role FROM academy_users WHERE id=?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Access user not found")
        if user_id == int(actor["id"]) and payload.status == "disabled":
            raise HTTPException(409, "You cannot disable your own account")
        _validate_link(conn, payload.role, payload.coach_id, payload.guardian_id, payload.player_id)
        try:
            conn.execute(
                """
                UPDATE academy_users SET email=?,display_name=?,role=?,coach_id=?,guardian_id=?,player_id=?,status=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    email, payload.display_name.strip(), payload.role, payload.coach_id,
                    payload.guardian_id, payload.player_id, payload.status, user_id,
                ),
            )
        except IntegrityErrors as exc:
            raise HTTPException(409, "A user with this email already exists") from exc
        if payload.status == "disabled":
            conn.execute("UPDATE academy_auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (_iso(_now()), user_id))
        _audit(conn, "update_user", int(actor["id"]), user_id, f"role={payload.role};status={payload.status}")
    return _user_row(user_id)


@router.post("/api/academy/access/users/{user_id}/password", status_code=204)
def reset_access_password(user_id: int, payload: PasswordResetPayload, actor: dict = Depends(require_access_admin)):
    salt, digest = _hash_password(payload.password)
    with connection() as conn:
        if not conn.execute("SELECT id FROM academy_users WHERE id=?", (user_id,)).fetchone():
            raise HTTPException(404, "Access user not found")
        conn.execute(
            "UPDATE academy_users SET password_salt=?,password_hash=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (salt, digest, user_id),
        )
        conn.execute("UPDATE academy_auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (_iso(_now()), user_id))
        _audit(conn, "reset_password", int(actor["id"]), user_id)
    return None


@router.get("/api/academy/access/audit")
def access_audit(limit: int = 50, _: dict = Depends(require_access_admin)):
    limit = max(1, min(int(limit), 200))
    return fetch_all(
        """
        SELECT a.*,actor.display_name AS actor_name,target.display_name AS target_name
        FROM academy_access_audit a
        LEFT JOIN academy_users actor ON actor.id=a.actor_user_id
        LEFT JOIN academy_users target ON target.id=a.target_user_id
        ORDER BY a.id DESC LIMIT ?
        """,
        (limit,),
    )
