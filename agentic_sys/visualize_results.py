#!/usr/bin/env python3
"""
Agent CLEAR Evaluation Visualizer
========================================
Generates detailed charts for per-step resource usage and execution time from
the JSON result files produced by clear_evaluation_system.py.

Usage:
    # auto-pick the latest run in artifacts/<agent>/phase3/ and generate all task dashboards
    python visualize_results.py

    # specific file
    python visualize_results.py artifacts/mini-agent/phase3/mini_agent_simple_file_operations_*.json

    # multiple files (generates per-file dashboard + comparison chart)
    python visualize_results.py artifacts/mini-agent/phase3/result_a.json artifacts/mini-agent/phase3/result_b.json

Outputs a PNG file next to each input JSON, plus an optional comparison PNG.
"""

import json
import sys
import argparse
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from glob import glob

from agent_runtime.script_config import read_agent_config, resolve_script_runtime_options

plt = None
mpatches = None
GridSpec = None
np = None

_PLOT_ENV_SENTINEL = "TEAM28_PLOT_ENV_READY"


def _configure_scientific_runtime_env() -> None:
    """
    Keep plotting imports in a single-threaded/serial mode.

    On this machine, NumPy/Matplotlib can load Intel OpenMP and fail with
    SHM-related runtime errors when trying to initialize shared-memory worker
    state. Setting these defaults before import keeps visualization stable.
    """
    defaults = {
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "KMP_LIBRARY": "serial",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def _ensure_subprocess_safe_plot_env() -> None:
    """
    Re-exec once with plotting-safe env vars applied from process start.

    Some MKL/OpenMP builds read thread/runtime settings before Python-level lazy
    imports happen. Re-executing early gives those libraries a clean process
    environment and avoids SHM initialization crashes on restricted machines.
    """
    if os.environ.get(_PLOT_ENV_SENTINEL) == "1":
        return
    _configure_scientific_runtime_env()
    os.environ[_PLOT_ENV_SENTINEL] = "1"
    os.execvpe(sys.executable, [sys.executable, *sys.argv], os.environ)


def _ensure_plotting_deps() -> None:
    global plt, mpatches, GridSpec, np
    if plt is not None and np is not None and GridSpec is not None and mpatches is not None:
        return
    _configure_scientific_runtime_env()
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as _plt
        import matplotlib.patches as _mpatches
        from matplotlib.gridspec import GridSpec as _GridSpec
        import numpy as _np
    except ImportError:
        print("Required packages not found. Install with:  pip install matplotlib numpy")
        sys.exit(1)
    plt = _plt
    mpatches = _mpatches
    GridSpec = _GridSpec
    np = _np

# ---------------------------------------------------------------------------
# Colour palette (pure ASCII string keys)
# ---------------------------------------------------------------------------
EVENT_COLORS = {
    "thinking":           "#4A90D9",
    "assistant_response": "#7B68EE",
    "tool_call":          "#F5A623",
    "tool_result":        "#52C41A",
    "success":            "#52C41A",
    "error":              "#D0021B",
    "init":               "#AAAAAA",
}
PHASE_COLORS = {
    "llm_inference":  "#4A90D9",
    "tool_execution": "#F5A623",
    "coordination":   "#9B9B9B",
    "init":           "#CCCCCC",
}
CLEAR_COLORS = {
    "cost":        "#2ECC71",
    "latency":     "#3498DB",
    "efficiency":  "#9B59B6",
    "assurance":   "#E67E22",
    "reliability": "#E74C3C",
}
MARKER_MAP = {
    "thinking":           "D",
    "assistant_response": "s",
    "tool_call":          "^",
    "tool_result":        "o",
    "success":            "o",
    "error":              "X",
    "init":               ".",
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_result(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_visualizable_result_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    test_case = payload.get("test_case")
    performance = payload.get("performance")
    if not isinstance(test_case, dict) or not isinstance(performance, dict):
        return False
    return "name" in test_case and "overall_clear_score" in performance


def _is_visualizable_result_file(path: Path) -> bool:
    if path.name.endswith("_run_manifest.json") or "_run_manifest_" in path.name:
        return False
    try:
        return _is_visualizable_result_payload(load_result(path))
    except Exception:
        return False


def latest_result(results_dir: Path = Path("phase3")) -> Optional[Path]:
    files = sorted(
        (path for path in results_dir.glob("*.json") if _is_visualizable_result_file(path)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def latest_run_manifest(results_dir: Path = Path("phase3")) -> Optional[Path]:
    manifests = sorted(
        (
            path
            for path in results_dir.glob("*_run_manifest_*.json")
            if path.is_file()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return manifests[0] if manifests else None


def result_files_from_manifest(manifest_path: Path) -> List[Path]:
    try:
        payload = load_result(manifest_path)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return []

    resolved: List[Path] = []
    seen = set()
    base_dir = manifest_path.parent
    for rel in artifacts:
        candidate = (base_dir / str(rel)).resolve()
        if not candidate.exists():
            continue
        if not _is_visualizable_result_file(candidate):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        resolved.append(candidate)
    return resolved


def _step_spans(profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert the flat event list into Gantt-ready span records.

    Each span: { step (str), phase (str), start_s (float), end_s (float) }
    Phases: 'init', 'llm', 'tool', 'coordination'
    """
    spans: List[Dict[str, Any]] = []

    # -- init phase (step == null) -----------------------------------------
    null_events = sorted(
        [p for p in profiles if p.get("step") is None],
        key=lambda e: e["time_offset_s"],
    )
    if null_events:
        spans.append({
            "step": "Init",
            "phase": "init",
            "start_s": null_events[0]["time_offset_s"],
            "end_s":   null_events[-1]["time_offset_s"],
        })
        prev_end = null_events[-1]["time_offset_s"]
    else:
        prev_end = 0.0

    # -- numbered steps -------------------------------------------------------
    numbered = sorted(set(p["step"] for p in profiles if p.get("step") is not None))
    for step_num in numbered:
        step_events = sorted(
            [p for p in profiles if p.get("step") == step_num],
            key=lambda e: e["time_offset_s"],
        )
        by_type: Dict[str, List[float]] = {}
        for e in step_events:
            by_type.setdefault(e["event_type"], []).append(e["time_offset_s"])

        step_start = step_events[0]["time_offset_s"]

        # coordination gap before this step
        if step_start > prev_end + 0.05:
            spans.append({
                "step": "Step %d" % step_num,
                "phase": "coordination",
                "start_s": prev_end,
                "end_s":   step_start,
            })

        think_t   = min(by_type.get("thinking",           [step_start]))
        resp_t    = min(by_type.get("assistant_response", [think_t]))
        success_t = max(
            by_type.get("tool_result", [resp_t]) +
            by_type.get("success",     [resp_t]) +  # backward compatibility
            by_type.get("tool_call",   [resp_t])
        )

        if resp_t > think_t:
            spans.append({
                "step": "Step %d" % step_num,
                "phase": "llm",
                "start_s": think_t,
                "end_s":   resp_t,
            })
        if success_t > resp_t:
            spans.append({
                "step": "Step %d" % step_num,
                "phase": "tool",
                "start_s": resp_t,
                "end_s":   success_t,
            })

        prev_end = step_events[-1]["time_offset_s"]

    return spans


# ---------------------------------------------------------------------------
# Individual chart functions
# ---------------------------------------------------------------------------

def plot_time_breakdown_bar(ax: Any, result: Dict[str, Any]) -> None:
    """Horizontal stacked bar: LLM / Tool / Coordination."""
    bd = result.get("time_breakdown", {})
    if not bd:
        ax.text(0.5, 0.5, "No time breakdown data",
                ha="center", va="center", transform=ax.transAxes, color="#888")
        ax.set_title("Execution Time Breakdown", fontsize=11)
        return

    keys = [
        ("llm_inference_s",  "LLM Inference",  PHASE_COLORS["llm_inference"]),
        ("tool_execution_s", "Tool Execution", PHASE_COLORS["tool_execution"]),
        ("coordination_s",   "Coordination",   PHASE_COLORS["coordination"]),
    ]
    values = {}
    for key, _, _ in keys:
        raw_value = bd.get(key, 0)
        values[key] = raw_value if isinstance(raw_value, (int, float)) and raw_value is not None else 0.0
    total = sum(values[k] for k, _, _ in keys) or 1.0

    left = 0.0
    for key, label, color in keys:
        val = values[key]
        pct = val / total * 100
        ax.barh(0, val, left=left, color=color,
                edgecolor="white", linewidth=1.5, height=0.5)
        if pct > 4:
            ax.text(
                left + val / 2, 0,
                "%s\n%.1fs  (%.0f%%)" % (label, val, pct),
                ha="center", va="center",
                fontsize=8.5, fontweight="bold", color="white",
            )
        left += val

    ax.set_xlim(0, total * 1.03)
    ax.set_ylim(-0.5, 0.5)
    ax.set_xlabel("Seconds", fontsize=9)
    ax.set_yticks([])
    ax.set_title(
        "Execution Time Breakdown  (total %.1fs)\n"
        "LLM events: %d  |  Tool events: %d  |  Coord events: %d  |  method: %s"
        % (
            total,
            bd.get("llm_events", 0),
            bd.get("tool_events", 0),
            bd.get("coord_events", 0),
            bd.get("method", "n/a"),
        ),
        fontsize=10,
    )
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)


def _numeric_value(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and value is not None:
        return float(value)
    return float(default)


def plot_clear_radar(ax: Any, result: Dict[str, Any]) -> None:
    """Radar / spider chart for the 5 CLEAR dimension scores."""
    dims = result.get("performance", {}).get("dimension_scores", {})
    if not dims:
        ax.text(0.5, 0.5, "No dimension scores",
                ha="center", va="center", transform=ax.transAxes)
        return

    categories = list(dims.keys())
    N = len(categories)
    values = [dims[c] for c in categories] + [dims[categories[0]]]
    angles = [n / N * 2 * np.pi for n in range(N)] + [0]

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([c.capitalize() for c in categories], size=8)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], size=6, color="gray")
    ax.set_rlabel_position(30)

    ax.plot(angles, values, color="#4A90D9", linewidth=2)
    ax.fill(angles, values, color="#4A90D9", alpha=0.25)

    for angle, val in zip(angles[:-1], values[:-1]):
        ax.text(angle, val + 0.12, "%.2f" % val,
                ha="center", va="center", size=7.5, color="#222")

    overall = result.get("performance", {}).get("overall_clear_score", 0)
    passed  = result.get("performance", {}).get("passed_thresholds", False)
    status  = "PASS" if passed else "FAIL"
    color   = "#2ECC71" if passed else "#E74C3C"
    ax.set_title(
        "CLEAR Dimensions\nScore: %.3f  [%s]" % (overall, status),
        fontsize=10, pad=15, color=color, fontweight="bold",
    )


def plot_gantt_timeline(ax: Any, result: Dict[str, Any]) -> None:
    """
    Gantt-style timeline.
    Y-axis = step, X-axis = wall-clock offset (seconds).
    Bars show LLM / tool / coordination phases; markers show individual events.
    """
    profiles = result.get("step_resource_profiles", [])
    total_t  = result.get("clear_metrics", {}).get("total_task_time", 30) or 30

    if not profiles:
        ax.text(0.5, 0.5, "No step resource profiles",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Per-Step Execution Timeline (Gantt)", fontsize=11)
        return

    spans = _step_spans(profiles)

    # Build ordered y-axis labels
    y_labels: List[str] = []
    seen_labels = set()
    for s in spans:
        lbl = s["step"]
        if lbl not in seen_labels:
            seen_labels.add(lbl)
            y_labels.append(lbl)

    y_map = {lbl: i for i, lbl in enumerate(y_labels)}
    bar_h = 0.55

    phase_label = {
        "llm":          "LLM Inference",
        "tool":         "Tool Execution",
        "coordination": "Coordination Gap",
        "init":         "Initialization",
    }
    phase_color = {
        "llm":          PHASE_COLORS["llm_inference"],
        "tool":         PHASE_COLORS["tool_execution"],
        "coordination": PHASE_COLORS["coordination"],
        "init":         PHASE_COLORS["init"],
    }
    legend_handles: Dict[str, mpatches.Patch] = {}

    for span in spans:
        phase = span["phase"]
        y     = y_map[span["step"]]
        start = span["start_s"]
        width = max(span["end_s"] - span["start_s"], 0.05)
        color = phase_color.get(phase, "#CCC")
        alpha = 0.50 if phase == "coordination" else 0.88

        ax.barh(y, width, left=start, height=bar_h,
                color=color, edgecolor="white", linewidth=0.8, alpha=alpha)
        if width > 0.8:
            ax.text(start + width / 2, y, "%.1fs" % width,
                    ha="center", va="center",
                    fontsize=7.5, fontweight="bold", color="white")

        if phase not in legend_handles:
            legend_handles[phase] = mpatches.Patch(
                color=color, alpha=alpha, label=phase_label.get(phase, phase)
            )

    # Event markers on top of bars
    for p in profiles:
        step  = p.get("step")
        etype = p["event_type"]
        t     = p["time_offset_s"]
        lbl   = "Init" if step is None else "Step %d" % step
        if lbl not in y_map:
            continue
        ax.scatter(t, y_map[lbl],
                   c=EVENT_COLORS.get(etype, "#444"),
                   marker=MARKER_MAP.get(etype, "o"),
                   s=50, zorder=5, edgecolors="white", linewidths=0.4)

    # Vertical grid every 5 s
    for t_g in range(0, int(total_t) + 6, 5):
        ax.axvline(t_g, color="#e8e8e8", linewidth=0.6, zorder=0)
        ax.text(t_g, len(y_labels) - 0.2, "%ds" % t_g,
                ha="center", va="bottom", fontsize=7, color="#999")

    ax.set_xlim(-0.5, total_t * 1.04)
    ax.set_ylim(-0.6, len(y_labels) - 0.4)
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels, fontsize=9)
    ax.set_xlabel("Wall-clock offset from task start (seconds)", fontsize=9)
    ax.set_title(
        "Per-Step Execution Timeline  --  %d events  |  total %.1fs"
        % (len(profiles), total_t),
        fontsize=11,
    )
    ax.legend(
        handles=list(legend_handles.values()),
        loc="lower right", fontsize=8, framealpha=0.9,
        ncol=min(4, len(legend_handles)),
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_resource_over_time(ax: Any, result: Dict[str, Any],
                             resource: str = "memory_mb") -> None:
    """Line chart of memory_mb or cpu_percent across all timeline events."""
    profiles = result.get("step_resource_profiles", [])
    if not profiles:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        return

    times  = [p["time_offset_s"] for p in profiles]
    values = [p.get(resource, 0) for p in profiles]
    etypes = [p["event_type"] for p in profiles]

    is_mem   = resource == "memory_mb"
    line_col = "#4A90D9" if is_mem else "#E67E22"
    label    = "Memory (MB)" if is_mem else "CPU Usage (%)"

    ax.plot(times, values, color=line_col, linewidth=1.6, alpha=0.7, zorder=2)
    ax.fill_between(times, values, alpha=0.12, color=line_col)

    for t, v, et in zip(times, values, etypes):
        ax.scatter(t, v,
                   c=EVENT_COLORS.get(et, "#888"),
                   s=35, zorder=4, edgecolors="white", linewidths=0.4)

    if values:
        vmax = max(values)
        imax = values.index(vmax)
        ax.annotate(
            "max %.1f" % vmax,
            xy=(times[imax], vmax),
            xytext=(0, 8), textcoords="offset points",
            ha="center", fontsize=7.5, color=line_col, fontweight="bold",
        )

    total_t = result.get("clear_metrics", {}).get("total_task_time", 30) or 30
    ax.set_xlim(0, total_t * 1.04)
    ax.set_xlabel("Time offset (s)", fontsize=9)
    ax.set_ylabel(label, fontsize=9)
    ax.set_title(label + " Over Time", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_event_distribution(ax: Any, result: Dict[str, Any]) -> None:
    """Horizontal bar chart: count of each event type."""
    profiles = result.get("step_resource_profiles", [])
    if not profiles:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        return

    counts: Dict[str, int] = {}
    for p in profiles:
        et = p["event_type"]
        counts[et] = counts.get(et, 0) + 1

    labels = list(counts.keys())
    vals   = [counts[l] for l in labels]
    colors = [EVENT_COLORS.get(l, "#888") for l in labels]

    bars = ax.barh(labels, vals, color=colors, edgecolor="white", linewidth=0.8, height=0.5)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                str(val), ha="left", va="center", fontsize=9, fontweight="bold")

    ax.set_xlabel("Event Count", fontsize=9)
    ax.set_title("Event Type Distribution", fontsize=10)
    ax.set_xlim(0, max(vals) * 1.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_step_duration_breakdown(ax: Any, result: Dict[str, Any]) -> None:
    """
    Grouped bar per step: LLM thinking time vs Tool/response time.
    Derived directly from event timestamps.
    """
    profiles = result.get("step_resource_profiles", [])
    numbered = sorted(set(p["step"] for p in profiles if p.get("step") is not None))
    if not numbered:
        ax.text(0.5, 0.5, "No per-step data",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Per-Step Duration Breakdown", fontsize=10)
        return

    step_labels: List[str] = []
    llm_times:   List[float] = []
    tool_times:  List[float] = []
    total_times: List[float] = []

    for sn in numbered:
        evts = sorted([p for p in profiles if p.get("step") == sn],
                      key=lambda e: e["time_offset_s"])
        by_type: Dict[str, List[float]] = {}
        for e in evts:
            by_type.setdefault(e["event_type"], []).append(e["time_offset_s"])

        step_start = evts[0]["time_offset_s"]
        step_end   = evts[-1]["time_offset_s"]

        think_t   = min(by_type.get("thinking",           [step_start]))
        resp_t    = min(by_type.get("assistant_response", [think_t]))
        success_t = max(
            by_type.get("tool_result", [resp_t]) +
            by_type.get("success",     [resp_t]) +  # backward compatibility
            by_type.get("tool_call",   [resp_t])
        )

        step_labels.append("Step %d" % sn)
        llm_times.append(max(resp_t - think_t, 0))
        tool_times.append(max(success_t - resp_t, 0))
        total_times.append(step_end - step_start)

    x = np.arange(len(step_labels))
    w = 0.28

    ax.bar(x - w, llm_times,  w * 2, label="LLM Thinking",
           color=PHASE_COLORS["llm_inference"],  edgecolor="white", linewidth=0.7)
    ax.bar(x + w, tool_times, w * 2, label="Tool / Response",
           color=PHASE_COLORS["tool_execution"], edgecolor="white", linewidth=0.7)

    ax.scatter(x, total_times, color="#333", zorder=5, s=40, label="Total step time")
    for xi, tt in zip(x, total_times):
        ax.text(xi, tt + 0.1, "%.1fs" % tt,
                ha="center", va="bottom", fontsize=7.5, color="#333")

    ax.set_xticks(x)
    ax.set_xticklabels(step_labels, fontsize=9)
    ax.set_ylabel("Duration (seconds)", fontsize=9)
    ax.set_title("Per-Step Duration:  LLM Thinking  vs  Tool Execution", fontsize=10)
    ax.legend(fontsize=8, loc="upper left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


# ---------------------------------------------------------------------------
# Dashboard assembler
# ---------------------------------------------------------------------------

def generate_dashboard(result: Dict[str, Any], output_path: Path) -> None:
    """
    Full 4-row dashboard:
      Row 1:  Execution time breakdown  |  CLEAR radar
      Row 2:  Gantt timeline (full width)
      Row 3:  Per-step LLM vs Tool bar  |  Event type distribution
      Row 4:  Memory over time  |  CPU over time
    """
    test_name   = result.get("test_case", {}).get("name", "unknown")
    total_t     = result.get("clear_metrics", {}).get("total_task_time", 0)
    clear_score = result.get("performance", {}).get("overall_clear_score", 0)
    passed      = result.get("performance", {}).get("passed_thresholds", False)
    status_str  = "PASS" if passed else "FAIL"
    title_color = "#2ECC71" if passed else "#E74C3C"

    fig = plt.figure(figsize=(18, 20))
    fig.patch.set_facecolor("#FAFAFA")
    fig.suptitle(
        "Agent Runtime -- Execution Analysis Dashboard\n"
        "Test: %s   |   Total time: %.1fs   |   CLEAR Score: %.3f  [%s]"
        % (test_name, total_t, clear_score, status_str),
        fontsize=13, fontweight="bold", y=0.99,
        color=title_color,
    )

    gs = GridSpec(4, 2, figure=fig, hspace=0.50, wspace=0.35,
                  left=0.07, right=0.97, top=0.95, bottom=0.04)

    ax_breakdown = fig.add_subplot(gs[0, 0])
    ax_radar     = fig.add_subplot(gs[0, 1], polar=True)
    ax_gantt     = fig.add_subplot(gs[1, :])
    ax_step_dur  = fig.add_subplot(gs[2, 0])
    ax_evt_dist  = fig.add_subplot(gs[2, 1])
    ax_mem       = fig.add_subplot(gs[3, 0])
    ax_cpu       = fig.add_subplot(gs[3, 1])

    plot_time_breakdown_bar(ax_breakdown, result)
    plot_clear_radar(ax_radar, result)
    plot_gantt_timeline(ax_gantt, result)
    plot_step_duration_breakdown(ax_step_dur, result)
    plot_event_distribution(ax_evt_dist, result)
    plot_resource_over_time(ax_mem, result, resource="memory_mb")
    plot_resource_over_time(ax_cpu, result, resource="cpu_percent")

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#FAFAFA")
    plt.close(fig)
    print("  Dashboard saved -> %s" % output_path)


# ---------------------------------------------------------------------------
# Comparison dashboard (multiple test results)
# ---------------------------------------------------------------------------

def generate_comparison(results: List[Dict[str, Any]], labels: List[str],
                         output_path: Path) -> None:
    """Side-by-side comparison of multiple test results."""
    n = len(results)
    if n == 0:
        return

    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.suptitle("Agent Runtime -- Multi-Test Comparison Dashboard",
                 fontsize=14, fontweight="bold")

    # -- Grouped bar: time breakdown ------------------------------------------
    ax = axes[0, 0]
    x  = np.arange(n)
    w  = 0.25
    llm_vals   = [_numeric_value(r.get("time_breakdown", {}).get("llm_inference_s", 0)) for r in results]
    tool_vals  = [_numeric_value(r.get("time_breakdown", {}).get("tool_execution_s", 0)) for r in results]
    coord_vals = [_numeric_value(r.get("time_breakdown", {}).get("coordination_s", 0)) for r in results]

    ax.bar(x - w, llm_vals,   w * 1.9, label="LLM Inference",
           color=PHASE_COLORS["llm_inference"],  edgecolor="white")
    ax.bar(x,     tool_vals,  w * 1.9, label="Tool Execution",
           color=PHASE_COLORS["tool_execution"], edgecolor="white")
    ax.bar(x + w, coord_vals, w * 1.9, label="Coordination",
           color=PHASE_COLORS["coordination"],   edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Seconds")
    ax.set_title("Execution Time Breakdown Comparison")
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # -- CLEAR dimension lines ------------------------------------------------
    ax = axes[0, 1]
    dim_keys = ["cost", "latency", "efficiency", "assurance", "reliability"]
    for i, dk in enumerate(dim_keys):
        vals = [_numeric_value(r.get("performance", {}).get("dimension_scores", {}).get(dk, 0))
                for r in results]
        col  = list(CLEAR_COLORS.values())[i]
        ax.plot(labels, vals, marker="o", label=dk.capitalize(), color=col, linewidth=1.8)
        for xi, v in enumerate(vals):
            ax.text(xi, v + 0.02, "%.2f" % v, ha="center", fontsize=7, color=col)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Score (0-1)")
    ax.set_title("CLEAR Dimension Scores Comparison")
    ax.legend(fontsize=8, loc="lower right")
    ax.tick_params(axis="x", rotation=30)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # -- Steps & tools --------------------------------------------------------
    ax = axes[1, 0]
    steps = [_numeric_value(r.get("clear_metrics", {}).get("steps_to_completion", 0)) for r in results]
    tools = [_numeric_value(len(r.get("execution", {}).get("tools_used", []))) for r in results]
    ax.bar(x - 0.2, steps, 0.35, label="Steps",        color="#9B59B6", edgecolor="white")
    ax.bar(x + 0.2, tools, 0.35, label="Unique Tools", color="#1ABC9C", edgecolor="white")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Count")
    ax.set_title("Steps & Unique Tool Usage Comparison")
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # -- Overall CLEAR score bar ----------------------------------------------
    ax = axes[1, 1]
    scores = [_numeric_value(r.get("performance", {}).get("overall_clear_score", 0)) for r in results]
    colors = [
        "#2ECC71" if r.get("performance", {}).get("passed_thresholds") else "#E74C3C"
        for r in results
    ]
    bars = ax.bar(x, scores, color=colors, edgecolor="white", linewidth=0.8)
    for bar, score in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                "%.3f" % score, ha="center", va="bottom",
                fontsize=8.5, fontweight="bold")
    ax.axhline(0.7, color="#888", linestyle="--", linewidth=1.2,
               label="Pass threshold (0.7)")
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Overall CLEAR Score")
    ax.set_title("Overall CLEAR Score Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("  Comparison chart saved -> %s" % output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Visualize Agent CLEAR evaluation JSON results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--agent",
        default="mini-agent",
        help="Agent whose phase3 results dir should be used when no files are specified.",
    )
    p.add_argument(
        "--agent-config",
        default=None,
        help="Optional path to agent config YAML (defaults to config/config.yaml).",
    )
    p.add_argument(
        "files", nargs="*",
        help="JSON result file(s). Defaults to all task result JSON files from the latest run manifest for --agent.",
    )
    p.add_argument(
        "--results-dir", default=None,
        help="Directory to search when no files are specified. Overrides config.yaml.",
    )
    return p.parse_args()


def _resolve_visualization_settings(args: argparse.Namespace) -> tuple[str, str]:
    results_dir, _, _ = resolve_script_runtime_options(
        args=args,
        script_name="phase3",
        default_results_dir="artifacts/mini-agent/phase3",
    )
    config_data, _ = read_agent_config(getattr(args, "agent_config", None))
    visualization_cfg = config_data.get("visualization") or {}
    if not isinstance(visualization_cfg, dict):
        visualization_cfg = {}
    comparison_filename = str(
        visualization_cfg.get("comparison_filename", "comparison_dashboard.png")
    ).strip() or "comparison_dashboard.png"
    return results_dir, comparison_filename


def main() -> None:
    _ensure_subprocess_safe_plot_env()
    args = parse_args()
    resolved_results_dir, comparison_filename = _resolve_visualization_settings(args)
    results_dir = args.results_dir or resolved_results_dir
    _ensure_plotting_deps()

    if args.files:
        expanded: List[Path] = []
        for pattern in args.files:
            matched = [Path(p) for p in glob(pattern)]
            expanded.extend(matched if matched else [Path(pattern)])
        paths = expanded
    else:
        manifest = latest_run_manifest(Path(results_dir))
        if manifest is not None:
            paths = result_files_from_manifest(manifest)
        else:
            found = latest_result(Path(results_dir))
            paths = [found] if found is not None else []
        if not paths:
            print("No visualizable task result JSON files found in %s/" % results_dir)
            sys.exit(1)

    print("\nVisualizing %d result file(s):\n" % len(paths))

    results: List[Dict[str, Any]] = []
    labels:  List[str]            = []

    for path in paths:
        path = Path(path)
        if not path.exists():
            print("  [skip] file not found: %s" % path)
            continue
        print("  Loading: %s" % path.name)
        result = load_result(path)
        if not _is_visualizable_result_payload(result):
            print("  [skip] not a task result JSON: %s" % path.name)
            continue
        results.append(result)
        labels.append(result.get("test_case", {}).get("name", path.stem)[:30])

        out_path = path.with_suffix(".png")
        generate_dashboard(result, out_path)

    if not results:
        print("\nNo visualizable task result JSON files were found.")
        sys.exit(1)

    if len(results) > 1:
        if args.files:
            parent_dirs = {Path(p).parent.resolve() for p in paths if Path(p).exists()}
            comp_dir = parent_dirs.pop() if len(parent_dirs) == 1 else Path.cwd()
        else:
            comp_dir = Path(results_dir)
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_path = comp_dir / comparison_filename
        print("\n  Generating comparison dashboard for %d results..." % len(results))
        generate_comparison(results, labels, comp_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
