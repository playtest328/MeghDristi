"""Canonical synthetic storm-cell trajectory.

Single source of truth for the fake storm's position over time, so the
synthetic radar (2c), synthetic satellite (2b), and lightning intensity
(2a/2d) all agree on where the storm is at a given timestamp instead of
each mock generator drawing an independent, physically inconsistent cell.
Real ingestion doesn't need this module — it exists only because we're
faking multiple sensors of the *same* storm.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from nowcast.configs.settings import get_region_bbox

DEFAULT_CELL = dict(
    bearing_deg=60,   # ENE track, typical monsoon convection over this region
    speed_kmh=30,
)


def _default_cell_latlon():
    """Storm starts at the active region's center — recomputed on every call
    so switching regions (settings.set_active_region) relocates the demo
    storm on the next ingest cycle, not just on process restart."""
    lon_min, lat_min, lon_max, lat_max = get_region_bbox()
    return (lat_min + lat_max) / 2, (lon_min + lon_max) / 2


def center_at(t_min, cell_lat=None, cell_lon=None, bearing_deg=None, speed_kmh=None):
    default_lat, default_lon = _default_cell_latlon()
    cell_lat = default_lat if cell_lat is None else cell_lat
    cell_lon = default_lon if cell_lon is None else cell_lon
    bearing_deg = DEFAULT_CELL["bearing_deg"] if bearing_deg is None else bearing_deg
    speed_kmh = DEFAULT_CELL["speed_kmh"] if speed_kmh is None else speed_kmh

    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * np.cos(np.radians(cell_lat))
    bearing_rad = np.radians(bearing_deg)

    dist_km = speed_kmh * (t_min / 60.0)
    dlat = (dist_km * np.cos(bearing_rad)) / km_per_deg_lat
    dlon = (dist_km * np.sin(bearing_rad)) / km_per_deg_lon
    return cell_lat + dlat, cell_lon + dlon


def cluster_intensity_fraction(
    lon_grid,
    lat_grid,
    center_lat,
    center_lon,
    bearing_deg=None,
    radius_km=8,
    n_cells=6,
    stretch=1.7,
    seed=None,
):
    """Storm intensity fraction in [0, 1], shaped like a real convective
    cluster instead of one perfectly circular Gaussian blob.

    A single `peak * exp(-(r/sigma)^2)` renders as smooth, equispaced
    concentric rings — visibly synthetic next to real radar/satellite
    imagery, which shows several cells of varying size clustered together
    and smeared along the direction of motion (gust-front outflow, cell
    trailing). This scatters `n_cells` randomly-sized sub-cells around
    (center_lat, center_lon), each stretched along `bearing_deg` (so they
    read as flowing/streaky rather than static), and combines them with a
    max so overlapping cells produce sharp local peaks instead of a flat
    average — mimicking the "concentrated big and small gradients" of a
    real storm cluster.

    `seed=None` means a fresh random cluster shape per call (matching the
    existing per-call noise every mock generator already adds) — only the
    cluster's centroid/direction is shared canon (via `center_at` above),
    not its exact cell layout.
    """
    bearing_deg = DEFAULT_CELL["bearing_deg"] if bearing_deg is None else bearing_deg
    rng = np.random.default_rng(seed)

    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * np.cos(np.radians(center_lat))
    bearing_rad = np.radians(bearing_deg)
    along = np.array([np.cos(bearing_rad), np.sin(bearing_rad)])  # (dlat, dlon) unit vector
    across = np.array([-np.sin(bearing_rad), np.cos(bearing_rad)])

    spread_km = radius_km * 1.8

    field = np.zeros_like(lon_grid, dtype=np.float32)
    for _ in range(n_cells):
        # Offsets biased along the bearing so cells trail behind/ahead of
        # the core like a real squall cluster, not a uniform circular scatter.
        off_along = rng.normal(0, spread_km * 0.7)
        off_across = rng.normal(0, spread_km * 0.4)
        dlat_km = off_along * along[0] + off_across * across[0]
        dlon_km = off_along * along[1] + off_across * across[1]
        cell_lat = center_lat + dlat_km / km_per_deg_lat
        cell_lon = center_lon + dlon_km / km_per_deg_lon

        cell_radius_km = radius_km * rng.uniform(0.35, 1.15)  # varying cell size
        cell_peak = rng.uniform(0.55, 1.0)

        dy_km = (lat_grid - cell_lat) * km_per_deg_lat
        dx_km = (lon_grid - cell_lon) * km_per_deg_lon
        d_along = dx_km * along[1] + dy_km * along[0]
        d_across = dx_km * across[1] + dy_km * across[0]
        r_km = np.sqrt((d_along / stretch) ** 2 + d_across**2)  # elongated = "current" look

        field = np.maximum(field, cell_peak * np.exp(-(r_km**2) / (2 * cell_radius_km**2)))

    return np.clip(field, 0, 1)


def default_india_storm_spots(now_epoch=None):
    """Canonical set of active storm locations across India right now: the
    active demo region's own storm (always included, at full intensity —
    the per-region pySTEPS/hazard-rule pipeline depends on a storm being
    there) plus every storm currently alive in the deterministic, time-
    seeded lifecycle (see processing/storm_lifecycle.py).

    Because that lifecycle is a pure function of real wall-clock time —
    not per-process randomness — two processes (or the same process before
    and after a restart) asking "what's active right now" get the same
    answer: the layout only actually changes as real time passes (storms
    are born, move, and fade out over tens of minutes to hours), not on
    every restart or refresh. Shared by hazard_india.py and
    satellite_insat.py so the all-India satellite IR and radar/hazard
    layers show the same storms in the same places rather than each
    independently randomizing its own."""
    from nowcast.processing.storm_lifecycle import active_storms

    region_lat, region_lon = center_at(0)
    region_spot = {
        "lat": region_lat,
        "lon": region_lon,
        "bearing_deg": DEFAULT_CELL["bearing_deg"],
        "radius_km": 20.0,
        "intensity": 1.0,
        "seed": 0,  # fixed — the region storm's texture shouldn't flicker either
    }
    return [region_spot] + active_storms(now_epoch)


def multi_cluster_intensity_fraction(lon_grid, lat_grid, spots):
    """Combine cluster_intensity_fraction for several `spots` (see
    default_india_storm_spots) via elementwise max, so multiple scattered,
    independently-appearing storms show up on one grid instead of a single
    permanent cell. Each spot's contribution is scaled by its own
    `intensity` (defaults to 1.0), which is what makes a storm fade in and
    out smoothly as it's born/dies rather than blinking on and off."""
    field = np.zeros_like(lon_grid, dtype=np.float32)
    for spot in spots:
        cell = cluster_intensity_fraction(
            lon_grid, lat_grid, spot["lat"], spot["lon"],
            bearing_deg=spot.get("bearing_deg"), radius_km=spot.get("radius_km", 20),
            seed=spot.get("seed"),
        )
        field = np.maximum(field, spot.get("intensity", 1.0) * cell)
    return field
