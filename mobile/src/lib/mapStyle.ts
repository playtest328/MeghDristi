import type { StyleSpecification } from "@maplibre/maplibre-gl-style-spec";

/** Same free, key-less raster basemap as the web dashboard
 * (nowcast/dashboard/src/map/MapProvider.tsx) — Esri dark-canvas tiles,
 * no API key/token needed. */
export const MAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    "esri-dark-canvas": {
      type: "raster",
      tiles: [
        "https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "Esri, HERE, Garmin, FAO, NOAA, USGS",
    },
  },
  layers: [
    { id: "bg-fallback", type: "background", paint: { "background-color": "#141c2b" } },
    { id: "esri-dark-canvas-layer", type: "raster", source: "esri-dark-canvas" },
  ],
};

/** [west, south, east, north] — same INDIA_BBOX as nowcast/configs/settings.py. */
export const INDIA_BBOX: [number, number, number, number] = [68.0, 6.5, 97.5, 37.0];
