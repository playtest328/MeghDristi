import { useEffect, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import type { Map as MaplibreMap, MapMouseEvent } from "maplibre-gl";
import { X } from "lucide-react";
import { useMeghMap } from "../MapProvider";
import { whenStyleReady } from "../styleReady";

/** Clickable, glowing state + district boundaries, plus an always-on
 * whole-country highlight.
 *
 * Boundary shapes come from static GeoJSON files in public/geo/
 * (states/districts simplified from a GADM-derived open dataset — see
 * that folder's provenance note; the India outline is a separate,
 * independently-sourced file, also documented there). Clicking a state
 * or district toggles its selection; each selected region gets a
 * distinct glow color from a fixed palette so multiple selections stay
 * visually distinguishable from each other, not just from the unselected
 * map. India itself isn't click-to-select (there's only one) — it's a
 * light-shade fill + outline toggled on/off like any other layer, on by
 * default.
 *
 * "Glow" is faked with three stacked line layers per boundary type at
 * increasing width and decreasing opacity around the selected outline —
 * MapLibre GL has no native blur/glow paint property, this is the usual
 * trick for one. Selection state itself lives in MapLibre feature-state
 * (not layer filters), so toggling doesn't require re-adding data.
 *
 * All three are rendered as real vector layers, not a rasterized PNG —
 * crisp at any zoom, which is what this India layer is FOR: giving a
 * sharp, correctly-shaped visual cue for India's real border. It does
 * NOT by itself hide the satellite/radar/weather rasters' own rectangular
 * edges past that border — those are still separately alpha-clipped to
 * India's outline server-side (nowcast/processing/india_shape.py),
 * which is necessary too: removing that clip once left the rasters
 * showing as a plain box again, this outline drawn on top or not,
 * since a border LINE doesn't hide what's under it. The two are
 * complementary, not alternatives: crisp vector outline for the visual
 * edge, server-side raster clip so there's no rectangle for it to be
 * drawn on top of in the first place.
 */

const GLOW_PALETTE = [
  "#22d3ee", "#f472b6", "#facc15", "#a78bfa", "#34d399",
  "#fb923c", "#60a5fa", "#f87171", "#4ade80", "#e879f9",
];

type Level = "states" | "districts";

interface Selection {
  key: string; // `${level}:${id}`
  level: Level;
  id: number;
  name: string;
  parentState?: string;
  color: string;
}

const GEO_URL: Record<Level, string> = {
  states: "/geo/india_states.geojson",
  districts: "/geo/india_districts.geojson",
};

const INDIA_GEO_URL = "/geo/india_outline.geojson";
const INDIA_TINT = "#3fb6ff"; // matches --accent

/** The whole-country highlight — same crisp vector rendering as the
 * states/districts fill/outline below (so it doesn't have the blur a
 * rasterized-and-resampled PNG mask does at any zoom), just always on
 * rather than click-to-select: one light-shade fill plus a clean outline
 * over all of India. Uses a dedicated outline (india_outline.geojson,
 * mirrored from nowcast/configs/geo/ — see that folder's README) rather
 * than india_states.geojson, since that dataset's raw Rajasthan polygon
 * has a real border error near Pakistan (see india_shape.py's old
 * docstring history / that README for how this was found). */
function addIndiaLayer(map: MaplibreMap, data: FeatureCollection) {
  if (map.getSource("india-src")) return;
  map.addSource("india-src", { type: "geojson", data });
  map.addLayer({
    id: "india-fill",
    type: "fill",
    source: "india-src",
    paint: { "fill-color": INDIA_TINT, "fill-opacity": 0.08 },
  });
  map.addLayer({
    id: "india-outline",
    type: "line",
    source: "india-src",
    paint: { "line-color": INDIA_TINT, "line-width": 1.4, "line-opacity": 0.55 },
  });
}

function addBoundaryLayers(map: MaplibreMap, level: Level, data: FeatureCollection) {
  const src = `${level}-src`;
  const outline = `${level}-outline`;
  const hit = `${level}-hit`;
  const fillSelected = `${level}-fill-selected`;
  const glowOuter = `${level}-glow-outer`;
  const glowMid = `${level}-glow-mid`;
  const glowInner = `${level}-glow-inner`;

  if (map.getSource(src)) return;

  map.addSource(src, { type: "geojson", data, generateId: true });

  map.addLayer({
    id: outline,
    type: "line",
    source: src,
    paint: { "line-color": "rgba(255,255,255,0.35)", "line-width": level === "states" ? 1.1 : 0.6 },
  });

  map.addLayer({
    id: fillSelected,
    type: "fill",
    source: src,
    paint: {
      "fill-color": ["coalesce", ["feature-state", "color"], "#ffffff"],
      "fill-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.22, 0],
    },
  });

  // Glow = three line layers, same color, widening + fading outward.
  for (const [id, width, opacity] of [
    [glowOuter, 9, 0.12],
    [glowMid, 5, 0.28],
    [glowInner, 2, 0.85],
  ] as const) {
    map.addLayer({
      id,
      type: "line",
      source: src,
      paint: {
        "line-color": ["coalesce", ["feature-state", "color"], "#ffffff"],
        "line-width": width,
        "line-opacity": ["case", ["boolean", ["feature-state", "selected"], false], opacity, 0],
        "line-blur": width > 2 ? width * 0.6 : 0,
      },
    });
  }

  // Invisible-ish fill purely for click hit-testing over the whole polygon
  // interior (clicking a thin outline is unreliable) — kept above the glow
  // layers in paint order isn't needed since opacity is ~0.
  map.addLayer({
    id: hit,
    type: "fill",
    source: src,
    paint: { "fill-color": "#000000", "fill-opacity": 0.01 },
  });
}

export function AdminBoundaries({
  statesVisible,
  districtsVisible,
  indiaVisible,
}: {
  statesVisible: boolean;
  districtsVisible: boolean;
  indiaVisible: boolean;
}) {
  const { map, ready } = useMeghMap();
  const [selections, setSelections] = useState<Selection[]>([]);
  const selectionsRef = useRef(selections);
  selectionsRef.current = selections;
  const nextColorRef = useRef(0);
  const visibleRef = useRef({ states: statesVisible, districts: districtsVisible });
  visibleRef.current = { states: statesVisible, districts: districtsVisible };

  // Load + add all three boundary sources/layers once, on map ready.
  useEffect(() => {
    if (!map || !ready) return;
    let cancelled = false;

    (["states", "districts"] as Level[]).forEach((level) => {
      fetch(GEO_URL[level])
        .then((r) => r.json())
        .then((data: FeatureCollection) => {
          if (cancelled) return;
          whenStyleReady(map, () => {
            if (cancelled || map.getSource(`${level}-src`)) return;
            addBoundaryLayers(map, level, data);
          });
        })
        .catch((e) => console.error(`[AdminBoundaries] failed to load ${level}`, e));
    });

    fetch(INDIA_GEO_URL)
      .then((r) => r.json())
      .then((data: FeatureCollection) => {
        if (cancelled) return;
        whenStyleReady(map, () => {
          if (cancelled || map.getSource("india-src")) return;
          addIndiaLayer(map, data);
        });
      })
      .catch((e) => console.error("[AdminBoundaries] failed to load india outline", e));

    return () => {
      cancelled = true;
    };
  }, [map, ready]);

  // Visibility toggles.
  useEffect(() => {
    if (!map) return;
    const setVis = (level: Level, visible: boolean) => {
      for (const suffix of ["outline", "hit", "fill-selected", "glow-outer", "glow-mid", "glow-inner"]) {
        const id = `${level}-${suffix}`;
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
      }
    };
    setVis("states", statesVisible);
    setVis("districts", districtsVisible);
  }, [map, statesVisible, districtsVisible]);

  useEffect(() => {
    if (!map) return;
    for (const id of ["india-fill", "india-outline"]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", indiaVisible ? "visible" : "none");
    }
  }, [map, indiaVisible]);

  // Click-to-select — a single map-level handler (queries whichever hit
  // layers are currently visible, topmost feature wins) rather than one
  // per layer, so district-over-state precedence just falls out of
  // MapLibre's own rendered-feature order.
  useEffect(() => {
    if (!map) return;

    const onClick = (e: MapMouseEvent) => {
      const layers: string[] = [];
      if (visibleRef.current.districts && map.getLayer("districts-hit")) layers.push("districts-hit");
      if (visibleRef.current.states && map.getLayer("states-hit")) layers.push("states-hit");
      if (layers.length === 0) return;

      const found = map.queryRenderedFeatures(e.point, { layers });
      if (found.length === 0) return;
      const f = found[0];
      const level: Level = f.layer!.id.startsWith("districts") ? "districts" : "states";
      const id = f.id as number;
      const key = `${level}:${id}`;

      const existing = selectionsRef.current.find((s) => s.key === key);
      if (existing) {
        map.setFeatureState({ source: `${level}-src`, id }, { selected: false });
        setSelections((prev) => prev.filter((s) => s.key !== key));
        return;
      }

      const color = GLOW_PALETTE[nextColorRef.current % GLOW_PALETTE.length];
      nextColorRef.current += 1;
      map.setFeatureState({ source: `${level}-src`, id }, { selected: true, color });
      const name = (f.properties?.name as string) ?? "Unknown";
      const parentState = level === "districts" ? (f.properties?.state as string) : undefined;
      setSelections((prev) => [...prev, { key, level, id, name, parentState, color }]);
    };

    const onMouseMove = (e: MapMouseEvent) => {
      const layers: string[] = [];
      if (visibleRef.current.districts && map.getLayer("districts-hit")) layers.push("districts-hit");
      if (visibleRef.current.states && map.getLayer("states-hit")) layers.push("states-hit");
      if (layers.length === 0) return;
      const found = map.queryRenderedFeatures(e.point, { layers });
      map.getCanvas().style.cursor = found.length > 0 ? "pointer" : "";
    };

    map.on("click", onClick);
    map.on("mousemove", onMouseMove);
    return () => {
      map.off("click", onClick);
      map.off("mousemove", onMouseMove);
    };
  }, [map]);

  const deselect = (sel: Selection) => {
    if (!map) return;
    map.setFeatureState({ source: `${sel.level}-src`, id: sel.id }, { selected: false });
    setSelections((prev) => prev.filter((s) => s.key !== sel.key));
  };

  const clearAll = () => {
    if (!map) return;
    for (const s of selections) {
      map.setFeatureState({ source: `${s.level}-src`, id: s.id }, { selected: false });
    }
    setSelections([]);
  };

  if (selections.length === 0) return null;

  return (
    <div
      style={{
        position: "absolute", bottom: 16, left: 16, zIndex: 5, maxWidth: 240,
        background: "var(--panel)", border: "1px solid var(--panel-border)",
        borderRadius: "10px", padding: "10px 12px", boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ fontSize: 10, color: "var(--text-dim)", fontWeight: 600 }}>
          Selected ({selections.length})
        </div>
        <button
          onClick={clearAll}
          style={{ background: "none", border: "none", color: "var(--text-faint)", fontSize: 9.5, cursor: "pointer" }}
        >
          Clear all
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 160, overflowY: "auto" }}>
        {selections.map((s) => (
          <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10.5 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: s.color, flex: "none", boxShadow: `0 0 6px ${s.color}` }} />
            <div style={{ flex: 1, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {s.name}
              {s.parentState ? <span style={{ color: "var(--text-faint)" }}> · {s.parentState}</span> : null}
            </div>
            <button
              onClick={() => deselect(s)}
              style={{ background: "none", border: "none", color: "var(--text-faint)", cursor: "pointer", padding: 0, display: "flex" }}
            >
              <X size={11} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
