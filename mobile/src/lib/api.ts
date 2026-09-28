import type { HazardsResponse, HealthResponse, RegionsResponse } from "./types";

export const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? "http://10.0.2.2:8000";

export class ApiError extends Error {
  constructor(public status: number, public path: string) {
    super(`API ${status} on ${path}`);
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new ApiError(res.status, path);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<HealthResponse>("/health"),
  hazards: (leadMinutes: number) => get<HazardsResponse>(`/hazards?lead_time=${leadMinutes}`),
  regions: () => get<RegionsResponse>("/regions"),
};
