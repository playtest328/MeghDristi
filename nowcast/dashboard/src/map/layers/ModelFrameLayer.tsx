import { useEffect, useRef, useState } from "react";
import type { FeatureCollection } from "geojson";
import type { GeoJSONSource } from "maplibre-gl";
import { Sparkles } from "lucide-react";
import { useMeghMap } from "../MapProvider";
import { useRasterLayer } from "../useRasterLayer";
import type { NowcastFrame, ModelId, Bbox } from "../../types";

const SMAAT_SRC = "smaat-placeholder-src";
const SMAAT_GLOW = ["smaat-glow-outer", "smaat-glow-mid", "smaat-glow-inner"] as const;
const SMAAT_COLOR = "#f0b429"; // amber — deliberately NOT the accent blue used for
// real data/selection boxes elsewhere, so this reads as a distinct "not real
// data" state at a glance, not just another forecast layer.

function boxPolygon(bbox: Bbox): FeatureCollection {
  const [lonMin, latMin, lonMax, latMax] = bbox;
  const coords = [
    [lonMin, latMax], [lonMax, latMax], [lonMax, latMin], [lonMin, latMin], [lonMin, latMax],
  ];
  return { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Polygon", coordinates: [coords] }, properties: {} }] };
}

/** pySTEPS/DGMR render as an actual colored raster (turbo vs plasma
 * colormap — see api/main.py's /nowcast-frame docstring) via useRasterLayer
 * below. SmaAt-UNet has no trained weights yet, so there's no real frame to
 * show — rather than render nothing (reads as "broken", or as "identical to
 * whichever model was on before") or fabricate forecast-looking data (never
 * does that here), this draws a deliberately eye-catching, unmistakably-a-
 * placeholder treatment: a slowly pulsing glow border over the same region
 * the other two models forecast, plus a floating badge explaining why.
 * Amber, not the app's accent blue, and no color heatmap at all — so it
 * can't be mistaken for real forecast output at a glance, only for what it
 * is: a clearly labeled "coming soon". */
function useSmaatPlaceholder(model: ModelId, frame: NowcastFrame | null, visible: boolean) {
  const { map, ready } = useMeghMap();
  const show = visible && model === "smaat" && !frame?.available && !!frame?.bbox;
  const [badgePos, setBadgePos] = useState<{ x: number; y: number } | null>(null);
  const bboxRef = useRef<Bbox | undefined>(frame?.bbox);
  bboxRef.current = frame?.bbox;

  useEffect(() => {
    if (!map || !ready || map.getSource(SMAAT_SRC)) return;
    map.addSource(SMAAT_SRC, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    const widths = [11, 6, 2.5];
    SMAAT_GLOW.forEach((id, i) => {
      map.addLayer({
        id,
        type: "line",
        source: SMAAT_SRC,
        paint: {
          "line-color": SMAAT_COLOR,
          "line-width": widths[i],
          "line-blur": i === 2 ? 0 : widths[i] * 0.5,
          "line-opacity": 0,
          "line-dasharray": i === 2 ? [3, 2] : [1, 0],
        },
      });
    });
  }, [map, ready]);

  // Breathing pulse: a slow sine wave drives all three glow layers' opacity
  // together, so the box visibly reads as "alive/in-progress" rather than
  // a static dead outline.
  useEffect(() => {
    if (!map || !show) return;
    let raf: number;
    const start = performance.now();
    const tick = (now: number) => {
      const t = (now - start) / 1000;
      const pulse = 0.55 + 0.45 * Math.sin(t * 1.6); // 0.1..1.0, ~4s period
      const bases = [0.16, 0.32, 0.8];
      SMAAT_GLOW.forEach((id, i) => {
        if (map.getLayer(id)) map.setPaintProperty(id, "line-opacity", bases[i] * pulse);
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [map, show]);

  useEffect(() => {
    if (!map || !ready) return;
    const source = map.getSource(SMAAT_SRC) as GeoJSONSource | undefined;
    if (!source) return;
    if (!show || !frame?.bbox) {
      source.setData({ type: "FeatureCollection", features: [] });
      SMAAT_GLOW.forEach((id) => { if (map.getLayer(id)) map.setPaintProperty(id, "line-opacity", 0); });
      setBadgePos(null);
      return;
    }
    source.setData(boxPolygon(frame.bbox));
  }, [map, ready, show, frame?.bbox]);

  // Badge screen position: a real React/CSS element (not MapLibre's canvas
  // text) so it can look like the rest of the app's UI — recomputed on
  // every map move/zoom so it stays pinned to the box.
  useEffect(() => {
    if (!map) return;
    const update = () => {
      const bbox = bboxRef.current;
      if (!show || !bbox) { setBadgePos(null); return; }
      const [lonMin, latMin, lonMax, latMax] = bbox;
      const p = map.project([(lonMin + lonMax) / 2, (latMin + latMax) / 2]);
      setBadgePos({ x: p.x, y: p.y });
    };
    update();
    map.on("move", update);
    map.on("zoom", update);
    return () => {
      map.off("move", update);
      map.off("zoom", update);
    };
  }, [map, show]);

  return badgePos;
}

export function ModelFrameLayer({ frame, visible, model }: { frame: NowcastFrame | null; visible: boolean; model: ModelId }) {
  const { map } = useMeghMap();
  useRasterLayer(map, "layer-model-frame", frame?.image, frame?.bbox, {
    opacity: 0.55,
    visible: visible && !!frame?.available,
    beforeId: "heat-hail",
  });
  const badgePos = useSmaatPlaceholder(model, frame, visible);

  if (!badgePos) return null;
  return (
    <div
      style={{
        position: "absolute", left: badgePos.x, top: badgePos.y, transform: "translate(-50%, -50%)",
        zIndex: 6, pointerEvents: "none", display: "flex", flexDirection: "column", alignItems: "center",
        gap: 6, animation: "smaat-badge-breathe 4s ease-in-out infinite",
      }}
    >
      <style>{`
        @keyframes smaat-badge-breathe { 0%, 100% { opacity: 0.75; transform: scale(0.98); } 50% { opacity: 1; transform: scale(1.03); } }
      `}</style>
      <div
        style={{
          display: "flex", alignItems: "center", gap: 7, padding: "7px 14px", borderRadius: 999,
          background: "rgba(13,18,28,0.9)", backdropFilter: "blur(8px)",
          border: `1px solid ${SMAAT_COLOR}`, boxShadow: `0 0 18px 2px rgba(240,180,41,0.35)`,
        }}
      >
        <Sparkles size={13} color={SMAAT_COLOR} />
        <span style={{ fontSize: 12, fontWeight: 700, color: "#fff", letterSpacing: 0.2 }}>SmaAt-UNet</span>
      </div>
      <div
        style={{
          fontSize: 9.5, fontWeight: 600, color: SMAAT_COLOR, letterSpacing: 0.6, textTransform: "uppercase",
          background: "rgba(13,18,28,0.85)", padding: "3px 9px", borderRadius: 6, border: "1px solid rgba(240,180,41,0.3)",
        }}
      >
        Training in progress
      </div>
    </div>
  );
}
