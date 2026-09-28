import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useInterval } from "./useInterval";
import type { HazardsResponse, StormEtaResponse, RawLayersResponse, WeatherLayersResponse, WindVectorsResponse, ForecastSummary, NowcastFrame, ModelId } from "../types";

const POLL_MS = 30_000;

export interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/** Polls `/hazards` for the given lead time on a 30s cadence (matches the
 * ingestion cycle cadence closely enough for a demo without hammering the
 * backend). Re-fetches immediately when leadMinutes changes. */
export function useHazards(leadMinutes: number): FetchState<HazardsResponse> {
  const [state, setState] = useState<FetchState<HazardsResponse>>({ data: null, loading: true, error: null });

  const fetchNow = useCallback(async () => {
    try {
      const data = await api.hazards(leadMinutes);
      setState({ data, loading: false, error: null });
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: describeError(e) }));
    }
  }, [leadMinutes]);

  useInterval(fetchNow, POLL_MS);
  return state;
}

export function useStormEta(): FetchState<StormEtaResponse> {
  const [state, setState] = useState<FetchState<StormEtaResponse>>({ data: null, loading: true, error: null });
  const fetchNow = useCallback(async () => {
    try {
      const data = await api.stormEta();
      setState({ data, loading: false, error: null });
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: describeError(e) }));
    }
  }, []);
  useInterval(fetchNow, POLL_MS);
  return state;
}

export function useRawLayers(): FetchState<RawLayersResponse> {
  const [state, setState] = useState<FetchState<RawLayersResponse>>({ data: null, loading: true, error: null });
  const fetchNow = useCallback(async () => {
    try {
      const data = await api.rawLayers();
      setState({ data, loading: false, error: null });
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: describeError(e) }));
    }
  }, []);
  useInterval(fetchNow, POLL_MS);
  return state;
}

/** Weather layers and wind vectors are enabled only once a variable is
 * actually selected (not needed for the primary hazard demo), but once
 * enabled they re-fetch on every leadMinutes change — same lead-time state
 * that drives hazards/nowcast-frame, so the existing Play/Pause button
 * animates the weather overlay through the full 0-6h window too, instead of
 * it staying frozen at "now". */
export function useWeatherLayers(leadMinutes: number, enabled: boolean): FetchState<WeatherLayersResponse> {
  const [state, setState] = useState<FetchState<WeatherLayersResponse>>({ data: null, loading: false, error: null });
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    api
      .weatherLayers(leadMinutes)
      .then((data) => !cancelled && setState({ data, loading: false, error: null }))
      .catch((e) => !cancelled && setState((s) => ({ ...s, loading: false, error: describeError(e) })));
    return () => {
      cancelled = true;
    };
  }, [leadMinutes, enabled]);
  return state;
}

export function useWindVectors(leadMinutes: number, enabled: boolean): FetchState<WindVectorsResponse> {
  const [state, setState] = useState<FetchState<WindVectorsResponse>>({ data: null, loading: false, error: null });
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    api
      .windVectors(leadMinutes)
      .then((data) => !cancelled && setState({ data, loading: false, error: null }))
      .catch((e) => !cancelled && setState((s) => ({ ...s, loading: false, error: describeError(e) })));
    return () => {
      cancelled = true;
    };
  }, [leadMinutes, enabled]);
  return state;
}

/** Denser wind grid (stride=2, ~4x the points of the arrow-icon field)
 * for WindParticles.tsx to interpolate a smooth flow from — polled on the
 * same cadence as the other layers so the underlying field slowly
 * updates, though the actual particle motion between polls is entirely
 * local (requestAnimationFrame) and never restarts on a poll. */
export function useWindParticleField(leadMinutes: number, enabled: boolean): FetchState<WindVectorsResponse> {
  const [state, setState] = useState<FetchState<WindVectorsResponse>>({ data: null, loading: false, error: null });
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const fetchNow = () => {
      api
        .windVectors(leadMinutes, 2)
        .then((data) => !cancelled && setState({ data, loading: false, error: null }))
        .catch((e) => !cancelled && setState((s) => ({ ...s, loading: false, error: describeError(e) })));
    };
    fetchNow();
    const id = setInterval(fetchNow, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [leadMinutes, enabled]);
  return state;
}

export function useForecastSummary(model: ModelId): FetchState<ForecastSummary> {
  const [state, setState] = useState<FetchState<ForecastSummary>>({ data: null, loading: true, error: null });
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    api
      .forecast(model)
      .then((data) => !cancelled && setState({ data, loading: false, error: null }))
      .catch((e) => !cancelled && setState({ data: null, loading: false, error: describeError(e) }));
    return () => {
      cancelled = true;
    };
  }, [model]);
  return state;
}

export function useNowcastFrame(model: ModelId, leadMinutes: number, enabled: boolean): FetchState<NowcastFrame> {
  const [state, setState] = useState<FetchState<NowcastFrame>>({ data: null, loading: false, error: null });
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    api
      .nowcastFrame(model, leadMinutes)
      .then((data) => !cancelled && setState({ data, loading: false, error: null }))
      .catch((e) => !cancelled && setState({ data: null, loading: false, error: describeError(e) }));
    return () => {
      cancelled = true;
    };
  }, [model, leadMinutes, enabled]);
  return state;
}

function describeError(e: unknown): string {
  if (e instanceof ApiError) return `API ${e.status} on ${e.path}`;
  if (e instanceof Error) return e.message;
  return "unknown error";
}
