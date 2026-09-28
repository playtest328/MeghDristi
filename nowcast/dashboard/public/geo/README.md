# India state/district boundaries

`india_states.geojson` (35 features) and `india_districts.geojson` (593
features) back the clickable, glowing State/District map layers
(`src/map/layers/AdminBoundaries.tsx`).

The satellite/radar "all India" rasters are clipped to India's actual
coastline server-side (`nowcast/processing/india_shape.py`, applied in
`api/main.py`'s `raw_layers()`), not here — see that module for how.

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
