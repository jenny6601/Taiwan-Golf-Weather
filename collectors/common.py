"""Shared CWA parsing, quality checks and Supabase persistence helpers."""
from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from supabase import create_client


def supabase_client():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SECRET_KEY"]
    return create_client(url, key)


def fetch_json(url: str, api_key: str) -> dict[str, Any]:
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                params={"Authorization": api_key, "format": "JSON"},
                headers={"User-Agent": "Taiwan-Golf-Weather-V32.1"},
                timeout=(10, 45),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("CWA response is not a JSON object")
            return payload
        except Exception as exc:  # retry transient API/network failures
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"CWA request failed after 3 attempts: {last_error}")


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number in (-99, -999, -999.0, -9999):
        return None
    return number


def nested_get(obj: dict[str, Any], *path: str) -> Any:
    current: Any = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def scalar_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("value", "Value", "AirTemperature", "RelativeHumidity",
                    "WindSpeed", "WindDirection", "Precipitation",
                    "PeakGustSpeed", "Speed"):
            if key in value:
                return scalar_value(value[key])
        return None
    return value


def first_number(*values: Any) -> float | None:
    for value in values:
        number = as_float(scalar_value(value))
        if number is not None:
            return number
    return None


def extract_station_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Handle CWA observation datasets whose station array is records.Station."""
    records = payload.get("records") or {}
    if not isinstance(records, dict):
        return []
    stations = records.get("Station") or records.get("station") or []
    if isinstance(stations, dict):
        stations = [stations]
    return [row for row in stations if isinstance(row, dict)]


def coordinate(station: dict[str, Any]) -> tuple[float | None, float | None]:
    geo = station.get("GeoInfo") or station.get("geoInfo") or {}
    coords = geo.get("Coordinates") or geo.get("coordinates") or []
    if isinstance(coords, dict):
        coords = [coords]
    lat = lon = None
    # Official CWA schema uses StationLatitude / StationLongitude inside
    # each Coordinates item; prefer WGS84 when both TWD67 and WGS84 exist.
    for item in coords:
        name = str(item.get("CoordinateName") or item.get("coordinateName") or "").upper()
        item_lat = as_float(item.get("StationLatitude") or item.get("stationLatitude"))
        item_lon = as_float(item.get("StationLongitude") or item.get("stationLongitude"))
        if item_lat is not None and item_lon is not None:
            if name == "WGS84" or lat is None or lon is None:
                lat, lon = item_lat, item_lon
    lat = lat if lat is not None else as_float(station.get("lat") or station.get("Latitude"))
    lon = lon if lon is not None else as_float(station.get("lon") or station.get("Longitude"))
    return lat, lon

def station_timestamp(station: dict[str, Any]) -> datetime | None:
    raw = (
        nested_get(station, "ObsTime", "DateTime")
        or nested_get(station, "obsTime", "dateTime")
        or nested_get(station, "ObsTime", "Now")
    )
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        # CWA observation timestamps are Taiwan local time if no offset is given.
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo("Asia/Taipei"))
    return dt.astimezone(timezone.utc)


def station_id_code(station: dict[str, Any]) -> str | None:
    value = station.get("StationId") or station.get("stationId") or station.get("StationID")
    return str(value).strip() if value else None


def station_name(station: dict[str, Any]) -> str:
    return str(station.get("StationName") or station.get("stationName") or station_id_code(station) or "Unknown")


def station_elevation(station: dict[str, Any]) -> float | None:
    geo = station.get("GeoInfo") or {}
    value = geo.get("StationAltitude") or geo.get("stationAltitude")
    if isinstance(value, dict):
        value = value.get("AltitudeValue") or value.get("value")
    return as_float(value)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def weather_values(station: dict[str, Any], dataset_code: str) -> dict[str, Any]:
    weather = station.get("WeatherElement") or station.get("weatherElement") or {}
    gust = weather.get("GustInfo") or weather.get("gustInfo") or {}
    peak = gust.get("PeakGustSpeed") or gust.get("peakGustSpeed")
    rain = station.get("RainfallElement") or station.get("rainfallElement") or {}

    precipitation = None
    precipitation_period = None
    if dataset_code == "O-A0002-001":
        # CWA O-A0002 defines rolling accumulation windows. Prefer past 1 hour
        # for hourly verification; retain the chosen period explicitly.
        rainfall_windows = [
            ("Past1hr", "past_1_hour"),
            ("Past1Hr", "past_1_hour"),
            ("Past10Min", "past_10_minutes"),
            ("Past3hr", "past_3_hours"),
            ("Past6hr", "past_6_hours"),
            ("Past12hr", "past_12_hours"),
            ("Past24hr", "past_24_hours"),
        ]
        for key, period in rainfall_windows:
            raw = nested_get(rain, key, "Precipitation")
            if raw is None:
                raw = nested_get(rain, key, "precipitation")
            if raw is not None:
                if str(raw).strip() == "-98":
                    precipitation = 0.0
                else:
                    precipitation = as_float(raw)
                precipitation_period = period
                break
    else:
        raw = nested_get(weather, "Now", "Precipitation")
        if raw is None:
            raw = nested_get(weather, "now", "precipitation")
        if raw is not None:
            precipitation = 0.0 if str(raw).strip() == "-98" else as_float(raw)
            precipitation_period = "daily_since_00_local"

    wind_direction = first_number(weather.get("WindDirection"), weather.get("windDirection"))
    if wind_direction == 990:
        wind_direction = None

    return {
        "temperature_c": first_number(weather.get("AirTemperature"), weather.get("airTemperature")),
        "relative_humidity_pct": first_number(weather.get("RelativeHumidity"), weather.get("relativeHumidity")),
        "precipitation_mm": precipitation,
        "precipitation_period": precipitation_period,
        "wind_speed_ms": first_number(weather.get("WindSpeed"), weather.get("windSpeed")),
        "wind_gust_ms": first_number(peak, gust.get("Speed")),
        "wind_direction_deg": wind_direction,
    }

def quality_check(values: dict[str, float | None]) -> tuple[str, list[str]]:
    bounds = {
        "temperature_c": (-35, 55),
        "relative_humidity_pct": (0, 100),
        "precipitation_mm": (0, 500),
        "wind_speed_ms": (0, 75),
        "wind_gust_ms": (0, 100),
        "wind_direction_deg": (0, 360),
    }
    flags = []
    present = 0
    # Validate only measured numeric fields. Metadata such as
    # precipitation_period is intentionally stored alongside measurements
    # but has no numeric range and must not be treated as a QC variable.
    for key, (low, high) in bounds.items():
        value = values.get(key)
        if value is None:
            continue
        present += 1
        if not low <= value <= high:
            flags.append(f"{key}_out_of_range")
    if flags:
        return "suspect", flags
    if present == 0:
        return "missing", ["all_variables_missing"]
    return "passed", []


def save_ingestion_log(client, provider: str, dataset: str, status: str,
                       received: int, stations: int, observations: int,
                       error: str | None = None, started_at: str | None = None):
    row = {
        "provider": provider,
        "dataset_code": dataset,
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "records_received": received,
        "stations_saved": stations,
        "observations_saved": observations,
        "error_message": error[:1500] if error else None,
    }
    client.table("ingestion_logs").insert(row).execute()
