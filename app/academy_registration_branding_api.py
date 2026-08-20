from __future__ import annotations

from fastapi import APIRouter, Depends

from .academy_registration_api import _invite_for_token, _require_sender
from .database import fetch_one


router = APIRouter(tags=["academy-registration-branding"])


def _academy_name(academy_id: int | None = None) -> str:
    row = None
    if academy_id:
        row = fetch_one("SELECT name FROM academies WHERE id=?", (academy_id,))
    if not row:
        row = fetch_one("SELECT name FROM academies ORDER BY id LIMIT 1")
    name = str((row or {}).get("name") or "").strip()
    return name or "Academy"


@router.get("/api/academy/registration/branding")
def academy_registration_branding(user: dict = Depends(_require_sender)):
    academy_id = int(user.get("academy_id") or 0) or None
    return {"academy_name": _academy_name(academy_id)}


@router.get("/api/public/registration/{token}/branding")
def public_registration_branding(token: str):
    invite = _invite_for_token(token)
    academy_id = int(invite.get("academy_id") or 0) or None
    return {"academy_name": _academy_name(academy_id)}
