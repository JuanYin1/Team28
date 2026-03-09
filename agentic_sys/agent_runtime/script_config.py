from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

DEFAULT_AGENT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yaml"

_LEGACY_ADAPTER_KEY_ALIASES = {
    "mini_agent_executable": "executable",
    "mini_agent_conda_env": "conda_env",
    "mini_agent_extra_args": "extra_args",
    "continue_executable": "executable",
    "continue_agent_name": "agent_name",
    "continue_config_path": "config_path",
    "continue_model_slugs": "model_slugs",
    "continue_allow_policies": "allow_policies",
    "continue_extra_args": "extra_args",
    "type": "adapter_type",
}


_DEFAULT_EVALUATION_CAPABILITIES = {
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

_TRACE_PATTERN_KEYS = {
    "tool_call_patterns",
    "step_patterns",
    "thinking_patterns",
    "assistant_patterns",
    "error_patterns",
    "tool_result_patterns",
    "log_file_patterns",
    "detailed_log_tool_patterns",
}

_TRACE_SCALAR_KEYS = {
    "session_stats_pattern",
    "session_duration_pattern",
}


def _copy_value(value: Any) -> Any:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def _deep_merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = _copy_value(value)
    return merged


def _normalize_evaluation_capabilities(raw_caps: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    caps = _deep_merge_dicts(_DEFAULT_EVALUATION_CAPABILITIES, raw_caps or {})
    normalized: Dict[str, Any] = {}
    for key, value in caps.items():
        if isinstance(value, dict):
            normalized[key] = {nested_key: bool(nested_value) for nested_key, nested_value in value.items()}
        else:
            normalized[key] = bool(value)
    return normalized


def _normalize_trace_parser_profile(raw_profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw_profile, dict):
        return {}

    normalized: Dict[str, Any] = {}

    for key in _TRACE_PATTERN_KEYS:
        value = raw_profile.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            normalized[key] = [value]
        elif isinstance(value, list):
            normalized[key] = [str(item) for item in value if str(item).strip()]

    for key in _TRACE_SCALAR_KEYS:
        value = raw_profile.get(key)
        if value is None:
            continue
        normalized[key] = str(value)

    known_tools = raw_profile.get("known_tools")
    if isinstance(known_tools, list):
        normalized["known_tools"] = [str(item) for item in known_tools if str(item).strip()]

    tool_aliases = raw_profile.get("tool_aliases")
    if isinstance(tool_aliases, dict):
        normalized_aliases: Dict[str, str] = {}
        for alias_key, canonical_name in tool_aliases.items():
            alias = str(alias_key or "").strip()
            canonical = str(canonical_name or "").strip()
            if alias and canonical:
                normalized_aliases[alias] = canonical
        if normalized_aliases:
            normalized["tool_aliases"] = normalized_aliases

    if "enforce_known_tools" in raw_profile:
        normalized["enforce_known_tools"] = bool(raw_profile.get("enforce_known_tools"))

    return normalized


def _resolve_capability_profile_path(
    *,
    source_path: Optional[Path],
    profile_dir: str,
    agent_id: str,
) -> Path:
    root = Path(profile_dir)
    if not root.is_absolute():
        base = source_path.parent if source_path else DEFAULT_AGENT_CONFIG_PATH.parent.parent
        root = (base / root).resolve()
    return root / f"{agent_id}.json"


def _load_capability_profile(
    *,
    source_path: Optional[Path],
    profile_dir: str,
    agent_id: str,
) -> Tuple[Optional[Dict[str, Any]], Path]:
    profile_path = _resolve_capability_profile_path(
        source_path=source_path,
        profile_dir=profile_dir,
        agent_id=agent_id,
    )
    if not profile_path.exists():
        return None, profile_path

    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return None, profile_path
    if not isinstance(payload, dict):
        return None, profile_path
    return payload, profile_path


def _copy_list(value: Any) -> Optional[list]:
    if value is None:
        return None
    if isinstance(value, list):
        return list(value)
    return [value]


def _read_config_yaml(config_path: Optional[str]) -> Tuple[Dict[str, Any], Optional[Path]]:
    path = Path(config_path).expanduser() if config_path else DEFAULT_AGENT_CONFIG_PATH
    if not path.exists():
        return {}, None

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}, path
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid agent config format in {path}: expected top-level mapping.")
    return loaded, path


def read_agent_config(config_path: Optional[str] = None) -> Tuple[Dict[str, Any], Optional[Path]]:
    """
    Public helper for loading the shared agent/evaluation config YAML.

    Returns (config_mapping, source_path). Missing files return ({}, None).
    """
    return _read_config_yaml(config_path)


def _normalize_name(raw: Any) -> str:
    return str(raw or "").strip().lower().replace("_", "-")


def _resolve_agent_profile(
    config: Dict[str, Any],
    agent: str,
) -> Tuple[Dict[str, Any], Optional[str]]:
    agents = config.get("agents") or {}
    if not isinstance(agents, dict):
        return {}, None

    requested = _normalize_name(agent)
    for key, profile in agents.items():
        if isinstance(profile, dict):
            profile_names = {_normalize_name(key)}
            aliases = profile.get("aliases")
            if isinstance(aliases, list):
                for alias in aliases:
                    profile_names.add(_normalize_name(alias))
            elif isinstance(aliases, str):
                profile_names.add(_normalize_name(aliases))
            if requested in profile_names:
                return profile, str(key)
    return {}, None


def _normalize_adapter_keys(adapter_cfg: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in adapter_cfg.items():
        target = _LEGACY_ADAPTER_KEY_ALIASES.get(key, key)
        normalized[target] = _copy_value(value)
    return normalized


def _parse_adapter_option_overrides(raw_options: Optional[list]) -> Dict[str, Any]:
    if not raw_options:
        return {}

    overrides: Dict[str, Any] = {}
    for raw_option in raw_options:
        if "=" not in raw_option:
            raise ValueError(
                f"Invalid --adapter-option '{raw_option}'. Expected KEY=VALUE."
            )
        key, raw_value = raw_option.split("=", 1)
        option_key = key.strip()
        if not option_key:
            raise ValueError(
                f"Invalid --adapter-option '{raw_option}'. KEY cannot be empty."
            )
        parsed_value = yaml.safe_load(raw_value)
        overrides[option_key] = parsed_value
    return overrides


def _legacy_cli_overrides(args: Namespace) -> Dict[str, Any]:
    """
    Temporary bridge for existing Continue-specific CLI flags.

    New adapters should use --adapter-option key=value instead of adding script args.
    """
    cli_overrides: Dict[str, Any] = {}
    if hasattr(args, "continue_agent_name") and getattr(args, "continue_agent_name") is not None:
        cli_overrides["agent_name"] = getattr(args, "continue_agent_name")
    if hasattr(args, "continue_config") and getattr(args, "continue_config") is not None:
        cli_overrides["config_path"] = getattr(args, "continue_config")
    if hasattr(args, "continue_model") and getattr(args, "continue_model") is not None:
        cli_overrides["model_slugs"] = _copy_list(getattr(args, "continue_model"))
    if hasattr(args, "continue_allow") and getattr(args, "continue_allow") is not None:
        cli_overrides["allow_policies"] = _copy_list(getattr(args, "continue_allow"))
    if hasattr(args, "continue_extra_arg") and getattr(args, "continue_extra_arg") is not None:
        cli_overrides["extra_args"] = _copy_list(getattr(args, "continue_extra_arg"))
    return cli_overrides


def resolve_script_runtime_options(
    *,
    args: Namespace,
    script_name: str,
    default_results_dir: str,
) -> Tuple[str, Dict[str, Any], Optional[Path]]:
    """
    Merge CLI inputs with YAML profile defaults.

    Priority: explicit CLI overrides > config.yaml > script hardcoded defaults.
    """

    config_data, source_path = _read_config_yaml(getattr(args, "agent_config", None))
    profile, profile_key = _resolve_agent_profile(config_data, getattr(args, "agent", "mini-agent"))

    scripts_cfg = profile.get("scripts") or {}
    script_cfg = scripts_cfg.get(script_name) if isinstance(scripts_cfg, dict) else {}
    if not isinstance(script_cfg, dict):
        script_cfg = {}

    adapter_cfg = profile.get("adapter") or {}
    if not isinstance(adapter_cfg, dict):
        adapter_cfg = {}

    results_dir = getattr(args, "results_dir", None) or script_cfg.get("results_dir") or default_results_dir

    adapter_kwargs = _normalize_adapter_keys(adapter_cfg)
    normalized_profile_key = _normalize_name(profile_key)
    if "adapter_type" not in adapter_kwargs:
        if normalized_profile_key in {"mini-agent", "mini"}:
            adapter_kwargs["adapter_type"] = "mini-agent"
        elif normalized_profile_key in {"continue", "continue-cn", "cn"}:
            adapter_kwargs["adapter_type"] = "continue-cn"
        elif "command" in adapter_kwargs:
            adapter_kwargs["adapter_type"] = "generic-cli"

    needs_agent_id = (
        bool(normalized_profile_key)
        or adapter_kwargs.get("adapter_type") == "generic-cli"
        or "command" in adapter_kwargs
    )
    if needs_agent_id and "agent_id" not in adapter_kwargs:
        adapter_kwargs["agent_id"] = normalized_profile_key or _normalize_name(
            getattr(args, "agent", "mini-agent")
        )

    adapter_kwargs.update(_legacy_cli_overrides(args))
    adapter_kwargs.update(
        _parse_adapter_option_overrides(getattr(args, "adapter_option", None))
    )

    return results_dir, adapter_kwargs, source_path


def resolve_evaluation_settings(
    *,
    config_path: Optional[str] = None,
    script_name: Optional[str] = None,
    agent: Optional[str] = None,
    use_capability_profile: bool = False,
) -> Tuple[Dict[str, Any], Optional[Path]]:
    """
    Resolve evaluation settings from config.yaml.

    Precedence:
      1) evaluation.scripts.<script_name>
      2) evaluation.shared
      3) evaluation (flat keys excluding helper maps)
    """
    config_data, source_path = _read_config_yaml(config_path)
    evaluation_cfg = config_data.get("evaluation") or {}
    if not isinstance(evaluation_cfg, dict):
        return {}, source_path

    resolved: Dict[str, Any] = {}

    shared_cfg = evaluation_cfg.get("shared")
    if isinstance(shared_cfg, dict):
        resolved.update({k: _copy_value(v) for k, v in shared_cfg.items()})

    for key, value in evaluation_cfg.items():
        if key in {"shared", "scripts"}:
            continue
        resolved[key] = _copy_value(value)

    scripts_cfg = evaluation_cfg.get("scripts")
    if script_name and isinstance(scripts_cfg, dict):
        script_cfg = scripts_cfg.get(script_name)
        if isinstance(script_cfg, dict):
            resolved.update({k: _copy_value(v) for k, v in script_cfg.items()})

    if agent:
        profile, profile_key = _resolve_agent_profile(config_data, agent)
        raw_declared_caps = {}
        trace_parser_profile: Dict[str, Any] = {}
        if isinstance(profile, dict):
            maybe_caps = profile.get("evaluation_capabilities")
            if isinstance(maybe_caps, dict):
                raw_declared_caps = maybe_caps
            maybe_parser = profile.get("evaluation_trace_parser")
            if isinstance(maybe_parser, dict):
                trace_parser_profile = _normalize_trace_parser_profile(maybe_parser)
        declared_caps = _normalize_evaluation_capabilities(raw_declared_caps)

        normalized_agent = _normalize_name(profile_key or agent) or _normalize_name(agent)
        v2_cfg = resolved.get("v2") if isinstance(resolved.get("v2"), dict) else {}
        probe_cfg = v2_cfg.get("capability_probe") if isinstance(v2_cfg.get("capability_probe"), dict) else {}
        profile_dir = str(probe_cfg.get("profile_dir", "artifacts/capability_profiles"))
        profile_path = _resolve_capability_profile_path(
            source_path=source_path,
            profile_dir=profile_dir,
            agent_id=normalized_agent,
        )
        profile_payload = None
        if use_capability_profile:
            profile_payload, profile_path = _load_capability_profile(
                source_path=source_path,
                profile_dir=profile_dir,
                agent_id=normalized_agent,
            )

        probed_caps = {}
        resolved_caps = declared_caps
        if isinstance(profile_payload, dict):
            maybe_probed = profile_payload.get("probed_capabilities")
            if isinstance(maybe_probed, dict):
                probed_caps = _normalize_evaluation_capabilities(maybe_probed)
            maybe_resolved = profile_payload.get("resolved_capabilities")
            if isinstance(maybe_resolved, dict):
                resolved_caps = _normalize_evaluation_capabilities(maybe_resolved)
            elif probed_caps:
                # Conservative merge: a capability is considered resolved only if declared and probed.
                merged = _normalize_evaluation_capabilities({})
                for key, value in declared_caps.items():
                    if isinstance(value, dict):
                        merged[key] = {
                            nested_key: bool(value.get(nested_key, False)) and bool(probed_caps.get(key, {}).get(nested_key, False))
                            for nested_key in value.keys()
                        }
                    else:
                        merged[key] = bool(value) and bool(probed_caps.get(key, False))
                resolved_caps = merged

        resolved["evaluation_agent_id"] = normalized_agent
        resolved["declared_capabilities"] = declared_caps
        resolved["probed_capabilities"] = probed_caps
        resolved["resolved_capabilities"] = resolved_caps
        resolved["trace_parser_profile"] = trace_parser_profile
        resolved["capability_profile_applied"] = bool(use_capability_profile and isinstance(profile_payload, dict))
        resolved["capability_profile_path"] = str(profile_path)

    return resolved, source_path
