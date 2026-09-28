# India state/district/country boundaries

`india_states.geojson` (35 features) and `india_districts.geojson` (593
features) back the clickable, glowing State/District map layers
(`src/map/layers/AdminBoundaries.tsx`). `india_outline.geojson` backs
that same file's always-on, light-shade India-wide highlight — it's a
separate, independently-sourced country-level boundary, not derived from
the state file: that dataset's raw Rajasthan polygon has a real border
error near 72°E/28°N (extends into Pakistan), confirmed against the
unmodified upstream file. Doesn't affect the click-to-select feature
here (the error is a small border-area sliver, not a visible distortion
of the state's overall shape), but ruled that dataset out for the
country outline specifically, where the exact international border
matters and the whole point is a clean edge. `india_outline.geojson` is
sourced from [datasets/geo-countries](https://github.com/datasets/geo-countries)
(Natural Earth-derived), India's feature extracted and re-saved
standalone. Cross-checked against 12 cities on both sides of India's
borders before being adopted: Delhi, Mumbai, Kanyakumari, and Leh
(Ladakh) correctly inside; Islamabad, Lahore, Multan, Quetta,
Kathmandu, Dhaka, Colombo, and Yangon correctly outside. To regenerate:
```python
import json
from shapely.geometry import shape, mapping
d = json.load(open("countries.geojson", encoding="utf-8"))  # datasets/geo-countries
india = shape(next(f for f in d["features"] if f["properties"]["name"] == "India")["geometry"]).buffer(0)
json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "India"}, "geometry": mapping(india)}]},
          open("india_outline.geojson", "w", encoding="utf-8"), separators=(",", ":"))
```

The same file also lives at `nowcast/configs/geo/india_outline.geojson` on the
backend, used by `nowcast/processing/india_shape.py` to alpha-clip the
satellite/radar/weather rasters to India's shape server-side. That clip and
this frontend outline layer are complementary, not redundant: the server-side
clip is what keeps those rasters from showing as a rectangle past India's
border at all; this layer draws a crisp visual edge/light shade on top of
whatever's there. Removing either one is a regression — keep both in sync if
`india_outline.geojson` is ever regenerated.

**Source (states/districts):** [geohacker/india](https://github.com/geohacker/india)
(GADM-derived, public domain-equivalent open data), simplified from the
original ~23MB/~34MB files to ~1MB/~1.6MB via `mapshaper -simplify 6-8%
-clean` for web performance.

**Known limitations** (disclosed rather than hidden, same policy as the
rest of this project's real-vs-synthetic data):
- Pre-dates Telangana's 2014 split from Andhra Pradesh — Telangana's
  districts still render as part of Andhra Pradesh's shape.
- `Orissa`/`Uttaranchal` renamed to `Odisha`/`Uttarakhand` in the
  `name` property (geometry unchanged) to match current official names.
- One tiny island district (Kavaratti, Lakshadweep) was dropped by the
  simplification's sliver-polygon cleanup.
- District count (593) is lower than India's current ~773, reflecting
  this dataset's vintage rather than every present-day district split.

Good enough for a demo map at country/state scale; not a substitute for
an authoritative survey boundary if this is ever used for anything
beyond visualization.
