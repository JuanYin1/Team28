from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .adapters import AgentAdapter, ContinueCnAdapter, GenericCLIAdapter, MiniAgentAdapter, MiniSweAgentAdapter


@dataclass
class SafeHealthcheckReport:
    success: bool
    command: List[str]
    return_code: Optional[int]
    stdout: str = ""
    stderr: str = ""


def build_safe_healthcheck_command(adapter: AgentAdapter) -> List[str]:
    """
    Build a non-billing healthcheck command for an adapter.

    This intentionally avoids prompt/task execution so it does not trigger model
    inference or credit usage.
    """
    if isinstance(adapter, MiniAgentAdapter):
        if adapter.conda_env:
            return ["conda", "run", "-n", adapter.conda_env, adapter.executable, "--version"]
        return [adapter.executable, "--version"]

    if isinstance(adapter, ContinueCnAdapter):
        return [adapter.executable, "--version"]

    if isinstance(adapter, MiniSweAgentAdapter):
        return [adapter.executable, "--help"]

    if isinstance(adapter, GenericCLIAdapter):
        executable = adapter.executable or (adapter.command[0] if adapter.command else adapter.agent_id)
        return [str(executable), "--help"]

    return [adapter.process_name_hint, "--version"]


def run_safe_healthcheck(adapter: AgentAdapter, *, timeout_seconds: float = 10.0) -> SafeHealthcheckReport:
    cmd = build_safe_healthcheck_command(adapter)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
        )
        return SafeHealthcheckReport(
            success=result.returncode == 0,
            command=cmd,
            return_code=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )
    except Exception as exc:
        return SafeHealthcheckReport(
            success=False,
            command=cmd,
            return_code=None,
            stderr=f"Execution error: {exc}",
        )
