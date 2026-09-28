"""India's real coastline/border outline, for clipping the all-India
satellite/radar rasters (satellite_insat.py / hazard_india.py) to India's
actual shape instead of leaving them as a plain rectangular grid that
visibly spans into Pakistan, China, Myanmar, the ocean, etc.

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

The clip itself is a direct rasterization of that polygon onto the
image, via PIL, in the image's OWN final pixel grid — not a per-point
polygon-containment test sampled from a hand-derived lon/lat grid, which
is exactly what caused two rounds of visible misalignment here (an easy
category of off-by-one/half-pixel bug to introduce and hard to spot by
inspection). Drawing directly into pixel space the same way any other
image content would be drawn removes that whole class of bug — there's
no separate coordinate formula to get subtly wrong. Supersampled 4x and
downsampled with antialiasing for a smooth coastline instead of a
blocky one at the underlying data grid's native resolution (~22km/cell).

Done server-side (zeroing the PNG's own alpha channel) rather than as a
separate mask layer on the frontend: an earlier attempt at a frontend
mask painted over the basemap itself, not just the raster tint, hiding
Pakistan/China/Myanmar/etc. behind a solid box — clipping the data at
its source avoids that failure mode entirely.
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import shape

_OUTLINE_GEOJSON = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "configs", "geo", "india_outline.geojson"
)
_SUPERSAMPLE = 4

_india_polygon = None  # lazy-cached
_mask_cache = {}  # (w, h, bbox) -> (H, W) uint8 alpha array


def _load_india_polygon():
    global _india_polygon
    if _india_polygon is not None:
        return _india_polygon
    with open(_OUTLINE_GEOJSON, encoding="utf-8") as f:
        data = json.load(f)
    _india_polygon = shape(data["features"][0]["geometry"]).buffer(0)
    return _india_polygon


def _rasterize_mask(w, h, bbox):
    """India's outline drawn directly onto a (h, w) uint8 alpha mask (255 =
    inside India, 0 = outside), in the image's own final pixel grid —
    row 0 = top = lat_max, row h-1 = bottom = lat_min, matching exactly
    how bboxToCoords (useRasterLayer.ts) declares the image's corners to
    MapLibre. Supersampled and downsampled for an antialiased edge."""
    key = (w, h, bbox)
    cached = _mask_cache.get(key)
    if cached is not None:
        return cached

    india = _load_india_polygon()
    lon_min, lat_min, lon_max, lat_max = bbox
    sw, sh = w * _SUPERSAMPLE, h * _SUPERSAMPLE

    def to_px(lon, lat):
        px = (lon - lon_min) / (lon_max - lon_min) * sw
        py = (lat_max - lat) / (lat_max - lat_min) * sh
        return px, py

    img = Image.new("L", (sw, sh), 0)
    draw = ImageDraw.Draw(img)
    polygons = india.geoms if india.geom_type == "MultiPolygon" else [india]
    for poly in polygons:
        draw.polygon([to_px(lon, lat) for lon, lat in poly.exterior.coords], fill=255)
        for hole in poly.interiors:
            draw.polygon([to_px(lon, lat) for lon, lat in hole.coords], fill=0)

    img = img.resize((w, h), Image.LANCZOS)
    mask = np.array(img, dtype=np.uint8)
    _mask_cache[key] = mask
    return mask


def clip_alpha_to_india(rgba, bbox):
    """Multiply the alpha channel of an (H, W, 4) uint8 RGBA array — already
    flipped to final image orientation (row 0 = north, per
    _array_to_png_data_url's np.flipud) — by India's rasterized outline
    mask, so pixels outside India become transparent and the map's own
    basemap shows through them. `bbox` is (lon_min, lat_min, lon_max,
    lat_max), matching how the image will be placed on the map. Mutates
    and returns `rgba`."""
    h, w = rgba.shape[:2]
    mask = _rasterize_mask(w, h, tuple(bbox))
    rgba[..., 3] = (rgba[..., 3].astype(np.uint16) * mask.astype(np.uint16) // 255).astype(np.uint8)
    return rgba
