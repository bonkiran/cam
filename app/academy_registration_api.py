from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .academy_auth_api import current_access_user
from .database import connection, fetch_all, fetch_one

router = APIRouter(tags=["academy-registration"])

PUBLIC_FORM = Path(__file__).resolve().parent / "static" / "academy_registration_public_v1.html"
INVITE_DAYS = 7
SENDER_ROLES = {"owner", "admin", "coach"}
ADMIN_ROLES = {"owner", "admin"}
ACTIVE_PARENT_STATUSES = {"created", "sent", "opened", "in_progress", "needs_information"}


class RegistrationInviteCreate(BaseModel):
    parent_first_name: str = Field(min_length=1, max_length=100)
    parent_last_name: str = Field(min_length=1, max_length=100)
    parent_phone: str = Field(min_length=7, max_length=60)
    parent_email: str | None = Field(default=None, max_length=200)
    expires_in_days: int = Field(default=INVITE_DAYS, ge=1, le=30)


class RegistrationSentPayload(BaseModel):
    channel: Literal["sms", "whatsapp", "email", "copy"]


class RegistrationContactPayload(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    relationship: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    address_line1: str | None = Field(default=None, max_length=240)
    address_line2: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=120)
    pickup_authorized: bool = True


class RegistrationApplicationPayload(BaseModel):
    player_first_name: str | None = Field(default=None, max_length=100)
    player_last_name: str | None = Field(default=None, max_length=100)
    player_date_of_birth: str | None = Field(default=None, max_length=20)
    player_gender: str | None = Field(default=None, max_length=50)
    cricket_role: Literal["Batter", "Bowler", "All-Rounder", "Wicketkeeper"] | None = None
    batting_order: Literal["TO", "MO", "LO", "N/A"] | None = None
    bowling_type: Literal["Pace", "Medium", "Spin", "N/A"] | None = None
    wicketkeeping: bool | None = None

    parent_first_name: str | None = Field(default=None, max_length=100)
    parent_last_name: str | None = Field(default=None, max_length=100)
    parent_relationship: str | None = Field(default=None, max_length=80)
    parent_email: str | None = Field(default=None, max_length=200)
    parent_phone: str | None = Field(default=None, max_length=60)
    parent_address_line1: str | None = Field(default=None, max_length=240)
    parent_address_line2: str | None = Field(default=None, max_length=240)
    parent_city: str | None = Field(default=None, max_length=120)
    parent_state: str | None = Field(default=None, max_length=120)
    parent_postal_code: str | None = Field(default=None, max_length=30)
    parent_country: str | None = Field(default=None, max_length=120)

    emergency_contacts: list[RegistrationContactPayload] = Field(default_factory=list, max_length=2)
    guardian_same_as_parent: bool = True
    guardian: RegistrationContactPayload | None = None

    injuries: str | None = Field(default=None, max_length=2000)
    surgeries: str | None = Field(default=None, max_length=2000)
    medical_considerations: str | None = Field(default=None, max_length=2000)
    allergies: str | None = Field(default=None, max_length=1200)
    physical_restrictions: str | None = Field(default=None, max_length=1200)
    additional_notes: str | None = Field(default=None, max_length=2500)
    consent_confirmed: bool = False


class RegistrationReviewPayload(BaseModel):
    action: Literal["needs_information", "approve", "decline"]
    note: str | None = Field(default=None, max_length=1500)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _academy_id(conn) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _require_sender(user: dict = Depends(current_access_user)) -> dict:
    if str(user.get("role")) not in SENDER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Coach, admin, or owner access is required")
    return user


def _require_admin(user: dict = Depends(current_access_user)) -> dict:
    if str(user.get("role")) not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner or admin access is required")
    return user


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_registration_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            sent_by_user_id BIGINT,
            sent_by_name TEXT NOT NULL,
            sent_by_role TEXT,
            parent_first_name TEXT NOT NULL,
            parent_last_name TEXT NOT NULL,
            parent_phone TEXT NOT NULL,
            parent_email TEXT,
            token_hash TEXT NOT NULL UNIQUE,
            token_last4 TEXT,
            status TEXT NOT NULL DEFAULT 'created',
            last_channel TEXT,
            expires_at TEXT NOT NULL,
            sent_at TEXT,
            opened_at TEXT,
            last_activity_at TEXT,
            submitted_at TEXT,
            reviewed_at TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL,
            FOREIGN KEY(sent_by_user_id) REFERENCES academy_users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_registration_invites_status ON academy_registration_invites(status);
        CREATE INDEX IF NOT EXISTS idx_registration_invites_sender ON academy_registration_invites(sent_by_user_id);
        CREATE INDEX IF NOT EXISTS idx_registration_invites_created ON academy_registration_invites(created_at);

        CREATE TABLE IF NOT EXISTS academy_registration_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invite_id BIGINT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft',
            player_first_name TEXT,
            player_last_name TEXT,
            player_date_of_birth TEXT,
            player_gender TEXT,
            cricket_role TEXT,
            batting_order TEXT,
            bowling_type TEXT,
            wicketkeeping INTEGER,
            parent_first_name TEXT,
            parent_last_name TEXT,
            parent_relationship TEXT,
            parent_email TEXT,
            parent_phone TEXT,
            parent_address_line1 TEXT,
            parent_address_line2 TEXT,
            parent_city TEXT,
            parent_state TEXT,
            parent_postal_code TEXT,
            parent_country TEXT,
            guardian_same_as_parent INTEGER NOT NULL DEFAULT 1,
            injuries TEXT,
            surgeries TEXT,
            medical_considerations TEXT,
            allergies TEXT,
            physical_restrictions TEXT,
            additional_notes TEXT,
            consent_confirmed INTEGER NOT NULL DEFAULT 0,
            review_note TEXT,
            reviewed_by_user_id BIGINT,
            reviewed_by_name TEXT,
            submitted_at TEXT,
            reviewed_at TEXT,
            approved_player_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(invite_id) REFERENCES academy_registration_invites(id) ON DELETE CASCADE,
            FOREIGN KEY(reviewed_by_user_id) REFERENCES academy_users(id) ON DELETE SET NULL,
            FOREIGN KEY(approved_player_id) REFERENCES players(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_registration_applications_status ON academy_registration_applications(status);

        CREATE TABLE IF NOT EXISTS academy_registration_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id BIGINT NOT NULL,
            contact_type TEXT NOT NULL,
            sequence_no INTEGER NOT NULL DEFAULT 1,
            first_name TEXT,
            last_name TEXT,
            relationship TEXT,
            email TEXT,
            phone TEXT,
            address_line1 TEXT,
            address_line2 TEXT,
            city TEXT,
            state TEXT,
            postal_code TEXT,
            country TEXT,
            pickup_authorized INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(application_id) REFERENCES academy_registration_applications(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_registration_contacts_application ON academy_registration_contacts(application_id);

        CREATE TABLE IF NOT EXISTS academy_player_registration_profiles (
            player_id BIGINT PRIMARY KEY,
            application_id BIGINT,
            cricket_role TEXT,
            batting_order TEXT,
            bowling_type TEXT,
            wicketkeeping INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(application_id) REFERENCES academy_registration_applications(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS academy_player_emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id BIGINT NOT NULL,
            sequence_no INTEGER NOT NULL,
            first_name TEXT,
            last_name TEXT,
            relationship TEXT,
            email TEXT,
            phone TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_player_emergency_contacts_player ON academy_player_emergency_contacts(player_id);

        CREATE TABLE IF NOT EXISTS academy_player_medical_profiles (
            player_id BIGINT PRIMARY KEY,
            application_id BIGINT,
            injuries TEXT,
            surgeries TEXT,
            medical_considerations TEXT,
            allergies TEXT,
            physical_restrictions TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(application_id) REFERENCES academy_registration_applications(id) ON DELETE SET NULL
        );
    """
    with connection() as conn:
        conn.executescript(schema)


def _application(application_id: int) -> dict:
    row = fetch_one("SELECT * FROM academy_registration_applications WHERE id=?", (application_id,))
    if not row:
        raise HTTPException(404, "Registration application not found")
    row["wicketkeeping"] = None if row.get("wicketkeeping") is None else bool(row.get("wicketkeeping"))
    row["guardian_same_as_parent"] = bool(row.get("guardian_same_as_parent"))
    row["consent_confirmed"] = bool(row.get("consent_confirmed"))
    contacts = fetch_all(
        "SELECT * FROM academy_registration_contacts WHERE application_id=? ORDER BY contact_type,sequence_no,id",
        (application_id,),
    )
    emergency = []
    guardian = None
    for item in contacts:
        item["pickup_authorized"] = bool(item.get("pickup_authorized"))
        if item.get("contact_type") == "emergency":
            emergency.append(item)
        elif item.get("contact_type") == "guardian":
            guardian = item
    row["emergency_contacts"] = emergency
    row["guardian"] = guardian
    return row


def _invite(invite_id: int) -> dict:
    row = fetch_one(
        """
        SELECT i.*,a.id AS application_id,a.status AS application_status,
               a.player_first_name,a.player_last_name,a.approved_player_id,a.review_note
        FROM academy_registration_invites i
        LEFT JOIN academy_registration_applications a ON a.invite_id=i.id
        WHERE i.id=?
        """,
        (invite_id,),
    )
    if not row:
        raise HTTPException(404, "Registration invite not found")
    return row


def _invite_for_token(token: str, *, mark_opened: bool = False) -> dict:
    token_hash = _hash_token(token)
    row = fetch_one("SELECT * FROM academy_registration_invites WHERE token_hash=?", (token_hash,))
    if not row:
        raise HTTPException(404, "Registration link is not valid")
    status_value = str(row.get("status") or "created")
    try:
        expires = datetime.fromisoformat(str(row["expires_at"]))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except Exception as exc:
        raise HTTPException(410, "Registration link has expired") from exc
    if expires <= _now() and status_value not in {"submitted", "approved", "declined"}:
        with connection() as conn:
            conn.execute(
                "UPDATE academy_registration_invites SET status='expired',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(row["id"]),),
            )
        raise HTTPException(410, "Registration link has expired")
    if status_value in {"cancelled", "expired"}:
        raise HTTPException(410, f"Registration link is {status_value}")
    if mark_opened and status_value in {"created", "sent"}:
        now = _iso(_now())
        with connection() as conn:
            conn.execute(
                """
                UPDATE academy_registration_invites
                SET status='opened',opened_at=COALESCE(opened_at,?),last_activity_at=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (now, now, int(row["id"])),
            )
        row = fetch_one("SELECT * FROM academy_registration_invites WHERE id=?", (int(row["id"]),)) or row
    return row


def _ensure_application(invite: dict) -> int:
    existing = fetch_one("SELECT id FROM academy_registration_applications WHERE invite_id=?", (int(invite["id"]),))
    if existing:
        return int(existing["id"])
    with connection() as conn:
        created = conn.execute(
            """
            INSERT INTO academy_registration_applications(
                invite_id,status,parent_first_name,parent_last_name,parent_email,parent_phone
            ) VALUES(?,'draft',?,?,?,?) RETURNING id
            """,
            (
                int(invite["id"]),
                invite.get("parent_first_name"),
                invite.get("parent_last_name"),
                invite.get("parent_email"),
                invite.get("parent_phone"),
            ),
        ).fetchone()
        return int(created["id"])


def _save_application(invite: dict, payload: RegistrationApplicationPayload, *, submitted: bool) -> dict:
    application_id = _ensure_application(invite)
    raw = payload.model_dump()
    emergency_contacts = raw.pop("emergency_contacts", [])
    guardian = raw.pop("guardian", None)
    raw["guardian_same_as_parent"] = 1 if raw.get("guardian_same_as_parent") else 0
    raw["wicketkeeping"] = None if raw.get("wicketkeeping") is None else (1 if raw.get("wicketkeeping") else 0)
    raw["consent_confirmed"] = 1 if raw.get("consent_confirmed") else 0
    for key, value in list(raw.items()):
        if isinstance(value, str):
            raw[key] = _clean(value)

    now = _iso(_now())
    target_status = "submitted" if submitted else "draft"
    invite_status = "submitted" if submitted else "in_progress"
    columns = [
        "player_first_name", "player_last_name", "player_date_of_birth", "player_gender", "cricket_role",
        "batting_order", "bowling_type", "wicketkeeping", "parent_first_name", "parent_last_name",
        "parent_relationship", "parent_email", "parent_phone", "parent_address_line1", "parent_address_line2",
        "parent_city", "parent_state", "parent_postal_code", "parent_country", "guardian_same_as_parent",
        "injuries", "surgeries", "medical_considerations", "allergies", "physical_restrictions",
        "additional_notes", "consent_confirmed",
    ]
    assignments = ",".join(f"{column}=?" for column in columns)
    values = [raw.get(column) for column in columns]

    with connection() as conn:
        conn.execute(
            f"""
            UPDATE academy_registration_applications
            SET {assignments},status=?,submitted_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (*values, target_status, now if submitted else None, application_id),
        )
        conn.execute("DELETE FROM academy_registration_contacts WHERE application_id=?", (application_id,))

        for index, contact in enumerate(emergency_contacts[:2], start=1):
            _insert_contact(conn, application_id, "emergency", index, contact)
        if not bool(raw.get("guardian_same_as_parent")) and guardian:
            _insert_contact(conn, application_id, "guardian", 1, guardian)

        conn.execute(
            """
            UPDATE academy_registration_invites
            SET status=?,last_activity_at=?,submitted_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (invite_status, now, now if submitted else None, int(invite["id"])),
        )
    return _application(application_id)


def _insert_contact(conn, application_id: int, contact_type: str, sequence_no: int, contact: dict) -> None:
    values = {key: (_clean(value) if isinstance(value, str) else value) for key, value in contact.items()}
    conn.execute(
        """
        INSERT INTO academy_registration_contacts(
            application_id,contact_type,sequence_no,first_name,last_name,relationship,email,phone,
            address_line1,address_line2,city,state,postal_code,country,pickup_authorized
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            application_id, contact_type, sequence_no, values.get("first_name"), values.get("last_name"),
            values.get("relationship"), values.get("email"), values.get("phone"), values.get("address_line1"),
            values.get("address_line2"), values.get("city"), values.get("state"), values.get("postal_code"),
            values.get("country"), 1 if values.get("pickup_authorized", True) else 0,
        ),
    )


def _validate_submission(payload: RegistrationApplicationPayload) -> None:
    required = {
        "Player first name": payload.player_first_name,
        "Player last name": payload.player_last_name,
        "Date of birth": payload.player_date_of_birth,
        "Gender": payload.player_gender,
        "Cricket role": payload.cricket_role,
        "Batting order": payload.batting_order,
        "Bowling type": payload.bowling_type,
        "Parent first name": payload.parent_first_name,
        "Parent last name": payload.parent_last_name,
        "Parent relationship": payload.parent_relationship,
        "Parent email": payload.parent_email,
        "Parent phone": payload.parent_phone,
        "Parent address": payload.parent_address_line1,
        "Parent city": payload.parent_city,
        "Parent state": payload.parent_state,
        "Parent ZIP": payload.parent_postal_code,
        "Parent country": payload.parent_country,
    }
    missing = [label for label, value in required.items() if not _clean(value) if isinstance(value, str)]
    missing += [label for label, value in required.items() if value is None and not isinstance(value, str)]
    if payload.wicketkeeping is None:
        missing.append("Wicketkeeping")
    if len(payload.emergency_contacts) != 2:
        missing.append("Two emergency contacts")
    else:
        for index, contact in enumerate(payload.emergency_contacts, start=1):
            if not all([_clean(contact.first_name), _clean(contact.last_name), _clean(contact.relationship), _clean(contact.phone)]):
                missing.append(f"Emergency contact {index} name, relationship and phone")
    if not payload.guardian_same_as_parent:
        g = payload.guardian
        if not g or not all([_clean(g.first_name), _clean(g.last_name), _clean(g.relationship), _clean(g.phone)]):
            missing.append("Guardian name, relationship and phone")
    if not payload.consent_confirmed:
        missing.append("Registration confirmation")
    if missing:
        unique = list(dict.fromkeys(missing))
        raise HTTPException(422, "Complete required registration fields: " + ", ".join(unique))


def _sender_scope(user: dict) -> tuple[str, list[object]]:
    if str(user.get("role")) in ADMIN_ROLES:
        return "", []
    user_id = int(user.get("id") or 0)
    return " WHERE sent_by_user_id=?", [user_id]


def _find_or_create_guardian(conn, *, academy_id: int | None, data: dict) -> int:
    email = _clean(data.get("email"))
    phone = _clean(data.get("phone"))
    existing = None
    if email and phone:
        existing = conn.execute(
            "SELECT id FROM guardians WHERE LOWER(email)=LOWER(?) AND phone=? ORDER BY id LIMIT 1",
            (email, phone),
        ).fetchone()
    elif email:
        existing = conn.execute(
            "SELECT id FROM guardians WHERE LOWER(email)=LOWER(?) ORDER BY id LIMIT 1",
            (email,),
        ).fetchone()
    if existing:
        return int(existing["id"])
    row = conn.execute(
        """
        INSERT INTO guardians(
            academy_id,first_name,last_name,relationship,email,phone,address_line1,address_line2,
            city,state,postal_code,country
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id
        """,
        (
            academy_id, _clean(data.get("first_name")) or "Parent", _clean(data.get("last_name")) or "Guardian",
            _clean(data.get("relationship")), email, phone, _clean(data.get("address_line1")),
            _clean(data.get("address_line2")), _clean(data.get("city")), _clean(data.get("state")),
            _clean(data.get("postal_code")), _clean(data.get("country")),
        ),
    ).fetchone()
    return int(row["id"])


def _approve(application: dict, user: dict) -> int:
    if str(application.get("status")) != "submitted":
        raise HTTPException(409, "Only a submitted application can be approved")
    full_name = f"{application.get('player_first_name') or ''} {application.get('player_last_name') or ''}".strip()
    if not full_name:
        raise HTTPException(422, "Player name is required")
    existing = fetch_one(
        "SELECT id FROM players WHERE LOWER(name)=LOWER(?) AND COALESCE(date_of_birth,'')=COALESCE(?, '')",
        (full_name, application.get("player_date_of_birth")),
    )
    if existing:
        raise HTTPException(409, "A player with the same name and date of birth already exists")

    emergency = application.get("emergency_contacts") or []
    first_emergency = emergency[0] if emergency else {}
    now = _iso(_now())
    reviewer_id = int(user.get("id") or 0) or None
    reviewer_name = str(user.get("display_name") or "Admin")

    with connection() as conn:
        academy_id = _academy_id(conn)
        row = conn.execute(
            """
            INSERT INTO players(
                name,first_name,last_name,date_of_birth,gender,bowling_style,
                emergency_contact_name,emergency_contact_phone,joined_on,status,notes,academy_id,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,'active',?,?,CURRENT_TIMESTAMP) RETURNING id
            """,
            (
                full_name, application.get("player_first_name"), application.get("player_last_name"),
                application.get("player_date_of_birth"), application.get("player_gender"),
                None if application.get("bowling_type") == "N/A" else application.get("bowling_type"),
                f"{first_emergency.get('first_name') or ''} {first_emergency.get('last_name') or ''}".strip() or None,
                first_emergency.get("phone"), date.today().isoformat(), _clean(application.get("additional_notes")), academy_id,
            ),
        ).fetchone()
        player_id = int(row["id"])

        parent_data = {
            "first_name": application.get("parent_first_name"),
            "last_name": application.get("parent_last_name"),
            "relationship": application.get("parent_relationship"),
            "email": application.get("parent_email"),
            "phone": application.get("parent_phone"),
            "address_line1": application.get("parent_address_line1"),
            "address_line2": application.get("parent_address_line2"),
            "city": application.get("parent_city"),
            "state": application.get("parent_state"),
            "postal_code": application.get("parent_postal_code"),
            "country": application.get("parent_country"),
        }
        parent_guardian_id = _find_or_create_guardian(conn, academy_id=academy_id, data=parent_data)
        conn.execute(
            """
            INSERT INTO player_guardians(player_id,guardian_id,is_primary,billing_contact,pickup_authorized)
            VALUES(?,?,1,1,1)
            """,
            (player_id, parent_guardian_id),
        )

        if not bool(application.get("guardian_same_as_parent")) and application.get("guardian"):
            guardian_data = application["guardian"]
            guardian_id = _find_or_create_guardian(conn, academy_id=academy_id, data=guardian_data)
            if guardian_id != parent_guardian_id:
                conn.execute(
                    """
                    INSERT INTO player_guardians(player_id,guardian_id,is_primary,billing_contact,pickup_authorized)
                    VALUES(?,?,0,0,?)
                    """,
                    (player_id, guardian_id, 1 if guardian_data.get("pickup_authorized", True) else 0),
                )

        conn.execute(
            """
            INSERT INTO academy_player_registration_profiles(
                player_id,application_id,cricket_role,batting_order,bowling_type,wicketkeeping
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                player_id, int(application["id"]), application.get("cricket_role"), application.get("batting_order"),
                application.get("bowling_type"), 1 if application.get("wicketkeeping") else 0,
            ),
        )
        for index, contact in enumerate(emergency[:2], start=1):
            conn.execute(
                """
                INSERT INTO academy_player_emergency_contacts(
                    player_id,sequence_no,first_name,last_name,relationship,email,phone
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    player_id, index, contact.get("first_name"), contact.get("last_name"),
                    contact.get("relationship"), contact.get("email"), contact.get("phone"),
                ),
            )
        conn.execute(
            """
            INSERT INTO academy_player_medical_profiles(
                player_id,application_id,injuries,surgeries,medical_considerations,allergies,physical_restrictions
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                player_id, int(application["id"]), application.get("injuries"), application.get("surgeries"),
                application.get("medical_considerations"), application.get("allergies"),
                application.get("physical_restrictions"),
            ),
        )
        conn.execute(
            """
            UPDATE academy_registration_applications
            SET status='approved',approved_player_id=?,reviewed_by_user_id=?,reviewed_by_name=?,reviewed_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (player_id, reviewer_id, reviewer_name, now, int(application["id"])),
        )
        conn.execute(
            """
            UPDATE academy_registration_invites
            SET status='approved',reviewed_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (now, int(application["invite_id"])),
        )
    return player_id


_ensure_tables()


@router.get("/api/academy/registration/invites")
def registration_invites(user: dict = Depends(_require_sender)):
    where, params = _sender_scope(user)
    rows = fetch_all(
        f"""
        SELECT i.id FROM academy_registration_invites i
        {where}
        ORDER BY i.created_at DESC,i.id DESC
        """,
        params,
    )
    return [_invite(int(row["id"])) for row in rows]


@router.get("/api/academy/registration/summary")
def registration_summary(user: dict = Depends(_require_sender)):
    where, params = _sender_scope(user)
    rows = fetch_all(f"SELECT status,COUNT(*) AS count FROM academy_registration_invites{where} GROUP BY status", params)
    counts = {str(row["status"]): int(row["count"] or 0) for row in rows}
    waiting = sum(counts.get(key, 0) for key in ("created", "sent", "opened", "in_progress", "needs_information"))
    return {
        "counts": counts,
        "waiting_on_parent": waiting,
        "submitted": counts.get("submitted", 0),
        "in_progress": counts.get("in_progress", 0),
        "approved": counts.get("approved", 0),
    }


@router.post("/api/academy/registration/invites", status_code=201)
def create_registration_invite(
    payload: RegistrationInviteCreate,
    request: Request,
    user: dict = Depends(_require_sender),
):
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(days=payload.expires_in_days)
    user_id = int(user.get("id") or 0) or None
    sent_by_name = str(user.get("display_name") or user.get("linked_name") or "Academy Staff")
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO academy_registration_invites(
                academy_id,sent_by_user_id,sent_by_name,sent_by_role,parent_first_name,parent_last_name,
                parent_phone,parent_email,token_hash,token_last4,status,expires_at,last_activity_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,'created',?,?) RETURNING id
            """,
            (
                _academy_id(conn), user_id, sent_by_name, user.get("role"), _clean(payload.parent_first_name),
                _clean(payload.parent_last_name), _clean(payload.parent_phone), _clean(payload.parent_email),
                _hash_token(token), token[-4:], _iso(expires), _iso(now),
            ),
        ).fetchone()
        invite_id = int(row["id"])
    base = str(request.base_url).rstrip("/")
    result = _invite(invite_id)
    result["registration_url"] = f"{base}/register/{token}"
    result["expires_in_days"] = payload.expires_in_days
    return result


@router.post("/api/academy/registration/invites/{invite_id}/sent")
def mark_registration_sent(
    invite_id: int,
    payload: RegistrationSentPayload,
    user: dict = Depends(_require_sender),
):
    invite = _invite(invite_id)
    if str(user.get("role")) == "coach" and int(invite.get("sent_by_user_id") or 0) != int(user.get("id") or 0):
        raise HTTPException(403, "Coaches can update only registration links they created")
    if str(invite.get("status")) in {"cancelled", "expired", "approved", "declined"}:
        raise HTTPException(409, "This registration link can no longer be sent")
    now = _iso(_now())
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_registration_invites
            SET status=CASE WHEN status='created' THEN 'sent' ELSE status END,last_channel=?,sent_at=COALESCE(sent_at,?),
                last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (payload.channel, now, now, invite_id),
        )
    return _invite(invite_id)


@router.post("/api/academy/registration/invites/{invite_id}/resend")
def resend_registration_invite(invite_id: int, request: Request, user: dict = Depends(_require_sender)):
    invite = _invite(invite_id)
    if str(user.get("role")) == "coach" and int(invite.get("sent_by_user_id") or 0) != int(user.get("id") or 0):
        raise HTTPException(403, "Coaches can resend only registration links they created")
    if str(invite.get("status")) in {"submitted", "approved", "declined", "cancelled"}:
        raise HTTPException(409, "This registration can no longer be resent")
    token = secrets.token_urlsafe(32)
    now = _now()
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_registration_invites
            SET token_hash=?,token_last4=?,status='created',expires_at=?,sent_at=NULL,opened_at=NULL,last_channel=NULL,
                last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (_hash_token(token), token[-4:], _iso(now + timedelta(days=INVITE_DAYS)), _iso(now), invite_id),
        )
    result = _invite(invite_id)
    result["registration_url"] = f"{str(request.base_url).rstrip('/')}/register/{token}"
    return result


@router.post("/api/academy/registration/invites/{invite_id}/cancel")
def cancel_registration_invite(invite_id: int, user: dict = Depends(_require_sender)):
    invite = _invite(invite_id)
    if str(user.get("role")) == "coach" and int(invite.get("sent_by_user_id") or 0) != int(user.get("id") or 0):
        raise HTTPException(403, "Coaches can cancel only registration links they created")
    if str(invite.get("status")) in {"submitted", "approved", "declined"}:
        raise HTTPException(409, "Submitted registrations must be reviewed rather than cancelled")
    with connection() as conn:
        conn.execute("UPDATE academy_registration_invites SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=?", (invite_id,))
    return _invite(invite_id)


@router.get("/api/academy/registration/applications/{application_id}")
def registration_application(application_id: int, _: dict = Depends(_require_admin)):
    return _application(application_id)


@router.post("/api/academy/registration/applications/{application_id}/review")
def review_registration_application(
    application_id: int,
    payload: RegistrationReviewPayload,
    user: dict = Depends(_require_admin),
):
    application = _application(application_id)
    now = _iso(_now())
    if payload.action == "approve":
        player_id = _approve(application, user)
        result = _application(application_id)
        result["player_id"] = player_id
        return result
    target = "needs_information" if payload.action == "needs_information" else "declined"
    if str(application.get("status")) not in {"submitted", "needs_information"}:
        raise HTTPException(409, "Only submitted registrations can be reviewed")
    reviewer_id = int(user.get("id") or 0) or None
    reviewer_name = str(user.get("display_name") or "Admin")
    with connection() as conn:
        conn.execute(
            """
            UPDATE academy_registration_applications
            SET status=?,review_note=?,reviewed_by_user_id=?,reviewed_by_name=?,reviewed_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (target, _clean(payload.note), reviewer_id, reviewer_name, now, application_id),
        )
        conn.execute(
            """
            UPDATE academy_registration_invites
            SET status=?,reviewed_at=?,last_activity_at=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (target, now, now, int(application["invite_id"])),
        )
    return _application(application_id)


@router.get("/api/public/registration/{token}")
def public_registration(token: str):
    invite = _invite_for_token(token, mark_opened=True)
    application_id = _ensure_application(invite)
    application = _application(application_id)
    return {
        "invite": {
            "id": int(invite["id"]),
            "parent_first_name": invite.get("parent_first_name"),
            "parent_last_name": invite.get("parent_last_name"),
            "parent_phone": invite.get("parent_phone"),
            "parent_email": invite.get("parent_email"),
            "status": invite.get("status"),
            "expires_at": invite.get("expires_at"),
            "sent_by_name": invite.get("sent_by_name"),
        },
        "application": application,
    }


@router.put("/api/public/registration/{token}/draft")
def save_public_registration_draft(token: str, payload: RegistrationApplicationPayload):
    invite = _invite_for_token(token)
    if str(invite.get("status")) not in ACTIVE_PARENT_STATUSES:
        raise HTTPException(409, "This registration is no longer editable")
    return _save_application(invite, payload, submitted=False)


@router.post("/api/public/registration/{token}/submit")
def submit_public_registration(token: str, payload: RegistrationApplicationPayload):
    invite = _invite_for_token(token)
    if str(invite.get("status")) not in ACTIVE_PARENT_STATUSES:
        raise HTTPException(409, "This registration is no longer editable")
    _validate_submission(payload)
    application = _save_application(invite, payload, submitted=True)
    return {"status": "submitted", "application_id": int(application["id"]), "submitted_at": application.get("submitted_at")}


@router.get("/register/{token}", response_class=HTMLResponse)
def registration_form_page(token: str):
    if not PUBLIC_FORM.exists():
        raise HTTPException(503, "Registration form is not available")
    return HTMLResponse(PUBLIC_FORM.read_text(encoding="utf-8"))
