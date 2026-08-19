from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .academy_auth_api import require_access_admin
from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy/owner-console", tags=["academy-owner-console"])


class NotificationEventPayload(BaseModel):
    event_type: Literal["session_rescheduled", "session_cancelled"]
    entity_type: Literal["session"] = "session"
    entity_id: int = Field(gt=0)
    channels: list[Literal["whatsapp", "push", "email"]] = Field(default_factory=list, max_length=3)
    message: str | None = Field(default=None, max_length=1200)
    metadata: dict[str, object] = Field(default_factory=dict)


def _ensure_tables() -> None:
    schema = """
        CREATE TABLE IF NOT EXISTS academy_notification_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            academy_id BIGINT,
            event_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id BIGINT NOT NULL,
            channels_json TEXT NOT NULL DEFAULT '[]',
            recipients_json TEXT NOT NULL DEFAULT '[]',
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'recorded',
            created_by_user_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_academy_notification_events_academy ON academy_notification_events(academy_id);
        CREATE INDEX IF NOT EXISTS idx_academy_notification_events_entity ON academy_notification_events(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_academy_notification_events_created ON academy_notification_events(created_at);
    """
    with connection() as conn:
        conn.executescript(schema)


def _academy_id() -> int | None:
    row = fetch_one("SELECT id FROM academies ORDER BY id LIMIT 1")
    return int(row["id"]) if row else None


def _session_recipients(session_id: int) -> list[dict]:
    session = fetch_one(
        """
        SELECT s.id,s.coach_id,c.first_name AS coach_first_name,c.last_name AS coach_last_name,
               c.phone AS coach_phone,c.email AS coach_email
        FROM academy_sessions s
        LEFT JOIN coaches c ON c.id=s.coach_id
        WHERE s.id=?
        """,
        (session_id,),
    )
    if not session:
        raise HTTPException(404, "Session not found")

    recipients: list[dict] = []
    if session.get("coach_id"):
        recipients.append(
            {
                "recipient_type": "coach",
                "id": int(session["coach_id"]),
                "name": " ".join(
                    value for value in [session.get("coach_first_name"), session.get("coach_last_name")] if value
                ).strip(),
                "phone": session.get("coach_phone"),
                "email": session.get("coach_email"),
            }
        )

    guardians = fetch_all(
        """
        SELECT DISTINCT g.id,g.first_name,g.last_name,g.phone,g.email
        FROM session_players sp
        JOIN player_guardians pg ON pg.player_id=sp.player_id
        JOIN guardians g ON g.id=pg.guardian_id
        WHERE sp.session_id=?
        ORDER BY g.last_name,g.first_name,g.id
        """,
        (session_id,),
    )
    for guardian in guardians:
        recipients.append(
            {
                "recipient_type": "guardian",
                "id": int(guardian["id"]),
                "name": f"{guardian.get('first_name') or ''} {guardian.get('last_name') or ''}".strip(),
                "phone": guardian.get("phone"),
                "email": guardian.get("email"),
            }
        )
    return recipients


def _decode_event(row: dict) -> dict:
    out = dict(row)
    for source, target in [
        ("channels_json", "channels"),
        ("recipients_json", "recipients"),
        ("payload_json", "payload"),
    ]:
        raw = out.pop(source, None)
        try:
            out[target] = json.loads(raw or ("[]" if target != "payload" else "{}"))
        except Exception:
            out[target] = [] if target != "payload" else {}
    return out


_ensure_tables()


@router.post("/notification-events", status_code=201)
def create_notification_event(
    payload: NotificationEventPayload,
    user: dict = Depends(require_access_admin),
):
    if payload.entity_type != "session":
        raise HTTPException(422, "Unsupported notification entity")
    recipients = _session_recipients(payload.entity_id)
    channels = list(dict.fromkeys(payload.channels))
    # CAM records the event and intended channels now. External dispatch remains
    # adapter-driven so a paid WhatsApp, push, or email provider is never invoked
    # unless an academy explicitly configures one later.
    status = "awaiting_provider" if channels else "recorded"
    event_payload = {
        "message": payload.message,
        "metadata": payload.metadata,
        "dispatch_attempted": False,
        "provider_configured": False,
    }
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO academy_notification_events(
                academy_id,event_type,entity_type,entity_id,channels_json,recipients_json,
                payload_json,status,created_by_user_id
            ) VALUES(?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (
                _academy_id(),
                payload.event_type,
                payload.entity_type,
                payload.entity_id,
                json.dumps(channels),
                json.dumps(recipients),
                json.dumps(event_payload),
                status,
                int(user["id"]),
            ),
        ).fetchone()
        event_id = int(row["id"])
    result = fetch_one("SELECT * FROM academy_notification_events WHERE id=?", (event_id,))
    if not result:
        raise HTTPException(500, "Notification event could not be recorded")
    decoded = _decode_event(result)
    decoded["recipient_count"] = len(recipients)
    return decoded


@router.get("/notification-events")
def notification_events(
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(require_access_admin),
):
    rows = fetch_all(
        "SELECT * FROM academy_notification_events ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [_decode_event(row) for row in rows]
