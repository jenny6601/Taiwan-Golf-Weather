"""Build a public, key-free forecast cache for the V32.2 preview page.

Runs in GitHub Actions. Fetches five deterministic Open-Meteo models for each
of the 57 courses and writes data/forecast_cache.json. No secrets are required.
"""
from __future__ import annotations
import concurrent.futures
import datetime as dt
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "v32.2-preview.html"
OUTPUT = ROOT / "data" / "forecast_cache.json"
MODELS = [
    ("ECMWF IFS", "ecmwf_ifs025"),
    ("NOAA GFS", "ncep_gfs_seamless"),
    ("DWD ICON", "icon_seamless"),
    ("JMA GSM", "jma_seamless"),
    ("Canada GEM", "cmc_gem_seamless"),
]
HOURLY = ",".join([
    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
    "precipitation", "precipitation_probability", "weather_code",
    "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
    "cloud_cover", "uv_index",
])
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Taiwan-Golf-Weather-V32.2/1.0"})


def courses_from_html():
    source = HTML.read_text(encoding="utf-8")
    match = re.search(r"const taiwanCourses\\s*=\\s*(\\[.*?\\]);", source, re.S)
    if not match:
        raise RuntimeError("Cannot locate taiwanCourses array in v32.2-preview.html")
    courses = json.loads(match.group(1))
    if len(courses) != 57:
        raise RuntimeError(f"Expected 57 courses, found {len(courses)}")
    return courses


def fetch_model(course, label, model):
    params = {
        "latitude": course["lat"], "longitude": course["lon"],
        "hourly": HOURLY, "models": model, "timezone": "Asia/Taipei",
        "forecast_days": 16, "wind_speed_unit": "kmh",
    }
    last = None
    for attempt in range(3):
        try:
            response = SESSION.get("https://api.open-meteo.com/v1/forecast",
                                   params=params, timeout=35)
            response.raise_for_status()
            data = response.json()
            hourly = data.get("hourly") or {}
            times = hourly.get("time")
            if not isinstance(times, list) or not times:
                raise RuntimeError("API response missing hourly.time")
            rows_by_date = {}
            for i, stamp in enumerate(times):
                date, clock = stamp[:10], stamp[11:16]
                hour = int(clock[:2])
                if not 6 <= hour <= 18:
                    continue
                def val(key):
                    values = hourly.get(key)
                    return values[i] if isinstance(values, list) and i < len(values) else None
                rows_by_date.setdefault(date, []).append({
                    "time": clock, "available": True,
                    "temp": val("temperature_2m"),
                    "feel": val("apparent_temperature"),
                    "rain": val("precipitation_probability"),
                    "mm": val("precipitation"),
                    "code": val("weather_code"),
                    "wind": val("wind_speed_10m"),
                    "gust": val("wind_gusts_10m"),
                    "dir": val("wind_direction_10m"),
                    "rh": val("relative_humidity_2m"),
                    "cloud": val("cloud_cover"), "uv": val("uv_index"),
                })
            return label, rows_by_date
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{label}: {last}")


def main():
    courses = courses_from_html()
    today = dt.datetime.now(dt.timezone.utc).astimezone(
        dt.timezone(dt.timedelta(hours=8))
    ).date()
    cache = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "timezone": "Asia/Taipei",
        "course_count": len(courses),
        "model_names": [x[0] for x in MODELS],
        "courses": {},
        "errors": [],
    }
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for course in courses:
            try:
                lat, lon = float(course["lat"]), float(course["lon"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("invalid coordinates")
                jobs.extend((course, pool.submit(fetch_model, course, label, model))
                            for label, model in MODELS)
            except Exception as exc:
                cache["errors"].append(f'{course.get("name", "unknown")}: {exc}')
        for course, future in jobs:
            name = course["name"]
            entry = cache["courses"].setdefault(name, {
                "lat": course["lat"], "lon": course["lon"], "dates": {}
            })
            try:
                label, date_rows = future.result()
                for date, rows in date_rows.items():
                    entry["dates"].setdefault(date, {"modelRows": {}, "forecastSource": "五組獨立模式"})
                    entry["dates"][date]["modelRows"][label] = rows
            except Exception as exc:
                cache["errors"].append(f"{name}: {exc}")
    # Validate the near-term default date and retain the cache even if some
    # individual models fail; the browser can render partial model consensus.
    today_key = today.isoformat()
    usable = sum(1 for c in cache["courses"].values()
                 if len(c["dates"].get(today_key, {}).get("modelRows", {})) > 0)
    if usable == 0:
        raise RuntimeError("No course returned usable forecast data; refusing to publish empty cache")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    print(f"Forecast cache written: {usable}/{len(courses)} courses have today's forecast; "
          f"{len(cache['errors'])} errors; generated_at={cache['generated_at']}")
    if len(cache["courses"]) != 57:
        raise RuntimeError(f"Cache has only {len(cache['courses'])}/57 courses")


if __name__ == "__main__":
    main()
