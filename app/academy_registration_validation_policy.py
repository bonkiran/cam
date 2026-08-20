from __future__ import annotations

from fastapi import HTTPException

from . import academy_registration_api as registration_api


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _validate_submission(payload) -> None:
    """Validate required registration fields while keeping emergency contacts optional.

    Parents may provide zero, one, or two emergency contacts. If they start an
    emergency-contact record, the core name/relationship/phone fields must be
    complete so CAM never stores a misleading partial safety contact.
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

    missing: list[str] = []
    for label, value in required.items():
        if isinstance(value, str):
            if not _clean(value):
                missing.append(label)
        elif value is None:
            missing.append(label)

    if payload.wicketkeeping is None:
        missing.append("Wicketkeeping")

    for index, contact in enumerate(payload.emergency_contacts, start=1):
        supplied_values = (
            contact.first_name,
            contact.last_name,
            contact.relationship,
            contact.phone,
            contact.email,
            contact.address_line1,
            contact.address_line2,
            contact.city,
            contact.state,
            contact.postal_code,
            contact.country,
        )
        if not any(_clean(value) for value in supplied_values if isinstance(value, str)):
            continue
        if not all(
            [
                _clean(contact.first_name),
                _clean(contact.last_name),
                _clean(contact.relationship),
                _clean(contact.phone),
            ]
        ):
            missing.append(f"Emergency contact {index} name, relationship and phone")

    if not payload.guardian_same_as_parent:
        guardian = payload.guardian
        if not guardian or not all(
            [
                _clean(guardian.first_name),
                _clean(guardian.last_name),
                _clean(guardian.relationship),
                _clean(guardian.phone),
            ]
        ):
            missing.append("Guardian name, relationship and phone")

    if not payload.consent_confirmed:
        missing.append("Registration confirmation")

    if missing:
        raise HTTPException(
            422,
            "Complete required registration fields: " + ", ".join(dict.fromkeys(missing)),
        )


def apply_registration_validation_policy() -> None:
    registration_api._validate_submission = _validate_submission
