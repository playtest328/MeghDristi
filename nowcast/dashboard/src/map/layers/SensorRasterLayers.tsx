import { useMeghMap } from "../MapProvider";
import { useRasterLayer } from "../useRasterLayer";
import type { RawLayer } from "../../types";

export function SensorRasterLayers({
  layers,
  satelliteVisible,
  radarVisible,
}: {
  layers: RawLayer[] | null;
  satelliteVisible: boolean;
  radarVisible: boolean;
}) {
  const { map } = useMeghMap();
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

  return null;
}
