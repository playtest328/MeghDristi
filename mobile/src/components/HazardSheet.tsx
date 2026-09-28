import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { SEVERITY_COLOR } from "../lib/colors";
import type { Hazard } from "../lib/types";

function hazardDetail(h: Hazard): string {
  if (h.reflectivity_dbz !== undefined) return `${h.reflectivity_dbz} dBZ`;
  if (h.velocity_delta_ms !== undefined) return `${h.velocity_delta_ms} m/s`;
  if (h.rainrate_mm_hr !== undefined) return `${h.rainrate_mm_hr} mm/hr`;
  return "";
}

export function HazardSheet({ hazard, onClose }: { hazard: Hazard | null; onClose: () => void }) {
  if (!hazard) return null;
  const color = SEVERITY_COLOR[hazard.severity] ?? SEVERITY_COLOR.moderate;
  const detail = hazardDetail(hazard);

  return (
    <Modal transparent animationType="slide" visible onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <View style={styles.row}>
          <View style={[styles.dot, { backgroundColor: color }]} />
          <Text style={styles.title}>{hazard.type[0].toUpperCase() + hazard.type.slice(1)}</Text>
        </View>
        <Text style={[styles.severity, { color }]}>Severity: {hazard.severity}</Text>
        {detail ? <Text style={styles.detail}>{detail}</Text> : null}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: { backgroundColor: "#131924", padding: 20, borderTopLeftRadius: 16, borderTopRightRadius: 16 },
  handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: "#334", alignSelf: "center", marginBottom: 16 },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  title: { color: "#fff", fontSize: 18, fontWeight: "700" },
  severity: { fontSize: 14, marginTop: 8, fontWeight: "600" },
  detail: { color: "#8a94a6", fontSize: 13, marginTop: 4 },
});
