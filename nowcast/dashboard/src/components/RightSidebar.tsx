import { X } from "lucide-react";
import { windCompass } from "../lib/colors";
import type { ForecastSummary, Hazard, HazardType, StormCell } from "../types";

const HAZARD_META: Record<HazardType, { icon: string; label: string }> = {
  hail: { icon: "🌩️", label: "Hail" },
  lightning: { icon: "⚡", label: "Lightning" },
  downburst: { icon: "🌬️", label: "Downburst" },
  cloudburst: { icon: "🌧️", label: "Cloudburst" },
};

// Cloudburst rain-rate thresholds mirror nowcast/configs/settings.py's
// CLOUDBURST_RAIN_RATE_MM_HR — bucket classification is derived from real
// pySTEPS forecast output, not fabricated.
const HIGH_THRESHOLD = 30;
const MODERATE_THRESHOLD = 15;

function findSoonest(cells: StormCell[], type: HazardType): { cell: StormCell; hazard: Hazard } | null {
  let best: { cell: StormCell; hazard: Hazard } | null = null;
  for (const cell of cells) {
    const hazard = cell.hazards.find((h) => h.type === type);
    if (hazard && (!best || cell.eta_minutes < best.cell.eta_minutes)) {
      best = { cell, hazard };
    }
  }
  return best;
}

function formatEta(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function bucketSeverity(forecast: ForecastSummary | null, fromMin: number, toMin: number): { label: string; color: string } {
  if (!forecast?.timestamps_min || !forecast.max_rainrate_mm_hr) {
    return { label: "—", color: "var(--text-dim)" };
  }
  let max = 0;
  forecast.timestamps_min.forEach((t, i) => {
    if (t >= fromMin && t <= toMin) max = Math.max(max, forecast.max_rainrate_mm_hr![i]);
  });
  if (max >= HIGH_THRESHOLD) return { label: "High", color: "var(--danger)" };
  if (max >= MODERATE_THRESHOLD) return { label: "Moderate", color: "var(--warn)" };
  return { label: "Low", color: "var(--ok)" };
}

export function RightSidebar({
  stormCells,
  forecast,
  mobileOpen,
  onMobileClose,
}: {
  stormCells: StormCell[] | null;
  forecast: ForecastSummary | null;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}) {
  const cells = stormCells ?? [];
  const primaryCell = cells.length ? [...cells].sort((a, b) => a.eta_minutes - b.eta_minutes)[0] : null;
  const buckets = [
    { label: "0-1h", from: 0, to: 60 },
    { label: "1-2h", from: 60, to: 120 },
    { label: "2-4h", from: 120, to: 240 },
    { label: "4-6h", from: 240, to: 360 },
  ];

  return (
    <div className={`sidebar right ${mobileOpen ? "mobile-open" : ""}`}>
      <button className="sidebar-mobile-close" onClick={onMobileClose} aria-label="Close panel">
        <X size={18} />
      </button>
      <div className="panel-section">
        <div className="section-title">Active Hazards</div>

        {(Object.keys(HAZARD_META) as HazardType[]).map((type) => {
          const found = findSoonest(cells, type);
          const meta = HAZARD_META[type];
          if (!found) return null;
          const { cell, hazard } = found;
          return (
            <div className={`hazard-card ${type}`} key={type}>
              <div className="hazard-head">
                <div className="icon">{meta.icon}</div>
                <div>{meta.label}</div>
              </div>
              <div className="hazard-stats">
                {type === "hail" && hazard.reflectivity_dbz !== undefined && (
                  <div className="hazard-stat">
                    <span className="lbl">Reflectivity</span>
                    <span className="val" style={{ color: "var(--danger)" }}>{hazard.reflectivity_dbz} dBZ</span>
                  </div>
                )}
                {type === "downburst" && hazard.velocity_delta_ms !== undefined && (
                  <div className="hazard-stat">
                    <span className="lbl">Velocity delta</span>
                    <span className="val" style={{ color: "var(--danger)" }}>{hazard.velocity_delta_ms} m/s</span>
                  </div>
                )}
                {type === "cloudburst" && hazard.rainrate_mm_hr !== undefined && (
                  <div className="hazard-stat">
                    <span className="lbl">Rain rate</span>
                    <span className="val" style={{ color: "var(--accent)" }}>{hazard.rainrate_mm_hr} mm/hr</span>
                  </div>
                )}
                {type === "lightning" && (
                  <div className="hazard-stat">
                    <span className="lbl">Severity</span>
                    <span className="val" style={{ color: "var(--danger)" }}>{hazard.severity}</span>
                  </div>
                )}
                <div className="hazard-stat">
                  <span className="lbl">Time to Arrival</span>
                  <span className="val">{formatEta(cell.eta_minutes)}</span>
                </div>
              </div>
            </div>
          );
        })}

        {cells.length === 0 && (
          <div style={{ fontSize: 11, color: "var(--text-dim)", padding: "8px 0" }}>No active hazards this cycle.</div>
        )}

        {primaryCell && (
          <div className="hazard-card" style={{ borderLeft: "3px solid var(--accent)" }}>
            <div className="hazard-head">
              <div className="icon">↗️</div>
              <div>Storm Motion ({primaryCell.name || primaryCell.station_id})</div>
            </div>
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
              {windCompass(primaryCell.bearing_deg)} {primaryCell.speed_kmh} km/h · {primaryCell.distance_km} km away ({primaryCell.motion_source})
            </div>
          </div>
        )}
      </div>

      <div className="panel-section">
        <div className="section-title">
          Next 6 Hours <span className="count">(pySTEPS rain-rate forecast)</span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {buckets.map((b) => {
            const sev = bucketSeverity(forecast, b.from, b.to);
            return (
              <div
                key={b.label}
                style={{
                  flex: 1,
                  background: `${sev.color}22`,
                  border: `1px solid ${sev.color}66`,
                  borderRadius: 6,
                  padding: "8px 4px",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: 10, color: "var(--text-dim)" }}>{b.label}</div>
                <div style={{ fontSize: 11, fontWeight: 600, color: sev.color, marginTop: 4 }}>{sev.label}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
