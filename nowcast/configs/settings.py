"""Central config: demo region, thresholds, paths.

Demo region default: Pune district, Maharashtra (good IMD AWS density,
inside MOSDAC radar footprint). Change BBOX to retarget the whole pipeline.
"""
import contextlib
import os
import threading
from dotenv import load_dotenv

load_dotenv()

# Selectable demo regions — the storm-scale grid (radar/satellite/pySTEPS/
# DGMR/hazards) is deliberately a small, fixed-size box (~0.5deg, matches
# GRID_SIZE=64 in synthetic_radar.py for ~800m/cell resolution): widening
# this box itself to cover all of India would collapse the demo storm to
# a sub-pixel blob and blow up hazard-rule filter windows tuned for this
# scale. Instead, the SAME size box can be repositioned to any major city,
# so real layers (RainViewer/Blitzortung/ECMWF, which already cover all of
# India) and the synthetic storm-scale grid both center on wherever the
# user picks.
REGIONS = {
    "pune": {"name": "Pune", "bbox": (73.6, 18.3, 74.1, 18.8)},
    "delhi": {"name": "Delhi NCR", "bbox": (76.85, 28.35, 77.35, 28.85)},
    "mumbai": {"name": "Mumbai", "bbox": (72.6, 18.85, 73.1, 19.35)},
    "chennai": {"name": "Chennai", "bbox": (80.0, 12.85, 80.5, 13.35)},
    "kolkata": {"name": "Kolkata", "bbox": (88.15, 22.35, 88.65, 22.85)},
    "bengaluru": {"name": "Bengaluru", "bbox": (77.35, 12.75, 77.85, 13.25)},
    "hyderabad": {"name": "Hyderabad", "bbox": (78.25, 17.15, 78.75, 17.65)},
    "ahmedabad": {"name": "Ahmedabad", "bbox": (72.35, 22.80, 72.85, 23.30)},
    "jaipur": {"name": "Jaipur", "bbox": (75.55, 26.65, 76.05, 27.15)},
    "guwahati": {"name": "Guwahati", "bbox": (91.5, 26.0, 92.0, 26.5)},
}

_active_region_key = "pune"  # persistent global, set only by set_active_region()
_region_override = threading.local()  # per-thread override, see override_active_region()


def get_active_region_key():
    """The active region — a thread-local override if one is in effect on
    *this* thread (see override_active_region), else the persistent global
    that every other thread/request sees."""
    return getattr(_region_override, "key", None) or _active_region_key


def set_active_region(key):
    """Persistently switch the active demo region for every future request
    on every thread — this is the real, user-facing switch (the
    /regions/{key} endpoint). Takes effect immediately: every consumer calls
    get_region_bbox()/get_region_name() fresh rather than importing a frozen
    constant. For a temporary, single-thread-only switch, use
    override_active_region() instead — see its docstring for why the
    distinction matters."""
    global _active_region_key
    if key not in REGIONS:
        raise ValueError(f"unknown region '{key}', choose from {list(REGIONS)}")
    _active_region_key = key


@contextlib.contextmanager
def override_active_region(key):
    """Temporarily switch the active region for the CURRENT THREAD ONLY,
    leaving the persistent global (and therefore every other in-flight
    request, which may run on a different threadpool thread) untouched.

    Exists for the background region pre-warm loop (api/main.py): warming
    region B for a ~10-20s ingest cycle must not make a concurrent request
    for region A transiently see region B's bbox — that happened in
    testing when this used a naive "save global, mutate it, restore it"
    approach instead, and a live request landed mid-warm and silently got
    the wrong region's data. threading.local() isolates it per-OS-thread,
    which is exactly the boundary FastAPI's sync-endpoint threadpool and
    this module's dedicated background thread both already respect.
    """
    if key not in REGIONS:
        raise ValueError(f"unknown region '{key}', choose from {list(REGIONS)}")
    prev = getattr(_region_override, "key", None)
    _region_override.key = key
    try:
        yield
    finally:
        if prev is None:
            del _region_override.key
        else:
            _region_override.key = prev


def get_region_bbox():
    return REGIONS[get_active_region_key()]["bbox"]


def get_region_name():
    return REGIONS[get_active_region_key()]["name"]


# Legacy static constants — frozen at import time, do NOT reflect region
# switches made after import. Kept only so nothing crashes if something still
# imports these directly; every ingestion/processing/model module in this
# project has been converted to call get_region_bbox()/get_region_name()
# instead. New code should always use the getters.
REGION_BBOX = REGIONS[_active_region_key]["bbox"]
REGION_NAME = REGIONS[_active_region_key]["name"]

# Wider weather-variable grid (temperature/humidity/wind/pressure) — always
# covers all of India, not just a box around the active region. Unlike the
# storm-scale REGION_BBOX (radar/satellite/hazards), this is a smooth
# ambient field with no per-pixel storm signature to collapse, and ECMWF
# Open Data genuinely covers the whole globe — cropping it to a small box
# was an artificial limit, not a resolution necessity. Decoupled from the
# region picker entirely: switching demo cities moves the storm-scale grid,
# this stays fixed on the whole country. 96 cells/side keeps real ECMWF
# fetch+regrid cheap (interpolation target size barely affects fetch time,
# which is dominated by GRIB download) while still looking reasonably
# smooth across a ~30x30deg extent.
WIDE_GRID_SIZE = 96
INDIA_BBOX = (68.0, 6.5, 97.5, 37.0)


def get_wide_bbox():
    return INDIA_BBOX

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
IMD_DIR = os.path.join(DATA_DIR, "imd")

# Hazard thresholds (section 4c of project.md) — documented here, not buried.
HAIL_LIGHTNING_CAT_MIN = "cat17"       # IMD hail flag category
CLOUDBURST_RAIN_RATE_MM_HR = 15.0      # IMD "very heavy rain" threshold
LIGHTNING_PROB_HIGH = 0.60             # Cat19 boundary

# Grid-based hail rule (4c): reflectivity core AND cold cloud top AND
# elevated lightning, all collocated on the fusion grid.
HAIL_REFLECTIVITY_MIN_DBZ = 55.0
HAIL_COLD_TOP_MAX_K = 210.0            # TIR-1 brightness temp, overshoot-top territory
HAIL_LIGHTNING_PROB_MIN = 0.30

# Downburst (4c): radial-velocity couplet magnitude — inbound/outbound
# delta across the storm core. Only computable with real radar velocity,
# never from a PNG overlay fallback.
DOWNBURST_VELOCITY_DELTA_MS = 25.0

INGEST_CYCLE_MINUTES = 15

# Twilio alerts configuration
ALERT_MIN_SEVERITY = os.getenv("ALERT_MIN_SEVERITY", "high")
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "60"))
