from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_CENSUS_ADDRESS_URL = "https://geocoding.geo.census.gov/geocoder/locations/address"


class AddressVerificationUnavailable(RuntimeError):
    """Raised when the external address verification service cannot be reached."""


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _fetch_json(url: str, *, timeout: float = 5.0) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": "CrickAnalysis/1.0 registration-address-validation",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AddressVerificationUnavailable("US address verification is temporarily unavailable") from exc


def verify_us_address(*, street: str, city: str, state: str, zip_code: str) -> dict:
    """Verify that street/city/state/ZIP resolve as one US address.

    Production uses the public U.S. Census Geocoder at submit time. Tests can set
    CAM_ADDRESS_VALIDATION_MODE=stub so routine registration tests remain
    deterministic and do not depend on external network availability.
    """
    mode = os.environ.get("CAM_ADDRESS_VALIDATION_MODE", "census").strip().lower()
    street = _clean(street)
    city = _clean(city)
    state = _clean(state).upper()
    zip_code = _clean(zip_code)

    if mode in {"stub", "test"}:
        return {
            "verified": True,
            "source": "stub",
            "matched_address": f"{street}, {city}, {state} {zip_code}".strip(),
            "city": city,
            "state": state,
            "zip": zip_code,
        }

    if mode in {"off", "disabled"}:
        return {
            "verified": True,
            "source": "disabled",
            "matched_address": None,
            "city": city,
            "state": state,
            "zip": zip_code,
        }

    query = urlencode(
        {
            "street": street,
            "city": city,
            "state": state,
            "zip": zip_code,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
    )
    data = _fetch_json(f"{_CENSUS_ADDRESS_URL}?{query}")
    matches = (((data or {}).get("result") or {}).get("addressMatches") or [])
    if not matches:
        return {
            "verified": False,
            "source": "US Census Geocoder",
            "matched_address": None,
            "city": None,
            "state": None,
            "zip": None,
        }

    match = matches[0] or {}
    components = match.get("addressComponents") or {}
    matched_state = _clean(components.get("state")).upper()
    matched_zip = _clean(components.get("zip"))

    # A Census match means the supplied street/city/state/ZIP combination could
    # be geocoded. Keep the explicit state/ZIP equality guard so a loose match
    # cannot silently change the billing-location fields the parent submitted.
    verified = matched_state == state and matched_zip == zip_code
    return {
        "verified": verified,
        "source": "US Census Geocoder",
        "matched_address": match.get("matchedAddress"),
        "city": _clean(components.get("city")) or None,
        "state": matched_state or None,
        "zip": matched_zip or None,
    }
