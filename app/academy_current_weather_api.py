from __future__ import annotations

import gzip
import json
import math
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


def _weather_com_current(postal_key: str) -> dict:
    def load() -> dict:
        query = urllib.parse.urlencode(
            {
                "postalKey": postal_key,
                "units": "e",
                "language": "en-US",
                "format": "json",
                "apiKey": WEATHER_API_KEY,
            }
        )
        payload = _json_request(f"https://api.weather.com/v3/wx/observations/current?{query}")
        if isinstance(payload.get("observation"), dict):
            return payload["observation"]
        return payload

    return _cached(f"weathercom:{postal_key}", load)


def _open_meteo_location(profile: dict) -> dict | None:
    postal = str(profile.get("postal_code") or "").strip()
    city = str(profile.get("city") or "").strip()
    state = str(profile.get("state") or "").strip()
    country_code = _country_code(profile.get("country"))

    search_term = postal or city
    if not search_term:
        return None
    if not postal and state:
        search_term = f"{city}, {state}"

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
            "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(params)
        )

    payload = _cached(f"geocode:{search_term}:{country_code or ''}", load)
    results = payload.get("results") or []
    if not isinstance(results, list) or not results:
        return None

    if postal:
        for result in results:
            postcodes = result.get("postcodes") or []
            if postal in [str(value) for value in postcodes]:
                return result
    if city:
        for result in results:
            if str(result.get("name") or "").lower() == city.lower():
                return result
    return results[0]


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
        return None

    latitude = geocoded.get("latitude")
    longitude = geocoded.get("longitude")
    if latitude is None or longitude is None:
        return None

    def load() -> dict:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,uv_index,wind_speed_10m",
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
        return None

    temperature = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    uv_index = current.get("uv_index")
    return {
        "provider": "Open-Meteo",
        "provider_mode": "no_key_fallback",
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


def _weather_com_response(profile: dict) -> dict | None:
    if not WEATHER_API_KEY:
        return None
    postal_code = str(profile.get("postal_code") or "").strip()
    country_code = _country_code(profile.get("country"))
    if not postal_code or not country_code:
        return None
    observation = _weather_com_current(f"{postal_code}:{country_code}")
    uv_index = observation.get("uvIndex", observation.get("uv_index"))
    temperature = observation.get("temperature", observation.get("temp"))
    if temperature is None:
        return None
    heat_index = observation.get("temperatureHeatIndex", observation.get("heat_index"))
    return {
        "provider": "The Weather Company / weather.com",
        "provider_mode": "configured_primary",
        "configured": True,
        "status": "ok",
        "location": {
            "city": profile.get("city"),
            "state": profile.get("state"),
            "postal_code": profile.get("postal_code"),
            "country": profile.get("country"),
        },
        "temperature_f": temperature,
        "feels_like_f": observation.get("temperatureFeelsLike", observation.get("feels_like")),
        "heat_index_f": heat_index if heat_index is not None else _heat_index_f(
            temperature, observation.get("relativeHumidity", observation.get("rh"))
        ),
        "uv_index": uv_index,
        "uv_description": observation.get("uvDescription", observation.get("uv_desc")) or _uv_description(uv_index),
        "condition": observation.get("wxPhraseLong", observation.get("wx_phrase")) or observation.get("cloudCoverPhrase"),
        "humidity": observation.get("relativeHumidity", observation.get("rh")),
        "wind_mph": observation.get("windSpeed", observation.get("wspd")),
        "observed_at": observation.get("validTimeLocal"),
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

    # Prefer the configured Weather.com adapter. During the controlled pilot,
    # fall back to Open-Meteo so the dashboard can show live conditions without
    # adding a paid credential or committing a secret.
    if WEATHER_API_KEY:
        try:
            weather_com = _weather_com_response(profile)
            if weather_com:
                return weather_com
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
            pass

    try:
        open_meteo = _open_meteo_current(profile)
        if open_meteo:
            return open_meteo
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError):
        pass

    has_location = bool(str(profile.get("postal_code") or "").strip() or str(profile.get("city") or "").strip())
    return {
        "provider": "Weather.com primary / Open-Meteo pilot fallback",
        "configured": True,
        "status": "unavailable" if has_location else "location_required",
        "location": location,
    }
