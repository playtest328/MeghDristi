import { useEffect } from "react";
import { StyleSheet, View } from "react-native";
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from "react-native-reanimated";
import { SEVERITY_COLOR } from "../lib/colors";
import type { Severity } from "../lib/types";

/** Native equivalent of the web dashboard's CSS pulsing-ring marker
 * (nowcast/dashboard/src/map/layers/HazardLayers.tsx buildMarkerElement +
 * the .hazard-marker-ring keyframes in index.css). RN has no CSS
 * animations, so the ring's grow+fade is driven by Reanimated instead —
 * same visual language (a colored dot with an expanding, fading ring),
 * different animation API. */
export function HazardMarker({ severity, delayMs = 0 }: { severity: Severity; delayMs?: number }) {
  const color = SEVERITY_COLOR[severity] ?? SEVERITY_COLOR.moderate;
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withDelay(
      delayMs,
      withRepeat(withTiming(1, { duration: 1800, easing: Easing.out(Easing.cubic) }), -1, false),
    );
  }, [delayMs, progress]);

  const ringStyle = useAnimatedStyle(() => {
    const size = 10 + progress.value * 24;
    return {
      width: size,
      height: size,
      borderRadius: size / 2,
      opacity: 1 - progress.value,
      borderColor: color,
    };
  });

  return (
    <View style={styles.wrap}>
      <Animated.View style={[styles.ring, ringStyle]} />
      <View style={[styles.dot, { backgroundColor: color, shadowColor: color }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { width: 34, height: 34, alignItems: "center", justifyContent: "center" },
  ring: { position: "absolute", borderWidth: 2 },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: "rgba(255,255,255,0.85)",
    shadowOpacity: 0.9,
    shadowRadius: 6,
    elevation: 6,
  },
});
