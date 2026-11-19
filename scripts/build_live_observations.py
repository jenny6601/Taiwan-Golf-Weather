"""Build a fresh 57-course CWA live snapshot for the V32.2 PWA.

This is intentionally separate from the Supabase pilot ingester: it fetches the
two public CWA station datasets once, maps the nearest recent station to every
registered course, and writes data/live_observations.json for the PWA and
forecast-verification archive.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from collectors.common import (
    as_float,
    coordinate,
    extract_station_rows,
    fetch_json,
    first_number,
    haversine_km,
    nested_get,
    quality_check,
    scalar_value,
    station_elevation,
    station_id_code,
    station_name,
    station_timestamp,
    weather_values,
)

CWA_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
WEATHER_DATASET = "O-A0001-001"
RAINFALL_DATASET = "O-A0002-001"
COURSE_FILE = Path("config/taiwan_golf_courses.json")
OUTPUT = Path("data/live_observations.json")
TZ = ZoneInfo("Asia/Taipei")
WEATHER_MAX_AGE_MIN = 180
RAINFALL_MAX_AGE_MIN = 30
WEATHER_MAX_DISTANCE_KM = 30.0
RAINFALL_MAX_DISTANCE_KM = 15.0


def parse_rain_window(station: dict, names: tuple[str, ...]) -> float | None:
    rainfall = station.get("RainfallElement") or station.get("rainfallElement") or {}
    for name in names:
        raw = nested_get(rainfall, name, "Precipitation")
        if raw is None:
            raw = nested_get(rainfall, name, "precipitation")
        if raw is None:
            continue
        value = scalar_value(raw)
        if str(value).strip() == "-98":
            return 0.0
        return as_float(value)
    return None


def weather_text(station: dict) -> str | None:
    element = station.get("WeatherElement") or station.get("weatherElement") or {}
    value = (
        element.get("Weather") or element.get("weather")
        or station.get("Weather") or station.get("weather")
    )
    value = scalar_value(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_courses() -> list[dict]:
    payload = json.loads(COURSE_FILE.read_text(encoding="utf-8"))
    courses = payload.get("courses", [])
    if len(courses) != 57:
        raise RuntimeError(f"Expected 57 configured golf courses; found {len(courses)}")
    return courses


def prepare_stations(payload: dict, dataset: str, now: datetime) -> list[dict]:
    prepared = []
    for station in extract_station_rows(payload):
        code = station_id_code(station)
        lat, lon = coordinate(station)
        observed_at = station_timestamp(station)
        if not code or lat is None or lon is None or observed_at is None:
            continue
        age = (now - observed_at).total_seconds() / 60
        if age < -5:
            continue
        values = weather_values(station, dataset)
        status, flags = quality_check(values)
        prepared.append({
            "raw": station,
            "code": code,
            "name": station_name(station),
            "lat": lat,
            "lon": lon,
            "elevation_m": station_elevation(station),
            "observed_at": observed_at,
            "age_min": max(0.0, age),
            "values": values,
            "quality_status": status,
            "quality_flags": flags,
        })
    return prepared


def nearest_station(course: dict, stations: list[dict], max_distance: float,
                    max_age: float) -> dict | None:
    candidates = []
    for item in stations:
        distance = haversine_km(
            float(course["latitude"]), float(course["longitude"]),
            item["lat"], item["lon"],
        )
        if distance > max_distance or item["age_min"] > max_age:
            continue
        if item["quality_status"] != "passed":
            continue
        candidates.append((distance, item["age_min"], item))
    if not candidates:
        return None
    distance, _, chosen = min(candidates, key=lambda x: (x[0], x[1]))
    return {**chosen, "distance_km": round(distance, 3)}


def station_summary(item: dict | None) -> dict | None:
    if item is None:
        return None
    return {
        "code": item["code"],
        "name": item["name"],
        "distance_km": item["distance_km"],
        "elevation_m": item["elevation_m"],
        "observed_at": item["observed_at"].isoformat(),
        "observation_age_minutes": round(item["age_min"], 1),
        "quality_status": item["quality_status"],
        "quality_flags": item["quality_flags"],
    }


def build_snapshot() -> dict:
    api_key = os.environ.get("CWA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CWA_API_KEY secret is required")
    now = datetime.now(timezone.utc)
    courses = load_courses()

    weather_payload = fetch_json(f"{CWA_BASE}/{WEATHER_DATASET}", api_key)
    rainfall_payload = fetch_json(f"{CWA_BASE}/{RAINFALL_DATASET}", api_key)
    weather_stations = prepare_stations(weather_payload, WEATHER_DATASET, now)
    rainfall_stations = prepare_stations(rainfall_payload, RAINFALL_DATASET, now)
    if not weather_stations:
        raise RuntimeError("CWA weather dataset returned no recent quality-passed stations")
    if not rainfall_stations:
        raise RuntimeError("CWA rainfall dataset returned no recent quality-passed stations")

    result = {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "refresh_interval_minutes": 10,
        "course_count": len(courses),
        "source": f"Taiwan CWA {WEATHER_DATASET} and {RAINFALL_DATASET}",
        "station_selection": {
            "weather_max_distance_km": WEATHER_MAX_DISTANCE_KM,
            "weather_max_age_minutes": WEATHER_MAX_AGE_MIN,
            "rainfall_max_distance_km": RAINFALL_MAX_DISTANCE_KM,
            "rainfall_max_age_minutes": RAINFALL_MAX_AGE_MIN,
            "method": "nearest recent quality-passed station per course",
        },
        "dataset_latest_observed_at": {
            WEATHER_DATASET: max(x["observed_at"] for x in weather_stations).isoformat(),
            RAINFALL_DATASET: max(x["observed_at"] for x in rainfall_stations).isoformat(),
        },
        "courses": {},
        "errors": [],
    }

    for course in courses:
        course_id = str(course["id"])
        weather = nearest_station(
            course, weather_stations, WEATHER_MAX_DISTANCE_KM, WEATHER_MAX_AGE_MIN
        )
        rain = nearest_station(
            course, rainfall_stations, RAINFALL_MAX_DISTANCE_KM, RAINFALL_MAX_AGE_MIN
        )

        if weather:
            w = weather["values"]
            weather_data = {
                "station": station_summary(weather),
                "weather_text": weather_text(weather["raw"]),
                "temperature_c": w.get("temperature_c"),
                "relative_humidity_pct": w.get("relative_humidity_pct"),
                "precipitation_mm": w.get("precipitation_mm"),
                "precipitation_period": w.get("precipitation_period"),
                "wind_speed_ms": w.get("wind_speed_ms"),
                "wind_gust_ms": w.get("wind_gust_ms"),
                "wind_direction_deg": w.get("wind_direction_deg"),
            }
        else:
            weather_data = {
                "station": None, "weather_text": None,
                "temperature_c": None, "relative_humidity_pct": None,
                "precipitation_mm": None, "precipitation_period": None,
                "wind_speed_ms": None, "wind_gust_ms": None,
                "wind_direction_deg": None,
            }

        if rain:
            rv = rain["values"]
            rain_10m = parse_rain_window(rain["raw"], ("Past10Min", "Past10min", "Past10MIN"))
            rain_1h = parse_rain_window(rain["raw"], ("Past1hr", "Past1Hr", "Past1HR"))
            if rain_1h is not None:
                rain_amount, rain_period = rain_1h, "past_1_hour"
            elif rain_10m is not None:
                rain_amount, rain_period = rain_10m, "past_10_minutes"
            else:
                rain_amount, rain_period = None, None
            rainfall_data = {
                "station": station_summary(rain),
                "temperature_c": rv.get("temperature_c"),
                "relative_humidity_pct": rv.get("relative_humidity_pct"),
                "precipitation_mm": rain_amount,
                "precipitation_period": rain_period,
                "wind_speed_ms": rv.get("wind_speed_ms"),
                "wind_gust_ms": rv.get("wind_gust_ms"),
                "wind_direction_deg": rv.get("wind_direction_deg"),
                "precipitation_10m_mm": rain_10m,
                "precipitation_1h_mm": rain_1h,
            }
        else:
            rainfall_data = {
                "station": None,
                "temperature_c": None, "relative_humidity_pct": None,
                "precipitation_mm": None, "precipitation_period": None,
                "wind_speed_ms": None, "wind_gust_ms": None,
                "wind_direction_deg": None,
                "precipitation_10m_mm": None, "precipitation_1h_mm": None,
            }

        result["courses"][course_id] = {
            "course_id": course_id,
            "course_name": course["name"],
            "county": course.get("county"),
            "latitude": course["latitude"],
            "longitude": course["longitude"],
            "weather": weather_data,
            "rainfall": rainfall_data,
        }

    weather_coverage = sum(1 for c in result["courses"].values() if c["weather"]["station"])
    rainfall_coverage = sum(1 for c in result["courses"].values() if c["rainfall"]["station"])
    result["coverage"] = {
        "weather_courses": weather_coverage,
        "rainfall_courses": rainfall_coverage,
        "courses_total": len(courses),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "generated_at": result["generated_at"],
        "course_count": len(courses),
        "weather_coverage": weather_coverage,
        "rainfall_coverage": rainfall_coverage,
        "weather_dataset_latest": result["dataset_latest_observed_at"][WEATHER_DATASET],
        "rainfall_dataset_latest": result["dataset_latest_observed_at"][RAINFALL_DATASET],
        "output": str(OUTPUT),
    }, ensure_ascii=False))
    if weather_coverage < 50 or rainfall_coverage < 50:
        raise SystemExit(
            f"Insufficient CWA station coverage: weather={weather_coverage}, rainfall={rainfall_coverage}"
        )
    return result


if __name__ == "__main__":
    build_snapshot()
