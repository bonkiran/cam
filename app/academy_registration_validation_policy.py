from __future__ import annotations

import re

from fastapi import HTTPException

from . import academy_registration_api as registration_api


_PHONE_ALLOWED = re.compile(r"^\+?[0-9 ()\-.]+$")
_ZIP_5 = re.compile(r"^[0-9]{5}$")

_US_STATES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}
_STATE_LOOKUP = {code.lower(): code for code in _US_STATES}
_STATE_LOOKUP.update({name.lower(): code for code, name in _US_STATES.items()})


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
    return 9 <= len(digits) <= 15


def _normalize_us_state(value: str | None) -> str | None:
    text = _clean(value)
    if not text:
        return None
    return _STATE_LOOKUP.get(text.lower())


def _valid_us_zip(value: str | None) -> bool:
    text = _clean(value)
    return bool(text and _ZIP_5.fullmatch(text))


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
    """Apply the current public parent-registration rules.

    - Emergency Contact 1 is required; Emergency Contact 2 is optional.
    - Parent and emergency-contact phone numbers use 9-15 digits and may use
      ordinary phone formatting characters, but never letters.
    - Parent state must be a valid US state/DC abbreviation or full name.
    - Parent ZIP must be exactly five digits. It remains text so leading zeroes
      are preserved.
    - The public form does not collect a separate Guardian/pickup-authorized
      field. Legacy API guardian payloads remain supported for compatibility.
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
        problems.append("Parent phone must contain 9-15 digits and no letters")

    normalized_state = _normalize_us_state(payload.parent_state)
    if _clean(payload.parent_state) and not normalized_state:
        problems.append("Parent state must be a valid US state name or 2-letter abbreviation")
    elif normalized_state:
        payload.parent_state = normalized_state

    if _clean(payload.parent_postal_code) and not _valid_us_zip(payload.parent_postal_code):
        problems.append("Parent ZIP must be a valid 5-digit US ZIP code")

    if payload.wicketkeeping is None:
        problems.append("Wicketkeeping")

    contacts = list(payload.emergency_contacts or [])
    if not contacts or not _contact_complete(contacts[0]):
        problems.append("Emergency contact 1 name, relationship and phone")
    elif not _valid_phone(contacts[0].phone):
        problems.append("Emergency contact 1 phone must contain 9-15 digits and no letters")

    if len(contacts) > 1:
        if not _contact_complete(contacts[1]):
            problems.append("Emergency contact 2 name, relationship and phone")
        elif not _valid_phone(contacts[1].phone):
            problems.append("Emergency contact 2 phone must contain 9-15 digits and no letters")

    # Legacy API clients may still submit an explicit additional guardian.
    if payload.guardian is not None:
        if not _contact_complete(payload.guardian):
            problems.append("Guardian name, relationship and phone")
        elif not _valid_phone(payload.guardian.phone):
            problems.append("Guardian phone must contain 9-15 digits and no letters")

    if not payload.consent_confirmed:
        problems.append("Registration confirmation")

    if problems:
        raise HTTPException(
            422,
            "Complete required registration fields: " + ", ".join(dict.fromkeys(problems)),
        )


def apply_registration_validation_policy() -> None:
    registration_api._validate_submission = _validate_submission
