from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .cam_auth_api import require_access_admin
from .database import connection, fetch_all, fetch_one

router = APIRouter(prefix="/api/cam/owner-console", tags=["cam-owner-console"])


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


def _player_directory_rows() -> list[dict]:
    rows = fetch_all(
        """
        SELECT p.id AS player_id,p.name AS player_name,p.status AS player_status,p.joined_on,
               b.id AS batch_id,b.name AS batch_name,bp.status AS batch_status,
               g.id AS guardian_id,g.first_name AS guardian_first_name,g.last_name AS guardian_last_name,
               g.phone AS guardian_phone,g.email AS guardian_email,pg.is_primary
        FROM players p
        LEFT JOIN batch_players bp ON bp.player_id=p.id AND bp.status IN ('active','waitlisted')
        LEFT JOIN batches b ON b.id=bp.batch_id
        LEFT JOIN player_guardians pg ON pg.player_id=p.id
        LEFT JOIN guardians g ON g.id=pg.guardian_id
        ORDER BY p.name COLLATE NOCASE,b.name COLLATE NOCASE,pg.is_primary DESC,g.last_name COLLATE NOCASE,g.first_name COLLATE NOCASE
        """
    )
    players: dict[int, dict] = {}
    for row in rows:
        player_id = int(row["player_id"])
        player = players.setdefault(
            player_id,
            {
                "id": player_id,
                "name": row.get("player_name"),
                "status": row.get("player_status"),
                "joined_on": row.get("joined_on"),
                "batches": [],
                "guardians": [],
                "cricclubs": {"status": "not_connected", "last_sync_at": None},
            },
        )
        if row.get("batch_id") and not any(int(item["id"]) == int(row["batch_id"]) for item in player["batches"]):
            player["batches"].append(
                {
                    "id": int(row["batch_id"]),
                    "name": row.get("batch_name"),
                    "status": row.get("batch_status"),
                }
            )
        if row.get("guardian_id") and not any(int(item["id"]) == int(row["guardian_id"]) for item in player["guardians"]):
            player["guardians"].append(
                {
                    "id": int(row["guardian_id"]),
                    "name": f"{row.get('guardian_first_name') or ''} {row.get('guardian_last_name') or ''}".strip(),
                    "phone": row.get("guardian_phone"),
                    "email": row.get("guardian_email"),
                    "is_primary": bool(row.get("is_primary")),
                }
            )
    return list(players.values())


def _player_summary(player_id: int) -> dict:
    player = fetch_one("SELECT * FROM players WHERE id=?", (player_id,))
    if not player:
        raise HTTPException(404, "Player not found")
    guardians = fetch_all(
        """
        SELECT g.*,pg.is_primary,pg.billing_contact,pg.pickup_authorized
        FROM player_guardians pg
        JOIN guardians g ON g.id=pg.guardian_id
        WHERE pg.player_id=?
        ORDER BY pg.is_primary DESC,g.last_name COLLATE NOCASE,g.first_name COLLATE NOCASE
        """,
        (player_id,),
    )
    batches = fetch_all(
        """
        SELECT bp.id,bp.status,bp.joined_on,b.id AS batch_id,b.name AS batch_name,
               pr.id AS program_id,pr.name AS program_name
        FROM batch_players bp
        JOIN batches b ON b.id=bp.batch_id
        LEFT JOIN programs pr ON pr.id=b.program_id
        WHERE bp.player_id=? AND bp.status IN ('active','waitlisted')
        ORDER BY b.name COLLATE NOCASE
        """,
        (player_id,),
    )
    coaches = fetch_all(
        """
        SELECT a.id,a.assignment_role,a.start_date,a.status,c.id AS coach_id,c.first_name,c.last_name
        FROM coach_player_assignments a
        JOIN coaches c ON c.id=a.coach_id
        WHERE a.player_id=? AND a.status='active'
        ORDER BY CASE WHEN a.assignment_role='primary' THEN 0 ELSE 1 END,c.last_name,c.first_name
        """,
        (player_id,),
    )
    attendance_rows = fetch_all(
        "SELECT status,COUNT(*) AS count FROM player_attendance WHERE player_id=? GROUP BY status",
        (player_id,),
    )
    attendance = {"present": 0, "late": 0, "absent": 0, "excused": 0}
    for row in attendance_rows:
        status = str(row.get("status") or "")
        if status in attendance:
            attendance[status] = int(row.get("count") or 0)
    review_count = 0
    try:
        row = fetch_one("SELECT COUNT(*) AS count FROM academy_player_reviews WHERE player_id=?", (player_id,))
        review_count = int((row or {}).get("count") or 0)
    except Exception:
        review_count = 0
    return {
        "player": player,
        "guardians": guardians,
        "batches": batches,
        "coaches": coaches,
        "attendance": attendance,
        "review_count": review_count,
        "cricclubs": {"status": "not_connected", "last_sync_at": None},
        "requests_complaints": {"count": 0, "status": "not_configured"},
    }


_ensure_tables()


@router.get("/players")
def owner_player_directory(_: dict = Depends(require_access_admin)):
    return _player_directory_rows()


@router.get("/players/{player_id}/summary")
def owner_player_summary(player_id: int, _: dict = Depends(require_access_admin)):
    return _player_summary(player_id)


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
