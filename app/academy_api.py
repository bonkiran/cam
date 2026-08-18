from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .database import IntegrityErrors, connection, database_backend, fetch_all, fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy"])


class AcademyProfilePayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    website: str | None = Field(default=None, max_length=240)
    address_line1: str | None = Field(default=None, max_length=240)
    address_line2: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default="United States", max_length=120)
    timezone: str | None = Field(default="America/New_York", max_length=100)


class GuardianPayload(BaseModel):
    id: int | None = None
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    relationship: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    address_line1: str | None = Field(default=None, max_length=240)
    address_line2: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=120)
    is_primary: bool = False
    billing_contact: bool = False
    pickup_authorized: bool = True


class PlayerPayload(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    preferred_name: str | None = Field(default=None, max_length=100)
    date_of_birth: str | None = Field(default=None, max_length=20)
    gender: str | None = Field(default=None, max_length=50)
    batting_style: str | None = Field(default=None, max_length=60)
    bowling_style: str | None = Field(default=None, max_length=100)
    handedness: str | None = Field(default=None, max_length=40)
    skill_level: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    address_line1: str | None = Field(default=None, max_length=240)
    address_line2: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=120)
    emergency_contact_name: str | None = Field(default=None, max_length=160)
    emergency_contact_phone: str | None = Field(default=None, max_length=60)
    joined_on: str | None = Field(default=None, max_length=20)
    status: Literal["active", "inactive", "waitlisted"] = "active"
    notes: str | None = Field(default=None, max_length=3000)
    guardians: list[GuardianPayload] | None = None


PLAYER_COLUMNS = [
    "name", "first_name", "last_name", "preferred_name", "date_of_birth", "gender",
    "batting_style", "bowling_style", "handedness", "skill_level", "email", "phone",
    "address_line1", "address_line2", "city", "state", "postal_code", "country",
    "emergency_contact_name", "emergency_contact_phone", "joined_on", "status", "notes",
]

GUARDIAN_COLUMNS = [
    "first_name", "last_name", "relationship", "email", "phone", "address_line1",
    "address_line2", "city", "state", "postal_code", "country",
]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _academy_row() -> dict | None:
    return fetch_one("SELECT * FROM academies ORDER BY id LIMIT 1")


def _academy_id(conn: Any) -> int | None:
    row = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _guardian_rows(player_id: int) -> list[dict]:
    return fetch_all(
        """
        SELECT g.*, pg.is_primary, pg.billing_contact, pg.pickup_authorized
        FROM guardians g
        JOIN player_guardians pg ON pg.guardian_id=g.id
        WHERE pg.player_id=?
        ORDER BY pg.is_primary DESC, g.last_name COLLATE NOCASE, g.first_name COLLATE NOCASE
        """,
        (player_id,),
    )


def _player_row(player_id: int) -> dict:
    player = fetch_one(
        """
        SELECT p.*,
               COUNT(DISTINCT v.id) AS video_count,
               SUM(CASE WHEN v.status='complete' THEN 1 ELSE 0 END) AS completed_analyses
        FROM players p
        LEFT JOIN videos v ON v.player_id=p.id
        WHERE p.id=?
        GROUP BY p.id
        """,
        (player_id,),
    )
    if not player:
        raise HTTPException(404, "Player not found")
    player["guardians"] = _guardian_rows(player_id)
    return player


def _payload_values(payload: PlayerPayload) -> list[str | None]:
    raw = payload.model_dump(exclude={"guardians"})
    values: list[str | None] = []
    for column in PLAYER_COLUMNS:
        value = raw.get(column)
        if isinstance(value, str):
            value = _clean(value)
        values.append(value)
    return values


def _save_guardians(conn: Any, player_id: int, academy_id: int | None,
                    guardians: list[GuardianPayload]) -> None:
    conn.execute("DELETE FROM player_guardians WHERE player_id=?", (player_id,))
    for guardian in guardians:
        raw = guardian.model_dump()
        guardian_id = raw.pop("id", None)
        is_primary = 1 if raw.pop("is_primary", False) else 0
        billing_contact = 1 if raw.pop("billing_contact", False) else 0
        pickup_authorized = 1 if raw.pop("pickup_authorized", True) else 0
        values = [_clean(raw.get(column)) for column in GUARDIAN_COLUMNS]

        if guardian_id is not None:
            existing = conn.execute("SELECT id FROM guardians WHERE id=?", (guardian_id,)).fetchone()
            if not existing:
                raise HTTPException(400, f"Guardian {guardian_id} not found")
            assignments = ", ".join(f"{column}=?" for column in GUARDIAN_COLUMNS)
            conn.execute(
                f"UPDATE guardians SET {assignments}, academy_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*values, academy_id, guardian_id),
            )
        else:
            placeholders = ",".join("?" for _ in GUARDIAN_COLUMNS)
            cur = conn.execute(
                f"INSERT INTO guardians({','.join(GUARDIAN_COLUMNS)},academy_id) VALUES({placeholders},?)",
                (*values, academy_id),
            )
            guardian_id = int(cur.lastrowid)

        conn.execute(
            """
            INSERT INTO player_guardians(player_id,guardian_id,is_primary,billing_contact,pickup_authorized)
            VALUES(?,?,?,?,?)
            """,
            (player_id, guardian_id, is_primary, billing_contact, pickup_authorized),
        )


@router.get("/profile")
def academy_profile():
    profile = _academy_row()
    return {"configured": bool(profile), "profile": profile, "database_backend": database_backend()}


@router.put("/profile")
def save_academy_profile(payload: AcademyProfilePayload):
    values = [
        _clean(payload.name), _clean(payload.email), _clean(payload.phone), _clean(payload.website),
        _clean(payload.address_line1), _clean(payload.address_line2), _clean(payload.city),
        _clean(payload.state), _clean(payload.postal_code), _clean(payload.country) or "United States",
        _clean(payload.timezone) or "America/New_York",
    ]
    with connection() as conn:
        existing = conn.execute("SELECT id FROM academies ORDER BY id LIMIT 1").fetchone()
        if existing:
            academy_id = int(existing["id"])
            conn.execute(
                """
                UPDATE academies SET name=?,email=?,phone=?,website=?,address_line1=?,address_line2=?,
                    city=?,state=?,postal_code=?,country=?,timezone=?,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (*values, academy_id),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO academies(name,email,phone,website,address_line1,address_line2,city,state,
                    postal_code,country,timezone)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                values,
            )
            academy_id = int(cur.lastrowid)
            conn.execute("UPDATE players SET academy_id=? WHERE academy_id IS NULL", (academy_id,))
    return {
        "configured": True,
        "profile": fetch_one("SELECT * FROM academies WHERE id=?", (academy_id,)),
        "database_backend": database_backend(),
    }


@router.get("/players")
def academy_players():
    rows = fetch_all(
        """
        SELECT p.*,
               COUNT(DISTINCT v.id) AS video_count,
               SUM(CASE WHEN v.status='complete' THEN 1 ELSE 0 END) AS completed_analyses
        FROM players p
        LEFT JOIN videos v ON v.player_id=p.id
        GROUP BY p.id
        ORDER BY p.name COLLATE NOCASE
        """
    )
    for row in rows:
        row["guardians"] = _guardian_rows(int(row["id"]))
    return rows


@router.get("/players/{player_id}")
def academy_player(player_id: int):
    return _player_row(player_id)


@router.post("/players", status_code=201)
def create_academy_player(payload: PlayerPayload):
    values = _payload_values(payload)
    placeholders = ",".join("?" for _ in PLAYER_COLUMNS)
    try:
        with connection() as conn:
            academy_id = _academy_id(conn)
            cur = conn.execute(
                f"INSERT INTO players({','.join(PLAYER_COLUMNS)},academy_id,updated_at) VALUES({placeholders},?,CURRENT_TIMESTAMP)",
                (*values, academy_id),
            )
            player_id = int(cur.lastrowid)
            if payload.guardians:
                _save_guardians(conn, player_id, academy_id, payload.guardians)
    except IntegrityErrors as exc:
        if "players.name" in str(exc) or "UNIQUE" in str(exc).upper() or "idx_players_name_nocase" in str(exc):
            raise HTTPException(409, "A player with this name already exists") from exc
        raise
    return _player_row(player_id)


@router.put("/players/{player_id}")
def update_academy_player(player_id: int, payload: PlayerPayload):
    values = _payload_values(payload)
    assignments = ", ".join(f"{column}=?" for column in PLAYER_COLUMNS)
    try:
        with connection() as conn:
            existing = conn.execute("SELECT id FROM players WHERE id=?", (player_id,)).fetchone()
            if not existing:
                raise HTTPException(404, "Player not found")
            academy_id = _academy_id(conn)
            conn.execute(
                f"UPDATE players SET {assignments}, academy_id=COALESCE(academy_id,?), updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*values, academy_id, player_id),
            )
            if payload.guardians is not None:
                _save_guardians(conn, player_id, academy_id, payload.guardians)
    except IntegrityErrors as exc:
        if "players.name" in str(exc) or "UNIQUE" in str(exc).upper() or "idx_players_name_nocase" in str(exc):
            raise HTTPException(409, "A player with this name already exists") from exc
        raise
    return _player_row(player_id)
