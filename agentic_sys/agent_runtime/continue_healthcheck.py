from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from .adapters import ContinueCnAdapter
from .models import AgentExecutionRequest, AgentExecutionResult


@dataclass
class ContinueHealthcheckReport:
    success: bool
    diagnosis: str
    executable: Optional[str] = None
    command: List[str] = field(default_factory=list)
    return_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""


def diagnose_continue_result(result: AgentExecutionResult) -> str:
    if result.success and (result.stdout or "").strip():
        return "ok"

    stderr = (result.stderr or "").lower()
    if "no credits remaining" in stderr:
        return "account_credits_exhausted"
    if "interceptors did not return an alternative response" in stderr:
        return "auth_or_model_not_configured"
    if "response returned an error code" in stderr:
        return "upstream_provider_error"
    if "fetch failed" in stderr:
        return "network_or_proxy_error"
    if result.timed_out:
        return "timeout"
    if "execution error" in stderr:
        return "execution_failure"
    if result.success and not (result.stdout or "").strip():
        return "empty_output"
    return "unknown_failure"


def run_continue_healthcheck(
    *,
    executable: Optional[str] = None,
    agent_name: Optional[str] = None,
    config_path: Optional[str] = "continuedev/default-cli-config",
    model_slugs: Optional[List[str]] = None,
    allow_policies: Optional[List[str]] = None,
    extra_args: Optional[List[str]] = None,
    prompt: str = "Reply with exactly OK and nothing else.",
    timeout_seconds: float = 45.0,
) -> ContinueHealthcheckReport:
    try:
        if executable:
            adapter = ContinueCnAdapter(
                executable=executable,
                agent_name=agent_name,
                config_path=config_path,
                model_slugs=model_slugs,
                allow_policies=allow_policies,
                extra_args=extra_args,
            )
        else:
            adapter = ContinueCnAdapter.auto_detect(
                agent_name=agent_name,
                config_path=config_path,
                model_slugs=model_slugs,
            )
            adapter.allow_policies = list(allow_policies or [])
            adapter.extra_args = list(extra_args or [])
    except RuntimeError as exc:
        return ContinueHealthcheckReport(
            success=False,
            diagnosis="binary_not_found",
            stderr=str(exc),
        )

    with tempfile.TemporaryDirectory() as workspace:
        request = AgentExecutionRequest(
            task_prompt=prompt,
            workspace=workspace,
            timeout_seconds=timeout_seconds,
        )
        execution = adapter.run(request)

    diagnosis = diagnose_continue_result(execution)
    return ContinueHealthcheckReport(
        success=execution.success and bool((execution.stdout or "").strip()),
        diagnosis=diagnosis,
        executable=adapter.executable,
        command=execution.command,
        return_code=execution.return_code,
        stdout=execution.stdout,
        stderr=execution.stderr,
    )
