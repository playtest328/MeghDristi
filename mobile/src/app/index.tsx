import { useMemo, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Camera, Map, Marker } from "@maplibre/maplibre-react-native";
import { useHazards } from "../hooks/useHazards";
import { HazardMarker } from "../components/HazardMarker";
import { HazardSheet } from "../components/HazardSheet";
import { INDIA_BBOX, MAP_STYLE } from "../lib/mapStyle";
import type { Hazard } from "../lib/types";

export default function MapScreen() {
  const { data, isLoading, isError } = useHazards(0);
  const [selected, setSelected] = useState<Hazard | null>(null);

  const counts = useMemo(() => {
    let hail = 0;
    let lightning = 0;
    for (const f of data?.features ?? []) {
      for (const h of f.properties.hazards) {
        if (h.type === "hail") hail++;
        else if (h.type === "lightning") lightning++;
      }
    }
    return { hail, lightning };
  }, [data]);

  return (
    <View style={styles.container}>
      <Map mapStyle={MAP_STYLE} style={styles.map} logo={false} attribution={false}>
        <Camera initialViewState={{ bounds: INDIA_BBOX, padding: { top: 40, bottom: 40, left: 40, right: 40 } }} />
        {data?.features.map((f, fi) =>
          f.properties.hazards.map((h, hi) => (
            <Marker
              key={`${fi}-${hi}`}
              id={`hazard-${fi}-${hi}`}
              lngLat={f.geometry.coordinates}
              onPress={() => setSelected(h)}
            >
              <HazardMarker severity={h.severity} delayMs={(hi % 2) * 900} />
            </Marker>
          )),
        )}
      </Map>

      <View style={styles.topBar}>
        <Text style={styles.title}>MeghDrishti</Text>
        {isLoading && <ActivityIndicator color="#3fb6ff" />}
      </View>

      <View style={styles.legend}>
        <View style={styles.legendRow}>
          <View style={[styles.legendDot, { backgroundColor: "#ef4444" }]} />
          <Text style={styles.legendText}>Hail: {counts.hail}</Text>
        </View>
        <View style={styles.legendRow}>
          <View style={[styles.legendDot, { backgroundColor: "#f0b429" }]} />
          <Text style={styles.legendText}>Lightning: {counts.lightning}</Text>
        </View>
        {isError && <Text style={styles.errorText}>Backend unreachable</Text>}
      </View>

      <HazardSheet hazard={selected} onClose={() => setSelected(null)} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0e16" },
  map: { flex: 1 },
  topBar: {
    position: "absolute",
    top: 48,
    left: 16,
    right: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: { color: "#fff", fontSize: 20, fontWeight: "700" },
  legend: {
    position: "absolute",
    bottom: 32,
    left: 16,
    backgroundColor: "rgba(19,25,36,0.9)",
    borderRadius: 10,
    padding: 12,
    gap: 6,
  },
  legendRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendText: { color: "#e5e7eb", fontSize: 12 },
  errorText: { color: "#ef4444", fontSize: 12, marginTop: 4 },
});
