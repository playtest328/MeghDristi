"""Synthetic reflectivity + radial-velocity generator — stand-in for real radar (2c).

No MOSDAC radar access yet, and PNG radar overlays (the other fallback in
section 2c) aren't quantitative, so pySTEPS (4a) can't run on them. This
generates a moving Gaussian storm cell on the demo grid so pySTEPS'
optical-flow + extrapolation has *something* physically plausible to work
on end to end. Swap for real CAPPI grids from `pyiwr`/Py-ART once MOSDAC
radar access exists — output shape/units (dBZ on a lat/lon grid) match
what the real pipeline will produce.

Cell position comes from `storm_track` so the same storm agrees across
radar, satellite, and lightning mock generators.
"""
import numpy as np

from nowcast.configs.settings import get_region_bbox
from nowcast.processing.storm_track import center_at, cluster_intensity_fraction, DEFAULT_CELL

GRID_SIZE = 64  # cells per side, ~ few hundred m to 1km depending on bbox extent


def _grid_coords():
    lon_min, lat_min, lon_max, lat_max = get_region_bbox()
    lons = np.linspace(lon_min, lon_max, GRID_SIZE)
    lats = np.linspace(lat_min, lat_max, GRID_SIZE)
    return np.meshgrid(lons, lats)


def generate_sequence(n_frames=6, dt_minutes=10, peak_dbz=58, radius_km=8, t_offset_min=None, **track_kwargs):
    """Return (frames, timestamps_min) — frames: list of (GRID_SIZE, GRID_SIZE) dBZ arrays.

    Storm cell advects per `storm_track`, one frame every `dt_minutes`, oldest
    first (as pySTEPS expects). `track_kwargs` override storm_track.DEFAULT_CELL.

    `t_offset_min` shifts the whole sequence in storm_track time; default
    None means the *last* frame lands at t=0 (i.e. frames are the recent
    past leading up to "now"), which is what pySTEPS extrapolation expects
    as its history window and what keeps this in sync with the single-frame
    "now" snapshot from `radar_puller`/`satellite_insat`/`imd_nowcast` (all
    anchored at storm_track t=0). Pass 0 explicitly to instead start the
    sequence AT t=0 (used by radar_puller for its single current-frame pull).
    """
    if t_offset_min is None:
        t_offset_min = -(n_frames - 1) * dt_minutes

    lon_grid, lat_grid = _grid_coords()
    km_per_deg_lat = 111.0
    _, bbox_lat_min, _, bbox_lat_max = get_region_bbox()
    km_per_deg_lon = 111.0 * np.cos(np.radians((bbox_lat_min + bbox_lat_max) / 2))

    bearing_deg = track_kwargs.get("bearing_deg")
    # One cluster shape (cell count/sizes/offsets) for the whole sequence,
    # just translated per-frame with the storm center — a shape that
    # re-randomized every frame would inject noise into pySTEPS' motion
    # estimate between consecutive frames.
    cluster_seed = np.random.default_rng().integers(0, 2**31 - 1)

    frames = []
    for i in range(n_frames):
        t_min = t_offset_min + i * dt_minutes
        c_lat, c_lon = center_at(t_min, **track_kwargs)

        cluster = cluster_intensity_fraction(
            lon_grid, lat_grid, c_lat, c_lon,
            bearing_deg=bearing_deg, radius_km=radius_km, seed=cluster_seed,
        )
        frame = peak_dbz * cluster
        frame += np.random.normal(0, 0.5, frame.shape)  # sensor noise
        frames.append(np.clip(frame, 0, None).astype(np.float32))

    return frames, [t_offset_min + i * dt_minutes for i in range(n_frames)]


def generate_velocity_frame(t_min=0, radius_km=8, max_velocity_ms=28, **track_kwargs):
    """Synthetic radial (Doppler) velocity couplet at the storm center.

    Real downburst signature: a tight inbound/outbound velocity dipole
    straddling the storm core along its motion axis (divergent outflow).
    We fake this as two offset Gaussian lobes of opposite sign, offset along
    the storm's bearing — a stand-in for what Py-ART would extract from a
    real volumetric scan. Units: m/s, positive = away from radar (outbound).
    """
    lon_grid, lat_grid = _grid_coords()
    km_per_deg_lat = 111.0
    _, bbox_lat_min, _, bbox_lat_max = get_region_bbox()
    km_per_deg_lon = 111.0 * np.cos(np.radians((bbox_lat_min + bbox_lat_max) / 2))

    bearing_deg = track_kwargs.get("bearing_deg", DEFAULT_CELL["bearing_deg"])
    c_lat, c_lon = center_at(t_min, **track_kwargs)
    bearing_rad = np.radians(bearing_deg)

    lobe_offset_km = radius_km * 0.5
    fwd_lat = c_lat + (lobe_offset_km * np.cos(bearing_rad)) / km_per_deg_lat
    fwd_lon = c_lon + (lobe_offset_km * np.sin(bearing_rad)) / km_per_deg_lon
    back_lat = c_lat - (lobe_offset_km * np.cos(bearing_rad)) / km_per_deg_lat
    back_lon = c_lon - (lobe_offset_km * np.sin(bearing_rad)) / km_per_deg_lon

    def _lobe(lat0, lon0, sign):
        dy_km = (lat_grid - lat0) * km_per_deg_lat
        dx_km = (lon_grid - lon0) * km_per_deg_lon
        r_km = np.sqrt(dx_km**2 + dy_km**2)
        return sign * max_velocity_ms * np.exp(-(r_km**2) / (2 * (radius_km * 0.4) ** 2))

    velocity = _lobe(fwd_lat, fwd_lon, +1) + _lobe(back_lat, back_lon, -1)
    velocity += np.random.normal(0, 0.5, velocity.shape)
    return velocity.astype(np.float32)
