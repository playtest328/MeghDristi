# India geo assets

`india_states.geojson` (35 features) and `india_districts.geojson` (593
features) back the clickable, glowing State/District map layers
(`src/map/layers/AdminBoundaries.tsx`).

`india_mask.geojson` is derived from `india_states.geojson`: union all 35
state polygons into one India outline (`shapely.ops.unary_union`), then
subtract that from INDIA_BBOX's own rectangle (`settings.INDIA_BBOX` /
`nowcast/configs/settings.py`) — the result is "everything in that
rectangle that ISN'T India," used by `SensorRasterLayers.tsx` to paint
over the satellite/radar rasters' rectangular edges outside India's
coastline (see that file's docstring). Regenerate it if `india_states.geojson`
or `INDIA_BBOX` ever change:
```python
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union
import json
data = json.load(open("india_states.geojson", encoding="utf-8"))
india = unary_union([shape(f["geometry"]).buffer(0) for f in data["features"]])
mask = box(68.0, 6.5, 97.5, 37.0).difference(india)  # INDIA_BBOX
json.dump({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": mapping(mask)}]},
          open("india_mask.geojson", "w", encoding="utf-8"), separators=(",", ":"))
```

**Source:** [geohacker/india](https://github.com/geohacker/india)
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
