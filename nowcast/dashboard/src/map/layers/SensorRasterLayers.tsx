import { useEffect } from "react";
import type { Map as MaplibreMap } from "maplibre-gl";
import { useMeghMap } from "../MapProvider";
import { useRasterLayer } from "../useRasterLayer";
import { whenStyleReady } from "../styleReady";
import type { RawLayer } from "../../types";

const MASK_SRC = "india-mask-src";
const MASK_LAYER = "india-mask-fill";
const MASK_URL = "/geo/india_mask.geojson";

/** The satellite/radar "all India" rasters (satellite_insat.py /
 * hazard_india.py) are generated as a plain rectangular grid over
 * INDIA_BBOX — visually a big box spanning well past India's actual
 * coastline into Pakistan, China, Myanmar, the ocean, etc. This paints
 * over everything in that same rectangle that ISN'T India with the map's
 * own background color, using an inverted mask polygon (INDIA_BBOX's own
 * rectangle with India's outline cut out as a hole — see
 * public/geo/README.md for how it's built) — the standard MapLibre/Mapbox
 * trick for clipping a layer to an arbitrary shape, since there's no
 * native raster-clip-to-vector paint property. Scoped to exactly
 * INDIA_BBOX rather than the whole world so this never paints over any
 * basemap outside where the raster ever was to begin with. */
function addMaskLayer(map: MaplibreMap) {
  if (map.getSource(MASK_SRC)) return;
  fetch(MASK_URL)
    .then((r) => r.json())
    .then((data) => {
      whenStyleReady(map, () => {
        if (map.getSource(MASK_SRC)) return;
        map.addSource(MASK_SRC, { type: "geojson", data });
        // Same beforeId as the satellite/radar raster layers above (and
        // added after them, so it stacks on top of both) — needs to cover
        // the rasters but stay below hazard markers/boundaries/heat-hail.
        map.addLayer(
          {
            id: MASK_LAYER,
            type: "fill",
            source: MASK_SRC,
            // Matches index.css's --bg (the app's base background color),
            // so the mask reads as "the map showing through" rather than
            // an obviously different patch of color.
            paint: { "fill-color": "#060910", "fill-opacity": 1 },
            layout: { visibility: "none" },
          },
          map.getLayer("heat-hail") ? "heat-hail" : undefined,
        );
      });
    })
    .catch((e) => console.error("[SensorRasterLayers] failed to load India mask", e));
}

export function SensorRasterLayers({
  layers,
  satelliteVisible,
  radarVisible,
}: {
  layers: RawLayer[] | null;
  satelliteVisible: boolean;
  radarVisible: boolean;
}) {
  const { map, ready } = useMeghMap();
  const byId = Object.fromEntries((layers ?? []).map((l) => [l.id, l]));

  useRasterLayer(map, "layer-satellite_tir1", byId.satellite_tir1?.image, byId.satellite_tir1?.bbox, {
    opacity: 0.45,
    visible: satelliteVisible,
    beforeId: "heat-hail",
  });
  useRasterLayer(map, "layer-radar_reflectivity", byId.radar_reflectivity?.image, byId.radar_reflectivity?.bbox, {
    opacity: 0.5,
    visible: radarVisible,
    beforeId: "heat-hail",
  });

  useEffect(() => {
    if (!map || !ready) return;
    addMaskLayer(map);
  }, [map, ready]);

  // Only masks while one of the rectangular-bbox rasters is actually
  // showing — otherwise this would permanently paint an India-shaped hole
  // over the base map even with both layers switched off.
  useEffect(() => {
    if (!map || !map.getLayer(MASK_LAYER)) return;
    map.setLayoutProperty(MASK_LAYER, "visibility", satelliteVisible || radarVisible ? "visible" : "none");
  }, [map, satelliteVisible, radarVisible]);

  return null;
}
