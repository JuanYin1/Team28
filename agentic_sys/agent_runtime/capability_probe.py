from __future__ import annotations

import json
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .adapters import AgentAdapter
from .models import AgentExecutionRequest


DEFAULT_CAPABILITIES: Dict[str, Any] = {
    "structured_trace": False,
    "tool_trace": False,
    "step_trace": False,
    "timeline_events": False,
    "session_stats": False,
    "provider_cost": False,
    "token_usage": False,
    "skills_runtime": False,
    "checker_support": {
        "file_artifacts": True,
        "stdout_capture": True,
        "exit_code": True,
        "behavior_validation": True,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def normalize_capabilities(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    caps = _deep_merge(DEFAULT_CAPABILITIES, raw or {})
    normalized: Dict[str, Any] = {}
    for key, value in caps.items():
        if isinstance(value, dict):
            normalized[key] = {nested_key: bool(nested_value) for nested_key, nested_value in value.items()}
        else:
            normalized[key] = bool(value)
    return normalized


def capability_profile_path(agent_id: str, profile_dir: str = "artifacts/capability_profiles") -> Path:
    return Path(profile_dir) / f"{agent_id}.json"


def load_capability_profile(agent_id: str, profile_dir: str = "artifacts/capability_profiles") -> Optional[Dict[str, Any]]:
    path = capability_profile_path(agent_id=agent_id, profile_dir=profile_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _and_capabilities(declared: Dict[str, Any], probed: Dict[str, Any]) -> Dict[str, Any]:
    resolved: Dict[str, Any] = {}
    for key, declared_value in declared.items():
        probed_value = probed.get(key)
        if isinstance(declared_value, dict):
            nested = {}
            observed_nested = probed_value if isinstance(probed_value, dict) else {}
            for nested_key, nested_declared in declared_value.items():
                nested[nested_key] = bool(nested_declared) and bool(observed_nested.get(nested_key, False))
            resolved[key] = nested
        else:
            resolved[key] = bool(declared_value) and bool(probed_value)
    return resolved


def run_capability_probe(
    *,
    adapter: AgentAdapter,
    agent_id: str,
    declared_capabilities: Dict[str, Any],
    profile_dir: str = "artifacts/capability_profiles",
    timeout_seconds: float = 30.0,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Run lightweight runtime probes and persist a capability profile.

    Probe tasks are intentionally small and safe:
    1) artifact verification
    2) trace observability
    3) error/retry observability
    4) session stats observability
    """
    normalized_declared = normalize_capabilities(declared_capabilities)
    probed_caps = normalize_capabilities({})

    artifact_prompt = (
        "Create a file named probe_artifact.txt with content 'probe-ok', "
        "then read it and print the content."
    )
    trace_prompt = (
        "Solve in multiple explicit steps. Step 1 create a.txt, step 2 create b.txt, "
        "step 3 list files and explain what tool/action you used."
    )
    error_prompt = (
        "Run an invalid command first to trigger an error, then correct it and show success."
    )
    stats_prompt = (
        "Respond briefly and include any available session metrics such as token usage, "
        "tool calls, or duration."
    )

    probe_results = []
    prompts = [artifact_prompt, trace_prompt, error_prompt, stats_prompt]
    total_prompts = len(prompts)
    for idx, prompt in enumerate(prompts, 1):
        if progress_callback:
            progress_callback(idx, total_prompts, "start")
        with tempfile.TemporaryDirectory() as workspace:
            request = AgentExecutionRequest(
                task_prompt=prompt,
                workspace=workspace,
                timeout_seconds=timeout_seconds,
            )
            started = time.time()
            execution = adapter.run(request)
            elapsed = max(0.0, time.time() - started)
            metadata = execution.metadata if isinstance(execution.metadata, dict) else {}
            trace_chunks = metadata.get("trace_log_chunks", [])
            trace_text_parts = []
            if isinstance(trace_chunks, list):
                for chunk in trace_chunks:
                    if not isinstance(chunk, dict):
                        continue
                    text = str(chunk.get("text", "")).strip()
                    if text:
                        trace_text_parts.append(text)
            probe_results.append(
                {
                    "prompt": prompt,
                    "workspace": workspace,
                    "stdout": execution.stdout or "",
                    "stderr": execution.stderr or "",
                    "trace_text": "\n".join(trace_text_parts),
                    "success": bool(execution.success),
                    "return_code": execution.return_code,
                    "reported_duration_s": float(execution.execution_time_seconds or 0.0),
                    "wall_clock_duration_s": elapsed,
                    "artifact_exists": (Path(workspace) / "probe_artifact.txt").exists(),
                }
            )
        if progress_callback:
            progress_callback(idx, total_prompts, "done")

    all_text = "\n".join(
        (
            f"{item['stdout']}\n{item['stderr']}\n{item.get('trace_text', '')}"
            for item in probe_results
        )
    ).lower()
    artifact_probe = probe_results[0]

    probed_caps["checker_support"]["file_artifacts"] = bool(artifact_probe.get("artifact_exists"))
    probed_caps["checker_support"]["stdout_capture"] = any(item["stdout"].strip() for item in probe_results)
    probed_caps["checker_support"]["exit_code"] = any(item.get("return_code") is not None for item in probe_results)
    probed_caps["checker_support"]["behavior_validation"] = bool(
        re.search(r"(error|failed|exception).*(fix|correct|retry|success)", all_text, re.DOTALL)
    )

    step_signal = re.search(
        r"(?im)(?:\bstep\s+\d+\b|\"step\"\s*:\s*\d+|^\s*\d+\.)",
        all_text,
    )
    tool_signal = re.search(
        r"(?im)(?:\"toolname\"\s*:\s*\"[a-zA-Z_][a-zA-Z0-9_\-]*\"|"
        r"\"function\"\s*:\s*\{\s*\"name\"\s*:\s*\"[a-zA-Z_][a-zA-Z0-9_\-]*\"|"
        r"\b(write_file|read_file|bash|edit|multiedit|tool call|tool)\b)",
        all_text,
    )
    llm_signal = re.search(r"(?im)\b(thinking|reasoning|assistant|final)\b", all_text)
    error_signal = re.search(r"(?im)\b(error|traceback|exception|failed)\b", all_text)

    probed_caps["step_trace"] = bool(step_signal)
    probed_caps["tool_trace"] = bool(tool_signal)
    probed_caps["structured_trace"] = bool(
        probed_caps["step_trace"] or probed_caps["tool_trace"] or llm_signal
    )
    event_types_seen = 0
    if probed_caps["step_trace"]:
        event_types_seen += 1
    if probed_caps["tool_trace"]:
        event_types_seen += 1
    if llm_signal:
        event_types_seen += 1
    if error_signal:
        event_types_seen += 1
    probed_caps["timeline_events"] = bool(
        probed_caps["structured_trace"] and event_types_seen >= 2
    )
    probed_caps["session_stats"] = bool(
        re.search(r"(total messages|tool calls|tokens used|session duration)", all_text)
    )
    probed_caps["token_usage"] = bool(
        re.search(r"(tokens used|token usage|api tokens)", all_text)
    )
    probed_caps["provider_cost"] = bool(re.search(r"(\$|usd|cost)", all_text))
    probed_caps["skills_runtime"] = bool(re.search(r"(get_skill|skills?)", all_text))

    resolved_caps = _and_capabilities(normalized_declared, probed_caps)

    generated_at_unix = int(time.time())
    generated_at_utc = datetime.fromtimestamp(generated_at_unix, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    profile = {
        "profile_metadata": {
            "auto_generated": True,
            "do_not_edit_manually": True,
            "notice": "AUTO-GENERATED FILE. DO NOT EDIT MANUALLY. Regenerate with --refresh-capability-profile or --probe-agent.",
            "generated_at_utc": generated_at_utc,
        },
        "agent_id": agent_id,
        "declared_capabilities": normalized_declared,
        "probed_capabilities": probed_caps,
        "resolved_capabilities": resolved_caps,
        "probe_results": [
            {
                "success": item["success"],
                "return_code": item["return_code"],
                "reported_duration_s": item["reported_duration_s"],
                "wall_clock_duration_s": item["wall_clock_duration_s"],
                "artifact_exists": item["artifact_exists"],
            }
            for item in probe_results
        ],
        "generated_at_unix": generated_at_unix,
        "generated_at_utc": generated_at_utc,
    }

    path = capability_profile_path(agent_id=agent_id, profile_dir=profile_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return profile
