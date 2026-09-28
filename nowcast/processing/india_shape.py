"""India's real coastline/border outline, for clipping the all-India
satellite/radar rasters (satellite_insat.py / hazard_india.py) to India's
actual shape instead of leaving them as a plain rectangular grid that
visibly spans into Pakistan, China, Myanmar, the ocean, etc.

The outline itself is derived from the frontend's own state boundary data
(nowcast/dashboard/public/geo/india_states.geojson — see that folder's
README for provenance/licensing) so there's one source of geometry, not
two copies drifting apart. Unioning 35 polygons is real work (~100ms), so
this is done once and cached at module scope, not per-request.

The actual clipping happens by zeroing a raster's alpha channel wherever
the pixel's (lon, lat) falls outside India — done in Python before the
PNG is ever sent to the frontend, so the browser gets an image that's
already transparent there and the basemap just shows through naturally.
This is deliberately NOT done as a separate opaque mask layer on the
frontend: an earlier attempt at that painted over the basemap itself
(not just the raster), hiding Pakistan/China/Myanmar/etc. behind a solid
box instead of leaving them visible — clipping the data at its source
avoids that failure mode entirely.
"""
import json
import os

import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union

_STATES_GEOJSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "nowcast", "dashboard", "public", "geo", "india_states.geojson",
)

_india_polygon = None  # lazy-cached union of all state polygons


def _load_india_polygon():
    global _india_polygon
    if _india_polygon is not None:
        return _india_polygon
    with open(_STATES_GEOJSON, encoding="utf-8") as f:
        data = json.load(f)
    geoms = [shape(f["geometry"]).buffer(0) for f in data["features"]]
    _india_polygon = unary_union(geoms)
    return _india_polygon


def clip_alpha_to_india(rgba, bbox):
    """Zero the alpha channel of an (H, W, 4) uint8 RGBA array wherever the
    corresponding grid cell's (lon, lat) falls outside India's real
    outline. `bbox` is (lon_min, lat_min, lon_max, lat_max), matching the
    grid `rgba` was rendered over (row 0 = south edge, per
    _array_to_png_data_url's np.flipud). Mutates and returns `rgba`.

    Samples each pixel's CENTER, not `linspace(lat_min, lat_max, h)`'s
    endpoint-inclusive points. MapLibre's image source treats `bbox` as
    the image's outer edges (row 0's top edge = lat_max, row h-1's bottom
    edge = lat_min), so pixel i's true center sits half a pixel in from
    those edges — using linspace's edge-inclusive samples instead offset
    the whole mask by ~half a pixel (visibly, since the mask has a sharp
    edge at India's coastline to reveal it, unlike the plain color data
    this same convention mismatch has always applied to unnoticed)."""
    from shapely.vectorized import contains

    india = _load_india_polygon()
    lon_min, lat_min, lon_max, lat_max = bbox
    h, w = rgba.shape[:2]
    lons = lon_min + (np.arange(w) + 0.5) / w * (lon_max - lon_min)
    lats = lat_min + (np.arange(h) + 0.5) / h * (lat_max - lat_min)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    inside = contains(india, lon_grid, lat_grid)
    rgba[..., 3] = np.where(inside, rgba[..., 3], 0)
    return rgba
