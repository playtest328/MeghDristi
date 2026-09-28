"""India's real coastline/border outline, for clipping the all-India
satellite/radar/weather rasters (satellite_insat.py / hazard_india.py /
weather_fields.py) to India's actual shape instead of leaving them as a
plain rectangular grid that visibly spans into Pakistan, China, Myanmar,
the ocean, etc.

The outline is a dedicated country-level boundary (nowcast/configs/geo/
india_outline.geojson — see that file's neighboring README for
provenance), not a union of the per-state polygons used elsewhere for the
clickable state/district layers. That was tried first and rejected: the
open per-state dataset used for AdminBoundaries.tsx turned out to have a
real data error (Rajasthan's raw, unmodified polygon extends into
Pakistan near 72E/28N — confirmed against the original upstream file, not
something introduced by any processing here), and unioning 35
independently-simplified polygons is generally fragile (shared borders
drift apart, self-intersections appear). A dedicated single country
outline sidesteps both problems and was cross-checked against 12 cities
on both sides of India's borders (Delhi/Mumbai/Kanyakumari/Leh inside;
Islamabad/Lahore/Multan/Quetta/Kathmandu/Dhaka/Colombo/Yangon outside)
before being adopted.

THE ALIGNMENT BUG, three times over, and what finally fixed it:
Every previous version of this module tested each pixel's geographic
position using some INDEPENDENTLY-DERIVED coordinate formula — first a
plain lon_min..lon_max linspace, then a "pixel-center" formula correcting
for how MapLibre's image source maps a bbox onto a texture, then a direct
PIL polygon rasterization using that same pixel-center convention. All
three were internally consistent and individually defensible, and all
three were STILL subtly wrong — because the actual color data being
clipped (hazard_india.synthetic_reflectivity, satellite_insat.
synthetic_india_tir1, weather_fields.generate_grid) is generated from ITS
OWN grid, built with plain `np.linspace(lon_min, lon_max, grid_size)` —
an endpoint-inclusive convention where index 0 sits exactly AT lon_min,
not a "pixel-center" convention (index 0 as a cell spanning the first
1/N of the range). Any mask built from a different formula than the one
the color data itself used is answering a different question — "is this
image pixel's on-screen position inside India" rather than "does the
color value stored at this array index represent a point inside India" —
and those two drift apart across the grid, worst toward the edges. That
mismatch is what kept showing up as the tint appearing shifted (most
visibly near the northern border, where the divergence is largest for a
grid spanning INDIA_BBOX).

The fix: don't derive a second coordinate formula at all. Reuse the
EXACT SAME np.linspace(...) calls the color-generating code uses, so a
mask value and the color value at the same array index are — by
construction, not by two formulas hopefully agreeing — talking about the
literal same grid point. See clip_alpha_to_india's docstring for the
mechanics (this needs the pre-flip array; see its call site in
api/main.py for why).
"""
import json
import os

import numpy as np
from shapely.geometry import shape

_OUTLINE_GEOJSON = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "configs", "geo", "india_outline.geojson"
)

_india_polygon = None  # lazy-cached
_mask_cache = {}  # (w, h, bbox) -> (h, w) uint8 alpha array, row 0 = SOUTH (pre-flip)


def _load_india_polygon():
    global _india_polygon
    if _india_polygon is not None:
        return _india_polygon
    with open(_OUTLINE_GEOJSON, encoding="utf-8") as f:
        data = json.load(f)
    _india_polygon = shape(data["features"][0]["geometry"]).buffer(0)
    return _india_polygon


def _mask_for_grid(w, h, bbox):
    """India-outline alpha mask (255 = inside, 0 = outside) on the EXACT
    grid `np.linspace(lon_min, lon_max, w)` / `np.linspace(lat_min,
    lat_max, h)` describes — row 0 = lat_min = south, matching every
    color-data generator's own grid construction (hazard_india.py /
    satellite_insat.py / weather_fields.py all build their lon/lat grids
    this exact same way). Not a separately-derived image-coordinate
    formula — see module docstring for why that was the whole problem."""
    key = (w, h, bbox)
    cached = _mask_cache.get(key)
    if cached is not None:
        return cached

    from shapely.vectorized import contains

    india = _load_india_polygon()
    lon_min, lat_min, lon_max, lat_max = bbox
    lons = np.linspace(lon_min, lon_max, w)
    lats = np.linspace(lat_min, lat_max, h)
    lon_grid, lat_grid = np.meshgrid(lons, lats)  # lat_grid[i, j] = lats[i], row 0 = south

    inside = contains(india, lon_grid, lat_grid)
    mask = np.where(inside, np.uint8(255), np.uint8(0))
    _mask_cache[key] = mask
    return mask


def clip_alpha_to_india(rgba_pre_flip, bbox):
    """Multiply the alpha channel of a PRE-FLIP (row 0 = south, i.e. before
    _array_to_png_data_url's np.flipud — same orientation as the arr that
    produced it) (H, W, 4) uint8 RGBA array by India's outline mask, so
    pixels outside India become transparent and the map's own basemap
    shows through them once flipped for display. `bbox` is (lon_min,
    lat_min, lon_max, lat_max) — the same bbox the color data's own grid
    was built over. Mutates and returns `rgba_pre_flip`."""
    h, w = rgba_pre_flip.shape[:2]
    mask = _mask_for_grid(w, h, tuple(bbox))
    rgba_pre_flip[..., 3] = np.minimum(rgba_pre_flip[..., 3], mask)
    return rgba_pre_flip
