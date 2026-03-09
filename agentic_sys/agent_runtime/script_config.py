from __future__ import annotations

from argparse import Namespace
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


def _copy_value(value: Any) -> Any:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


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

    return resolved, source_path
