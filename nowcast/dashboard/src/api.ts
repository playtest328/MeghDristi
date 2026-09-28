import type {
  HazardsResponse,
  StormEtaResponse,
  RawLayersResponse,
  WeatherLayersResponse,
  WindVectorsResponse,
  RegionForecast,
  ForecastSummary,
  NowcastFrame,
  ModelId,
  HistoryTimestampsResponse,
  HistoryHazardsResponse,
  RegionsResponse,
  AreaForecast,
  Bbox,
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

class ApiError extends Error {
  path: string;
  status: number;

  constructor(path: string, status: number) {
    super(`${path} -> ${status}`);
    this.path = path;
    this.status = status;
  }
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new ApiError(path, res.status);
  return (await res.json()) as T;
}

async function postJSON<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path, { method: "POST" });
  if (!res.ok) throw new ApiError(path, res.status);
  return (await res.json()) as T;
}

export const api = {
  health: () => getJSON<{ status: string; loaded_from: string | null }>("/health"),
  hazards: (leadMinutes: number) => getJSON<HazardsResponse>(`/hazards?lead_time=${leadMinutes}`),
  stormEta: () => getJSON<StormEtaResponse>("/storm-eta"),
  rawLayers: () => getJSON<RawLayersResponse>("/raw-layers"),
  weatherLayers: (leadMinutes: number) => getJSON<WeatherLayersResponse>(`/weather-layers?lead_time=${leadMinutes}`),
  windVectors: (leadMinutes: number, stride = 4) => getJSON<WindVectorsResponse>(`/wind-vectors?lead_time=${leadMinutes}&stride=${stride}`),
  regionForecast: (lat: number, lon: number, leadMinutes: number) =>
    getJSON<RegionForecast>(`/region-forecast?lat=${lat}&lon=${lon}&lead_time=${leadMinutes}`),
  forecast: (model: ModelId) => getJSON<ForecastSummary>(`/forecast?model=${model}`),
  nowcastFrame: (model: ModelId, leadMinutes: number) =>
    getJSON<NowcastFrame>(`/nowcast-frame?model=${model}&lead_time=${leadMinutes}`),
  historyTimestamps: () => getJSON<HistoryTimestampsResponse>("/history/timestamps"),
  historyHazards: (timestamp: string) => getJSON<HistoryHazardsResponse>(`/history/hazards?timestamp=${timestamp}`),
  regions: () => getJSON<RegionsResponse>("/regions"),
  setRegion: (key: string) => postJSON<{ active: string; name: string }>(`/regions/${key}`),
  areaForecast: (bbox: Bbox, leadMinutes: number) => {
    const [lonMin, latMin, lonMax, latMax] = bbox;
    return getJSON<AreaForecast>(
      `/area-forecast?lon_min=${lonMin}&lat_min=${latMin}&lon_max=${lonMax}&lat_max=${latMax}&lead_time=${leadMinutes}`
    );
  },
};

export { ApiError };
