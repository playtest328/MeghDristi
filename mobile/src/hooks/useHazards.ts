import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/** Polls /hazards on the same 30s cadence the web dashboard uses
 * (nowcast/dashboard/src/hooks/useNowcastData.ts POLL_MS). Changing
 * leadMinutes changes the query key, so React Query refetches immediately
 * — no equivalent of the useInterval dependency-array bug that had to be
 * fixed on the web side. */
export function useHazards(leadMinutes: number) {
  return useQuery({
    queryKey: ["hazards", leadMinutes],
    queryFn: () => api.hazards(leadMinutes),
    refetchInterval: 30_000,
    staleTime: 25_000,
  });
}
