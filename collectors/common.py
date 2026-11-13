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


def first_number(*values: Any) -> float | None:
    for value in values:
        number = as_float(value)
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
    for item in coords:
        name = str(item.get("CoordinateName") or item.get("coordinateName") or "").lower()
        value = as_float(item.get("CoordinateValue") or item.get("coordinateValue"))
        if value is None:
            continue
        if "wgs" in name and ("lat" in name or "latitude" in name):
            lat = value
        elif "wgs" in name and ("lon" in name or "longitude" in name):
            lon = value
        elif "latitude" in name:
            lat = value
        elif "longitude" in name:
            lon = value
    # Some CWA products expose direct Position fields.
    lat = lat if lat is not None else as_float(station.get("lat") or station.get("Latitude"))
    lon = lon if lon is not None else as_float(station.get("lon") or station.get("Longitude"))
    # Fallback to the common CWA WGS84 CoordinateFormat entries.
    if lat is None or lon is None:
        for item in coords:
            fmt = str(item.get("CoordinateFormat") or "").lower()
            value = as_float(item.get("CoordinateValue"))
            if value is None or "decimal" not in fmt:
                continue
            cname = str(item.get("CoordinateName") or "").lower()
            if "latitude" in cname:
                lat = value
            elif "longitude" in cname:
                lon = value
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


def weather_values(station: dict[str, Any], dataset_code: str) -> dict[str, float | None]:
    weather = station.get("WeatherElement") or station.get("weatherElement") or {}
    now = weather.get("Now") or weather.get("now") or {}
    gust = weather.get("GustInfo") or weather.get("gustInfo") or {}
    peak = gust.get("PeakGustSpeed") or gust.get("peakGustSpeed") or {}
    rain = station.get("RainfallElement") or station.get("rainfallElement") or {}
    rain_now = rain.get("Now") or rain.get("now") or {}

    precipitation = first_number(
        nested_get(weather, "Now", "Precipitation"),
        nested_get(weather, "now", "precipitation"),
        nested_get(rain, "Now", "Precipitation"),
        nested_get(rain, "now", "precipitation"),
        nested_get(weather, "Past10Min", "Precipitation"),
    )

    if dataset_code == "O-A0002-001":
        # Rainfall station product; retain its precipitation without inventing
        # temperature/wind observations.
        precipitation = first_number(
            nested_get(rain, "Now", "Precipitation"),
            nested_get(rain, "now", "precipitation"),
            nested_get(station, "RainfallElement", "Now", "Precipitation"),
            nested_get(station, "WeatherElement", "Now", "Precipitation"),
            nested_get(station, "RainfallElement", "Past1Hr", "Precipitation"),
        )

    return {
        "temperature_c": first_number(weather.get("AirTemperature"), weather.get("airTemperature")),
        "relative_humidity_pct": first_number(weather.get("RelativeHumidity"), weather.get("relativeHumidity")),
        "precipitation_mm": precipitation,
        "wind_speed_ms": first_number(weather.get("WindSpeed"), weather.get("windSpeed")),
        "wind_gust_ms": first_number(peak.get("PeakGustSpeed"), peak.get("peakGustSpeed"), peak.get("Speed")),
        "wind_direction_deg": first_number(weather.get("WindDirection"), weather.get("windDirection")),
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
    for key, value in values.items():
        if value is None:
            continue
        present += 1
        low, high = bounds[key]
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
