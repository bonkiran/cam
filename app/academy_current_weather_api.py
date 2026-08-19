from __future__ import annotations

import gzip
import json
import logging
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends

from .academy_auth_api import current_access_user
from .database import fetch_one

router = APIRouter(prefix="/api/academy", tags=["academy-current-weather"])

logger = logging.getLogger(__name__)

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
        index = float(value)
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


def _json_request(url: str, *, timeout: int = 8) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "CAM-Academy-Dashboard/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        if str(response.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _cached(key: str, loader) -> dict:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_SECONDS:
            return hit[1]
    payload = loader()
    with _cache_lock:
        _cache[key] = (now, payload)
    return payload


def _open_meteo_search(search_term: str, country_code: str | None) -> list[dict]:
    def load() -> dict:
        params = {
            "name": search_term,
            "count": 8,
            "language": "en",
            "format": "json",
        }
        if country_code:
            params["countryCode"] = country_code
        return _json_request(
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode(params)
        )

    payload = _cached(f"geocode:{search_term}:{country_code or ''}", load)
    results = payload.get("results") or []
    return results if isinstance(results, list) else []


def _open_meteo_location(profile: dict) -> dict | None:
    postal = str(profile.get("postal_code") or "").strip()
    city = str(profile.get("city") or "").strip()
    state = str(profile.get("state") or "").strip()
    country_code = _country_code(profile.get("country"))

    # Prefer the named academy city/state. It is easier to verify visually and
    # avoids selecting a nearby municipality when a ZIP spans multiple places.
    search_terms: list[str] = []
    if city and state:
        search_terms.append(f"{city}, {state}")
    if city:
        search_terms.append(city)
    if postal:
        search_terms.append(postal)

    seen: set[str] = set()
    for search_term in search_terms:
        normalized = search_term.lower()
        if normalized in seen:
            continue
        seen.add(normalized)

        results = _open_meteo_search(search_term, country_code)
        if not results:
            continue

        if city:
            for result in results:
                if str(result.get("name") or "").strip().lower() == city.lower():
                    return result

        if postal:
            for result in results:
                postcodes = result.get("postcodes") or []
                if postal in [str(value) for value in postcodes]:
                    return result

        return results[0]

    return None


def _weather_code_label(code: object) -> str:
    try:
        value = int(code)
    except (TypeError, ValueError):
        return "Current conditions"
    labels = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Rime fog",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Heavy drizzle",
        61: "Light rain",
        63: "Rain",
        65: "Heavy rain",
        71: "Light snow",
        73: "Snow",
        75: "Heavy snow",
        80: "Rain showers",
        81: "Rain showers",
        82: "Heavy rain showers",
        95: "Thunderstorms",
        96: "Thunderstorms with hail",
        99: "Severe thunderstorms with hail",
    }
    return labels.get(value, "Current conditions")


def _heat_index_f(temp_f: object, humidity: object) -> float | None:
    try:
        t = float(temp_f)
        rh = float(humidity)
    except (TypeError, ValueError):
        return None
    if t < 80 or rh < 40:
        return round(t, 1)
    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * rh
        - 0.22475541 * t * rh
        - 0.00683783 * t * t
        - 0.05481717 * rh * rh
        + 0.00122874 * t * t * rh
        + 0.00085282 * t * rh * rh
        - 0.00000199 * t * t * rh * rh
    )
    if rh < 13 and 80 <= t <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt(max(0.0, (17 - abs(t - 95)) / 17))
    elif rh > 85 and 80 <= t <= 87:
        hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round(hi, 1)


def _open_meteo_current(profile: dict) -> dict | None:
    geocoded = _open_meteo_location(profile)
    if not geocoded:
        logger.warning(
            "Open-Meteo geocoding returned no location for city=%r state=%r postal_code=%r country=%r",
            profile.get("city"),
            profile.get("state"),
            profile.get("postal_code"),
            profile.get("country"),
        )
        return None

    latitude = geocoded.get("latitude")
    longitude = geocoded.get("longitude")
    if latitude is None or longitude is None:
        logger.warning("Open-Meteo geocoding result did not contain latitude/longitude: %r", geocoded)
        return None

    def load() -> dict:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,uv_index,wind_speed_10m"
            ),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
            "forecast_days": 1,
        }
        return _json_request(
            "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
        )

    payload = _cached(f"openmeteo:{latitude}:{longitude}", load)
    current = payload.get("current") or {}
    if not isinstance(current, dict) or current.get("temperature_2m") is None:
        logger.warning("Open-Meteo response did not contain current temperature: %r", payload)
        return None

    temperature = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    uv_index = current.get("uv_index")

    return {
        "provider": "Open-Meteo",
        "provider_mode": "primary_no_key",
        "configured": True,
        "status": "ok",
        "location": {
            "city": profile.get("city") or geocoded.get("name"),
            "state": profile.get("state") or geocoded.get("admin1"),
            "postal_code": profile.get("postal_code"),
            "country": profile.get("country") or geocoded.get("country"),
        },
        "temperature_f": temperature,
        "feels_like_f": current.get("apparent_temperature"),
        "heat_index_f": _heat_index_f(temperature, humidity),
        "uv_index": uv_index,
        "uv_description": _uv_description(uv_index),
        "condition": _weather_code_label(current.get("weather_code")),
        "humidity": humidity,
        "wind_mph": current.get("wind_speed_10m"),
        "observed_at": current.get("time"),
    }


@router.get("/weather/current")
def academy_current_weather(_: dict = Depends(current_access_user)):
    profile = _academy() or {}
    location = {
        "city": profile.get("city"),
        "state": profile.get("state"),
        "postal_code": profile.get("postal_code"),
        "country": profile.get("country"),
    }

    has_location = bool(
        str(profile.get("postal_code") or "").strip()
        or str(profile.get("city") or "").strip()
    )
    if not has_location:
        return {
            "provider": "Open-Meteo",
            "configured": True,
            "status": "location_required",
            "location": location,
        }

    try:
        open_meteo = _open_meteo_current(profile)
        if open_meteo:
            return open_meteo
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ):
        logger.exception(
            "Open-Meteo current weather lookup failed for city=%r state=%r postal_code=%r country=%r",
            profile.get("city"),
            profile.get("state"),
            profile.get("postal_code"),
            profile.get("country"),
        )

    return {
        "provider": "Open-Meteo",
        "provider_mode": "primary_no_key",
        "configured": True,
        "status": "unavailable",
        "location": location,
    }
