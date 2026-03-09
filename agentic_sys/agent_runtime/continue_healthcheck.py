from __future__ import annotations

import subprocess
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


@dataclass
class ContinueLoginReport:
    success: bool
    diagnosis: str
    executable: Optional[str] = None
    command: List[str] = field(default_factory=list)
    return_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""


def _resolve_continue_adapter(
    *,
    executable: Optional[str],
    agent_name: Optional[str],
    config_path: Optional[str],
    model_slugs: Optional[List[str]],
    allow_policies: Optional[List[str]],
    extra_args: Optional[List[str]],
) -> ContinueCnAdapter:
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
    return adapter


def diagnose_continue_result(result: AgentExecutionResult) -> str:
    if result.success and (result.stdout or "").strip():
        return "ok"

    combined = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
    if "no credits remaining" in combined:
        return "account_credits_exhausted"
    if "interceptors did not return an alternative response" in combined:
        return "auth_or_model_not_configured"
    if "response returned an error code" in combined:
        return "upstream_provider_error"
    if "fetch failed" in combined:
        return "network_or_proxy_error"
    if result.timed_out:
        return "timeout"
    if "execution error" in combined:
        return "execution_failure"
    if result.success and not (result.stdout or "").strip():
        return "empty_output"
    return "unknown_failure"


def run_continue_login(
    *,
    executable: Optional[str] = None,
    timeout_seconds: float = 120.0,
) -> ContinueLoginReport:
    try:
        adapter = _resolve_continue_adapter(
            executable=executable,
            agent_name=None,
            config_path=None,
            model_slugs=None,
            allow_policies=None,
            extra_args=None,
        )
    except RuntimeError as exc:
        return ContinueLoginReport(
            success=False,
            diagnosis="binary_not_found",
            stderr=str(exc),
        )

    cmd = [adapter.executable, "login"]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return ContinueLoginReport(
            success=False,
            diagnosis="timeout",
            executable=adapter.executable,
            command=cmd,
            return_code=None,
            stdout=stdout,
            stderr=stderr,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        return ContinueLoginReport(
            success=False,
            diagnosis="execution_failure",
            executable=adapter.executable,
            command=cmd,
            return_code=None,
            stderr=str(exc),
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    combined = f"{stdout}\n{stderr}".lower()

    # `cn login` can complete auth but still exit non-zero when trying to open TTY mode.
    success_markers = (
        "successfully logged in",
        "already logged in",
    )
    login_success = any(marker in combined for marker in success_markers)
    if login_success:
        diagnosis = "ok"
    elif "fetch failed" in combined:
        diagnosis = "network_or_proxy_error"
    elif "authentication code" in combined and "waiting for confirmation" in combined:
        diagnosis = "confirmation_timeout_or_not_completed"
    else:
        diagnosis = "unknown_failure"

    return ContinueLoginReport(
        success=login_success,
        diagnosis=diagnosis,
        executable=adapter.executable,
        command=cmd,
        return_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


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
        adapter = _resolve_continue_adapter(
            executable=executable,
            agent_name=agent_name,
            config_path=config_path,
            model_slugs=model_slugs,
            allow_policies=allow_policies,
            extra_args=extra_args,
        )
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
