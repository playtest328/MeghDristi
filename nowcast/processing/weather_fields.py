"""Ambient weather fields — temperature, humidity, wind.

Synthetic: smooth latitude-driven climatology plus a storm-proximity
perturbation (cooler, more humid, windier near the fake storm core, like a
real gust front/cold pool) so it still reads as physically coherent with
the rest of the demo. Not part of
project.md's original data sources (IMD/MOSDAC nowcast feeds don't give
gridded temperature/humidity/wind directly at this resolution) — added on
top as a "situational awareness" layer so the map shows colored data
across the whole visible region, not just the narrow storm bbox used for
radar/satellite/hazards.

Two access patterns:
- `generate_grid(t_min)`: full raster over settings.get_wide_bbox() (follows
  the active region), for the colored map overlay.
- `sample_point(lat, lon, t_min)`: single-point value, for the per-region
  "future trend" panel — cheap, no need to build the whole grid per click
  (in live mode, this samples the same cached grid `generate_grid` would
  have built, not a separate real-time query per point).
"""
import numpy as np

from nowcast.configs.settings import get_wide_bbox, WIDE_GRID_SIZE
from nowcast.processing.storm_track import center_at

# Baseline climatology for the demo region/season (rough Maharashtra
# pre-monsoon/monsoon values) — purely illustrative, not sourced from IMD.
_TEMP_BASE_C = 29.0
_TEMP_LAT_GRADIENT = -0.35     # slightly cooler further north/inland per degree lat
_TEMP_DIURNAL_AMPLITUDE_C = 3.5
_HUMIDITY_BASE_PCT = 55.0
_WIND_BASE_MS = 4.0
_WIND_BASE_BEARING_DEG = 250   # prevailing westerly-ish background flow

_STORM_COOLING_C = 6.0
_STORM_HUMIDITY_BOOST_PCT = 30.0
_STORM_WIND_BOOST_MS = 9.0
_STORM_INFLUENCE_KM = 45.0

_PRESSURE_BASE_HPA = 1010.0
_STORM_PRESSURE_DIP_HPA = 12.0  # mesoscale convective low at the storm core


def _grid_coords():
    lon_min, lat_min, lon_max, lat_max = get_wide_bbox()
    lons = np.linspace(lon_min, lon_max, WIDE_GRID_SIZE)
    lats = np.linspace(lat_min, lat_max, WIDE_GRID_SIZE)
    return np.meshgrid(lons, lats)


def _diurnal_factor(t_min):
    # simple sinusoidal day/night cycle, arbitrary phase for demo purposes
    return np.sin((t_min / 60.0) / 24.0 * 2 * np.pi)


def _storm_proximity(lat, lon, t_min):
    c_lat, c_lon = center_at(t_min)
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * np.cos(np.radians(c_lat))
    dy_km = (lat - c_lat) * km_per_deg_lat
    dx_km = (lon - c_lon) * km_per_deg_lon
    r_km = np.sqrt(dx_km**2 + dy_km**2)
    return np.exp(-(r_km**2) / (2 * _STORM_INFLUENCE_KM**2))


def _fields_at(lat, lon, t_min):
    """Core formulas, vectorized-friendly (lat/lon can be arrays or scalars)."""
    proximity = _storm_proximity(lat, lon, t_min)
    diurnal = _diurnal_factor(t_min)

    temperature_c = (
        _TEMP_BASE_C
        + _TEMP_LAT_GRADIENT * (lat - get_wide_bbox()[1])
        + _TEMP_DIURNAL_AMPLITUDE_C * diurnal
        - _STORM_COOLING_C * proximity
    )
    humidity_pct = np.clip(
        _HUMIDITY_BASE_PCT - 10 * diurnal + _STORM_HUMIDITY_BOOST_PCT * proximity, 5, 100
    )
    wind_speed_ms = _WIND_BASE_MS + _STORM_WIND_BOOST_MS * proximity
    # wind backs toward the storm center as you get close to it (simple
    # inflow approximation), otherwise holds the prevailing bearing
    c_lat, c_lon = center_at(t_min)
    inflow_bearing = (np.degrees(np.arctan2(c_lon - lon, c_lat - lat)) + 360) % 360
    wind_dir_deg = _WIND_BASE_BEARING_DEG * (1 - proximity) + inflow_bearing * proximity
    pressure_hpa = _PRESSURE_BASE_HPA - _STORM_PRESSURE_DIP_HPA * proximity

    return temperature_c, humidity_pct, wind_speed_ms, wind_dir_deg, pressure_hpa


def _generate_grid_mock(t_min=0):
    lon_grid, lat_grid = _grid_coords()
    temperature_c, humidity_pct, wind_speed_ms, wind_dir_deg, pressure_hpa = _fields_at(lat_grid, lon_grid, t_min)
    noise = lambda scale: np.random.normal(0, scale, lat_grid.shape)
    return {
        "temperature_c": (temperature_c + noise(0.4)).astype(np.float32),
        "humidity_pct": np.clip(humidity_pct + noise(2.0), 0, 100).astype(np.float32),
        "wind_speed_ms": np.clip(wind_speed_ms + noise(0.3), 0, None).astype(np.float32),
        "wind_dir_deg": (wind_dir_deg % 360).astype(np.float32),
        "pressure_hpa": (pressure_hpa + noise(0.5)).astype(np.float32),
        "bbox": get_wide_bbox(),
        "grid_size": WIDE_GRID_SIZE,
        "source": "synthetic",
    }


def generate_grid(t_min=0):
    return _generate_grid_mock(t_min)


def sample_point(lat, lon, t_min=0):
    temperature_c, humidity_pct, wind_speed_ms, wind_dir_deg, pressure_hpa = _fields_at(lat, lon, t_min)
    return {
        "temperature_c": round(float(temperature_c), 1),
        "humidity_pct": round(float(np.clip(humidity_pct, 0, 100)), 1),
        "wind_speed_ms": round(float(max(wind_speed_ms, 0)), 1),
        "wind_dir_deg": round(float(wind_dir_deg % 360), 1),
        "pressure_hpa": round(float(pressure_hpa), 1),
    }


def _stat(arr):
    return {"min": round(float(arr.min()), 1), "mean": round(float(arr.mean()), 1), "max": round(float(arr.max()), 1)}


def area_stats(bbox, t_min=0):
    """Min/mean/max temperature/humidity/wind/pressure over a user-drawn
    area (drag-select), not just a single point — backs the area-inspect
    panel. Masks generate_grid()'s cells to whatever falls inside `bbox`;
    if the drawn area doesn't overlap WIDE_BBOX at all, falls back to a
    single center-point sample so the panel still shows something instead
    of empty stats."""
    lon_min, lat_min, lon_max, lat_max = bbox
    grid = generate_grid(t_min)
    glon_min, glat_min, glon_max, glat_max = grid["bbox"]
    n = grid["grid_size"]
    lons = np.linspace(glon_min, glon_max, n)
    lats = np.linspace(glat_min, glat_max, n)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    mask = (lon_grid >= lon_min) & (lon_grid <= lon_max) & (lat_grid >= lat_min) & (lat_grid <= lat_max)

    if not mask.any():
        center = sample_point((lat_min + lat_max) / 2, (lon_min + lon_max) / 2, t_min)
        return {k: {"min": v, "mean": v, "max": v} for k, v in center.items()}

    return {
        "temperature_c": _stat(grid["temperature_c"][mask]),
        "humidity_pct": _stat(grid["humidity_pct"][mask]),
        "wind_speed_ms": _stat(grid["wind_speed_ms"][mask]),
        "pressure_hpa": _stat(grid["pressure_hpa"][mask]),
    }


def wind_vector_points(stride=4, t_min=0):
    """Sparse sample of wind vectors for arrow-symbol rendering (dense grids
    of arrows are unreadable — this thins WIDE_GRID_SIZE down by `stride`)."""
    lon_min, lat_min, lon_max, lat_max = get_wide_bbox()
    lons = np.linspace(lon_min, lon_max, WIDE_GRID_SIZE)[::stride]
    lats = np.linspace(lat_min, lat_max, WIDE_GRID_SIZE)[::stride]
    points = []
    for lat in lats:
        for lon in lons:
            v = sample_point(lat, lon, t_min)
            points.append({"lat": float(lat), "lon": float(lon), **{
                "wind_speed_ms": v["wind_speed_ms"], "wind_dir_deg": v["wind_dir_deg"]}})
    return points


if __name__ == "__main__":
    g = generate_grid()
    for k in ["temperature_c", "humidity_pct", "wind_speed_ms", "wind_dir_deg", "pressure_hpa"]:
        arr = g[k]
        print(f"{k}: min={arr.min():.1f} max={arr.max():.1f} mean={arr.mean():.1f}")
    print("point sample @storm core:", sample_point(18.30, 73.65, 0))
    print("point sample far away:", sample_point(16.0, 74.0, 0))
