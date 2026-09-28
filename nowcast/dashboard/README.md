# MeghDrishti dashboard

React + TypeScript + Vite. Talks to the FastAPI backend (`nowcast/api/main.py`)
over HTTP — no server-side rendering, just a static SPA.

## Run

```bash
npm install
npm run dev
```

Opens at `http://localhost:5173`. Requires the backend running at
`http://localhost:8000` (see the repo root README) — override with a
`.env.local` setting `VITE_API_BASE` if it's running elsewhere (see
`.env.example`).

## Structure

- `src/api.ts`, `src/types.ts` — typed client + response shapes for every
  backend endpoint. Keep in sync with `nowcast/api/main.py` manually.
- `src/hooks/` — data-fetching hooks (polling for live data, lazy-load for
  on-demand layers like weather variables).
- `src/map/` — MapLibre integration. `MapProvider` owns the one `Map`
  instance via React context; `layers/*` are side-effect-only components
  that sync MapLibre layers to React state (heatmaps, raster overlays,
  station markers, the region-selection box, wind arrows).
- `src/components/` — presentational UI (cards, panels, the region trend
  chart).
- `src/lib/mosdacLayers.ts` — real ISRO/MOSDAC/Bhuvan WMS layer catalog (16
  overlays + 7 base layers), reverse-engineered from MOSDAC's own live
  CloudBurst DSS. See the file's header comment for provenance/verification
  notes before adding or changing any entry — every layer name here was
  confirmed against the live server, not guessed.

## Build

```bash
npm run build   # tsc -b && vite build, outputs to dist/
```
