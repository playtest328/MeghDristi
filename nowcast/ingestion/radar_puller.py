"""Radar puller (section 2c of project.md).

MOSDAC volumetric DWR access is still under review, so this generates a
synthetic CAPPI-like reflectivity + velocity grid instead (see
nowcast/processing/synthetic_radar.py).

Writes CAPPI-like output to data/radar/<ts>.npz with keys: reflectivity_dbz,
velocity_ms, bbox, timestamp.
"""
import os
import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from nowcast.configs.settings import get_region_bbox, DATA_DIR
from nowcast.processing.synthetic_radar import generate_sequence, generate_velocity_frame

RADAR_DIR = os.path.join(DATA_DIR, "radar")


def _fetch_mock():
    frames, _ = generate_sequence(n_frames=1, dt_minutes=0)
    reflectivity = frames[0]
    velocity = generate_velocity_frame(t_min=0)
    return reflectivity, velocity


def pull():
    os.makedirs(RADAR_DIR, exist_ok=True)
    reflectivity, velocity = _fetch_mock()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(RADAR_DIR, f"{ts}.npz")
    np.savez(out_path, reflectivity_dbz=reflectivity, velocity_ms=velocity, bbox=np.array(get_region_bbox()))
    print(f"[radar_puller] wrote CAPPI reflectivity+velocity -> {out_path}")
    return out_path


if __name__ == "__main__":
    pull()
