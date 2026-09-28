import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "../api";
import { useForecastSummary } from "../hooks/useNowcastData";
import { TrendChart } from "./TrendChart";
import type { NowcastFrame } from "../types";

// This page only ever renders pySTEPS vs DGMR side by side (see the two
// ModelColumn calls below) — "smaat" is a valid ModelId elsewhere (the
// backend model query param, the lead-time slider's LEAD_MAX) but has no
// column here, so MODEL_META/ModelColumn are typed to just the two models
// actually used instead of the full ModelId union.
type ChartModelId = "pysteps" | "dgmr";

const MODEL_META: Record<ChartModelId, { label: string; desc: string; unit: string; max: number; step: number }> = {
  pysteps: {
    label: "pySTEPS",
    desc: "Optical-flow extrapolation baseline. Calibrated mm/hr, 0-6h horizon.",
    unit: " mm/hr",
    max: 360,
    step: 10,
  },
  dgmr: {
    label: "DGMR",
    desc: "DeepMind's pretrained Skillful Nowcasting GAN, run zero-shot. Relative intensity (0-1), not calibrated mm/hr. 0-90min horizon.",
    unit: "",
    max: 90,
    step: 5,
  },
};

function ModelColumn({ model }: { model: ChartModelId }) {
  const meta = MODEL_META[model];
  const forecast = useForecastSummary(model);
  const [leadMinutes, setLeadMinutes] = useState(0);
  const [frame, setFrame] = useState<NowcastFrame | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.nowcastFrame(model, leadMinutes).then((f) => !cancelled && setFrame(f));
    return () => {
      cancelled = true;
    };
  }, [model, leadMinutes]);

  const values = forecast.data?.max_rainrate_mm_hr ?? forecast.data?.max_intensity;
  const trendPoints = forecast.data?.timestamps_min && values ? forecast.data.timestamps_min.map((t, i) => ({ leadMin: t, value: values[i] })) : [];
  const leadLabel = leadMinutes === 0 ? "Now" : `+${Math.floor(leadMinutes / 60)}h ${leadMinutes % 60}m`;

  return (
    <div className="panel-section" style={{ flex: 1, borderRight: model === "pysteps" ? "1px solid var(--panel-border)" : "none" }}>
      <div className="section-title">{meta.label}</div>
      <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5, marginBottom: 16 }}>{meta.desc}</div>

      {forecast.data?.available === false ? (
        <div style={{ fontSize: 12, color: "var(--danger)" }}>Unavailable: {forecast.data.reason}</div>
      ) : (
        <>
          <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 6 }}>
            Max {model === "pysteps" ? "rain rate" : "intensity"} over forecast horizon
          </div>
          {trendPoints.length > 1 ? (
            <TrendChart points={trendPoints} color="var(--accent)" unit={meta.unit} height={90} />
          ) : (
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Loading…</div>
          )}

          <div style={{ marginTop: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--text-dim)", marginBottom: 4 }}>
              <span>Preview lead time</span>
              <span style={{ color: "var(--accent)", fontWeight: 600 }}>{leadLabel}</span>
            </div>
            <input
              type="range"
              min={0}
              max={meta.max}
              step={meta.step}
              value={leadMinutes}
              onChange={(e) => setLeadMinutes(parseInt(e.target.value, 10))}
            />
            <div style={{ marginTop: 10, borderRadius: 8, overflow: "hidden", border: "1px solid var(--panel-border)", background: "#000" }}>
              {frame?.available && frame.image ? (
                <img src={frame.image} alt={`${meta.label} forecast frame`} style={{ width: "100%", display: "block", imageRendering: "pixelated" }} />
              ) : (
                <div style={{ height: 180, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-dim)", fontSize: 11 }}>
                  {frame ? `Unavailable: ${frame.reason}` : "Loading frame…"}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function ForecastPage({ onClose }: { onClose: () => void }) {
  return (
    <div className="hazards-page">
      <div className="hazards-page-head">
        <h1>Forecast — pySTEPS vs. DGMR</h1>
        <button className="drawer-close" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
      </div>
      <div className="hazards-page-body" style={{ display: "flex", gap: 0 }}>
        <ModelColumn model="pysteps" />
        <ModelColumn model="dgmr" />
      </div>
    </div>
  );
}
