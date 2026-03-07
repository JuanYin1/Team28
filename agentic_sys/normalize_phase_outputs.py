#!/usr/bin/env python3
"""
Normalize historical phase output artifacts to current schema conventions.
"""

import json
from pathlib import Path
from typing import Any, Dict


BASE = Path(__file__).resolve().parent


def clamp01(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return value


def normalize_phase1(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("schema_version", "phase1.v2")
    return payload


def normalize_phase2(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("schema_version", "phase2.v2")
    perf = payload.get("performance_monitoring")
    if isinstance(perf, dict):
        peak = perf.get("process_peak_memory_mb", 0.0)
        avg_cpu = perf.get("process_avg_cpu", 0.0)
        thread_growth = perf.get("process_thread_growth", 0)
        if peak == 0.0 and avg_cpu == 0.0 and thread_growth == 0:
            perf["process_peak_memory_mb"] = None
            perf["process_avg_cpu"] = None
            perf["process_thread_growth"] = None
            perf["process_metrics_available"] = False
            details = perf.get("bottleneck_details")
            if isinstance(details, dict):
                process_analysis = details.get("process_analysis")
                if isinstance(process_analysis, dict):
                    process_analysis["peak_memory_mb"] = None
                    process_analysis["avg_cpu_percent"] = None
                    process_analysis["thread_growth"] = None
                    process_analysis["metrics_available"] = False
    return payload


def normalize_phase3(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload.setdefault("schema_version", "phase3.v2")
    payload.setdefault("time_breakdown", {})
    payload.setdefault("step_resource_profiles", [])

    clear_metrics = payload.get("clear_metrics")
    if isinstance(clear_metrics, dict):
        if "output_quality_score" in clear_metrics:
            clear_metrics["output_quality_score"] = clamp01(clear_metrics["output_quality_score"])

    performance = payload.get("performance")
    if isinstance(performance, dict):
        if "overall_clear_score" in performance:
            performance["overall_clear_score"] = clamp01(performance["overall_clear_score"])
        dims = performance.get("dimension_scores")
        if isinstance(dims, dict):
            for key, value in list(dims.items()):
                dims[key] = clamp01(value)

    return payload


def process_dir(dir_name: str, normalizer) -> int:
    target = BASE / dir_name
    changed = 0
    for path in sorted(target.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        before = json.dumps(payload, sort_keys=True)
        payload = normalizer(payload)
        after = json.dumps(payload, sort_keys=True)
        if before != after:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            changed += 1
    return changed


def main() -> None:
    changed = 0
    changed += process_dir("phase1", normalize_phase1)
    changed += process_dir("phase2", normalize_phase2)
    changed += process_dir("phase3", normalize_phase3)
    print(f"Normalized files: {changed}")


if __name__ == "__main__":
    main()
