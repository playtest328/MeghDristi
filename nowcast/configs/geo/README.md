# India outline (backend)

`india_outline.geojson` is India's country-level boundary (mainland +
islands, MultiPolygon), used by `nowcast/processing/india_shape.py` to
clip the all-India satellite/radar/weather rasters to India's actual
shape instead of leaving them as a rectangle over `settings.INDIA_BBOX`.

**Source:** [datasets/geo-countries](https://github.com/datasets/geo-countries)
(Natural Earth-derived), India's feature extracted and re-saved standalone.
Chosen over unioning the per-state polygons in
`nowcast/dashboard/public/geo/india_states.geojson` (used elsewhere for
the clickable State/District layers) after that approach produced a
visibly wrong result: the *upstream, unmodified* Rajasthan polygon in
that dataset extends into Pakistan near 72°E/28°N — a real data error in
that specific open dataset, not something introduced by any processing
in this repo. A dedicated country-level outline sidesteps both that and
the general fragility of unioning many independently-simplified state
polygons (shared borders drift apart after separate simplification,
producing self-intersections).

Cross-checked against 12 cities before being adopted: Delhi, Mumbai,
Kanyakumari, and Leh (Ladakh) correctly inside; Islamabad, Lahore,
Multan, Quetta, Kathmandu, Dhaka, Colombo, and Yangon correctly outside.

To regenerate (e.g. if a more current/higher-resolution source is ever
wanted):
```python
import json
from shapely.geometry import shape, mapping
d = json.load(open("countries.geojson", encoding="utf-8"))  # datasets/geo-countries
india = shape(next(f for f in d["features"] if f["properties"]["name"] == "India")["geometry"]).buffer(0)
json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "India"}, "geometry": mapping(india)}]},
          open("india_outline.geojson", "w", encoding="utf-8"), separators=(",", ":"))
```
