import type { Severity } from "./types";

/** Same green/yellow/red mapping as the web dashboard's
 * nowcast/dashboard/src/lib/colors.ts SEVERITY_COLOR. */
export const SEVERITY_COLOR: Record<Severity, string> = {
  low: "#22c55e",
  moderate: "#f0b429",
  high: "#ef4444",
};
