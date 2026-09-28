"""Fusion layer (section 3 of project.md).

Regrids satellite + radar onto the common demo grid, attaches lightning
probability to the nearest grid cell, and stacks
`[TIR1, WV, MWIR, reflectivity, lightning_prob]` per timestep — the same
channel structure SEVIR uses (section 3, item 4). Maintains a rolling
buffer of the last `INGEST_CYCLE_MINUTES`-spaced frames covering ~1-2h,
used as model input context.

All three sources currently share GRID_SIZE/REGION_BBOX by construction
(they're synthetic, generated on the same grid), so regridding here is
effectively identity — but `_regrid_nearest` is real nearest-neighbor
regridding, not a no-op shortcut, so swapping in real satellite (4-8km
native) or radar (1km native) grids later only changes the input arrays,
not this function.
"""
import glob
import os
from datetime import datetime

import numpy as np

from nowcast.configs.settings import DATA_DIR, get_region_bbox
from nowcast.processing.synthetic_radar import GRID_SIZE

CHANNELS = ["tir1", "wv", "mwir", "reflectivity_dbz", "lightning_prob"]


def _grid_coords():
    lon_min, lat_min, lon_max, lat_max = get_region_bbox()
    lons = np.linspace(lon_min, lon_max, GRID_SIZE)
    lats = np.linspace(lat_min, lat_max, GRID_SIZE)
    return np.meshgrid(lons, lats)


def _regrid_nearest(src_lons, src_lats, src_values, dst_lon_grid, dst_lat_grid):
    """Nearest-neighbor regrid from a source lat/lon grid onto the target grid."""
    if src_values.shape == dst_lon_grid.shape:
        return src_values.astype(np.float32)
    from scipy.interpolate import griddata

    points = np.column_stack([src_lons.ravel(), src_lats.ravel()])
    return griddata(
        points, src_values.ravel(), (dst_lon_grid, dst_lat_grid), method="nearest"
    ).astype(np.float32)


def _latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def _load_latest_satellite():
    path = _latest(os.path.join(DATA_DIR, "satellite", "*.npz"))
    if path is None:
        return None
    data = np.load(path)
    return {"tir1": data["tir1"], "wv": data["wv"], "mwir": data["mwir"]}, path


def _load_latest_radar():
    path = _latest(os.path.join(DATA_DIR, "radar", "*.npz"))
    if path is None:
        return None
    data = np.load(path)
    return {"reflectivity_dbz": data["reflectivity_dbz"], "velocity_ms": data["velocity_ms"]}, path


def _load_latest_lightning():
    import json

    path = _latest(os.path.join(DATA_DIR, "imd", "*.json"))
    if path is None:
        return None
    with open(path) as f:
        data = json.load(f)
    return data["records"], path


def _lightning_to_grid(records, lon_grid, lat_grid, influence_km=6.0):
    """Attach lightning-probability points to the fusion grid (section 3, item 3).

    IMD's lightning-probability categories are district/area products, not
    point taps, so each station's probability is spread over a Gaussian
    footprint (`influence_km`) rather than assigned to a single nearest
    cell — otherwise the hail rule (needs reflectivity + cold top +
    lightning collocated) would almost never fire given how sparse the
    station network is relative to the grid.
    """
    grid = np.zeros_like(lon_grid, dtype=np.float32)
    if not records:
        return grid
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * np.cos(np.radians(float(lat_grid.mean())))
    for rec in records:
        prob = rec.get("lightning_prob", 0.0)
        dy_km = (lat_grid - rec["lat"]) * km_per_deg_lat
        dx_km = (lon_grid - rec["lon"]) * km_per_deg_lon
        r_km = np.sqrt(dx_km**2 + dy_km**2)
        footprint = prob * np.exp(-(r_km**2) / (2 * influence_km**2))
        grid = np.maximum(grid, footprint)
    return grid


def build_fused_frame():
    """Assemble the current multi-channel raster from the latest ingestion files.

    Returns None if any source hasn't produced a snapshot yet (callers
    should trigger the pullers first — see api/main.py's ingest cycle).
    """
    sat = _load_latest_satellite()
    radar = _load_latest_radar()
    lightning = _load_latest_lightning()
    if sat is None or radar is None or lightning is None:
        return None

    sat_data, sat_path = sat
    radar_data, radar_path = radar
    lightning_records, lightning_path = lightning

    lon_grid, lat_grid = _grid_coords()
    # Native grids coincide with the demo grid for the synthetic sources;
    # _regrid_nearest still runs the real interpolation path once shapes differ.
    reflectivity = _regrid_nearest(lon_grid, lat_grid, radar_data["reflectivity_dbz"], lon_grid, lat_grid)
    lightning_grid = _lightning_to_grid(lightning_records, lon_grid, lat_grid)

    channels = {
        "tir1": sat_data["tir1"],
        "wv": sat_data["wv"],
        "mwir": sat_data["mwir"],
        "reflectivity_dbz": reflectivity,
        "velocity_ms": radar_data["velocity_ms"],
        "lightning_prob": lightning_grid,
    }
    return {
        "channels": channels,
        "bbox": get_region_bbox(),
        "grid_size": GRID_SIZE,
        "sources": {"satellite": sat_path, "radar": radar_path, "lightning": lightning_path},
    }


TIMESTAMP_FMT = "%Y%m%dT%H%M%SZ"


def _parse_ts(filepath):
    base = os.path.splitext(os.path.basename(filepath))[0]
    return datetime.strptime(base, TIMESTAMP_FMT)


def list_imd_timestamps():
    """Every IMD snapshot timestamp currently on disk, oldest first — the
    real (if short-lived) historical archive Replay is built on. Each pull
    cycle writes a new timestamped file rather than overwriting the last
    one, so this genuinely grows over the life of the server process."""
    files = sorted(glob.glob(os.path.join(DATA_DIR, "imd", "*.json")))
    return [os.path.splitext(os.path.basename(f))[0] for f in files]


def _nearest_file(directory, target_dt):
    files = glob.glob(os.path.join(directory, "*.npz"))
    if not files:
        return None
    return min(files, key=lambda f: abs((_parse_ts(f) - target_dt).total_seconds()))


def build_fused_frame_for_timestamp(timestamp_str):
    """Reconstruct a fusion frame for a specific historical IMD snapshot,
    pairing it with the nearest satellite/radar snapshots by time
    (ingestion cycles run together, so these are normally seconds apart).

    This is real historical reconstruction — unlike pySTEPS' forecast
    (which always regenerates its own synthetic present-moment history
    regardless of what timestamp you ask about, see pysteps_baseline.py),
    hail/downburst grid rules only need a single fused frame, so replaying
    them for a past moment is meaningful. Cloudburst is NOT included in
    replay for that reason (see api/main.py's /history/hazards docstring).
    """
    imd_path = os.path.join(DATA_DIR, "imd", f"{timestamp_str}.json")
    if not os.path.exists(imd_path):
        return None
    target_dt = _parse_ts(imd_path)

    sat_path = _nearest_file(os.path.join(DATA_DIR, "satellite"), target_dt)
    radar_path = _nearest_file(os.path.join(DATA_DIR, "radar"), target_dt)
    if sat_path is None or radar_path is None:
        return None

    import json

    sat_npz = np.load(sat_path)
    radar_npz = np.load(radar_path)
    with open(imd_path) as f:
        lightning_records = json.load(f)["records"]

    lon_grid, lat_grid = _grid_coords()
    reflectivity = _regrid_nearest(lon_grid, lat_grid, radar_npz["reflectivity_dbz"], lon_grid, lat_grid)
    lightning_grid = _lightning_to_grid(lightning_records, lon_grid, lat_grid)

    channels = {
        "tir1": sat_npz["tir1"],
        "wv": sat_npz["wv"],
        "mwir": sat_npz["mwir"],
        "reflectivity_dbz": reflectivity,
        "velocity_ms": radar_npz["velocity_ms"],
        "lightning_prob": lightning_grid,
    }
    return {
        "channels": channels,
        "bbox": get_region_bbox(),
        "grid_size": GRID_SIZE,
        "sources": {"satellite": sat_path, "radar": radar_path, "lightning": imd_path},
        "timestamp": timestamp_str,
    }


if __name__ == "__main__":
    fr = build_fused_frame()
    if fr is None:
        print("[fusion] missing a source snapshot — run the ingestion pullers first")
    else:
        for name, arr in fr["channels"].items():
            print(f"{name}: shape={arr.shape} min={arr.min():.1f} max={arr.max():.1f}")
