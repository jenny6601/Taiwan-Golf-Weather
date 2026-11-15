"""Nationwide CWA observations for all registered Taiwan golf courses.

Fetch each CWA dataset once per run, map nearby stations to every active course,
persist normalized observations, and publish a safe static JSON snapshot for Pages.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from collectors.common import (
    coordinate, extract_station_rows, fetch_json, haversine_km,
    quality_check, save_ingestion_log, station_elevation, station_id_code,
    station_name, station_timestamp, supabase_client, weather_values, as_float,
)

CWA_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
DATASETS = ("O-A0001-001", "O-A0002-001")
COURSE_CONFIG = Path("config/taiwan_golf_courses.json")
OUTPUT = Path("data/live_observations.json")
UTC = timezone.utc


def load_courses():
    payload = json.loads(COURSE_CONFIG.read_text(encoding="utf-8"))
    return [c for c in payload["courses"] if c.get("active", True)]


def rainfall_windows(station):
    rain = station.get("RainfallElement") or station.get("rainfallElement") or {}
    def read(*keys):
        for key in keys:
            item = rain.get(key)
            if isinstance(item, dict):
                value = item.get("Precipitation", item.get("precipitation"))
            else:
                value = item
            if value is not None and str(value).strip() != "":
                return 0.0 if str(value).strip() == "-98" else as_float(value)
        return None
    return {
        "precipitation_10m_mm": read("Past10Min", "Past10min", "Past10MIN"),
        "precipitation_1h_mm": read("Past1hr", "Past1Hr", "Past1HR"),
    }


def fetch_dataset(dataset_code, api_key):
    payload = fetch_json(f"{CWA_BASE}/{dataset_code}", api_key)
    rows = extract_station_rows(payload)
    normalized = []
    for station in rows:
        code = station_id_code(station)
        lat, lon = coordinate(station)
        observed = station_timestamp(station)
        if not code or lat is None or lon is None or observed is None:
            continue
        values = weather_values(station, dataset_code)
        if dataset_code == "O-A0002-001":
            values.update(rainfall_windows(station))
            values["precipitation_mm"] = (
                values.get("precipitation_1h_mm")
                if values.get("precipitation_1h_mm") is not None
                else values.get("precipitation_10m_mm")
            )
            values["precipitation_period"] = (
                "past_1_hour" if values.get("precipitation_1h_mm") is not None
                else "past_10_minutes" if values.get("precipitation_10m_mm") is not None
                else None
            )
        q_values = {k: v for k, v in values.items()
                    if k not in ("precipitation_period", "precipitation_10m_mm", "precipitation_1h_mm")}
        q_status, q_flags = quality_check(q_values)
        normalized.append({
            "code": code, "name": station_name(station), "lat": lat, "lon": lon,
            "elevation_m": station_elevation(station), "observed_at": observed,
            "values": values, "quality_status": q_status, "quality_flags": q_flags,
            "raw": station,
        })
    return len(rows), normalized


def station_row(dataset_code, item):
    return {
        "provider": "CWA", "station_code": item["code"], "station_name": item["name"],
        "latitude": item["lat"], "longitude": item["lon"],
        "elevation_m": item["elevation_m"], "station_type": "CWA observation station",
        "active": True, "last_seen_at": datetime.now(UTC).isoformat(),
        "metadata": {"dataset_code": dataset_code},
    }


def persist_dataset(client, dataset_code, items, courses):
    # Keep only stations relevant to at least one course; map each to every
    # course inside its configured search radius.
    used = {}
    map_rows_by_course = {c["id"]: [] for c in courses}
    for item in items:
        distances = []
        for course in courses:
            distance = haversine_km(course["latitude"], course["longitude"], item["lat"], item["lon"])
            if distance <= float(course.get("station_search_radius_km", 30)):
                distances.append((course, distance))
        if not distances:
            continue
        used[item["code"]] = item
        for course, distance in distances:
            map_rows_by_course[course["id"]].append((item["code"], distance, course, item))

    if not used:
        return {}, 0, 0
    rows = [station_row(dataset_code, item) for item in used.values()]
    for offset in range(0, len(rows), 300):
        client.table("weather_stations").upsert(
            rows[offset:offset + 300], on_conflict="provider,station_code"
        ).execute()
    codes = list(used)
    found = client.table("weather_stations").select("id,station_code").eq(
        "provider", "CWA"
    ).in_("station_code", codes).execute().data or []
    ids = {r["station_code"]: r["id"] for r in found}

    map_rows = []
    for course_id, candidates in map_rows_by_course.items():
        for code, distance, course, item in candidates:
            sid = ids.get(code)
            if not sid:
                continue
            map_rows.append({
                "course_id": course_id, "station_id": sid,
                "distance_km": round(distance, 3),
                "elevation_difference_m": (
                    round(float(item["elevation_m"]) - float(course["elevation_m"]), 1)
                    if item["elevation_m"] is not None and course.get("elevation_m") is not None
                    else None
                ),
                "representativeness": "candidate",
                "notes": "Automatically matched by distance only; terrain/exposure review required.",
            })
    for offset in range(0, len(map_rows), 300):
        client.table("station_course_map").upsert(
            map_rows[offset:offset + 300], on_conflict="course_id,station_id"
        ).execute()

    observations = []
    for code, item in used.items():
        values = dict(item["values"])
        values["station_id"] = ids[code]
        values.update({
            "provider": "CWA", "dataset_code": dataset_code,
            "observed_at": item["observed_at"].isoformat(),
            "source_updated_at": item["observed_at"].isoformat(),
            "quality_status": item["quality_status"],
            "quality_flags": item["quality_flags"],
            "raw_data": item["raw"],
        })
        observations.append(values)
    for offset in range(0, len(observations), 250):
        client.table("observation_hourly").upsert(
            observations[offset:offset + 250],
            on_conflict="station_id,provider,dataset_code,observed_at",
        ).execute()
    return {code: ids[code] for code in used}, len(used), len(observations)


def choose_station(candidates, now):
    if not candidates:
        return None
    # Prefer valid measurements, then the closest station. Keep timestamps
    # explicit so the UI can identify stale data instead of presenting it as live.
    def key(item):
        valid = item["quality_status"] == "passed"
        age = max(0.0, (now - item["observed_at"]).total_seconds())
        return (not valid, item["distance_km"], age)
    return sorted(candidates, key=key)[0]


def build_snapshot(courses, datasets):
    now = datetime.now(UTC)
    output = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "refresh_interval_minutes": 10,
        "course_count": len(courses),
        "source": "Taiwan CWA O-A0001-001 and O-A0002-001",
        "courses": {},
    }
    for course in courses:
        cid = course["id"]
        course_entry = {
            "course_id": cid, "course_name": course["name"], "county": course["county"],
            "latitude": course["latitude"], "longitude": course["longitude"],
            "weather": None, "rainfall": None,
        }
        for dataset_code in DATASETS:
            candidates = []
            for item in datasets.get(dataset_code, []):
                distance = haversine_km(course["latitude"], course["longitude"], item["lat"], item["lon"])
                if distance <= float(course.get("station_search_radius_km", 30)):
                    candidates.append({**item, "distance_km": round(distance, 2)})
            selected = choose_station(candidates, now)
            if not selected:
                continue
            station = {
                "code": selected["code"], "name": selected["name"],
                "distance_km": selected["distance_km"],
                "observed_at": selected["observed_at"].isoformat(),
                "quality_status": selected["quality_status"],
                "quality_flags": selected["quality_flags"],
            }
            if dataset_code == "O-A0001-001":
                course_entry["weather"] = {"station": station, **selected["values"]}
            else:
                course_entry["rainfall"] = {"station": station, **selected["values"]}
        output["courses"][cid] = course_entry
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return output


def main():
    api_key = os.environ["CWA_API_KEY"]
    client = supabase_client()
    courses = load_courses()
    if len(courses) != 57:
        raise SystemExit(f"Expected 57 active golf courses, found {len(courses)}")
    datasets = {}
    for dataset_code in DATASETS:
        started = datetime.now(UTC).isoformat()
        try:
            received, items = fetch_dataset(dataset_code, api_key)
            datasets[dataset_code] = items
            _, stations, observations = persist_dataset(client, dataset_code, items, courses)
            save_ingestion_log(client, "CWA", dataset_code, "success", received,
                               stations, observations, started_at=started)
            print(json.dumps({
                "dataset": dataset_code, "records_received": received,
                "stations_saved": stations, "observations_saved": observations,
                "status": "success",
            }, ensure_ascii=False))
        except Exception as exc:
            save_ingestion_log(client, "CWA", dataset_code, "failed", 0, 0, 0,
                               str(exc), started)
            raise
    snapshot = build_snapshot(courses, datasets)
    covered = sum(1 for c in snapshot["courses"].values() if c["weather"] or c["rainfall"])
    print(json.dumps({
        "snapshot": str(OUTPUT), "courses": len(courses),
        "courses_with_any_observation": covered,
        "generated_at": snapshot["generated_at"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
