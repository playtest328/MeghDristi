"""Synthetic weather/station nowcast generator for MeghDrishti.

Writes normalized JSON to data/imd/<timestamp>.json.

The output schema is kept compatible with the existing MeghDrishti
pipeline:

{
    station_id,
    name,
    lat,
    lon,
    timestamp,
    ts_severity,
    lightning_prob_cat,
    lightning_prob,
    hail_flag,
    source
}
"""

import json
import math
import os
import random
import sys
from datetime import datetime, timezone

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
)

from nowcast.configs.settings import (
    get_region_bbox,
    get_region_name,
    get_active_region_key,
    IMD_DIR,
)

from nowcast.processing.storm_track import center_at


# ---------------------------------------------------------------------------
# Demo stations — six AWS-style points spread around whichever region is
# active (settings.set_active_region), same relative layout (km offsets from
# region center) the original hardcoded Pune stations used. Regenerated on
# every call rather than a static list so switching regions doesn't leave
# stale station names/coordinates from the previous city.
# ---------------------------------------------------------------------------

_STATION_OFFSETS = [
    ("001", "City", 2.2, 2.7),
    ("002", "North Metro", 14.5, -3.2),
    ("003", "Hills AWS", 28.0, -24.5),
    ("004", "East Outskirts", -16.5, 51.0),
    ("005", "Reservoir AWS", -9.0, -7.0),
    ("006", "Storm-adjacent AWS", -20.0, -18.0),
]


def get_stations():
    lon_min, lat_min, lon_max, lat_max = get_region_bbox()
    center_lat, center_lon = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
    region_key = get_active_region_key()
    region_name = get_region_name()

    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(center_lat))

    stations = []
    for suffix, label, dlat_km, dlon_km in _STATION_OFFSETS:
        stations.append(
            {
                "station_id": f"{region_key.upper()[:3]}{suffix}",
                "name": f"{region_name} {label}",
                "lat": round(center_lat + dlat_km / km_per_deg_lat, 4),
                "lon": round(center_lon + dlon_km / km_per_deg_lon, 4),
            }
        )
    return stations


LIGHTNING_CATS = {
    "cat6": 0.15,
    "cat11": 0.45,
    "cat19": 0.75,
}


def _km_from_storm_core(lat, lon, t_min=0):
    """Calculate approximate distance from the synthetic storm core."""

    c_lat, c_lon = center_at(t_min)

    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(c_lat))

    dy = (lat - c_lat) * km_per_deg_lat
    dx = (lon - c_lon) * km_per_deg_lon

    return math.hypot(dx, dy)


def _fetch_mock():
    """Generate the synthetic weather/storm feed."""

    now = datetime.now(timezone.utc).isoformat()

    records = []

    for station in get_stations():
        dist_km = _km_from_storm_core(
            station["lat"],
            station["lon"],
        )

        proximity = math.exp(
            -(dist_km ** 2) / (2 * 15.0 ** 2)
        )

        if proximity > 0.6:
            weights = [
                0.05,
                0.25,
                0.70,
            ]

        elif proximity > 0.2:
            weights = [
                0.20,
                0.50,
                0.30,
            ]

        else:
            weights = [
                0.70,
                0.25,
                0.05,
            ]

        cat = random.choices(
            list(LIGHTNING_CATS.keys()),
            weights=weights,
        )[0]

        severity = random.choice(
            [
                "nil",
                "isolated",
                "scattered",
                "widespread",
            ]
        )

        hail_flag = (
            cat == "cat19"
            and random.random()
            < (
                0.6
                if proximity > 0.6
                else 0.1
            )
        )

        records.append(
            {
                "station_id": station["station_id"],
                "name": station["name"],
                "lat": station["lat"],
                "lon": station["lon"],
                "timestamp": now,

                "ts_severity": severity,
                "lightning_prob_cat": cat,
                "lightning_prob": LIGHTNING_CATS[cat],
                "hail_flag": hail_flag,

                "source": "mock-replay",
            }
        )

    return records


def pull():
    """Generate synthetic weather data and write normalized JSON to the data directory."""

    os.makedirs(
        IMD_DIR,
        exist_ok=True,
    )

    records = _fetch_mock()

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    out_path = os.path.join(
        IMD_DIR,
        f"{timestamp}.json",
    )

    with open(
        out_path,
        "w",
        encoding="utf-8",
    ) as output_file:

        json.dump(
            {
                "bbox": get_region_bbox(),
                "records": records,
            },
            output_file,
            indent=2,
        )

    print(
        f"[imd_nowcast] wrote "
        f"{len(records)} records -> {out_path}"
    )

    return out_path


if __name__ == "__main__":
    pull()
