"""Deterministic, time-seeded storm lifecycle across India.

Storms are a pure function of wall-clock time rather than per-process
randomness. Real time is divided into fixed-width "spawn slots"
(_SLOT_MINUTES each); each slot deterministically may spawn a storm, seeded
by the slot's own index (not by anything process-local), with a randomized
birth position, lifetime, motion, and size all drawn from that same
per-slot seed. A storm's position and intensity at any later moment are
computed purely from elapsed real time since its birth (advected like
storm_track.center_at, faded in/out at the start/end of its life) — never
from unseeded `np.random` at call time.

This gives three properties for free, with no persistent state, database,
or separate server — purely because it's a deterministic function of time:

- Two processes (or the same process before and after a restart) asking
  "what storms exist right now" get the IDENTICAL answer, since both just
  evaluate the same function at the same wall-clock time.
- Storms move continuously and are born/die gradually over real minutes-
  to-hours (motion and fade-in/fade-out are both continuous functions of
  elapsed time), not discrete flips every refresh.
- Two timestamps far apart draw from different, independent spawn slots,
  so the storm layout genuinely differs; two timestamps close together
  (a quick restart, a normal poll) overlap almost entirely in which slots
  are "live" and how far each storm has moved, so the layout barely changes.
"""
import hashlib
import time as _time

import numpy as np

from nowcast.configs.settings import INDIA_BBOX

_SLOT_MINUTES = 12  # a new spawn opportunity every N minutes
_SPAWN_PROB = 0.55  # chance a given slot actually spawns a storm
_MIN_LIFETIME_MIN = 25
_MAX_LIFETIME_MIN = 240  # up to 4h — most storms are shorter, a few run long
_FADE_FRACTION = 0.15  # first/last 15% of life ramps intensity in/out
_LOOKBACK_SLOTS = int(_MAX_LIFETIME_MIN / _SLOT_MINUTES) + 2
_MARGIN_DEG = 2.0  # keep spawns off the immediate INDIA_BBOX edge


def _slot_rng(slot_index):
    """RNG seeded purely by the slot's integer index — the same slot always
    produces the same storm, on any machine, in any process, whenever it's
    evaluated."""
    digest = hashlib.sha256(f"meghdrishti-storm-slot-{slot_index}".encode()).digest()
    seed = int.from_bytes(digest[:8], "big")
    return np.random.default_rng(seed)


def _spawn_for_slot(slot_index):
    """A storm dict for this slot (birth_epoch, lifetime_min, lat, lon,
    bearing_deg, speed_kmh, radius_km), or None if this slot doesn't spawn
    one. Deterministic in `slot_index` alone."""
    rng = _slot_rng(slot_index)
    if rng.random() >= _SPAWN_PROB:
        return None

    slot_start_epoch = slot_index * _SLOT_MINUTES * 60
    birth_jitter_s = rng.uniform(0, _SLOT_MINUTES * 60)

    lon_min, lat_min, lon_max, lat_max = INDIA_BBOX
    return {
        "birth_epoch": slot_start_epoch + birth_jitter_s,
        "lifetime_min": float(rng.uniform(_MIN_LIFETIME_MIN, _MAX_LIFETIME_MIN)),
        "lat": float(rng.uniform(lat_min + _MARGIN_DEG, lat_max - _MARGIN_DEG)),
        "lon": float(rng.uniform(lon_min + _MARGIN_DEG, lon_max - _MARGIN_DEG)),
        "bearing_deg": float(rng.uniform(0, 360)),
        "speed_kmh": float(rng.uniform(10, 35)),
        # Skewed toward smaller cells with an occasional big system, same
        # reasoning as storm_track.random_india_storm_spots used to have.
        "radius_km": float(18 + (rng.uniform(0, 1) ** 2) * 47),
        # Fixed per-storm seed for its internal sub-cell texture (see
        # storm_track.cluster_intensity_fraction) — drawn once here, from
        # the same deterministic per-slot RNG, so a storm's shape stays
        # stable across renders instead of re-randomizing (flickering)
        # every time it's drawn while it sits at the same position.
        "texture_seed": int(rng.integers(0, 2**31 - 1)),
    }


def _advect(storm, elapsed_min):
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * np.cos(np.radians(storm["lat"]))
    bearing_rad = np.radians(storm["bearing_deg"])
    dist_km = storm["speed_kmh"] * (elapsed_min / 60.0)
    dlat = (dist_km * np.cos(bearing_rad)) / km_per_deg_lat
    dlon = (dist_km * np.sin(bearing_rad)) / km_per_deg_lon
    return storm["lat"] + dlat, storm["lon"] + dlon


def active_storms(now_epoch=None):
    """All storms alive at `now_epoch` (defaults to real wall-clock time),
    as a list of {lat, lon, bearing_deg, radius_km, intensity} dicts.
    `intensity` is in [0, 1]: it ramps up over the storm's first
    _FADE_FRACTION of life and back down over its last _FADE_FRACTION, so
    storms fade in and out smoothly instead of appearing/vanishing
    instantly."""
    now_epoch = _time.time() if now_epoch is None else now_epoch
    current_slot = int(now_epoch // (_SLOT_MINUTES * 60))

    storms = []
    for slot_index in range(current_slot - _LOOKBACK_SLOTS, current_slot + 1):
        storm = _spawn_for_slot(slot_index)
        if storm is None:
            continue
        age_min = (now_epoch - storm["birth_epoch"]) / 60.0
        if age_min < 0 or age_min > storm["lifetime_min"]:
            continue

        fade_min = storm["lifetime_min"] * _FADE_FRACTION
        if age_min < fade_min:
            intensity = age_min / fade_min
        elif age_min > storm["lifetime_min"] - fade_min:
            intensity = (storm["lifetime_min"] - age_min) / fade_min
        else:
            intensity = 1.0
        intensity = float(np.clip(intensity, 0, 1))

        lat, lon = _advect(storm, age_min)
        storms.append(
            {
                "lat": lat,
                "lon": lon,
                "bearing_deg": storm["bearing_deg"],
                "radius_km": storm["radius_km"],
                "intensity": intensity,
                "seed": storm["texture_seed"],
            }
        )
    return storms


if __name__ == "__main__":
    for s in active_storms():
        print(
            f"lat={s['lat']:.2f} lon={s['lon']:.2f} radius_km={s['radius_km']:.0f} "
            f"intensity={s['intensity']:.2f}"
        )
