"""Synthetic hail + lightning hazard demo across all of India.

Unlike the per-region demo (models/hazard.py + processing/synthetic_radar.py,
still used by the Forecast/Replay pages), this has no fixed demo city — it
generates a synthetic reflectivity field and lightning strikes across the
whole country (centered on the same moving storm cell used everywhere else
in the demo, via storm_track) and flags wherever they indicate
hail-favorable conditions or a strike.

Downburst (needs Doppler radial velocity) and cloudburst (needs a persisted
radar time-series for pySTEPS to extrapolate from) have no all-India
equivalent here — both remain available, synthetic-backed, in the
per-region demo instead.

Hail rule here is simplified from hazard.py's grid rule: reflectivity +
collocated lightning only, no cold-cloud-top requirement.

Severity is 3-tier (low/moderate/high, colored green/yellow/red on the map)
based on reflectivity for hail, bumped up a tier if a strike is collocated;
lightning strikes are always "high".

`lead_minutes` (used by /hazards' lead-time slider) does NOT re-run
detection at a future time. Instead each point's position is advected by
the synthetic wind vector at that location (processing/weather_fields.py),
a standard simplified nowcasting technique (storms roughly follow the
steering flow) — NOT a re-detected forecast, just the current detections
moved along the current wind field.

All output here is synthetic demo data — no live network calls.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from nowcast.configs.settings import INDIA_BBOX, HAIL_REFLECTIVITY_MIN_DBZ
from nowcast.configs.districts_india import nearest_districts_vectorized
from nowcast.processing.storm_track import default_india_storm_spots, multi_cluster_intensity_fraction

INDIA_GRID_SIZE = 150  # ~0.2deg/cell, ~22km — fine enough for a country overview
LIGHTNING_PROXIMITY_KM = 25.0  # collocated-with-lightning bumps hail severity up a tier
HAIL_MODERATE_DBZ = 65.0  # >= this (and below HIGH) -> "moderate"
HAIL_HIGH_DBZ = 78.0  # >= this -> "high"

# Synthetic all-India storm field — multiple scattered cells (see
# storm_track.default_india_storm_spots), each rendered wider than the
# per-region demo storm since a country-scale cell should read as bigger
# on this much coarser grid.
_SYNTHETIC_PEAK_DBZ = 72.0
_SYNTHETIC_STRIKE_COUNT = 3  # per active spot, not total
_SYNTHETIC_STRIKE_SPREAD_DEG = 0.15

_SEVERITY_ORDER = ["low", "moderate", "high"]


def _bump_severity(severity):
    idx = min(_SEVERITY_ORDER.index(severity) + 1, len(_SEVERITY_ORDER) - 1)
    return _SEVERITY_ORDER[idx]


def _km_per_deg(lat):
    return 111.0, 111.0 * np.cos(np.radians(lat))


def advect_point(lat, lon, lead_minutes):
    """Shift (lat, lon) by the synthetic wind vector at that point over
    `lead_minutes` — see module docstring for what this is and isn't."""
    if lead_minutes <= 0:
        return lat, lon
    from nowcast.processing import weather_fields

    sample = weather_fields.sample_point(lat, lon, lead_minutes)
    speed_ms = sample["wind_speed_ms"]
    if speed_ms <= 0:
        return lat, lon
    # wind_dir_deg is the direction wind blows FROM (met convention) —
    # movement is the opposite direction.
    to_rad = np.radians((sample["wind_dir_deg"] + 180) % 360)
    distance_km = speed_ms * (lead_minutes * 60) / 1000.0
    km_lat, km_lon = _km_per_deg(lat)
    dlat = (distance_km * np.cos(to_rad)) / km_lat
    dlon = (distance_km * np.sin(to_rad)) / km_lon
    return lat + dlat, lon + dlon


def advect_hazards(hazards, lead_minutes):
    """Apply advect_point to a list of hazard dicts (main.py calls this on
    the cached "now" detections per-request instead of re-running the full
    ~15s RainViewer+Blitzortung fetch for every lead_time)."""
    if lead_minutes <= 0:
        return hazards
    out = []
    for h in hazards:
        lat, lon = advect_point(h["lat"], h["lon"], lead_minutes)
        out.append({**h, "lat": lat, "lon": lon})
    return out


def synthetic_reflectivity(spots=None):
    """Synthetic all-India reflectivity grid — several clustered storm
    cells scattered across the country (see storm_track.
    default_india_storm_spots), each independently appearing/disappearing
    over time, rendered onto INDIA_BBOX at INDIA_GRID_SIZE resolution.

    `spots` lets callers (main.py, synthetic_strikes below) share one
    storm-spot draw between reflectivity/strikes/satellite so they all
    show the same storms in the same places — left as None, generates its
    own so the module stays runnable standalone."""
    if spots is None:
        spots = default_india_storm_spots()

    lon_min, lat_min, lon_max, lat_max = INDIA_BBOX
    lons = np.linspace(lon_min, lon_max, INDIA_GRID_SIZE)
    lats = np.linspace(lat_min, lat_max, INDIA_GRID_SIZE)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    cluster = multi_cluster_intensity_fraction(lon_grid, lat_grid, spots)

    frame = _SYNTHETIC_PEAK_DBZ * cluster
    frame += np.random.normal(0, 0.5, frame.shape)
    return np.clip(frame, 0, None).astype(np.float32)


def synthetic_strikes(spots=None):
    """A handful of synthetic lightning strikes scattered near each active
    storm spot (see synthetic_reflectivity)."""
    if spots is None:
        spots = default_india_storm_spots()

    strikes = []
    for spot in spots:
        for _ in range(_SYNTHETIC_STRIKE_COUNT):
            strikes.append(
                {
                    "lat": float(spot["lat"] + np.random.normal(0, _SYNTHETIC_STRIKE_SPREAD_DEG)),
                    "lon": float(spot["lon"] + np.random.normal(0, _SYNTHETIC_STRIKE_SPREAD_DEG)),
                }
            )
    return strikes


def detect(reflectivity=None, strikes=None, spots=None):
    """Synthetic hail + lightning hazard points across all of India.

    `reflectivity`/`strikes` can be pre-generated and passed in (main.py
    does this, sharing one synthetic fetch between hazard detection and the
    /raw-layers all-India radar image instead of generating twice) —
    `spots` (see storm_track.default_india_storm_spots) is used to generate
    whichever of the two isn't already provided, so they still agree on
    where the active storms are. All left as None, this generates
    everything itself, so the module stays runnable standalone via
    `python -m nowcast.models.hazard_india`.

    Returns a list of {lat, lon, type, severity, ...} dicts.
    """
    if spots is None and (reflectivity is None or strikes is None):
        spots = default_india_storm_spots()

    if reflectivity is None:
        reflectivity = synthetic_reflectivity(spots=spots)

    if strikes is None:
        strikes = synthetic_strikes(spots=spots)

    lon_min, lat_min, lon_max, lat_max = INDIA_BBOX
    lons = np.linspace(lon_min, lon_max, INDIA_GRID_SIZE)
    lats = np.linspace(lat_min, lat_max, INDIA_GRID_SIZE)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    hazards = []

    for s in strikes:
        # A real strike is inherently an immediate hazard, not a graded
        # risk — always "high" (red), unlike hail's threshold-based tiers.
        hazards.append({"lat": s["lat"], "lon": s["lon"], "type": "lightning", "severity": "high"})

    strike_lats = np.array([s["lat"] for s in strikes]) if strikes else None
    strike_lons = np.array([s["lon"] for s in strikes]) if strikes else None

    ys, xs = np.where(reflectivity >= HAIL_REFLECTIVITY_MIN_DBZ)
    for y, x in zip(ys.tolist(), xs.tolist()):
        cell_lat, cell_lon = float(lat_grid[y, x]), float(lon_grid[y, x])
        dbz = float(reflectivity[y, x])
        if dbz >= HAIL_HIGH_DBZ:
            severity = "high"
        elif dbz >= HAIL_MODERATE_DBZ:
            severity = "moderate"
        else:
            severity = "low"
        if strikes:
            km_lat, km_lon = _km_per_deg(cell_lat)
            nearest_km = np.min(
                np.hypot((cell_lat - strike_lats) * km_lat, (cell_lon - strike_lons) * km_lon)
            )
            if nearest_km <= LIGHTNING_PROXIMITY_KM:
                severity = _bump_severity(severity)
        hazards.append(
            {
                "lat": cell_lat,
                "lon": cell_lon,
                "type": "hail",
                "severity": severity,
                "reflectivity_dbz": round(dbz, 1),
            }
        )

    for h in hazards:
        h["source"] = "synthetic"

    # District/state labels (judges think in districts, not grid cells —
    # see districts_india.py for what "nearest centroid" actually means
    # here). Vectorized across every hazard point at once rather than a
    # per-point lookup loop, same reasoning as the lightning-proximity
    # vectorization above.
    if hazards:
        district_labels = nearest_districts_vectorized(
            [h["lat"] for h in hazards], [h["lon"] for h in hazards]
        )
        for h, label in zip(hazards, district_labels):
            h["district"] = label["district"]
            h["state"] = label["state"]

    return hazards


if __name__ == "__main__":
    result = detect()
    hail = [h for h in result if h["type"] == "hail"]
    lightning = [h for h in result if h["type"] == "lightning"]
    print(f"{len(hail)} hail point(s), {len(lightning)} lightning strike(s) across India right now")
    for h in hail[:5]:
        print(h)
