# MeghDrishti Mobile (Kotlin/Native) — Implementation Plan

Alternative to `MOBILE_APP.md`'s React Native plan: a **native Android app**,
Kotlin + Jetpack Compose + the native MapLibre Android SDK, talking to the
same unmodified `nowcast/api/main.py` FastAPI backend. Pick this doc over
the React Native one if the team is more comfortable in Kotlin than
TypeScript, or only ever cares about Android (no iOS path) and wants the
smoothest possible map/animation performance with no JS bridge in the way.

This is a genuinely different codebase from the React Native plan, not a
variant of it — nothing here shares code with `nowcast/dashboard/src/`.
Every response type gets hand-written as a Kotlin data class, and the
hazard-marker/pulse/legend logic gets rebuilt in Compose from scratch. The
trade-off (spelled out when this was discussed): best native performance
and platform-API access, at the cost of zero code sharing with the web
dashboard and no iOS story unless someone later writes a second, separate
iOS app.

## 1. Stack decision

| Layer | Choice | Why |
|---|---|---|
| Language/UI | **Kotlin + Jetpack Compose** | Modern Android baseline; no XML layouts, no Fragments. |
| Map | **MapLibre Native Android SDK** (`org.maplibre.gl:android-sdk`) | Same open-source MapLibre engine the web dashboard and the React Native plan both use — just the direct native SDK, no bridge. Same mental model as `nowcast/dashboard/src/map/MapProvider.tsx`: a `Style` JSON with sources/layers, `Symbol`/`Circle` layers, `GeoJsonSource`. |
| Compose/Map interop | **`maplibre-compose`** (community Compose wrapper around the native SDK) if available/stable at build time; otherwise wrap `MapView` via `AndroidView` in Compose (standard, well-documented pattern) | Either works; `AndroidView`-wrapped `MapView` is the safer fallback if the Compose-native wrapper's API is still churning. |
| Networking | **Retrofit + Moshi** (or kotlinx.serialization) | Retrofit's declarative `@GET` interfaces map directly onto the endpoint table in Section 3 below; Moshi/kotlinx.serialization decode the JSON (including the base64-PNG-in-JSON fields — decoded with `android.graphics.BitmapFactory.decodeByteArray` after `Base64.decode`). |
| Async/reactive | **Kotlin Coroutines + Flow** | `Flow`-based polling (`flow { while(true) { emit(fetch()); delay(30_000) } }`) replaces the web app's `useInterval`/React Query polling pattern. |
| Background work | **WorkManager** (periodic hazard-check job) + **Firebase Cloud Messaging** (push delivery) | See Section 8 — same push-alert feature as the React Native plan, implemented with Android-native tooling instead of Expo Notifications. |
| Location | **Fused Location Provider** (Google Play services) | For "alert me about hazards near my current location." |
| Local persistence | **Room** (small local DB: last-known hazards for offline display, registered alert preferences) | Matches "show last-known state when offline" from the RN plan's Section 4.3 cache behavior, implemented with Android's own DB layer instead of a query-cache. |
| DI | **Hilt** | Standard for a Compose+Retrofit+Room app this size. |
| Animation (pulsing hazard marker) | **Compose `Animatable`/`InfiniteTransition`** on a Canvas-drawn ring, or a MapLibre `SymbolLayer` icon with a pre-rendered pulse sprite sheet if per-marker Compose overlays turn out to be too expensive at scale | Native equivalent of the web's CSS `@keyframes` pulse and the RN plan's Reanimated `withRepeat`. |

## 2. Why this instead of React Native

- No Metro/Hermes/JS-bridge layer between touch input and map rendering — relevant if the team wants the map to feel as snappy as possible with many animated markers.
- Direct access to every Android platform API (WorkManager, FCM, Fused Location, notification channels) without going through Expo's abstraction layer — useful if the push-alert feature (Section 8) needs to go beyond what Expo's push service supports.
- One language, one toolchain (Android Studio, Gradle) for the whole app — no Node/npm/Metro/Expo CLI dependency chain alongside it.
- Cost: **no code or type sharing with the web dashboard.** Every time `nowcast/api/main.py` changes a response shape, both `nowcast/dashboard/src/types.ts` *and* this app's Kotlin data classes need updating by hand, by two people who don't necessarily read the same diff. Budget for that drift risk explicitly — e.g. a lightweight OpenAPI/JSON-schema export from the FastAPI backend (FastAPI generates one for free at `/openapi.json`) that a codegen step turns into Kotlin data classes, so the two clients don't silently diverge.

## 3. Backend contract (same backend, same endpoints as the RN plan)

No backend changes needed to start — `nowcast/api/main.py` already has
`CORSMiddleware(allow_origins=["*"])`, though CORS is irrelevant for a
native client anyway (it's a browser-only mechanism). Base URL in dev:
`http://10.0.2.2:8000` from an Android emulator (see Section 7 for the
LAN-device wrinkle, identical to the RN plan's).

| Endpoint | Method | Key params | Returns | Poll? |
|---|---|---|---|---|
| `/health` | GET | — | `{status, loaded_from}` | on app foreground |
| `/regions` | GET | — | `{active, options: [{key, name, bbox}]}` (10 demo cities) | once |
| `/regions/{key}` | POST | path `key` | `{active, name, instant}` | on user action |
| `/hazards` | GET | `lead_time` (0–360 min) | GeoJSON `FeatureCollection` — **real, all-India** hail+lightning | 30s |
| `/hazards/region` | GET | `lead_time` | legacy per-region demo (4 hazard types) — v2 | — |
| `/storm-eta` | GET | — | `{cells: StormCell[]}` | 30s |
| `/forecast` | GET | `model: pysteps\|dgmr` | rain-rate time series | v2 |
| `/nowcast-frame` | GET | `model`, `lead_time` | single forecast frame, base64 PNG | v2 |
| `/raw-layers` | GET | — | radar (all-India, real) + satellite (region-scoped), base64 PNG each | 30s |
| `/weather-layers` | GET | `lead_time` | temp/humidity/wind/pressure/rainfall, base64 PNG each | on lead_time/var change |
| `/wind-vectors` | GET | `lead_time` | `{points: [{lat, lon, wind_speed_ms, wind_dir_deg}]}` | on demand |
| `/region-forecast` | GET | `lat, lon, lead_time` | point sample | on tap |
| `/area-forecast` | GET | `lon_min,lat_min,lon_max,lat_max, lead_time` | min/mean/max stats | v2 |
| `/wms-proxy/bhuvan` | GET | passthrough | image bytes | v2 |
| `/history/timestamps` | GET | — | `{timestamps: string[]}` | v2 (Replay) |
| `/history/hazards` | GET | `timestamp` | historical `FeatureCollection` | v2 (Replay) |

**`/hazards` response shape** (the v1 primary data source):
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
`type` is `"hail" | "lightning"` here only (downburst/cloudburst exist
only in the legacy `/hazards/region`, out of v1 scope, same as the RN
plan). `severity` is `"low" | "moderate" | "high"`, always real (no
synthetic filler as of the latest backend change). `lead_time>0`
**advects** existing detections along real ECMWF wind — not a re-run
forecast; surface the `note` field's explanation in the UI rather than
silently animating markers with no context.

### 3.1 Real vs. synthetic data — same table as the RN plan

| Field/layer | Real when | Source |
|---|---|---|
| `/hazards` hail+lightning, all lead times | always | RainViewer reflectivity + Blitzortung strikes |
| `/raw-layers` radar | `USE_LIVE_RADAR=true` | RainViewer |
| `/raw-layers` satellite | `USE_LIVE_SATELLITE=true` | Copernicus Sentinel-3 SLSTR, region-scoped only |
| `/weather-layers` temp/humidity/wind/pressure | `USE_LIVE_ECMWF=true` | ECMWF Open Data HRES, all-India |
| `/weather-layers` rainfall | tied to radar cache | Marshall-Palmer Z-R off RainViewer reflectivity |
| `/forecast`, `/nowcast-frame` | always synthetic-input | pySTEPS/DGMR, per-region demo box only |
| downburst, cloudburst (`/hazards/region` only) | always synthetic-backed | no public Doppler-velocity or persisted-radar-sequence source |

Don't render "real"/"synthetic" badges in the UI — same standing project rule as the RN plan.

## 4. Kotlin data model

Hand-written to mirror `nowcast/dashboard/src/types.ts` exactly (field
names/types must match what the backend actually sends — see Section 2's
drift-risk note about keeping these in sync):

```kotlin
enum class HazardType { @Json(name = "hail") HAIL, @Json(name = "lightning") LIGHTNING,
  @Json(name = "downburst") DOWNBURST, @Json(name = "cloudburst") CLOUDBURST }

enum class Severity { @Json(name = "low") LOW, @Json(name = "moderate") MODERATE, @Json(name = "high") HIGH }

data class Hazard(
  val type: HazardType,
  val severity: Severity,
  @Json(name = "reflectivity_dbz") val reflectivityDbz: Double? = null,
  @Json(name = "velocity_delta_ms") val velocityDeltaMs: Double? = null,
  @Json(name = "rainrate_mm_hr") val rainrateMmHr: Double? = null,
  val source: String? = null,
)

data class HazardGeometry(val type: String, val coordinates: List<Double>) // [lon, lat]

data class HazardFeatureProperties(
  @Json(name = "station_id") val stationId: String? = null,
  val name: String? = null,
  val hazards: List<Hazard>,
  @Json(name = "lead_minutes") val leadMinutes: Int? = null,
)

data class HazardFeature(val type: String, val geometry: HazardGeometry, val properties: HazardFeatureProperties)

data class HazardsResponse(
  val type: String,
  val features: List<HazardFeature>,
  @Json(name = "lead_time_minutes") val leadTimeMinutes: Int,
  val note: String? = null,
)

typealias Bbox = List<Double> // [lonMin, latMin, lonMax, latMax]

data class RegionOption(val key: String, val name: String, val bbox: Bbox)
data class RegionsResponse(val active: String, val options: List<RegionOption>)
data class HealthResponse(val status: String, @Json(name = "loaded_from") val loadedFrom: String?)
```

```kotlin
interface MeghDrishtiApi {
  @GET("/health") suspend fun health(): HealthResponse
  @GET("/regions") suspend fun regions(): RegionsResponse
  @POST("/regions/{key}") suspend fun setRegion(@Path("key") key: String): RegionsResponse
  @GET("/hazards") suspend fun hazards(@Query("lead_time") leadMinutes: Int = 0): HazardsResponse
  @GET("/raw-layers") suspend fun rawLayers(): RawLayersResponse
  @GET("/weather-layers") suspend fun weatherLayers(@Query("lead_time") leadMinutes: Int = 0): WeatherLayersResponse
  @GET("/region-forecast") suspend fun regionForecast(
    @Query("lat") lat: Double, @Query("lon") lon: Double, @Query("lead_time") leadMinutes: Int = 0,
  ): RegionForecast
}
```

## 5. Screen map (same feature set/scope as the RN plan's Section 5 and 9)

| Screen | v1/v2 |
|---|---|
| Home (live hazard counts, CTA into map) | v1 |
| Map (default landing screen) — MapLibre + severity-colored pulsing hazard markers, Radar/Lightning/Hazards/Satellite toggles, lead-time slider + play/pause | v1 |
| Hazard detail — Compose `ModalBottomSheet` | v1 |
| Hazards list — `LazyColumn` | v1 |
| Region picker | v1, same scope caveat as the RN plan (only moves the small per-region demo box, not the all-India hazard layer) |
| Settings (push radius/severity threshold, region default, units) | v1 |
| Weather-variable overlay | v1 |
| Push alerts for nearby hazards | v1.5 — see Section 8 |
| Forecast chart, Replay/history scrub, full WMS layer picker, DEM basemap | v2, same reasoning as the RN plan (freehand drag-select and a 16-item layer picker don't fit a phone screen cleanly; ship the core live-hazard view first) |

## 6. Project layout

```
MeghDrishti/
  nowcast/                     # existing backend + web dashboard (unchanged)
  mobile-kotlin/                # new: native Android app (separate Gradle project)
    app/
      src/main/java/com/meghdrishti/
        MainActivity.kt
        data/
          api/MeghDrishtiApi.kt
          model/                # Hazard, HazardsResponse, etc. (Section 4)
          repository/HazardRepository.kt   # Retrofit call + Room cache + Flow polling
        ui/
          map/MapScreen.kt, HazardMarker.kt, HazardSheet.kt
          home/HomeScreen.kt
          hazards/HazardsListScreen.kt
          settings/SettingsScreen.kt
        push/
          PushTokenSync.kt, HazardCheckWorker.kt, HazardMessagingService.kt
        di/AppModule.kt          # Hilt
      build.gradle.kts
    build.gradle.kts
    settings.gradle.kts
```

Keep `mobile-kotlin/` as a sibling to `mobile/` if the React Native
prototype from earlier in this project stays around for comparison —
they're independent apps, no shared build tooling.

## 7. Dev-environment wrinkle: LAN backend, not `localhost`

Same underlying issue as the RN plan, Android-only details:

- **Android emulator**: backend reachable at `http://10.0.2.2:8000`.
- **Physical device**: dev machine's LAN IP (e.g. `http://192.168.x.x:8000`), same Wi-Fi.
- **Cleartext HTTP**: Android 9+ (`targetSdkVersion 28+`) blocks plaintext HTTP by default. Add a debug-only network security config:
  ```xml
  <!-- app/src/debug/res/xml/network_security_config.xml -->
  <network-security-config>
    <domain-config cleartextTrafficPermitted="true">
      <domain includeSubdomains="true">10.0.2.2</domain>
      <domain includeSubdomains="true">192.168.0.0/16</domain>
    </domain-config>
  </network-security-config>
  ```
  wired via `android:networkSecurityConfig` in the debug manifest only —
  never ship this in a release build; production should sit behind a
  real TLS-terminating reverse proxy regardless of mobile.
- Base URL as a Gradle `buildConfigField` per build type (`debug` → `http://10.0.2.2:8000`, `release` → the real backend URL), read via `BuildConfig.API_BASE_URL` — same idea as the RN plan's `EXPO_PUBLIC_API_BASE`, just resolved at compile time via Gradle instead of Expo's env-var inlining.

## 8. Push alerts (v1.5) — same feature, native implementation

The headline feature from the RN plan, reimplemented with Android-native tooling:

1. **Backend addition** (shared with the RN plan, not duplicated per-client): `POST /devices/register` on `nowcast/api/main.py` — `{fcm_token, lat, lon, radius_km, min_severity}`, persisted alongside `nowcast/data/` the same way the rest of this project persists state (a JSON file, no new DB dependency for a hackathon-scale deployment).
2. **Backend background job**: after each 180s `_india_hazards_loop()` refresh, diff new hazards against the previous cycle, and for matches against a registered device's radius/severity, call Firebase Cloud Messaging's HTTP v1 API (needs a service-account key on the backend — this is the one piece of backend config specific to the Kotlin app's choice of FCM over the RN plan's Expo push service).
3. **Client**: request notification permission (Android 13+ runtime permission), get an FCM token via `FirebaseMessaging.getInstance().token`, get last-known location via Fused Location Provider, `POST /devices/register` on token/location change (a `WorkManager` periodic job, not just on launch, so a moved device stays accurate), and a `FirebaseMessagingService` subclass that builds a notification + deep-links into `MapScreen` centered on the alert's coordinates via an explicit `Intent` extra.

## 9. Build & release

- **Dev**: run directly from Android Studio or `./gradlew installDebug` onto an emulator/device — no bundler/dev-server step at all (unlike the RN plan's Metro), since this is a fully native build every time.
- **Internal testing**: `./gradlew assembleRelease` (signed with a debug/internal keystore) → shared APK, or Play Console internal testing track.
- **Production config**: Gradle product flavors or build-config fields for `debug`/`staging`/`release` API base URLs, same three-tier idea as the RN plan's `eas.json` profiles, just expressed as Gradle build variants instead.

## 10. Suggested build order

1. Project skeleton: Compose + Hilt + Retrofit/Moshi wired up, `MeghDrishtiApi.health()` called on launch, debug network-security config in place.
2. Map screen: MapLibre Android SDK (same Esri dark-canvas raster style as the web dashboard — no API key needed), `/hazards` polled via a `Flow` every 30s, severity-colored pulsing markers (Compose `Canvas` overlay or `SymbolLayer` + sprite), bottom sheet on tap.
3. Toolbar toggles (Radar/Lightning/Hazards/Satellite) + lead-time slider/play-pause, wired to `/raw-layers` and the advected `/hazards`.
4. Region picker (`/regions`, `/regions/{key}`).
5. Hazards list screen + storm-ETA (`/storm-eta`).
6. Push alerts end-to-end (Section 8) — backend `/devices/register` + diff/FCM-send job, `FirebaseMessagingService`, deep-link on tap.
7. Weather-variable overlay (`/weather-layers`) + Settings screen.
8. Polish: Room-backed offline/last-known-hazards cache, loading/error states, app icon/splash from `logo.png`.
9. v2 backlog: Forecast chart, Replay, reduced WMS layer picker, DEM basemap — same deferral list as the RN plan.
