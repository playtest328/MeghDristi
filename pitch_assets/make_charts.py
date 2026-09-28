"""Generates PPT-ready PNG charts/diagrams for MeghDrishti from live backend
data. Run with the backend up at http://localhost:8000. Colors match the
dashboard's dark theme (nowcast/dashboard/src/index.css) so slides feel
consistent with the product screenshots."""
import json
import os
import urllib.request

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BG = "#0a0e16"
PANEL = "#131924"
TEXT = "#e5e7eb"
DIM = "#8a94a6"
ACCENT = "#3fb6ff"
GREEN, YELLOW, RED = "#22c55e", "#f0b429", "#ef4444"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "text.color": TEXT,
    "axes.edgecolor": DIM,
    "axes.labelcolor": TEXT,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
    "font.size": 13,
    "font.family": "sans-serif",
})


def fetch(path):
    with urllib.request.urlopen(f"http://localhost:8000{path}", timeout=30) as r:
        return json.load(r)


# ---------------------------------------------------------------- 1. severity pie
def chart_severity_pie():
    data = fetch("/hazards")
    sev = {"low": 0, "moderate": 0, "high": 0}
    for f in data["features"]:
        for h in f["properties"]["hazards"]:
            sev[h["severity"]] += 1
    total = sum(sev.values())

    fig, ax = plt.subplots(figsize=(6, 6))
    colors = [GREEN, YELLOW, RED]
    labels = [f"{k.title()}\n{v} pts" for k, v in sev.items()]
    wedges, _ = ax.pie(
        sev.values(), colors=colors, startangle=90, wedgeprops={"width": 0.42, "edgecolor": BG, "linewidth": 3},
    )
    ax.legend(wedges, labels, loc="center", frameon=False, fontsize=13, labelcolor=TEXT)
    ax.text(0, 0, "", ha="center")
    fig.suptitle(f"Live Hazard Severity Split — {total} points now", color=TEXT, fontsize=15, y=0.98)
    fig.text(0.5, 0.02, "Source: /hazards (real RainViewer + Blitzortung detections, all-India)", ha="center", color=DIM, fontsize=9)
    fig.savefig("severity_pie.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return sev, total


# ---------------------------------------------------------------- 2. type bar
def chart_type_bar():
    data = fetch("/hazards")
    types = {"hail": 0, "lightning": 0}
    for f in data["features"]:
        for h in f["properties"]["hazards"]:
            types[h["type"]] = types.get(h["type"], 0) + 1

    fig, ax = plt.subplots(figsize=(6, 4.5))
    bars = ax.bar(types.keys(), types.values(), color=[ACCENT, "#f0b429"], width=0.5)
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.3, str(int(b.get_height())),
                 ha="center", color=TEXT, fontsize=14, fontweight="bold")
    ax.set_title("Live Hazard Count by Type — All India", color=TEXT, fontsize=14)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylabel("Active points")
    fig.text(0.5, -0.02, "Source: /hazards, real detections only (no synthetic filler)", ha="center", color=DIM, fontsize=9)
    fig.savefig("type_bar.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return types


# ---------------------------------------------------------------- 3. latency bar
def chart_latency():
    import subprocess

    endpoints = ["/health", "/hazards", "/regions", "/raw-layers", "/storm-eta"]
    times = {}
    for ep in endpoints:
        # curl's own timing, not urllib's (urllib adds ~2s of fixed
        # connection-setup overhead on this Windows box that has nothing to
        # do with the server's actual processing time).
        samples = []
        for _ in range(3):
            out = subprocess.run(
                ["curl", "-s", "-o", os.devnull, "-w", "%{time_total}", f"http://localhost:8000{ep}"],
                capture_output=True, text=True,
            )
            samples.append(float(out.stdout.strip()) * 1000)
        times[ep] = min(samples)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.barh(list(times.keys()), list(times.values()), color=ACCENT)
    for b, v in zip(bars, times.values()):
        ax.text(v + 3, b.get_y() + b.get_height() / 2, f"{v:.0f} ms", va="center", color=TEXT, fontsize=11)
    ax.set_title("API Response Time — Cached All-India Endpoints", color=TEXT, fontsize=14)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("milliseconds")
    fig.text(0.5, -0.03, "Backed by a 180s server-side hazard cache — not fetched live per-request", ha="center", color=DIM, fontsize=9)
    fig.savefig("latency_bar.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return times


# ---------------------------------------------------------------- 4. data source table
def chart_data_sources():
    rows = [
        ("Hail + Lightning (/hazards)", "Always real", "RainViewer + Blitzortung"),
        ("Radar reflectivity", "Real (USE_LIVE_RADAR)", "RainViewer, IMD-sourced, all-India"),
        ("Satellite IR", "Real, region-scoped", "Copernicus Sentinel-3 SLSTR"),
        ("Temp / Humidity / Wind / Pressure", "Real (USE_LIVE_ECMWF)", "ECMWF Open Data HRES, all-India"),
        ("Rainfall estimate", "Real, derived", "Marshall-Palmer Z-R off RainViewer"),
        ("Forecast frames (pySTEPS/DGMR)", "Synthetic-input, demo box only", "No public all-India nowcast source"),
        ("Downburst / Cloudburst", "Synthetic-backed, legacy demo", "No public Doppler-velocity source"),
    ]
    fig, ax = plt.subplots(figsize=(14, 4.6))
    ax.axis("off")
    col_widths = [0.34, 0.32, 0.34]
    header = ["Layer", "Status", "Source"]
    table = ax.table(
        cellText=rows, colLabels=header, cellLoc="left", colLoc="left",
        colWidths=col_widths, loc="center", bbox=[0, 0, 1, 1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#243044")
        cell.set_facecolor(PANEL if r else "#1b2433")
        cell.set_text_props(color=TEXT if r else ACCENT, fontweight="bold" if r == 0 else "normal")
    fig.suptitle("MeghDrishti Data Sources — Real vs. Synthetic, Honestly Labeled", color=TEXT, fontsize=14, y=0.98)
    fig.savefig("data_sources_table.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------- 5. architecture diagram
def chart_architecture():
    fig, ax = plt.subplots(figsize=(13, 7.5))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7.5)
    ax.axis("off")

    def box(x, y, w, h, text, color=PANEL, textcolor=TEXT, fontsize=11, edge=ACCENT):
        r = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.12",
                            linewidth=1.6, edgecolor=edge, facecolor=color, zorder=2)
        ax.add_patch(r)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color=textcolor,
                 fontsize=fontsize, fontweight="bold", zorder=3, wrap=True)
        return (x, y, w, h)

    def arrow(b1, b2, side1="right", side2="left"):
        x1, y1, w1, h1 = b1
        x2, y2, w2, h2 = b2
        p1 = {"right": (x1 + w1, y1 + h1 / 2), "top": (x1 + w1 / 2, y1 + h1), "bottom": (x1 + w1 / 2, y1)}[side1]
        p2 = {"left": (x2, y2 + h2 / 2), "top": (x2 + w2 / 2, y2 + h2), "bottom": (x2 + w2 / 2, y2)}[side2]
        a = FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=16, color=ACCENT, linewidth=1.8, zorder=1)
        ax.add_patch(a)

    sources = [
        "RainViewer\n(radar dBZ)",
        "Blitzortung\n(lightning)",
        "ECMWF Open Data\n(wind/temp/humidity)",
        "Copernicus\nSentinel-3 (IR)",
        "IMD / Tomorrow.io\n(station obs)",
    ]
    src_boxes = []
    for i, s in enumerate(sources):
        b = box(0.3, 6.6 - i * 1.35, 2.6, 1.05, s, color="#1b2433", fontsize=9.5)
        src_boxes.append(b)

    ingest = box(3.6, 3.6, 2.2, 1.3, "Ingestion +\nFusion", color="#1e2a3f")
    hazard = box(6.4, 3.6, 2.2, 1.3, "Hazard Model\n(hazard_india.py)", color="#1e2a3f")
    api = box(9.2, 3.6, 2.2, 1.3, "FastAPI\n(nowcast/api)", color="#16324f", edge="#5fd0ff")

    web = box(9.2, 5.6, 2.2, 1.0, "Web Dashboard\n(React + MapLibre)", color="#132a1c", edge=GREEN)
    mobile = box(9.2, 1.6, 2.2, 1.0, "Mobile App\n(React Native / Kotlin)", color="#2a1f14", edge=YELLOW)

    for b in src_boxes:
        arrow(b, ingest, side1="right", side2="left")
    arrow(ingest, hazard)
    arrow(hazard, api)
    arrow(api, web, side1="right", side2="bottom")
    arrow(api, mobile, side1="right", side2="top")

    fig.suptitle("MeghDrishti — All-India Real-Time Hazard Pipeline", color=TEXT, fontsize=16, y=0.97)
    fig.savefig("architecture.png", dpi=200, bbox_inches="tight", facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------- 6. project scale stat cards
def chart_project_scale():
    """Real numbers only: lines counted from git-tracked .py/.ts/.tsx files,
    commit count from `git log`, endpoint count from a manual read of
    nowcast/api/main.py's @app.get/@app.post decorators. No estimates."""
    stats = [
        ("8,167", "lines of code\n(Python + TypeScript)"),
        ("64", "source files\n(25 backend, 39 frontend)"),
        ("16", "REST API endpoints"),
        ("5", "live external\ndata integrations"),
        ("50", "commits\n(active development)"),
    ]
    fig, axes = plt.subplots(1, len(stats), figsize=(16, 3.2))
    for ax, (value, label) in zip(axes, stats):
        ax.axis("off")
        ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=30, fontweight="bold", color=ACCENT)
        ax.text(0.5, 0.18, label, ha="center", va="center", fontsize=11, color=TEXT)
        ax.add_patch(FancyBboxPatch((0.03, 0.05), 0.94, 0.9, boxstyle="round,pad=0.02,rounding_size=0.06",
                                     transform=ax.transAxes, linewidth=1.2, edgecolor="#243044",
                                     facecolor=PANEL, zorder=-1))
    fig.suptitle("MeghDrishti — Project Scale", color=TEXT, fontsize=16, y=1.05)
    fig.savefig("project_scale.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return stats


# ---------------------------------------------------------------- 7. coverage stat cards
def chart_coverage():
    """India's land area (3.287M km^2) is a standard public figure (Survey
    of India / govt sources), not computed from the bbox — the bbox is
    larger than the country's actual outline since it's a rectangle."""
    stats = [
        ("3.29M km²", "India's area\ncovered end-to-end"),
        ("150 x 150", "hazard detection grid\n(~22 km / cell)"),
        ("15 min", "ingestion\nrefresh cycle"),
        ("180 s", "hazard cache\nrefresh (server)"),
        ("30 s", "dashboard\npoll interval"),
    ]
    fig, axes = plt.subplots(1, len(stats), figsize=(16, 3.2))
    for ax, (value, label) in zip(axes, stats):
        ax.axis("off")
        ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=26, fontweight="bold", color=GREEN)
        ax.text(0.5, 0.18, label, ha="center", va="center", fontsize=11, color=TEXT)
        ax.add_patch(FancyBboxPatch((0.03, 0.05), 0.94, 0.9, boxstyle="round,pad=0.02,rounding_size=0.06",
                                     transform=ax.transAxes, linewidth=1.2, edgecolor="#243044",
                                     facecolor=PANEL, zorder=-1))
    fig.suptitle("MeghDrishti — Coverage & Update Cadence", color=TEXT, fontsize=16, y=1.05)
    fig.savefig("coverage.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return stats


# ---------------------------------------------------------------- 8. severity threshold scale
def chart_severity_thresholds():
    """Visualizes the actual thresholds in nowcast/models/hazard_india.py:
    HAIL_MODERATE_DBZ=65.0, HAIL_HIGH_DBZ=78.0, plus the lightning-proximity
    severity bump within LIGHTNING_PROXIMITY_KM=25.0."""
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.set_xlim(30, 95)
    ax.set_ylim(0, 1)
    ax.axis("off")

    bands = [(30, 65, GREEN, "Low"), (65, 78, YELLOW, "Moderate"), (78, 95, RED, "High")]
    for x0, x1, color, label in bands:
        ax.axvspan(x0, x1, color=color, alpha=0.85, ymin=0.35, ymax=0.75)
        ax.text((x0 + x1) / 2, 0.55, label, ha="center", va="center", fontsize=13, fontweight="bold", color="#0a0e16")

    for x, label in [(65, "65 dBZ"), (78, "78 dBZ")]:
        ax.axvline(x, color=TEXT, linestyle="--", linewidth=1)
        ax.text(x, 0.85, label, ha="center", color=TEXT, fontsize=10)

    ax.text(62.5, 0.12, "+1 severity tier if a real Blitzortung lightning strike\nis within 25 km of the hail cell", ha="center", color=DIM, fontsize=10)
    ax.set_title("Hail Severity Thresholds — Reflectivity (dBZ)", color=TEXT, fontsize=14, pad=14)
    fig.savefig("severity_thresholds.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    sev, total = chart_severity_pie()
    types = chart_type_bar()
    times = chart_latency()
    chart_data_sources()
    chart_architecture()
    chart_project_scale()
    chart_coverage()
    chart_severity_thresholds()
    print("severity:", sev, "total:", total)
    print("types:", types)
    print("latency_ms:", {k: round(v, 1) for k, v in times.items()})
    print("Charts written to:", __file__)
