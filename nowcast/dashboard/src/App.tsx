import { useEffect, useRef, useState } from "react";
import { MapProvider, MapCanvas, useMeghMap } from "./map/MapProvider";
import { ReferenceLabels } from "./map/layers/ReferenceLabels";
import { HazardLayers } from "./map/layers/HazardLayers";
import { SensorRasterLayers } from "./map/layers/SensorRasterLayers";
import { WeatherRasterLayers } from "./map/layers/WeatherRasterLayers";
import { WindArrows } from "./map/layers/WindArrows";
import { WindParticles } from "./map/layers/WindParticles";
import { AdminBoundaries } from "./map/layers/AdminBoundaries";
import { ModelFrameLayer } from "./map/layers/ModelFrameLayer";
import { RegionBox } from "./map/layers/RegionBox";
import { AreaBox } from "./map/layers/AreaBox";
import { WmsBaseLayer } from "./map/layers/WmsBaseLayer";
import { WmsOverlayLayers } from "./map/layers/WmsOverlayLayers";
import { useRegionClick } from "./map/useRegionClick";
import { useAreaDrag } from "./map/useAreaDrag";

import { TopBar } from "./components/TopBar";
import { Banner } from "./components/Banner";
import { LeftNavigation, type ActivePanel } from "./components/LeftNavigation";
import { HazardsPage } from "./components/HazardsPage";
import { ForecastPage } from "./components/ForecastPage";
import { ReplayPage } from "./components/ReplayPage";
import { LeftSidebar } from "./components/LeftSidebar";
import { RightSidebar } from "./components/RightSidebar";
import { BottomPanel } from "./components/BottomPanel";
import { LayersDrawer } from "./components/LayersDrawer";
import { RegionFloating } from "./components/RegionFloating";
import { AreaFloating, type AreaVarId } from "./components/AreaFloating";
import { VAR_COLOR_STOPS, VAR_RANGE, lerpColor } from "./lib/colors";
import { Play, Pause, Frame } from "lucide-react";

import { api, API_BASE, ApiError } from "./api";
import {
  useHazards,
  useStormEta,
  useRawLayers,
  useForecastSummary,
  useNowcastFrame,
  useWeatherLayers,
  useWindVectors,
  useWindParticleField,
} from "./hooks/useNowcastData";
import type { ModelId, RegionForecast, HazardsResponse, RawLayer, WeatherLayer, WindPoint, NowcastFrame, AreaForecast, Bbox } from "./types";

type VarId = "none" | "temperature" | "humidity" | "wind_speed" | "pressure" | "rainfall" | "composite_risk";

const LEAD_MAX = { pysteps: 360, dgmr: 90, smaat: 60 } as const;

function Dashboard() {
  const { map, tileError } = useMeghMap();

  const [leadMinutes, setLeadMinutes] = useState(0);
  const [model, setModel] = useState<ModelId>("pysteps");
  // Satellite and the pySTEPS/DGMR model-frame overlay are still tied to
  // the small per-region demo bbox (no real all-India single-request
  // satellite source exists, and the model frame is inherently a
  // per-region forecast) — defaulting them off keeps the main view free of
  // any Pune-sized (or whichever city's) box unless someone explicitly
  // opts into the per-region demo layers via their toggles.
  const [satelliteVisible, setSatelliteVisible] = useState(false);
  const [radarVisible, setRadarVisible] = useState(true);
  const [heatmapsVisible, setHeatmapsVisible] = useState(true);
  const [lightningVisible, setLightningVisible] = useState(true);
  const [modelFrameVisible, setModelFrameVisible] = useState(false);
  const [windAnimationVisible, setWindAnimationVisible] = useState(false);
  const [statesVisible, setStatesVisible] = useState(false);
  const [districtsVisible, setDistrictsVisible] = useState(false);
  const [indiaVisible, setIndiaVisible] = useState(true);
  const [activeVar, setActiveVar] = useState<VarId>("none");
  const [baseMapId, setBaseMapId] = useState("none");
  const [activeOverlayIds, setActiveOverlayIds] = useState<Set<string>>(new Set());
  const [region, setRegion] = useState<{ lat: number; lon: number } | null>(null);
  const [regionLeadMinutes, setRegionLeadMinutes] = useState(0);
  const [regionReading, setRegionReading] = useState<RegionForecast | null>(null);
  const [areaSelectMode, setAreaSelectMode] = useState(false);
  const [drawingArea, setDrawingArea] = useState<Bbox | null>(null);
  const [area, setArea] = useState<Bbox | null>(null);
  const [areaLeadMinutes, setAreaLeadMinutes] = useState(0);
  const [areaReading, setAreaReading] = useState<AreaForecast | null>(null);
  const [areaError, setAreaError] = useState<string | null>(null);
  const [areaLoading, setAreaLoading] = useState(false);
  const [areaVar, setAreaVar] = useState<AreaVarId>("none");
  const [activePanel, setActivePanel] = useState<ActivePanel>("none");
  const [isPlaying, setIsPlaying] = useState(false);
  const [apiUnreachable, setApiUnreachable] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  // Below the ~900px breakpoint, LeftSidebar/RightSidebar become off-canvas
  // drawers (see index.css) instead of permanently-docked 320px columns —
  // these track whether each is currently slid open. Irrelevant above the
  // breakpoint (CSS keeps them visibly docked there regardless of this).
  const [mobileLeftOpen, setMobileLeftOpen] = useState(false);
  const [mobileRightOpen, setMobileRightOpen] = useState(false);

  const hazards = useHazards(leadMinutes);
  const stormEta = useStormEta();
  const rawLayers = useRawLayers();
  const forecastSummary = useForecastSummary(model);
  const nowcastFrame = useNowcastFrame(model, leadMinutes, modelFrameVisible);
  // Rainfall is now a normal /weather-layers entry (real, all-India, from
  // live radar via Z-R — see main.py) like temp/humidity/wind/pressure,
  // not a special case reusing the per-region pySTEPS frame — that used to
  // make "Rainfall" the one weather variable still secretly scoped to
  // whichever demo city was active.
  const weatherLayers = useWeatherLayers(leadMinutes, activeVar !== "none");
  const windVectors = useWindVectors(leadMinutes, activeVar === "wind_speed");
  const windParticleField = useWindParticleField(leadMinutes, windAnimationVisible);
  const displayedWeatherLayers = weatherLayers.data?.layers ?? [];

  useEffect(() => {
    setApiUnreachable(Boolean(hazards.error && hazards.error.includes("Failed to fetch")));
    if (!hazards.error) setLastUpdated(new Date());
  }, [hazards.error, hazards.data]);

  // Default camera shows all of India, matching the default hazard/radar
  // view (both real, all-India — see hazard_india.py) — not whichever demo
  // city happens to be selected in the region picker, which only matters
  // for the separate Forecast/Replay pySTEPS/DGMR pages now. Runs once the
  // map's ready and doesn't fight the user's own panning/zooming afterward.
  useEffect(() => {
    if (!map) return;
    map.fitBounds(
      [
        [68.0, 6.5],
        [97.5, 37.0],
      ],
      { padding: 40, duration: 0 }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // reset to a clean lead-time position whenever the model changes, since
  // DGMR's horizon (90min) is shorter than pySTEPS' (6h)
  useEffect(() => {
    setLeadMinutes(0);
  }, [model]);


  // simple auto-play: advance the lead-time slider one step per second
  const playRef = useRef({ model, leadMinutes });
  playRef.current = { model, leadMinutes };
  useEffect(() => {
    if (!isPlaying) return;
    const step = model === "dgmr" ? 15 : model === "smaat" ? 10 : 60;
    const id = setInterval(() => {
      const { model: m, leadMinutes: cur } = playRef.current;
      const max = LEAD_MAX[m];
      setLeadMinutes(cur + step > max ? 0 : cur + step);
    }, 1000);
    return () => clearInterval(id);
  }, [isPlaying, model]);

  useRegionClick(!areaSelectMode, (lat, lon) => selectRegion(lat, lon));
  useAreaDrag(areaSelectMode, setDrawingArea, (bbox) => selectArea(bbox));

  async function selectRegion(lat: number, lon: number) {
    setArea(null);
    setRegion({ lat, lon });
    setRegionLeadMinutes(0);
    setRegionReading(null);
    map?.flyTo({ center: [lon, lat], zoom: Math.min((map.getZoom() ?? 10) + 1.6, 13), duration: 800 });
    try {
      const reading = await api.regionForecast(lat, lon, 0);
      setRegionReading(reading);
    } catch {
      // region panel just stays in its loading state; not worth a banner for this
    }
  }

  async function onRegionLeadChange(m: number) {
    setRegionLeadMinutes(m);
    if (!region) return;
    try {
      const reading = await api.regionForecast(region.lat, region.lon, m);
      setRegionReading(reading);
    } catch {
      /* keep last known reading on transient failure */
    }
  }

  async function selectArea(bbox: Bbox) {
    setRegion(null);
    setAreaSelectMode(false);
    setArea(bbox);
    setAreaLeadMinutes(0);
    setAreaReading(null);
    setAreaError(null);
    setAreaLoading(true);
    const [lonMin, latMin, lonMax, latMax] = bbox;
    map?.fitBounds(
      [
        [lonMin, latMin],
        [lonMax, latMax],
      ],
      { padding: 80, duration: 800 }
    );
    try {
      // areaLoading keeps the panel from looking frozen while this resolves.
      const reading = await api.areaForecast(bbox, 0);
      setAreaReading(reading);
    } catch (e) {
      console.error("[area-forecast] fetch failed", e);
      setAreaError(e instanceof ApiError ? `API ${e.status} on ${e.path}` : "request failed — see console");
    } finally {
      setAreaLoading(false);
    }
  }

  async function onAreaLeadChange(m: number) {
    setAreaLeadMinutes(m);
    if (!area) return;
    setAreaLoading(true);
    try {
      const reading = await api.areaForecast(area, m);
      setAreaReading(reading);
      setAreaError(null);
    } catch (e) {
      console.error("[area-forecast] fetch failed", e);
      setAreaError(e instanceof ApiError ? `API ${e.status} on ${e.path}` : "request failed — see console");
    } finally {
      setAreaLoading(false);
    }
  }

  function toggleOverlay(id: string) {
    setActiveOverlayIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const activeMeta = activeVar !== "none" ? displayedWeatherLayers.find((l) => l.id === activeVar) ?? null : null;

  // Colors the selected-area box by whichever variable the area panel picked
  // (temp/humidity/wind/pressure), using its mean over the area — same
  // palette/range as the main weather overlay's legend — so "no hazards
  // here" reads as "here's the actual weather", not an empty rectangle.
  const AREA_VAR_FIELD = {
    temperature: "temperature_c",
    humidity: "humidity_pct",
    wind_speed: "wind_speed_ms",
    pressure: "pressure_hpa",
  } as const;
  let areaFillColor: string | undefined;
  let areaFillOpacity: number | undefined;
  if (areaVar !== "none" && areaReading) {
    const stat = areaReading[AREA_VAR_FIELD[areaVar]];
    const [vmin, vmax] = VAR_RANGE[areaVar];
    const t = (stat.mean - vmin) / (vmax - vmin);
    areaFillColor = lerpColor(VAR_COLOR_STOPS[areaVar], t);
    areaFillOpacity = 0.45;
  }
  const dgmrUnavailable = forecastSummary.data?.available === false;
  const apiOk = !apiUnreachable && !hazards.error;
  const banner =
    tileError ?? (apiUnreachable ? `Can't reach the backend at ${API_BASE} — start it with: uvicorn nowcast.api.main:app --port 8000` : null);

  const leadLabel = leadMinutes === 0 ? "Now" : `+${Math.floor(leadMinutes / 60)}h ${leadMinutes % 60}m`;

  return (
    <div className="app-shell">
      <LeftNavigation active={activePanel} onSelect={setActivePanel} />

      <div className="app-content">
        <TopBar
          apiOk={apiOk}
          lastUpdated={lastUpdated}
          onToggleLeftSidebar={() => setMobileLeftOpen((v) => !v)}
          onToggleRightSidebar={() => setMobileRightOpen((v) => !v)}
        />

        <div className="main-body">
          {(mobileLeftOpen || mobileRightOpen) && (
            <div
              className="sidebar-backdrop"
              onClick={() => {
                setMobileLeftOpen(false);
                setMobileRightOpen(false);
              }}
            />
          )}
          {activePanel === "hazards" && (
            <HazardsPage
              hazards={hazards.data ?? null}
              stormCells={stormEta.data?.cells ?? null}
              onClose={() => setActivePanel("none")}
              onSelectLocation={(lat, lon) => {
                setActivePanel("none");
                selectRegion(lat, lon);
              }}
            />
          )}
          {activePanel === "forecast" && <ForecastPage onClose={() => setActivePanel("none")} />}
          {activePanel === "replay" && <ReplayPage onClose={() => setActivePanel("none")} />}

          <LeftSidebar
            hazards={hazards.data ?? null}
            model={model}
            apiOk={apiOk}
            lastUpdated={lastUpdated}
            mobileOpen={mobileLeftOpen}
            onMobileClose={() => setMobileLeftOpen(false)}
          />

          <div className="map-area">
            <MapCanvas />
            <MapLayers
              hazards={hazards.data ?? null}
              heatmapsVisible={heatmapsVisible}
              lightningVisible={lightningVisible}
              rawLayers={rawLayers.data?.layers ?? null}
              satelliteVisible={satelliteVisible}
              radarVisible={radarVisible}
              weatherLayers={displayedWeatherLayers}
              activeVar={activeVar}
              windPoints={windVectors.data?.points ?? null}
              windParticlePoints={windParticleField.data?.points ?? null}
              windAnimationVisible={windAnimationVisible}
              statesVisible={statesVisible}
              districtsVisible={districtsVisible}
              indiaVisible={indiaVisible}
              modelFrame={nowcastFrame.data ?? null}
              modelFrameVisible={modelFrameVisible}
              region={region}
              drawingArea={drawingArea}
              area={area}
              areaFillColor={areaFillColor}
              areaFillOpacity={areaFillOpacity}
              baseMapId={baseMapId}
              activeOverlayIds={activeOverlayIds}
            />

            {activePanel === "layers" && (
              <LayersDrawer
                onClose={() => setActivePanel("none")}
                model={model}
                onModelChange={setModel}
                dgmrUnavailable={dgmrUnavailable}
                modelFrameVisible={modelFrameVisible}
                onModelFrameVisibleChange={setModelFrameVisible}
                baseMapId={baseMapId}
                onBaseMapChange={setBaseMapId}
                activeOverlayIds={activeOverlayIds}
                onOverlayToggle={toggleOverlay}
                activeVar={activeVar}
                onVarChange={setActiveVar}
                activeVarMeta={activeMeta}
                weatherSource={weatherLayers.data?.source ?? null}
              />
            )}

            <div className="map-controls-top">
              <div className="layer-toggles">
                <button className={`layer-btn ${radarVisible ? "active" : ""}`} onClick={() => setRadarVisible((v) => !v)}>
                  <div className={`status-dot ${radarVisible ? "ok" : ""}`} /> Radar
                </button>
                <button className={`layer-btn ${satelliteVisible ? "active" : ""}`} onClick={() => setSatelliteVisible((v) => !v)}>
                  <div className={`status-dot ${satelliteVisible ? "ok" : ""}`} /> Satellite (IR)
                </button>
                <button className={`layer-btn ${lightningVisible ? "active" : ""}`} onClick={() => setLightningVisible((v) => !v)}>
                  <div className={`status-dot ${lightningVisible ? "ok" : ""}`} /> Lightning
                </button>
                <button className={`layer-btn ${heatmapsVisible ? "active" : ""}`} onClick={() => setHeatmapsVisible((v) => !v)}>
                  <div className={`status-dot ${heatmapsVisible ? "ok" : ""}`} /> Hazards
                </button>
                <button
                  className={`layer-btn ${windAnimationVisible ? "active" : ""}`}
                  onClick={() => setWindAnimationVisible((v) => !v)}
                  title="Animated flowing wind particles across India"
                >
                  <div className={`status-dot ${windAnimationVisible ? "ok" : ""}`} /> Wind
                </button>
                <button
                  className={`layer-btn ${indiaVisible ? "active" : ""}`}
                  onClick={() => setIndiaVisible((v) => !v)}
                  title="Highlight all of India with a light shade"
                >
                  <div className={`status-dot ${indiaVisible ? "ok" : ""}`} /> India
                </button>
                <button
                  className={`layer-btn ${statesVisible ? "active" : ""}`}
                  onClick={() => setStatesVisible((v) => !v)}
                  title="Click a state to select it and highlight it with a glow"
                >
                  <div className={`status-dot ${statesVisible ? "ok" : ""}`} /> States
                </button>
                <button
                  className={`layer-btn ${districtsVisible ? "active" : ""}`}
                  onClick={() => setDistrictsVisible((v) => !v)}
                  title="Click a district to select it and highlight it with a glow"
                >
                  <div className={`status-dot ${districtsVisible ? "ok" : ""}`} /> Districts
                </button>
                <button
                  className={`layer-btn ${baseMapId === "dem" ? "active" : ""}`}
                  onClick={() => setBaseMapId((v) => (v === "dem" ? "none" : "dem"))}
                >
                  <div className={`status-dot ${baseMapId === "dem" ? "ok" : ""}`} /> Topography
                </button>
                <button
                  className={`layer-btn ${areaSelectMode ? "active" : ""}`}
                  onClick={() => {
                    setRegion(null);
                    setArea(null);
                    setAreaSelectMode((v) => !v);
                  }}
                  title="Drag on the map to select an area and see its current + forecast stats"
                >
                  <Frame size={12} /> {areaSelectMode ? "Drag to select…" : "Select area"}
                </button>
              </div>

              <div className="time-scrubber">
                <span style={{ fontSize: "11px", fontWeight: 600, color: "#fff" }}>{leadLabel}</span>
                <div
                  className="icon-btn"
                  style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--accent)", color: "#000", border: "none", cursor: "pointer" }}
                  onClick={() => setIsPlaying((v) => !v)}
                >
                  {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                </div>
                <input
                  type="range"
                  min={0}
                  max={LEAD_MAX[model]}
                  step={model === "dgmr" ? 5 : 10}
                  value={Math.min(leadMinutes, LEAD_MAX[model])}
                  onChange={(e) => setLeadMinutes(parseInt(e.target.value, 10))}
                  style={{ width: 100 }}
                />
                <span style={{ fontSize: "11px", fontWeight: 600, color: "#fff" }}>{model === "dgmr" ? "90m" : model === "smaat" ? "60m" : "6h"}</span>
              </div>
            </div>

            <div className="map-legends">
              <div className="panel-section" style={{ padding: "10px 12px", background: "var(--panel)", borderRadius: "10px", border: "1px solid var(--panel-border)" }}>
                <div style={{ fontSize: "10px", color: "var(--text-dim)", marginBottom: "6px", fontWeight: 600 }}>Radar Reflectivity (dBZ)</div>
                <div
                  style={{
                    height: "6px",
                    background: "linear-gradient(90deg, #102e85, #1461c2, #1bb55e, #c0da27, #f7981b, #eb1b1e, #d715d0)",
                    borderRadius: "3px",
                  }}
                />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "8px", marginTop: "3px", color: "var(--text-faint)", fontFamily: "'JetBrains Mono', monospace" }}>
                  <span>10</span>
                  <span>30</span>
                  <span>50</span>
                  <span>70</span>
                </div>
              </div>

              <div className="panel-section" style={{ padding: "10px 12px", background: "var(--panel)", borderRadius: "10px", border: "1px solid var(--panel-border)" }}>
                <div style={{ fontSize: "10px", color: "var(--text-dim)", marginBottom: "6px", fontWeight: 600 }}>Hazard Severity</div>
                <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "9.5px", fontWeight: 500 }}>
                    <div style={{ width: 8, height: 8, background: "#ef4444", border: "1px solid #fff", borderRadius: "50%", flex: "none" }} /> High
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "9.5px", fontWeight: 500 }}>
                    <div style={{ width: 8, height: 8, background: "#f0b429", border: "1px solid #fff", borderRadius: "50%", flex: "none" }} /> Moderate
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "9.5px", fontWeight: 500 }}>
                    <div style={{ width: 8, height: 8, background: "#22c55e", border: "1px solid #fff", borderRadius: "50%", flex: "none" }} /> Low
                  </div>
                </div>
                <div style={{ fontSize: 8.5, color: "var(--text-faint)", marginTop: 6, lineHeight: 1.3 }}>
                  Real hail + lightning, all India.
                </div>
              </div>
            </div>

            {region ? (
              <RegionFloating
                region={region}
                reading={regionReading}
                leadMinutes={regionLeadMinutes}
                onLeadChange={onRegionLeadChange}
                onClose={() => setRegion(null)}
              />
            ) : area ? (
              <AreaFloating
                bbox={area}
                reading={areaReading}
                loading={areaLoading}
                error={areaError}
                leadMinutes={areaLeadMinutes}
                onLeadChange={onAreaLeadChange}
                hazardCount={hazardsInBbox(hazards.data, area)}
                areaVar={areaVar}
                onAreaVarChange={setAreaVar}
                onClose={() => setArea(null)}
              />
            ) : (
              <div className="region-hint">
                {areaSelectMode ? "Drag on the map to draw an area" : "Click to inspect a point, or use Select area to drag-draw a region"}
              </div>
            )}

            <Banner message={banner} />
          </div>

          <RightSidebar
            stormCells={stormEta.data?.cells ?? null}
            forecast={forecastSummary.data ?? null}
            mobileOpen={mobileRightOpen}
            onMobileClose={() => setMobileRightOpen(false)}
          />
        </div>

        <BottomPanel
          model={model}
          leadMinutes={leadMinutes}
          onLeadChange={setLeadMinutes}
          forecast={forecastSummary.data ?? null}
          hazards={hazards.data ?? null}
          onOpenReplay={() => setActivePanel("replay")}
        />
      </div>
    </div>
  );
}

function MapLayers(props: {
  hazards: HazardsResponse | null;
  heatmapsVisible: boolean;
  lightningVisible: boolean;
  rawLayers: RawLayer[] | null;
  satelliteVisible: boolean;
  radarVisible: boolean;
  weatherLayers: WeatherLayer[] | null;
  activeVar: VarId;
  windPoints: WindPoint[] | null;
  windParticlePoints: WindPoint[] | null;
  windAnimationVisible: boolean;
  statesVisible: boolean;
  districtsVisible: boolean;
  indiaVisible: boolean;
  modelFrame: NowcastFrame | null;
  modelFrameVisible: boolean;
  region: { lat: number; lon: number } | null;
  drawingArea: Bbox | null;
  area: Bbox | null;
  areaFillColor?: string;
  areaFillOpacity?: number;
  baseMapId: string;
  activeOverlayIds: Set<string>;
}) {
  return (
    <>
      <WmsBaseLayer selectedId={props.baseMapId} />
      <HazardLayers hazards={props.hazards} hailVisible={props.heatmapsVisible} lightningVisible={props.lightningVisible} />
      <WmsOverlayLayers activeIds={props.activeOverlayIds} />
      <SensorRasterLayers layers={props.rawLayers} satelliteVisible={props.satelliteVisible} radarVisible={props.radarVisible} />
      <WeatherRasterLayers layers={props.weatherLayers} activeVar={props.activeVar} />
      <WindArrows points={props.windPoints} visible={props.activeVar === "wind_speed"} />
      <WindParticles points={props.windParticlePoints} visible={props.windAnimationVisible} />
      <AdminBoundaries statesVisible={props.statesVisible} districtsVisible={props.districtsVisible} indiaVisible={props.indiaVisible} />
      <ModelFrameLayer frame={props.modelFrame} visible={props.modelFrameVisible} />
      <RegionBox region={props.region} />
      <AreaBox drawing={props.drawingArea} selected={props.area} fillColor={props.areaFillColor} fillOpacity={props.areaFillOpacity} />
      <ReferenceLabels />
    </>
  );
}

function hazardsInBbox(hazards: HazardsResponse | null, bbox: Bbox): number {
  if (!hazards) return 0;
  const [lonMin, latMin, lonMax, latMax] = bbox;
  return hazards.features.filter((f) => {
    const [lon, lat] = f.geometry.coordinates;
    return lon >= lonMin && lon <= lonMax && lat >= latMin && lat <= latMax;
  }).length;
}

export default function App() {
  return (
    <MapProvider>
      <Dashboard />
    </MapProvider>
  );
}
