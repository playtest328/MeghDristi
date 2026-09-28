export type HazardType = "hail" | "downburst" | "cloudburst" | "lightning";
export type Severity = "low" | "moderate" | "high";

export interface Hazard {
  type: HazardType;
  severity: Severity;
  reflectivity_dbz?: number;
  velocity_delta_ms?: number;
  rainrate_mm_hr?: number;
  source?: string;
}

export interface HazardFeatureProperties {
  station_id?: string;
  name?: string;
  hazards: Hazard[];
  ts_severity?: string;
  lightning_prob_cat?: string;
  timestamp?: string;
  lead_minutes?: number;
}

export interface HazardFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: HazardFeatureProperties;
}

export interface HazardsResponse {
  type: "FeatureCollection";
  features: HazardFeature[];
  lead_time_minutes: number;
  note?: string;
}

export type Bbox = [number, number, number, number];

export interface RegionOption {
  key: string;
  name: string;
  bbox: Bbox;
}

export interface RegionsResponse {
  active: string;
  options: RegionOption[];
}

export interface HealthResponse {
  status: string;
  loaded_from: string | null;
}
