from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Tuple, Type

from .adapters import AgentAdapter, ContinueCnAdapter, MiniAgentAdapter


@dataclass(frozen=True)
class AgentRegistration:
    """Data-driven runtime registration entry."""

    key: str
    cli_name: str
    aliases: Tuple[str, ...]
    adapter_cls: Type[AgentAdapter]
    default_adapter_kwargs: Mapping[str, Any] = field(default_factory=dict)

    def all_names(self) -> Tuple[str, ...]:
        # Include canonical key and stable CLI name in alias matching.
        return (self.key, self.cli_name, *self.aliases)


AGENT_REGISTRY: Dict[str, AgentRegistration] = {
    "mini-agent": AgentRegistration(
        key="mini-agent",
        cli_name="mini-agent",
        aliases=("mini",),
        adapter_cls=MiniAgentAdapter,
        default_adapter_kwargs={"executable": "mini-agent"},
    ),
    "continue-cn": AgentRegistration(
        key="continue-cn",
        cli_name="continue",
        aliases=("continue", "cn"),
        adapter_cls=ContinueCnAdapter,
        default_adapter_kwargs={"config_path": "continuedev/default-cli-config"},
    ),
}


def iter_registrations() -> Iterable[AgentRegistration]:
    return AGENT_REGISTRY.values()


def supported_agent_cli_choices() -> list[str]:
    return [registration.cli_name for registration in iter_registrations()]


def canonicalize_agent(agent: str) -> str:
    normalized = (agent or "").strip().lower()
    if not normalized:
        raise ValueError("Agent name cannot be empty.")
    for registration in iter_registrations():
        names = {value.strip().lower() for value in registration.all_names() if value}
        if normalized in names:
            return registration.key
    expected = ", ".join(supported_agent_cli_choices())
    raise ValueError(f"Unsupported agent '{agent}'. Expected one of: {expected}.")


def get_registration(agent: str) -> AgentRegistration:
    return AGENT_REGISTRY[canonicalize_agent(agent)]
