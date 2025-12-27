from __future__ import annotations

from datetime import datetime


def build_dwd_solar_query(*, lat: float, lon: float, start: datetime, end: datetime) -> str:
    """Query DWD solar-energy cumulative forecast.

    Assumptions (initial implementation):
      - table has columns: run_time_utc, interval_end_utc, lat, lon, solar_energy_kwh_per_m2
      - solar_energy_kwh_per_m2 is cumulative up to interval_end_utc for a given run_time_utc
      - we select the latest run_time_utc available <= start
      - we then take the max cumulative within [start, end] as 'total' for the window
    """
    # Use a small bounding box to avoid exact-float equality on lat/lon
    lat_eps = 0.02
    lon_eps = 0.02

    return f"""
    WITH latest_run AS (
      SELECT max(run_time_utc) AS run_time_utc
      FROM dwd_icon_d2_solar_energy
      WHERE run_time_utc <= '{start.isoformat()}'
        AND lat BETWEEN {lat - lat_eps} AND {lat + lat_eps}
        AND lon BETWEEN {lon - lon_eps} AND {lon + lon_eps}
    )
    SELECT
      run_time_utc,
      interval_end_utc,
      lat,
      lon,
      solar_energy_kwh_per_m2
    FROM dwd_icon_d2_solar_energy
    WHERE run_time_utc = (SELECT run_time_utc FROM latest_run)
      AND interval_end_utc > '{start.isoformat()}'
      AND interval_end_utc <= '{end.isoformat()}'
      AND lat BETWEEN {lat - lat_eps} AND {lat + lat_eps}
      AND lon BETWEEN {lon - lon_eps} AND {lon + lon_eps}
    ORDER BY interval_end_utc
    """


def build_weather_hourly_query(
    *,
    start: datetime,
    end: datetime,
    lat: float | None = None,
    lon: float | None = None,
    location_id: str | None = None,
) -> str:
    """Query hourly weather rows (cloudiness etc.).

    If location_id is provided, use it (preferred).
    Otherwise fallback to lat/lon bounding box.
    """
    filters = [f"ts >= '{start.isoformat()}'", f"ts < '{end.isoformat()}'"]

    if location_id:
        filters.append(f"location_id = '{location_id}'")
    else:
        # bounding box fallback
        lat_eps = 0.02
        lon_eps = 0.02
        if lat is not None:
            filters.append(f"lat BETWEEN {lat - lat_eps} AND {lat + lat_eps}")
        if lon is not None:
            filters.append(f"lon BETWEEN {lon - lon_eps} AND {lon + lon_eps}")

    where = " AND ".join(filters)

    return f"""
    SELECT
      ts,
      clouds,
      uvi,
      weather_main,
      weather_description
    FROM folgaria_weather_hourly
    WHERE {where}
    ORDER BY ts
    """
