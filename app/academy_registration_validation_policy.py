from __future__ import annotations

import re

from fastapi import HTTPException

from . import academy_registration_api as registration_api
from .database import connection


_ORIGINAL_APPROVE = registration_api._approve
_PHONE_ALLOWED = re.compile(r"^\+?[0-9 ()\-.]+$")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _valid_phone(value: str | None) -> bool:
    text = _clean(value)
    if not text or not _PHONE_ALLOWED.fullmatch(text):
        return False
    digits = re.sub(r"\D", "", text)
    return 7 <= len(digits) <= 15


def _contact_complete(contact) -> bool:
    return bool(
        contact
        and all(
            [
                _clean(contact.first_name),
                _clean(contact.last_name),
                _clean(contact.relationship),
                _clean(contact.phone),
            ]
        )
    )


def _validate_submission(payload) -> None:
    """Apply the current parent-registration rules.

    Emergency Contact 1 is required. Emergency Contact 2 is optional, but if it
    is supplied its core name/relationship/phone fields must be complete.

    Parent and emergency-contact phone numbers accept normal phone formatting
    characters, but must contain 7-15 digits and cannot contain letters.

    The public form no longer collects a separate Guardian section. For the
    current data model, guardian_same_as_parent is reused by that form as the
    primary parent's pickup-authorization flag. Explicit legacy guardian
    payloads remain supported for backward compatibility.
    """
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

    problems: list[str] = []
    for label, value in required.items():
        if isinstance(value, str):
            if not _clean(value):
                problems.append(label)
        elif value is None:
            problems.append(label)

    if _clean(payload.parent_phone) and not _valid_phone(payload.parent_phone):
        problems.append("Parent phone must be a valid phone number")

    if payload.wicketkeeping is None:
        problems.append("Wicketkeeping")

    contacts = list(payload.emergency_contacts or [])
    if not contacts or not _contact_complete(contacts[0]):
        problems.append("Emergency contact 1 name, relationship and phone")
    elif not _valid_phone(contacts[0].phone):
        problems.append("Emergency contact 1 phone must be a valid phone number")

    if len(contacts) > 1:
        if not _contact_complete(contacts[1]):
            problems.append("Emergency contact 2 name, relationship and phone")
        elif not _valid_phone(contacts[1].phone):
            problems.append("Emergency contact 2 phone must be a valid phone number")

    # Legacy API clients may still submit an explicit additional guardian.
    # Validate it when present, but do not require one merely because the
    # public-form pickup checkbox is unchecked.
    if payload.guardian is not None:
        if not _contact_complete(payload.guardian):
            problems.append("Guardian name, relationship and phone")
        elif not _valid_phone(payload.guardian.phone):
            problems.append("Guardian phone must be a valid phone number")

    if not payload.consent_confirmed:
        problems.append("Registration confirmation")

    if problems:
        raise HTTPException(
            422,
            "Complete required registration fields: " + ", ".join(dict.fromkeys(problems)),
        )


def _approve_with_parent_pickup(application: dict, user: dict) -> int:
    """Preserve legacy guardians while applying the new primary-parent pickup flag."""
    # An explicit guardian means this is an older/API-driven application. Keep
    # the original approval behavior so existing registrations are not changed.
    if application.get("guardian"):
        return _ORIGINAL_APPROVE(application, user)

    parent_pickup_authorized = bool(application.get("guardian_same_as_parent"))
    normalized = dict(application)
    normalized["guardian_same_as_parent"] = True
    normalized["guardian"] = None

    player_id = _ORIGINAL_APPROVE(normalized, user)
    with connection() as conn:
        conn.execute(
            """
            UPDATE player_guardians
            SET pickup_authorized=?
            WHERE player_id=? AND is_primary=1
            """,
            (1 if parent_pickup_authorized else 0, player_id),
        )
    return player_id


def apply_registration_validation_policy() -> None:
    registration_api._validate_submission = _validate_submission
    registration_api._approve = _approve_with_parent_pickup
