from __future__ import annotations

import inspect
from typing import Any, Dict

from .adapters import (
    AgentAdapter,
    ContinueCnAdapter,
    GenericCLIAdapter,
    MiniAgentAdapter,
    MiniSweAgentAdapter,
)
from .registry import get_registration, supported_agent_cli_choices


_LEGACY_KWARG_ALIASES = {
    "mini_agent_executable": "executable",
    "mini_agent_conda_env": "conda_env",
    "mini_agent_extra_args": "extra_args",
    "continue_executable": "executable",
    "continue_agent_name": "agent_name",
    "continue_config_path": "config_path",
    "continue_model_slugs": "model_slugs",
    "continue_allow_policies": "allow_policies",
    "continue_extra_args": "extra_args",
    "mini_swe_executable": "executable",
    "mini_swe_model_name": "model_name",
    "mini_swe_config_specs": "config_specs",
    "mini_swe_extra_args": "extra_args",
}

_ADAPTER_TYPE_MAP = {
    "mini-agent": MiniAgentAdapter,
    "mini": MiniAgentAdapter,
    "continue-cn": ContinueCnAdapter,
    "continue": ContinueCnAdapter,
    "cn": ContinueCnAdapter,
    "mini-swe-agent": MiniSweAgentAdapter,
    "mini-swe": MiniSweAgentAdapter,
    "mini-swe-agent-cli": MiniSweAgentAdapter,
    "generic-cli": GenericCLIAdapter,
    "generic": GenericCLIAdapter,
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def _normalize_adapter_kwargs(raw_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in raw_kwargs.items():
        target = _LEGACY_KWARG_ALIASES.get(key, key)
        normalized[target] = value
    return normalized


def _filter_kwargs_for_callable(callable_obj, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    signature = inspect.signature(callable_obj)
    accepted = {
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY)
    }
    accepted.discard("self")
    return {
        key: value
        for key, value in kwargs.items()
        if key in accepted and _has_value(value)
    }


def create_agent_adapter(
    *,
    agent: str = "mini-agent",
    auto_detect: bool = True,
    **adapter_kwargs: Any,
) -> AgentAdapter:
    """Build an adapter from normalized CLI/config options."""

    normalized_kwargs = _normalize_adapter_kwargs(adapter_kwargs)
    adapter_type = normalized_kwargs.pop("adapter_type", None)

    adapter_cls = None
    registration_defaults: Dict[str, Any] = {}

    if _has_value(adapter_type):
        adapter_type_key = str(adapter_type).strip().lower()
        adapter_cls = _ADAPTER_TYPE_MAP.get(adapter_type_key)
        if adapter_cls is None:
            expected = ", ".join(sorted(_ADAPTER_TYPE_MAP.keys()))
            raise ValueError(
                f"Unsupported adapter type '{adapter_type}'. Expected one of: {expected}."
            )
    else:
        try:
            registration = get_registration(agent)
            adapter_cls = registration.adapter_cls
            registration_defaults = dict(registration.default_adapter_kwargs)
        except ValueError:
            has_generic_command = _has_value(normalized_kwargs.get("command"))
            has_executable = _has_value(normalized_kwargs.get("executable"))
            if not (has_generic_command or has_executable):
                raise ValueError(
                    f"Unsupported agent '{agent}'. "
                    "Add an adapter profile in config.yaml with `adapter.type: generic-cli` "
                    "and `adapter.command: [...]`."
                )
            adapter_cls = GenericCLIAdapter

    for key, default_value in registration_defaults.items():
        if not _has_value(normalized_kwargs.get(key)):
            normalized_kwargs[key] = default_value

    if adapter_cls is GenericCLIAdapter and not _has_value(normalized_kwargs.get("agent_id")):
        normalized_kwargs["agent_id"] = agent

    constructor_kwargs = _filter_kwargs_for_callable(adapter_cls.__init__, normalized_kwargs)

    auto_detect_candidate = (
        auto_detect
        and not _has_value(constructor_kwargs.get("executable"))
        and not (adapter_cls is MiniAgentAdapter and _has_value(constructor_kwargs.get("conda_env")))
        and adapter_cls is not GenericCLIAdapter
    )
    if auto_detect_candidate:
        auto_detect_kwargs = _filter_kwargs_for_callable(
            adapter_cls.auto_detect,
            constructor_kwargs,
        )
        detected = adapter_cls.auto_detect(**auto_detect_kwargs)
        detected_executable = getattr(detected, "executable", None)
        if _has_value(detected_executable):
            constructor_kwargs["executable"] = detected_executable

    if (
        adapter_cls is GenericCLIAdapter
        and not _has_value(constructor_kwargs.get("command"))
        and not _has_value(constructor_kwargs.get("executable"))
    ):
        raise ValueError(
            f"Generic adapter for '{agent}' requires `adapter.command` (or `adapter.executable`) in config.yaml."
        )

    return adapter_cls(**constructor_kwargs)
