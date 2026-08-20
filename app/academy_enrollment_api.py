from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .academy_registration_api import _application, _approve, _clean, _require_admin
from .academy_registration_branding_api import _academy_name
from .database import connection, fetch_all, fetch_one

router = APIRouter(tags=["academy-enrollment"])

PUBLIC_FORM = Path(__file__).resolve().parent / "static" / "academy_enrollment_public_v1.html"
ENROLLMENT_LINK_DAYS = 14
ACTIVE_STATUSES = {"created", "sent", "opened", "in_progress"}


class EnrollmentSentPayload(BaseModel):
    channel: Literal["sms", "whatsapp", "email"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_enrollment_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            application_id BIGINT NOT NULL UNIQUE,
            player_id BIGINT NOT NULL,
            created_by_user_id BIGINT,
            created_by_name TEXT,
            parent_first_name TEXT,
            parent_last_name TEXT,
            parent_phone TEXT,
            parent_email TEXT,
            token_hash TEXT NOT NULL UNIQUE,
            token_last4 TEXT,
            status TEXT NOT NULL DEFAULT 'created',
            last_channel TEXT,
            expires_at TEXT NOT NULL,
            sent_at TEXT,
            opened_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            last_activity_at TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(application_id) REFERENCES academy_registration_applications(id) ON DELETE CASCADE,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by_user_id) REFERENCES academy_users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_enrollment_invites_status ON academy_enrollment_invites(status);
        CREATE INDEX IF NOT EXISTS idx_enrollment_invites_player ON academy_enrollment_invites(player_id);
    """
    with connection() as conn:
        conn.executescript(schema)


def _enrollment(enrollment_id: int) -> dict:
    row = fetch_one(
        """
        SELECT e.*,a.player_first_name,a.player_last_name,a.status AS registration_status
        FROM academy_enrollment_invites e
        JOIN academy_registration_applications a ON a.id=e.application_id
        WHERE e.id=?
        """,
        (enrollment_id,),
    )
    if not row:
        raise HTTPException(404, "Enrollment record not found")
    row["academy_name"] = _academy_name(int(row.get("academy_id") or 0) or None)
    row["player_name"] = " ".join(
        part for part in [str(row.get("player_first_name") or "").strip(), str(row.get("player_last_name") or "").strip()] if part
    )
    return row


def _enrollment_by_application(application_id: int) -> dict | None:
    row = fetch_one("SELECT id FROM academy_enrollment_invites WHERE application_id=?", (application_id,))
    return _enrollment(int(row["id"])) if row else None


def _enrollment_for_token(token: str, *, mark_opened: bool = False) -> dict:
    row = fetch_one("SELECT id FROM academy_enrollment_invites WHERE token_hash=?", (_hash_token(token),))
    if not row:
        raise HTTPException(404, "Enrollment link is not valid")
    enrollment = _enrollment(int(row["id"]))
    try:
        expires = datetime.fromisoformat(str(enrollment["expires_at"]))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise HTTPException(410, "Enrollment link has expired") from exc
    if expires <= _now() and str(enrollment.get("status")) != "completed":
        with connection() as conn:
            conn.execute(
                "UPDATE academy_enrollment_invites SET status='expired',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(enrollment["id"]),),
            )
        raise HTTPException(410, "Enrollment link has expired")
    if str(enrollment.get("status")) == "expired":
        raise HTTPException(410, "Enrollment link has expired")
    if mark_opened and str(enrollment.get("status")) in {"created", "sent"}:
        now = _iso(_now())
        with connection() as conn:
            conn.execute(
                """
                UPDATE academy_enrollment_invites
                SET status='opened',opened_at=COALESCE(opened_at,?),last_activity_at=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (now, now, int(enrollment["id"])),
            )
        enrollment = _enrollment(int(enrollment["id"]))
    return enrollment


def _academy_id_for_application(application_id: int) -> int | None:
    row = fetch_one(
        """
        SELECT i.academy_id
        FROM academy_registration_applications a
        JOIN academy_registration_invites i ON i.id=a.invite_id
        WHERE a.id=?
        """,
        (application_id,),
    )
    return int(row["academy_id"]) if row and row.get("academy_id") else None


def _create_or_rotate_enrollment(application: dict, player_id: int, user: dict, request: Request) -> dict:
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(days=ENROLLMENT_LINK_DAYS)
    academy_id = _academy_id_for_application(int(application["id"]))
    existing = _enrollment_by_application(int(application["id"]))
    user_id = int(user.get("id") or 0) or None
    user_name = str(user.get("display_name") or "Admin")

    with connection() as conn:
        if existing:
            if str(existing.get("status")) == "completed":
                raise HTTPException(409, "Enrollment is already complete")
            conn.execute(
                """
                UPDATE academy_enrollment_invites
                SET token_hash=?,token_last4=?,status='created',expires_at=?,last_channel=NULL,sent_at=NULL,
                    opened_at=NULL,started_at=NULL,last_activity_at=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (_hash_token(token), token[-4:], _iso(expires), _iso(now), int(existing["id"])),
            )
            enrollment_id = int(existing["id"])
        else:
            row = conn.execute(
                """
                INSERT INTO academy_enrollment_invites(
                    academy_id,application_id,player_id,created_by_user_id,created_by_name,
                    parent_first_name,parent_last_name,parent_phone,parent_email,
                    token_hash,token_last4,status,expires_at,last_activity_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'created',?,?) RETURNING id
                """,
                (
                    academy_id,
                    int(application["id"]),
                    player_id,
                    user_id,
                    user_name,
                    _clean(application.get("parent_first_name")),
                    _clean(application.get("parent_last_name")),
                    _clean(application.get("parent_phone")),
                    _clean(application.get("parent_email")),
                    _hash_token(token),
                    token[-4:],
                    _iso(expires),
                    _iso(now),
                ),
            ).fetchone()
            enrollment_id = int(row["id"])

    result = _enrollment(enrollment_id)
    result["enrollment_url"] = f"{str(request.base_url).rstrip('/')}/enroll/{token}"
    result["expires_in_days"] = ENROLLMENT_LINK_DAYS
    return result


_ensure_tables()


@router.post("/api/academy/enrollments/from-registration/{application_id}")
def approve_and_create_enrollment(
    application_id: int,
    request: Request,
    user: dict = Depends(_require_admin),
):
    application = _application(application_id)
    status_value = str(application.get("status") or "")
    if status_value == "submitted":
        player_id = _approve(application, user)
        application = _application(application_id)
    elif status_value == "approved" and application.get("approved_player_id"):
        player_id = int(application["approved_player_id"])
    else:
        raise HTTPException(409, "Only a submitted or approved registration can start enrollment")
    return _create_or_rotate_enrollment(application, int(player_id), user, request)


@router.get("/api/academy/enrollments")
def list_enrollments(_: dict = Depends(_require_admin)):
    rows = fetch_all("SELECT id FROM academy_enrollment_invites ORDER BY created_at DESC,id DESC")
    return [_enrollment(int(row["id"])) for row in rows]


@router.get("/api/academy/enrollments/by-application/{application_id}")
def enrollment_by_application(application_id: int, _: dict = Depends(_require_admin)):
    enrollment = _enrollment_by_application(application_id)
    if not enrollment:
        raise HTTPException(404, "Enrollment has not been created for this registration")
    return enrollment


@router.post("/api/academy/enrollments/{enrollment_id}/sent")
def mark_enrollment_sent(
    enrollment_id: int,
    payload: EnrollmentSentPayload,
    _: dict = Depends(_require_admin),
):
    enrollment = _enrollment(enrollment_id)
    if str(enrollment.get("status")) not in ACTIVE_STATUSES:
        raise HTTPException(409, "This enrollment link can no longer be sent")
    now = _iso(_now())
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_enrollment_invites
            SET status=CASE WHEN status='created' THEN 'sent' ELSE status END,last_channel=?,
                sent_at=COALESCE(sent_at,?),last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (payload.channel, now, now, enrollment_id),
        )
    return _enrollment(enrollment_id)


@router.get("/api/public/enrollment/{token}")
def public_enrollment(token: str):
    enrollment = _enrollment_for_token(token, mark_opened=True)
    return {
        "enrollment": {
            "id": int(enrollment["id"]),
            "status": enrollment.get("status"),
            "expires_at": enrollment.get("expires_at"),
            "academy_name": enrollment.get("academy_name"),
            "player_name": enrollment.get("player_name"),
            "parent_first_name": enrollment.get("parent_first_name"),
            "parent_last_name": enrollment.get("parent_last_name"),
        },
        "steps": [
            {"key": "summary", "label": "Enrollment Summary", "status": "available"},
            {"key": "agreements", "label": "Agreements & Documents", "status": "next"},
            {"key": "payment", "label": "Fees & Payment", "status": "later"},
            {"key": "complete", "label": "Complete", "status": "later"},
        ],
    }


@router.post("/api/public/enrollment/{token}/start")
def start_public_enrollment(token: str):
    enrollment = _enrollment_for_token(token)
    if str(enrollment.get("status")) not in ACTIVE_STATUSES:
        raise HTTPException(409, "This enrollment can no longer be started")
    now = _iso(_now())
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_enrollment_invites
            SET status='in_progress',started_at=COALESCE(started_at,?),last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (now, now, int(enrollment["id"])),
        )
    return {"status": "in_progress", "next_step": "agreements"}


@router.get("/enroll/{token}", response_class=HTMLResponse)
def enrollment_form_page(token: str):
    if not PUBLIC_FORM.exists():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Enrollment portal is not available")
    return HTMLResponse(PUBLIC_FORM.read_text(encoding="utf-8"))
