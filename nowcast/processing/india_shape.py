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

# Small empirical correction: even with the mask sampling the exact same
# grid the color data uses (see module docstring), the shaded region still
# reads as a little larger than the crisp vector outline in practice —
# most visibly at the northern border, while the southern tip (Kanyakumari)
# already lines up correctly. Whatever residual causes that (texture
# filtering bleed when MapLibre stretches the raster image across the
# bbox, coarse-grid edge quantization, or some combination) shrinks
# uniformly toward the south, i.e. scaling each row's distance from
# lat_min down by this factor, so the anchor point users confirmed already
# matches (the south edge) stays fixed and only the northward overreach is
# pulled in. Empirical, not derived from a specific geometric cause — if
# the fit still isn't right, adjust this number rather than re-deriving
# the coordinate math again (that part is now verified correct; see
# module docstring's history of that separate bug).
_NORTH_SHRINK = 0.03  # 3%

# Two local, per-longitude-band corrections on top of the uniform
# _NORTH_SHRINK above — each a smooth raised-cosine bump (1.0 at the
# band's center, tapering to 0.0 at/past its edges, so it blends into the
# uniform shrink everywhere else with no visible seam):
#
# - Kashmir/Ladakh needed to extend further NORTH than the uniform shrink
#   left it at — a NEGATIVE local addition to the shrink (cancelling part
#   of it). _KASHMIR_BOOST=1.0 would cancel it completely at the band
#   center (the unshrunk true boundary there); <1.0 only partially.
# - Gujarat (Kutch/Rann of Kutch, its northernmost extent) needed to pull
#   IN from the north a bit more than the uniform shrink already did — a
#   POSITIVE local addition on top of it. Same mechanism, opposite sign.
#
# Both are independently tunable; see _local_bump/_mask_for_grid below for
# how they combine.
_KASHMIR_LON_CENTER = 76.5
_KASHMIR_LON_HALF_WIDTH = 3.5
_KASHMIR_BOOST = 0.6  # fraction of _NORTH_SHRINK to CANCEL at the band center

_GUJARAT_LON_CENTER = 71.0
_GUJARAT_LON_HALF_WIDTH = 3.0
_GUJARAT_EXTRA_SHRINK = 0.02  # ADDED to _NORTH_SHRINK at the band center


def _local_bump(lons, center, half_width):
    """1.0 at `center`, smoothly falling to 0.0 by `center +/- half_width`,
    0.0 beyond that — a raised-cosine window, shared by every per-region
    correction below so they all blend into the uniform shrink the same
    way (no hard edges anywhere)."""
    lon_dist = np.abs(lons - center)
    return np.where(lon_dist < half_width, 0.5 * (1 + np.cos(np.pi * lon_dist / half_width)), 0.0)


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

    # Per-column shrink: _NORTH_SHRINK everywhere, locally reduced near
    # Kashmir/Ladakh and locally increased near Gujarat (see the two
    # _local_bump-based corrections above).
    kashmir_bump = _local_bump(lons, _KASHMIR_LON_CENTER, _KASHMIR_LON_HALF_WIDTH)
    gujarat_bump = _local_bump(lons, _GUJARAT_LON_CENTER, _GUJARAT_LON_HALF_WIDTH)
    shrink_per_col = _NORTH_SHRINK * (1 - _KASHMIR_BOOST * kashmir_bump) + _GUJARAT_EXTRA_SHRINK * gujarat_bump  # (w,)

    # Test each row/column against a point EXTRAPOLATED slightly further
    # from lat_min (south) than its true position — see _NORTH_SHRINK
    # above. This makes rows near the true north edge test against a point
    # just past it (more likely outside any real landmass there), so they
    # flip to transparent, pulling the visible shaded region's northern
    # extent inward. Dividing (not multiplying) by (1 - shrink) is what
    # makes this an expansion of the test point away from the south
    # anchor, not a contraction toward it — a contraction would test
    # closer to the interior instead and make the shaded region LARGER,
    # the opposite of what's wanted here. Only affects which
    # polygon-containment answer each cell gets, not which row a color
    # value is displayed at, so this can't reintroduce the data/mask index
    # mismatch that was the actual earlier bug.
    lon_grid, lat_col = np.meshgrid(lons, lats)  # both (h, w); lat_col[i, j] = lats[i]
    test_lat_grid = lat_min + (lat_col - lat_min) / (1 - shrink_per_col[None, :])  # (h, w), row 0 = south

    inside = contains(india, lon_grid, test_lat_grid)
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
