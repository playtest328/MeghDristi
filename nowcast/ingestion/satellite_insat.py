"""INSAT-3D/3DR satellite puller (section 2b of project.md).

Original plan: mdapi.py client against MOSDAC, datasetId 3DIMG_L1B_STD or
3DIMG_L1C_ASIA_MER, parsed with h5py/satpy, reprojected with pyresample —
not implemented, still needs MOSDAC approval (section 1).

Generates synthetic TIR-1 (10.8um), WV (6.7um), and MWIR fields correlated
with the same storm cell as the synthetic radar (via storm_track), so a
real convective signature is visible — cold cloud top and moist WV signal
collocated with the reflectivity core, not independent noise. Writes to
data/satellite/<ts>.npz with keys: tir1, wv, mwir (each GRID_SIZE x
GRID_SIZE), bbox, timestamp.
"""
import os
import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from nowcast.configs.settings import get_region_bbox, INDIA_BBOX, DATA_DIR
from nowcast.processing.storm_track import center_at, cluster_intensity_fraction, default_india_storm_spots, multi_cluster_intensity_fraction
from nowcast.processing.synthetic_radar import GRID_SIZE

SATELLITE_DIR = os.path.join(DATA_DIR, "satellite")

# Ambient (clear-sky) brightness temps and convective cold-top minimum, Kelvin.
_TIR1_AMBIENT_K = 298.0
_TIR1_COLD_TOP_K = 198.0  # deep convection overshoot territory
_WV_AMBIENT_K = 245.0
_WV_MOIST_K = 220.0
_MWIR_AMBIENT_K = 285.0


def _grid_coords():
    lon_min, lat_min, lon_max, lat_max = get_region_bbox()
    lons = np.linspace(lon_min, lon_max, GRID_SIZE)
    lats = np.linspace(lat_min, lat_max, GRID_SIZE)
    return np.meshgrid(lons, lats)


def _fetch_mock(t_min=0):
    lon_grid, lat_grid = _grid_coords()
    c_lat, c_lon = center_at(t_min)

    # Cold cloud top footprint is broader than the reflectivity core —
    # anvil/cirrus shield extends beyond the precip core in real convection
    # — and clustered/varying-size rather than one perfect circle, same
    # reasoning as synthetic_radar's cluster_intensity_fraction.
    cloud_radius_km = 18
    cold_frac = cluster_intensity_fraction(lon_grid, lat_grid, c_lat, c_lon, radius_km=cloud_radius_km)

    tir1 = _TIR1_AMBIENT_K - cold_frac * (_TIR1_AMBIENT_K - _TIR1_COLD_TOP_K)
    wv = _WV_AMBIENT_K - cold_frac * (_WV_AMBIENT_K - _WV_MOIST_K)
    mwir = _MWIR_AMBIENT_K - cold_frac * (_MWIR_AMBIENT_K - _TIR1_COLD_TOP_K - 10)

    noise = lambda k: np.random.normal(0, k, tir1.shape)
    tir1 = (tir1 + noise(1.0)).astype(np.float32)
    wv = (wv + noise(1.0)).astype(np.float32)
    mwir = (mwir + noise(1.0)).astype(np.float32)
    return tir1, wv, mwir


def synthetic_india_tir1(grid_size, spots=None):
    """Synthetic all-India TIR-1 brightness-temperature grid — several
    scattered storm cells (see storm_track.default_india_storm_spots),
    rendered over INDIA_BBOX instead of the small active-region bbox.
    Exists because the per-region tir1 grid (_fetch_mock, ~0.5deg box) is
    imperceptibly small on the default all-India map view — this gives the
    Satellite IR layer a footprint visible without zooming into the active
    demo city, and (via `spots`) the same storms in the same places as the
    radar/hazard layers rather than an independent random draw.

    `spots` lets main.py pass the same storm-spot draw hazard_india used
    for reflectivity/strikes this refresh cycle — left as None, generates
    its own so the module stays runnable standalone."""
    if spots is None:
        spots = default_india_storm_spots()

    lon_min, lat_min, lon_max, lat_max = INDIA_BBOX
    lons = np.linspace(lon_min, lon_max, grid_size)
    lats = np.linspace(lat_min, lat_max, grid_size)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    cold_frac = multi_cluster_intensity_fraction(lon_grid, lat_grid, spots)
    tir1 = _TIR1_AMBIENT_K - cold_frac * (_TIR1_AMBIENT_K - _TIR1_COLD_TOP_K)
    tir1 = (tir1 + np.random.normal(0, 1.0, tir1.shape)).astype(np.float32)
    return tir1


def pull():
    os.makedirs(SATELLITE_DIR, exist_ok=True)
    tir1, wv, mwir = _fetch_mock()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(SATELLITE_DIR, f"{ts}.npz")
    np.savez(out_path, tir1=tir1, wv=wv, mwir=mwir, bbox=np.array(get_region_bbox()))
    print(f"[satellite_insat] wrote TIR1/WV/MWIR grid -> {out_path}")
    return out_path


if __name__ == "__main__":
    pull()
