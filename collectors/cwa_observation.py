"""Collect CWA O-A0001-001 and O-A0002-001 observations near the Jiaoxi course."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from collectors.common import (
    coordinate, extract_station_rows, fetch_json, haversine_km,
    quality_check, save_ingestion_log, station_elevation, station_id_code,
    station_name, station_timestamp, supabase_client, weather_values,
)

CWA_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
DATASETS = ("O-A0001-001", "O-A0002-001")
COURSE_CONFIG = Path("config/pilot_courses.json")


def load_course():
    config = json.loads(COURSE_CONFIG.read_text(encoding="utf-8"))
    return next(c for c in config["pilot_courses"] if c["id"] == "JIAOXI")


def collect_dataset(client, api_key: str, dataset_code: str, course: dict) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    received = stations_saved = observations_saved = 0
    station_payloads = []
    observation_payloads = []
    station_map_payloads = []
    try:
        payload = fetch_json(f"{CWA_BASE}/{dataset_code}", api_key)
        rows = extract_station_rows(payload)
        received = len(rows)

        for station in rows:
            code = station_id_code(station)
            lat, lon = coordinate(station)
            observed_at = station_timestamp(station)
            if not code or lat is None or lon is None or observed_at is None:
                continue

            distance = haversine_km(course["latitude"], course["longitude"], lat, lon)
            if distance > float(course["station_search_radius_km"]):
                continue

            station_payloads.append({
                "provider": "CWA",
                "station_code": code,
                "station_name": station_name(station),
                "latitude": lat,
                "longitude": lon,
                "elevation_m": station_elevation(station),
                "station_type": str(station.get("StationType") or station.get("stationType") or "CWA observation station"),
                "active": True,
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "dataset_code": dataset_code,
                    "county": station.get("GeoInfo", {}).get("CountyName"),
                    "town": station.get("GeoInfo", {}).get("TownName"),
                },
            })
            values = weather_values(station, dataset_code)
            quality_status, quality_flags = quality_check(values)
            observation_payloads.append({
                "provider": "CWA",
                "dataset_code": dataset_code,
                "observed_at": observed_at.isoformat(),
                "source_updated_at": observed_at.isoformat(),
                **values,
                "quality_status": quality_status,
                "quality_flags": quality_flags,
                "raw_data": station,
            })
            station_map_payloads.append({
                "station_code": code,
                "distance_km": round(distance, 3),
                "elevation_difference_m": (
                    round(float(station_elevation(station)) - float(course.get("elevation_m")), 1)
                    if station_elevation(station) is not None and course.get("elevation_m") is not None
                    else None
                ),
            })

        if station_payloads:
            client.table("weather_stations").upsert(
                station_payloads, on_conflict="provider,station_code"
            ).execute()
            codes = list({x["station_code"] for x in station_payloads})
            found = client.table("weather_stations").select("id,station_code").eq(
                "provider", "CWA"
            ).in_("station_code", codes).execute().data
            id_by_code = {x["station_code"]: x["id"] for x in (found or [])}
            stations_saved = len(id_by_code)

            map_rows = []
            for item in station_map_payloads:
                station_id = id_by_code.get(item["station_code"])
                if station_id:
                    map_rows.append({
                        "course_id": course["id"],
                        "station_id": station_id,
                        "distance_km": item["distance_km"],
                        "elevation_difference_m": item["elevation_difference_m"],
                        "representativeness": "candidate",
                        "notes": f"Auto-discovered within {course['station_search_radius_km']} km; requires terrain review.",
                    })
            if map_rows:
                client.table("station_course_map").upsert(
                    map_rows, on_conflict="course_id,station_id"
                ).execute()

            for row in observation_payloads:
                row["station_id"] = id_by_code.get(
                    next((s["station_code"] for s in station_payloads
                          if s["station_name"] == ""), "")
                )
            # Match each observation to its station by source order/code.
            observations_by_code = {}
            for station, obs in zip(rows, observation_payloads):
                code = station_id_code(station)
                if code and code in id_by_code and obs["observed_at"]:
                    obs["station_id"] = id_by_code[code]
                    observations_by_code.setdefault(code, []).append(obs)
            flattened = [obs for group in observations_by_code.values() for obs in group]
            for offset in range(0, len(flattened), 300):
                client.table("observation_hourly").upsert(
                    flattened[offset:offset + 300],
                    on_conflict="station_id,provider,dataset_code,observed_at",
                ).execute()
            observations_saved = len(flattened)

        save_ingestion_log(
            client, "CWA", dataset_code, "success", received,
            stations_saved, observations_saved, started_at=started,
        )
        return {
            "dataset": dataset_code,
            "records_received": received,
            "stations_saved": stations_saved,
            "observations_saved": observations_saved,
            "status": "success",
        }
    except Exception as exc:
        try:
            save_ingestion_log(
                client, "CWA", dataset_code, "failed", received,
                stations_saved, observations_saved, str(exc), started,
            )
        except Exception:
            pass
        return {
            "dataset": dataset_code,
            "records_received": received,
            "stations_saved": stations_saved,
            "observations_saved": observations_saved,
            "status": "failed",
            "error": str(exc),
        }


def main():
    api_key = os.environ["CWA_API_KEY"]
    client = supabase_client()
    course = load_course()
    results = [collect_dataset(client, api_key, dataset, course) for dataset in DATASETS]
    for result in results:
        print(json.dumps(result, ensure_ascii=False))
    if all(x["status"] == "failed" for x in results):
        raise SystemExit("All CWA datasets failed; see ingestion_logs for details.")


if __name__ == "__main__":
    main()
