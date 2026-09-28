import { useEffect, useRef } from "react";
import { useMeghMap } from "../MapProvider";
import type { WindPoint } from "../../types";

/** Flowing wind-particle animation (windy.com-style): thousands of tiny
 * points drift across the map following the real wind field, leaving short
 * fading trails, instead of the static arrow icons (WindArrows.tsx).
 *
 * Implemented as a plain 2D canvas overlaid on the map (not a MapLibre
 * layer) — simpler and easier to get right than a WebGL shader-based
 * particle system, at the cost of being capped by JS/canvas perf rather
 * than the GPU. A few hundred particles is plenty at country-scale zoom
 * and comfortably holds 60fps in a 2D canvas.
 *
 * The animation loop is entirely local (requestAnimationFrame) and does
 * NOT re-run when `points` refreshes every 30s — particles just start
 * sampling the newly-arrived field on their next frame, via a ref, so the
 * motion never stutters/restarts on a data poll.
 */

const PARTICLE_COUNT = 700;
const MIN_LIFETIME_S = 2.5;
const MAX_LIFETIME_S = 6;
// Real wind speeds (a few m/s to a few tens of m/s) would take minutes to
// visibly cross a country-sized map — this is a pure display exaggeration
// (like every wind-flow visualization uses) so motion actually reads as
// "flowing wind" at a glance. It does not affect any displayed number
// (speed/direction shown elsewhere is unaffected, this only scales how
// fast the animated dots move).
const VISUAL_SPEED_SCALE = 220;
const TRAIL_FADE_ALPHA = 0.08; // lower = longer streak trails

interface Particle {
  lon: number;
  lat: number;
  age: number;
  lifetime: number;
}

interface Grid {
  lats: number[]; // ascending
  lons: number[]; // ascending
  u: Float32Array; // [latIdx * lons.length + lonIdx], east-west component, m/s
  v: Float32Array; // north-south component, m/s
  lonMin: number;
  lonMax: number;
  latMin: number;
  latMax: number;
}

function buildGrid(points: WindPoint[]): Grid | null {
  if (points.length === 0) return null;
  const latSet = Array.from(new Set(points.map((p) => p.lat))).sort((a, b) => a - b);
  const lonSet = Array.from(new Set(points.map((p) => p.lon))).sort((a, b) => a - b);
  const u = new Float32Array(latSet.length * lonSet.length);
  const v = new Float32Array(latSet.length * lonSet.length);
  const latIndex = new Map(latSet.map((lat, i) => [lat, i]));
  const lonIndex = new Map(lonSet.map((lon, i) => [lon, i]));

  for (const p of points) {
    const li = latIndex.get(p.lat)!;
    const oi = lonIndex.get(p.lon)!;
    const idx = li * lonSet.length + oi;
    // wind_dir_deg is the direction wind blows FROM (met convention);
    // u/v (east/north components) are the direction it blows TOWARD —
    // interpolating u/v instead of (speed, angle) avoids the wraparound
    // bug you'd get averaging e.g. 359deg and 1deg directly.
    const rad = (p.wind_dir_deg * Math.PI) / 180;
    u[idx] = -p.wind_speed_ms * Math.sin(rad);
    v[idx] = -p.wind_speed_ms * Math.cos(rad);
  }

  return {
    lats: latSet,
    lons: lonSet,
    u,
    v,
    lonMin: lonSet[0],
    lonMax: lonSet[lonSet.length - 1],
    latMin: latSet[0],
    latMax: latSet[latSet.length - 1],
  };
}

function sampleWind(grid: Grid, lon: number, lat: number): [number, number] {
  const { lats, lons, u, v } = grid;
  const nLon = lons.length;

  // Binary-search-free linear scan is fine here (grid is small, ~30-50
  // cells/side) — clamp to the last interior cell so points on/near the
  // edge still interpolate instead of falling off the end.
  let li = 0;
  while (li < lats.length - 2 && lats[li + 1] < lat) li++;
  let oi = 0;
  while (oi < lons.length - 2 && lons[oi + 1] < lon) oi++;

  const lat0 = lats[li], lat1 = lats[li + 1];
  const lon0 = lons[oi], lon1 = lons[oi + 1];
  const tLat = lat1 > lat0 ? (lat - lat0) / (lat1 - lat0) : 0;
  const tLon = lon1 > lon0 ? (lon - lon0) / (lon1 - lon0) : 0;

  const i00 = li * nLon + oi, i01 = li * nLon + (oi + 1);
  const i10 = (li + 1) * nLon + oi, i11 = (li + 1) * nLon + (oi + 1);

  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
  const u0 = lerp(u[i00], u[i01], tLon), u1 = lerp(u[i10], u[i11], tLon);
  const v0 = lerp(v[i00], v[i01], tLon), v1 = lerp(v[i10], v[i11], tLon);
  return [lerp(u0, u1, tLat), lerp(v0, v1, tLat)];
}

function respawn(p: Particle, grid: Grid) {
  p.lon = grid.lonMin + Math.random() * (grid.lonMax - grid.lonMin);
  p.lat = grid.latMin + Math.random() * (grid.latMax - grid.latMin);
  p.age = 0;
  p.lifetime = MIN_LIFETIME_S + Math.random() * (MAX_LIFETIME_S - MIN_LIFETIME_S);
}

export function WindParticles({ points, visible }: { points: WindPoint[] | null; visible: boolean }) {
  const { map } = useMeghMap();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const gridRef = useRef<Grid | null>(null);
  const particlesRef = useRef<Particle[]>([]);
  const rafRef = useRef<number | null>(null);
  const lastTsRef = useRef<number | null>(null);

  // Rebuild the interpolation grid whenever fresh points arrive, without
  // touching the particle positions/ages (so motion doesn't jump/restart).
  useEffect(() => {
    if (!points) return;
    const grid = buildGrid(points);
    gridRef.current = grid;
    if (grid && particlesRef.current.length === 0) {
      const particles: Particle[] = [];
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const p: Particle = { lon: 0, lat: 0, age: 0, lifetime: 1 };
        respawn(p, grid);
        p.age = Math.random() * p.lifetime; // stagger initial ages
        particles.push(p);
      }
      particlesRef.current = particles;
    }
  }, [points]);

  // Canvas lifecycle: create once the map exists, size it to the map's own
  // canvas container, keep it in sync on resize.
  useEffect(() => {
    if (!map) return;
    const container = map.getCanvasContainer();
    const canvas = document.createElement("canvas");
    canvas.style.position = "absolute";
    canvas.style.inset = "0";
    canvas.style.pointerEvents = "none";
    canvas.style.zIndex = "5";
    container.appendChild(canvas);
    canvasRef.current = canvas;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = map.getCanvas().clientWidth;
      const h = map.getCanvas().clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const ctx = canvas.getContext("2d");
      ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    map.on("resize", resize);

    return () => {
      map.off("resize", resize);
      container.removeChild(canvas);
      canvasRef.current = null;
    };
  }, [map]);

  // The animation loop itself — started/stopped only by `visible` and map
  // readiness, never by `points` updating, so a 30s data refresh never
  // interrupts the motion.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!map || !canvas) return;

    if (!visible) {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      lastTsRef.current = null;
      const ctx = canvas.getContext("2d");
      ctx?.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    const ctx = canvas.getContext("2d")!;
    const kmPerDegLat = 111.0;

    const frame = (ts: number) => {
      const grid = gridRef.current;
      const last = lastTsRef.current;
      lastTsRef.current = ts;
      rafRef.current = requestAnimationFrame(frame);
      if (!grid || last === null) return;

      const dtS = Math.min((ts - last) / 1000, 0.1); // clamp long pauses (tab switch)
      const w = canvas.clientWidth, h = canvas.clientHeight;

      ctx.fillStyle = `rgba(10, 14, 22, ${TRAIL_FADE_ALPHA})`;
      ctx.fillRect(0, 0, w, h);

      ctx.lineWidth = 1.1;
      for (const p of particlesRef.current) {
        const [u, v] = sampleWind(grid, p.lon, p.lat);
        const speed = Math.hypot(u, v);

        const screenBefore = map.project([p.lon, p.lat]);

        const kmPerDegLon = 111.0 * Math.cos((p.lat * Math.PI) / 180);
        const distKm = speed * VISUAL_SPEED_SCALE * dtS;
        const norm = speed > 1e-6 ? distKm / speed : 0;
        p.lat += (v * norm) / kmPerDegLat;
        p.lon += (u * norm) / kmPerDegLon;
        p.age += dtS;

        if (
          p.age > p.lifetime ||
          p.lon < grid.lonMin || p.lon > grid.lonMax ||
          p.lat < grid.latMin || p.lat > grid.latMax
        ) {
          respawn(p, grid);
          continue;
        }

        const screenAfter = map.project([p.lon, p.lat]);
        if (screenAfter.x < 0 || screenAfter.x > w || screenAfter.y < 0 || screenAfter.y > h) continue;

        const speedFrac = Math.min(speed / 15, 1); // ~15 m/s -> full brightness
        const alpha = 0.35 + 0.55 * speedFrac;
        const hue = 200 - 60 * speedFrac; // calm = blue, strong = warm cyan-white
        ctx.strokeStyle = `hsla(${hue}, 90%, ${65 + 15 * speedFrac}%, ${alpha})`;
        ctx.beginPath();
        ctx.moveTo(screenBefore.x, screenBefore.y);
        ctx.lineTo(screenAfter.x, screenAfter.y);
        ctx.stroke();
      }
    };

    rafRef.current = requestAnimationFrame(frame);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      lastTsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, visible]);

  return null;
}
