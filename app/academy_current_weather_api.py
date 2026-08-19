from __future__ import annotations

import gzip
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends

from .academy_auth_api import current_access_user
from .database import fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-current-weather"])

WEATHER_API_KEY = os.environ.get("WEATHER_COM_API_KEY", "").strip()
_CACHE_SECONDS = 10 * 60
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _academy() -> dict | None:
    return fetch_one("SELECT * FROM academies ORDER BY id LIMIT 1")


def _country_code(country: str | None) -> str | None:
    value = (country or "").strip()
    aliases = {
        "united states": "US",
        "united states of america": "US",
        "usa": "US",
        "us": "US",
        "canada": "CA",
        "ca": "CA",
        "india": "IN",
        "in": "IN",
        "united kingdom": "GB",
        "uk": "GB",
        "gb": "GB",
    }
    if value.lower() in aliases:
        return aliases[value.lower()]
    if len(value) == 2 and value.isalpha():
        return value.upper()
    return None


def _uv_description(value: object) -> str | None:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    if index <= 2:
        return "Low"
    if index <= 5:
        return "Moderate"
    if index <= 7:
        return "High"
    if index <= 10:
        return "Very High"
    return "Extreme"


def _request_current(postal_key: str) -> dict:
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(postal_key)
        if cached and now - cached[0] < _CACHE_SECONDS:
            return cached[1]

    query = urllib.parse.urlencode(
        {
            "postalKey": postal_key,
            "units": "e",
            "language": "en-US",
            "format": "json",
            "apiKey": WEATHER_API_KEY,
        }
    )
    request = urllib.request.Request(
        f"https://api.weather.com/v3/wx/observations/current?{query}",
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "CAM-Academy-Dashboard/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read()
        if str(response.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))

    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if isinstance(payload, dict) and isinstance(payload.get("observation"), dict):
        payload = payload["observation"]
    if not isinstance(payload, dict):
        payload = {}

    with _cache_lock:
        _cache[postal_key] = (now, payload)
    return payload


@router.get("/weather/current")
def academy_current_weather(_: dict = Depends(current_access_user)):
    profile = _academy() or {}
    location = {
        "city": profile.get("city"),
        "state": profile.get("state"),
        "postal_code": profile.get("postal_code"),
        "country": profile.get("country"),
    }

    if not WEATHER_API_KEY:
        return {
            "provider": "The Weather Company / weather.com",
            "configured": False,
            "status": "api_key_required",
            "location": location,
        }

    postal_code = str(profile.get("postal_code") or "").strip()
    country_code = _country_code(profile.get("country"))
    if not postal_code or not country_code:
        return {
            "provider": "The Weather Company / weather.com",
            "configured": True,
            "status": "location_required",
            "location": location,
        }

    try:
        observation = _request_current(f"{postal_code}:{country_code}")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        return {
            "provider": "The Weather Company / weather.com",
            "configured": True,
            "status": "unavailable",
            "location": location,
        }

    uv_index = observation.get("uvIndex", observation.get("uv_index"))
    uv_description = observation.get("uvDescription", observation.get("uv_desc")) or _uv_description(uv_index)
    temperature = observation.get("temperature", observation.get("temp"))
    heat_index = observation.get("temperatureHeatIndex", observation.get("heat_index"))
    feels_like = observation.get("temperatureFeelsLike", observation.get("feels_like"))
    condition = observation.get("wxPhraseLong", observation.get("wx_phrase")) or observation.get("cloudCoverPhrase")

    return {
        "provider": "The Weather Company / weather.com",
        "configured": True,
        "status": "ok",
        "location": location,
        "temperature_f": temperature,
        "feels_like_f": feels_like,
        "heat_index_f": heat_index if heat_index is not None else temperature,
        "uv_index": uv_index,
        "uv_description": uv_description,
        "condition": condition,
        "humidity": observation.get("relativeHumidity", observation.get("rh")),
        "observed_at": observation.get("validTimeLocal"),
    }
