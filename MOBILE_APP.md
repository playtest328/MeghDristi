# MeghDrishti Mobile — Implementation Plan

A native mobile client for the existing MeghDrishti nowcasting system. This
document describes what to build and how, grounded in the actual backend
API and web dashboard as they exist today (`nowcast/api/main.py`,
`nowcast/dashboard/src/`) — no invented endpoints, no backend rewrite
required to ship v1.

## 1. Scope and non-goals

**In scope:** a phone-first app (Android first, iOS if there's an Apple
dev account) that shows the same real all-India hazard picture the web
dashboard shows, plus two things a phone can do that a browser tab can't:
push alerts when a real hazard appears near the user, and a usable map
experience with touch gestures instead of a mouse.

**Non-goal for v1:** re-implementing every web-dashboard feature 1:1.
Some of them (16-layer WMS overlay picker, freehand drag-to-select-area
with three independent lead-time sliders) are desktop-shaped UI that
doesn't translate to a phone screen well. Section 9 lists what's in v1,
v2, and deliberately dropped.

**No backend changes required to start.** `nowcast/api/main.py` already
has `CORSMiddleware(allow_origins=["*"])` and returns plain JSON /
base64-PNG-in-JSON — both fetch cleanly from React Native's `fetch()`.
The only backend-adjacent work is optional (Section 8: push notifications
need a new endpoint to register device tokens).

## 2. Stack decision

| Choice | Decision | Why |
|---|---|---|
| Framework | **React Native + Expo (SDK 52+, managed workflow, EAS Build)** | The web dashboard is already React + TypeScript. `types.ts`'s interfaces, `api.ts`'s fetch wrapper, and the `useNowcastData.ts` polling hooks port over almost unchanged — see Section 4. Expo also gets push notifications, background location, and native builds without touching Xcode/Android Studio config by hand. |
| Map | **`@maplibre/maplibre-react-native`** | Same MapLibre GL engine the web app uses (`maplibre-gl` JS). Same vector-tile basemap, same idea of sources/layers, same mental model — porting `MapProvider.tsx`'s source/layer setup is a translation, not a redesign. Do **not** reach for `react-native-maps` (Google/Apple Maps wrapper) — it can't consume the base64 PNG raster overlays `/raw-layers` and `/weather-layers` return the way MapLibre's `ImageSource` can. |
| Server state / polling | **TanStack Query (`@tanstack/react-query`)** | Replaces the hand-rolled `useInterval` + `FetchState<T>` pattern in `useNowcastData.ts` with `refetchInterval`, built-in retry/backoff, and cache-on-mount (so re-opening the app shows the last-known hazard picture instantly instead of a blank loading state — the app was reportedly minimized often, so this matters more on mobile than on a desktop browser tab). |
| Navigation | **React Navigation** (bottom tabs + native stack) | Standard, works inside Expo managed workflow without ejecting. |
| Local state | React Context for the handful of cross-screen values (`leadMinutes`, `model`, active region) — same shape as `App.tsx`'s `useState` today, no Redux needed for this app's size. |
| Styling | **NativeWind** (Tailwind-in-RN) or plain `StyleSheet` — either works; NativeWind if whoever builds this already knows Tailwind from the dashboard's CSS variables. |
| Push notifications | **Expo Notifications** (`expo-notifications`) + FCM (Android) / APNs (iOS) under the hood — Expo manages both from one API. |
| Background location (optional, v2) | **`expo-location`** with background permission, for "alert me about hazards near my current location, not just where I last opened the app." |

Why not Flutter: nothing in this stack needs it, and every fetch/parse
concern the mobile app has (endpoint shapes, hazard severity tiers,
lead-time semantics) is *already solved and typed* in the TypeScript
dashboard code. Rebuilding that in Dart doubles the type-contract surface
for zero benefit — React Native lets the mobile client and the web
dashboard share a mental model (and in a monorepo, literally share the
`types.ts` file, see Section 4.1).

## 3. Backend contract (as it exists today — reference while building)

All endpoints below are unauthenticated `GET` (one `POST`), CORS-open,
served from `nowcast/api/main.py`. Base URL in dev is
`http://<backend-host>:8000` (see Section 7 for the LAN/emulator wrinkle).

| Endpoint | Method | Key params | Returns | Poll? |
|---|---|---|---|---|
| `/health` | GET | — | `{status, loaded_from}` | on app foreground |
| `/regions` | GET | — | `{active, options: [{key, name, bbox}]}` (10 demo cities) | once |
| `/regions/{key}` | POST | path `key` | `{active, name, instant}` | on user action |
| `/hazards` | GET | `lead_time` (0–360 min) | `HazardsResponse` — **real, all-India** hail+lightning, GeoJSON `FeatureCollection` | 30s |
| `/hazards/region` | GET | `lead_time` | legacy per-region demo (all 4 hazard types, station-level) — **v2, not v1** | — |
| `/storm-eta` | GET | — | `{cells: StormCell[]}` | 30s |
| `/forecast` | GET | `model: pysteps\|dgmr` | rain-rate time series for the chart | on model change |
| `/nowcast-frame` | GET | `model`, `lead_time` | single forecast frame as base64 PNG | on lead_time change, if overlay enabled |
| `/raw-layers` | GET | — | radar (all-India, real) + satellite (region-scoped) as base64 PNG | 30s |
| `/weather-layers` | GET | `lead_time` | temperature/humidity/wind_speed/pressure/rainfall as base64 PNG | on lead_time/var change |
| `/wind-vectors` | GET | `lead_time` | `{points: [{lat, lon, wind_speed_ms, wind_dir_deg}]}` | on demand |
| `/region-forecast` | GET | `lat, lon, lead_time` | point sample (temp/humidity/wind/pressure/cloudburst) | on tap |
| `/area-forecast` | GET | `lon_min,lat_min,lon_max,lat_max, lead_time` | min/mean/max stats over a bbox | v2 (drag-select) |
| `/wms-proxy/bhuvan` | GET | passthrough | Bhuvan WMS image bytes (CORS workaround) | v2 (basemap layers) |
| `/history/timestamps` | GET | — | `{timestamps: string[]}` | on Replay screen open |
| `/history/hazards` | GET | `timestamp` | historical `HazardsResponse` | on scrub |

**Hazard shape** (`/hazards`, the v1 primary data source):
```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": { "type": "Point", "coordinates": [lon, lat] },
    "properties": {
      "hazards": [{ "type": "hail", "severity": "moderate", "reflectivity_dbz": 71.2, "source": "real" }],
      "lead_minutes": 0
    }
  }],
  "lead_time_minutes": 0,
  "note": "..."
}
```
`type` is `"hail" | "lightning"` here (downburst/cloudburst only exist in
the legacy `/hazards/region`, which is out of v1 scope). `severity` is
`"low" | "moderate" | "high"` — map to the same green/yellow/red as the
web app's `SEVERITY_COLOR` in `nowcast/dashboard/src/lib/colors.ts`.
`lead_time>0` **advects** existing detections along real ECMWF wind — it
is not a re-run forecast; surface this distinction in the UI copy (the
web app's `note` field already says so — just render it).

### 3.1 Known real vs. synthetic data (be accurate in the UI, don't badge it)

| Field/layer | Real when | Source |
|---|---|---|
| `/hazards` hail+lightning, all lead times | always (as of the latest backend change, no synthetic filler) | RainViewer reflectivity + Blitzortung strikes |
| `/raw-layers` radar | `USE_LIVE_RADAR=true` (default in prod) | RainViewer |
| `/raw-layers` satellite | `USE_LIVE_SATELLITE=true` | Copernicus Sentinel-3 SLSTR, region-scoped only |
| `/weather-layers` temp/humidity/wind/pressure | `USE_LIVE_ECMWF=true` | ECMWF Open Data HRES, all-India |
| `/weather-layers` rainfall | tied to radar cache | Marshall-Palmer Z-R off RainViewer reflectivity |
| `/forecast`, `/nowcast-frame` | always synthetic-input | pySTEPS/DGMR extrapolation, per-region demo box only |
| downburst, cloudburst (legacy `/hazards/region` only) | always synthetic-backed | no public Doppler-velocity or persisted-radar-sequence source exists |

Per the project's standing rule, don't render "real"/"synthetic" badges
anywhere in the UI — this table is for the team building the app, not
end-user copy.

## 4. Porting the frontend logic

### 4.1 Types — reuse, don't retype

`nowcast/dashboard/src/types.ts` already has exact interfaces for every
response shape above (`HazardsResponse`, `HazardFeature`, `Hazard`,
`WeatherLayer`, `RawLayer`, `NowcastFrame`, `WindPoint`, `Bbox`,
`RegionsResponse`, `StormEtaResponse`, etc.). If the mobile app lives in
the same repo (recommended — see Section 6), symlink or directly import
that file rather than hand-copying it; the two clients will drift
otherwise the first time the backend adds a field.

### 4.2 API client — translate almost verbatim

`nowcast/dashboard/src/api.ts` is a thin `fetch` wrapper around
`API_BASE`. Port it as-is, swapping `import.meta.env.VITE_API_BASE` for
Expo's env mechanism (`expo-constants` / `app.config.ts` `extra` field, or
`EXPO_PUBLIC_API_BASE` which Expo SDK 49+ inlines automatically — prefer
the latter, no extra config needed):

```ts
// mobile/src/api.ts
export const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(public status: number, public path: string) {
    super(`API ${status} on ${path}`);
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new ApiError(res.status, path);
  return res.json();
}
// ...same api.hazards(leadTime), api.stormEta(), etc. as the web client
```

### 4.3 Polling hooks — replace with React Query, keep the cadence

`useNowcastData.ts`'s `POLL_MS = 30_000` and the "re-fetch immediately
when `leadMinutes` changes" behavior (the bug that was fixed in
`useInterval.ts` by adding `callback` to its dependency array) map
directly onto React Query:

```ts
function useHazards(leadMinutes: number) {
  return useQuery({
    queryKey: ["hazards", leadMinutes],
    queryFn: () => api.hazards(leadMinutes),
    refetchInterval: 30_000,
    staleTime: 25_000,
  });
}
```

Changing `leadMinutes` changes the `queryKey`, so React Query fetches
immediately on change for free — the exact bug that needed a manual fix
on the web side doesn't exist here.

### 4.4 Map layers — MapLibre RN equivalents

| Web (`maplibre-gl` JS) | Native (`@maplibre/maplibre-react-native`) | Notes |
|---|---|---|
| `map.addSource({type: "geojson", ...})` | `<ShapeSource id="..." shape={geojson}>` | Direct port of the `HazardLayers.tsx` `stations` source (though that source is currently always-empty/dead code on web — don't port it, see 4.5). |
| Individual `maplibregl.Marker` HTML elements with CSS pulse animation (current hazard-marker implementation) | `<PointAnnotation>` per feature, custom child `View` | RN has no CSS keyframes. Use `react-native-reanimated`'s `withRepeat(withTiming(...))` on a `View`'s `transform: scale` + `opacity` to reproduce the pulsing ring — same visual language, different animation API. Budget one `Animated.View` per marker; with typically 10-40 hazard points this is fine, but if a future change makes the all-India grid denser, switch to a single `ShapeSource` + `CircleLayer` with a paint-property animation instead (cheaper, no per-marker native view). |
| `map.addLayer({type: "raster", ...})` fed a base64 PNG for radar/satellite/weather layers | `<ImageSource url={dataUri} coordinates={[...4 corners from bbox]}}><RasterLayer /></ImageSource>` | `RawLayer`/`WeatherLayer`'s `image` field is already a `data:image/png;base64,...` URI — MapLibre RN's `ImageSource` accepts that directly, no decode step needed. Compute the 4 corner coordinates from `bbox: [lonMin, latMin, lonMax, latMax]` the same way the web `SensorRasterLayers`/`WeatherRasterLayers` components already do. |
| `maplibregl.Popup` on marker click | `<Callout>` or a custom bottom-sheet (`@gorhom/bottom-sheet`) | A bottom sheet reads better on mobile than a small map popup — recommend it over a literal `Callout` port for the hazard-detail view (type, severity, dBZ). |
| Legend boxes (`.map-legends` CSS panels) | A collapsible bottom-sheet section or a small floating card, same content (dBZ gradient scale, severity dot key) | Keep it collapsed by default on phone screens — the web version was already fixed once for "covering too much" on a much bigger canvas; screen space is tighter here. |

### 4.5 What NOT to port

- The `stations` GeoJSON source/layer pair in `HazardLayers.tsx` — it's
  dead code on web already (no `/hazards` feature has carried a
  `station_id` since the all-India rewrite). Don't reintroduce it.
- `useInterval.ts` itself — React Query's `refetchInterval` replaces it
  entirely; don't hand-roll a native `setInterval` hook.
- The drag-to-select-area tool (`useAreaDrag`) as a literal port — see
  Section 9, replace with a simpler tap-and-hold-to-pick-a-point flow for
  v1, revisit a touch-friendly area-select gesture for v2 if there's
  demand.

## 5. Screen map (maps 1:1 onto the web dashboard's `activePanel` states)

| Screen | Web equivalent | v1/v2 |
|---|---|---|
| **Home** | `HomePage.tsx` — live hazard counts, CTA into the map | v1 |
| **Map** (default landing tab) | `App.tsx`'s map canvas + toolbar toggles (Radar/Lightning/Hazards/Satellite) + lead-time slider + play/pause | v1 |
| **Hazard detail sheet** | hazard-marker popup | v1 |
| **Hazards list** | `HazardsPage` (`activePanel: "hazards"`) — flat list + storm-ETA cells, good fit for a `FlatList` on mobile, arguably *better* here than on web | v1 |
| **Region picker** | region dropdown | v1 — but scoped to what it actually controls: the small per-region demo box (satellite/pySTEPS/DGMR), not the all-India hazard layer. Be honest about that distinction in the UI copy, same as the backend's own `/regions` note. |
| **Forecast** | `ForecastPage` — pySTEPS/DGMR rain-rate chart | v2 |
| **Replay** | `ReplayPage` — `/history/timestamps` + `/history/hazards` scrub | v2 |
| **Layers drawer** | model selector, weather-variable picker, WMS overlay toggles | v1 for model + weather-variable (core value); v2 for the full 16-layer WMS picker |
| **Settings** | n/a on web | v1 (new) — push-notification radius/severity threshold, region default, units (°C/°F, km/mi) |

## 6. Repo layout

Recommend adding the mobile app **inside this repo** (monorepo), not a
separate one — it needs zero backend changes to start and benefits
directly from sharing `types.ts` and eventually `api.ts`:

```
MeghDrishti/
  nowcast/                # existing FastAPI backend + web dashboard (unchanged)
  mobile/                 # new: Expo app
    app/                  # expo-router screens (or /src/screens if using React Navigation directly)
      (tabs)/
        index.tsx          # Map screen
        hazards.tsx
        forecast.tsx
        replay.tsx
        settings.tsx
      home.tsx             # pre-tab landing screen, mirrors HomePage.tsx
    src/
      api.ts               # ported from nowcast/dashboard/src/api.ts
      types.ts              # symlink or copy of nowcast/dashboard/src/types.ts
      hooks/
        useHazards.ts, useStormEta.ts, ...   # React Query versions of useNowcastData.ts
      map/
        HazardMarkers.tsx, RasterLayer.tsx, RegionPicker.tsx
      components/
      lib/
        colors.ts           # ported SEVERITY_COLOR
    app.config.ts
    package.json
    eas.json
```

## 7. Dev-environment wrinkle: LAN backend, not `localhost`

The web dashboard's `VITE_API_BASE` defaults to `http://localhost:8000`
because the browser and the backend share a machine. A phone (physical
device or emulator) does not share `localhost` with the dev machine:

- **Android emulator**: backend reachable at `http://10.0.2.2:8000`.
- **iOS simulator**: `http://localhost:8000` actually works (shares the
  host network namespace).
- **Physical device** (Expo Go or a dev build): needs the dev machine's
  LAN IP, e.g. `http://192.168.x.x:8000`, and both devices on the same
  Wi-Fi. Set via `EXPO_PUBLIC_API_BASE` in `mobile/.env`.
- Since the backend is plain HTTP (no TLS) in dev, **Android 9+ blocks
  cleartext traffic by default**. Expo's managed workflow needs
  `expo-build-properties` config to set `usesCleartextTraffic: true` for
  dev builds, or the app must point at an HTTPS-fronted backend (e.g. via
  ngrok/Cloudflare Tunnel) for anything beyond Expo Go on the same LAN.
  This is dev-only — production should put the FastAPI backend behind a
  real TLS-terminating reverse proxy regardless of mobile.

## 8. Mobile-specific value-add: push alerts (v1.5, needs one small backend addition)

The one piece of new backend work worth doing early because it's the
actual reason to have an app instead of a mobile-web bookmark:

1. **New endpoint** `POST /devices/register` — `{expo_push_token, lat, lon, radius_km, min_severity}`. Store in a small SQLite table or even a JSON file next to `nowcast/data/` (matches this project's existing file-based persistence style, no new DB dependency needed for a hackathon-scale deployment).
2. **New background job** alongside the existing `_india_hazards_loop()` in `main.py`: after each 180s hazard-cache refresh, diff the new hazard list against the previous cycle's, and for any *new* hazard at/above a registered device's `min_severity` within `radius_km` of its last known `lat/lon`, send an Expo push via `https://exp.host/--/api/v2/push/send` (Expo's push service takes a plain HTTPS POST with the token — no Firebase/APNs credential wrangling needed as long as the app stays in Expo's managed push flow).
3. **Client side**: `expo-notifications` to request permission + get the push token on first launch, `expo-location` (foreground, or background if the team wants "near me" to track live movement) to get `lat/lon`, `POST /devices/register` on token/location change, and a notification handler that deep-links into the Map screen centered on the alert's coordinates.

This is the single feature that makes "build an app for it" worth doing
over just making the existing dashboard responsive — treat it as the
headline feature, not an afterthought bolted on at the end.

## 9. Feature parity table (what's in, what's deferred, what's dropped)

| Web feature | Mobile v1 | Notes |
|---|---|---|
| All-India real hazard map, severity colors, pulsing markers | ✅ | core feature |
| Radar/Lightning/Hazards/Satellite toggles | ✅ | same toolbar, adapted to a bottom toolbar or FAB menu |
| Lead-time slider (0–6h) + play/pause | ✅ | |
| Region picker (10 demo cities) | ✅ | with the scope caveat from Section 5 |
| Hazard popup/detail | ✅ (as bottom sheet) | |
| Push notifications for nearby hazards | ✅ (v1.5) | new, mobile-only — see Section 8 |
| Weather-variable overlay (temp/humidity/wind/pressure/rainfall) | ✅ | |
| Forecast chart (pySTEPS/DGMR) | v2 | secondary to the live hazard view |
| Replay/history scrub | v2 | |
| Drag-to-select-area tool | **dropped for v1**, reconsidered v2 as tap-to-pick-point → later a pinch-to-select-region gesture if there's real demand | freehand rectangle drag doesn't translate to touch as cleanly as a tap; `/area-forecast` stays unused until then |
| Full 16-layer WMS/Bhuvan overlay picker | v2, reduced set | phone screens can't usefully host a 16-item layer picker; ship the model selector + weather-variable picker first, revisit which WMS layers actually get used on web before porting all 16 |
| DEM/topography basemap | v2 | |
| Station reports panel | **dropped** | backed by data that's already largely inert on the all-India view (see 4.5's `stations` source note) |

## 10. Build & release

- **Dev**: Expo Go for fast iteration on the Map + Hazards screens (no
  native module needs prevent this — MapLibre RN and
  expo-notifications/expo-location are all Expo-compatible).
- **Internal testing**: EAS Build → Android internal-testing APK, shared
  directly or via Play Console internal track. iOS TestFlight only if
  an Apple Developer account is available (not required for an
  Android-first SIH demo).
- **Production-shaped config**: `eas.json` profiles for `development`
  (cleartext HTTP, local backend), `preview` (staging backend, HTTPS),
  `production` (real backend URL baked in via `EXPO_PUBLIC_API_BASE` at
  build time — Expo inlines `EXPO_PUBLIC_*` vars at build, not runtime,
  so a separate build per environment is expected, not a bug).

## 11. Suggested build order

1. Expo app skeleton, React Navigation tabs, `api.ts`/`types.ts` ported, `EXPO_PUBLIC_API_BASE` wired up, `/health` check on launch.
2. Map screen: MapLibre basemap, `/hazards` via React Query, severity-colored pulsing markers, hazard bottom-sheet on tap.
3. Toolbar toggles (Radar/Lightning/Hazards/Satellite) + lead-time slider/play-pause, wired to `/raw-layers` and the advected `/hazards`.
4. Region picker (`/regions`, `/regions/{key}`).
5. Hazards list screen + storm-ETA (`/storm-eta`).
6. Push notifications end-to-end (Section 8) — register device, backend diff/send job, deep-link on tap.
7. Weather-variable overlay (`/weather-layers`) + Settings screen (severity threshold, radius, units).
8. Polish pass: offline/last-known-cache via React Query's persisted cache, loading/error states, app icon/splash from `logo.png`.
9. v2 backlog: Forecast chart, Replay, reduced WMS layer picker, DEM basemap.
