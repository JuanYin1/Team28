from __future__ import annotations

import abc
import os
import subprocess
import time
from typing import Callable, Dict, List, Optional
import shutil
from pathlib import Path

from .models import AgentExecutionRequest, AgentExecutionResult


class AgentAdapter(abc.ABC):
    """Abstract execution adapter for different agent implementations."""

    @property
    @abc.abstractmethod
    def agent_id(self) -> str:
        raise NotImplementedError

    @property
    def process_name_hint(self) -> str:
        return self.agent_id

    @abc.abstractmethod
    def run(
        self,
        request: AgentExecutionRequest,
        on_process_start: Optional[Callable[[int], None]] = None,
    ) -> AgentExecutionResult:
        raise NotImplementedError


class GenericCLIAdapter(AgentAdapter):
    """
    Generic template-driven CLI adapter.

    This supports onboarding new runtimes with config only. Command and env values can
    reference placeholders: `{workspace}`, `{task_prompt}`, `{timeout_seconds}`.
    """

    _SUPPORTED_PLACEHOLDERS = ("workspace", "task_prompt", "timeout_seconds")

    def __init__(
        self,
        *,
        agent_id: str = "generic-cli",
        command: Optional[List[str]] = None,
        executable: Optional[str] = None,
        process_name_hint: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = "{workspace}",
        success_codes: Optional[List[int]] = None,
        extra_args: Optional[List[str]] = None,
    ) -> None:
        self._agent_id = agent_id
        self._configured_process_name_hint = process_name_hint
        self.command = list(command or [])
        self.executable = executable
        self.env = dict(env or {})
        self.cwd = cwd
        self.success_codes = list(success_codes or [0])
        self.extra_args = list(extra_args or [])

        if not self.command:
            if not executable:
                raise ValueError(
                    "GenericCLIAdapter requires either `command` or `executable`."
                )
            self.command = [executable, "{task_prompt}"]
        if not self.executable and self.command:
            self.executable = str(self.command[0])

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def process_name_hint(self) -> str:
        if self._configured_process_name_hint:
            return self._configured_process_name_hint
        if self.command:
            return Path(self.command[0]).name
        return self._agent_id

    @classmethod
    def auto_detect(
        cls,
        *,
        agent_id: str = "generic-cli",
        command: Optional[List[str]] = None,
        executable: Optional[str] = None,
        process_name_hint: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = "{workspace}",
        success_codes: Optional[List[int]] = None,
        extra_args: Optional[List[str]] = None,
    ) -> "GenericCLIAdapter":
        if executable and shutil.which(executable):
            executable = shutil.which(executable)
        return cls(
            agent_id=agent_id,
            command=command,
            executable=executable,
            process_name_hint=process_name_hint,
            env=env,
            cwd=cwd,
            success_codes=success_codes,
            extra_args=extra_args,
        )

    def _template_context(self, request: AgentExecutionRequest) -> Dict[str, str]:
        return {
            "workspace": request.workspace,
            "task_prompt": request.task_prompt,
            "timeout_seconds": str(request.timeout_seconds),
        }

    def _render_template(self, value: str, context: Dict[str, str]) -> str:
        try:
            return value.format(**context)
        except KeyError as exc:
            key = str(exc).strip("'")
            supported = ", ".join(self._SUPPORTED_PLACEHOLDERS)
            raise ValueError(
                f"Unsupported placeholder '{key}' in generic adapter template. "
                f"Supported: {supported}."
            ) from exc

    def build_command(self, request: AgentExecutionRequest) -> List[str]:
        context = self._template_context(request)
        rendered = [self._render_template(str(part), context) for part in self.command]
        if self.extra_args:
            rendered.extend(
                self._render_template(str(part), context) for part in self.extra_args
            )
        return rendered

    def _build_env(self, request: AgentExecutionRequest) -> Dict[str, str]:
        if not self.env:
            return dict(os.environ)
        context = self._template_context(request)
        merged = dict(os.environ)
        for key, value in self.env.items():
            merged[str(key)] = self._render_template(str(value), context)
        return merged

    def _resolve_cwd(self, request: AgentExecutionRequest) -> Optional[str]:
        if self.cwd is None:
            return None
        return self._render_template(str(self.cwd), self._template_context(request))

    def run(
        self,
        request: AgentExecutionRequest,
        on_process_start: Optional[Callable[[int], None]] = None,
    ) -> AgentExecutionResult:
        start = time.time()
        process = None

        try:
            cmd = self.build_command(request)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self._resolve_cwd(request),
                env=self._build_env(request),
            )
            if on_process_start and process.pid is not None:
                try:
                    on_process_start(process.pid)
                except Exception:
                    pass

            try:
                stdout, stderr = process.communicate(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                elapsed = time.time() - start
                timeout_msg = f"Task timed out after {request.timeout_seconds} seconds"
                stderr_with_timeout = f"{stderr}\n{timeout_msg}" if stderr else timeout_msg
                return AgentExecutionResult(
                    command=cmd,
                    stdout=stdout or "",
                    stderr=stderr_with_timeout,
                    success=False,
                    execution_time_seconds=elapsed,
                    return_code=process.returncode,
                    pid=process.pid,
                    timed_out=True,
                )

            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd,
                stdout=stdout or "",
                stderr=stderr or "",
                success=process.returncode in self.success_codes,
                execution_time_seconds=elapsed,
                return_code=process.returncode,
                pid=process.pid,
            )

        except FileNotFoundError as exc:
            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd if "cmd" in locals() else [],
                stdout="",
                stderr=f"Execution error: {exc}",
                success=False,
                execution_time_seconds=elapsed,
                return_code=None,
                pid=getattr(process, "pid", None),
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd if "cmd" in locals() else [],
                stdout="",
                stderr=f"Execution error: {exc}",
                success=False,
                execution_time_seconds=elapsed,
                return_code=getattr(process, "returncode", None),
                pid=getattr(process, "pid", None),
            )


class MiniAgentAdapter(AgentAdapter):
    """Adapter for Mini-Agent CLI (`mini-agent --workspace --task ...`)."""

    def __init__(
        self,
        executable: str = "mini-agent",
        *,
        conda_env: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> None:
        self.executable = executable
        self.conda_env = conda_env
        self.extra_args = list(extra_args or [])

    @property
    def agent_id(self) -> str:
        return "mini-agent"

    @property
    def process_name_hint(self) -> str:
        return "mini-agent"

    @classmethod
    def auto_detect(cls, conda_env: str = "mini-agent") -> "MiniAgentAdapter":
        """Best-effort runtime discovery with a deterministic fallback strategy."""

        found = shutil.which("mini-agent")
        if found:
            return cls(executable=found)

        try:
            probe = subprocess.run(
                ["conda", "run", "-n", conda_env, "mini-agent", "--version"],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                return cls(executable="mini-agent", conda_env=conda_env)
        except FileNotFoundError:
            pass

        raise RuntimeError(
            "Could not find mini-agent executable. "
            "Install mini-agent or provide an explicit executable path."
        )

    def build_command(self, request: AgentExecutionRequest) -> List[str]:
        base: List[str]
        if self.conda_env:
            base = ["conda", "run", "-n", self.conda_env, self.executable]
        else:
            base = [self.executable]

        return [
            *base,
            "--workspace",
            request.workspace,
            "--task",
            request.task_prompt,
            *self.extra_args,
        ]

    def run(
        self,
        request: AgentExecutionRequest,
        on_process_start: Optional[Callable[[int], None]] = None,
    ) -> AgentExecutionResult:
        cmd = self.build_command(request)
        start = time.time()
        process = None

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=request.workspace,
            )
            if on_process_start and process.pid is not None:
                try:
                    on_process_start(process.pid)
                except Exception:
                    pass

            try:
                stdout, stderr = process.communicate(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                elapsed = time.time() - start
                timeout_msg = f"Task timed out after {request.timeout_seconds} seconds"
                stderr_with_timeout = f"{stderr}\n{timeout_msg}" if stderr else timeout_msg
                return AgentExecutionResult(
                    command=cmd,
                    stdout=stdout or "",
                    stderr=stderr_with_timeout,
                    success=False,
                    execution_time_seconds=elapsed,
                    return_code=process.returncode,
                    pid=process.pid,
                    timed_out=True,
                )

            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd,
                stdout=stdout or "",
                stderr=stderr or "",
                success=process.returncode == 0,
                execution_time_seconds=elapsed,
                return_code=process.returncode,
                pid=process.pid,
            )

        except FileNotFoundError as exc:
            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd,
                stdout="",
                stderr=f"Execution error: {exc}",
                success=False,
                execution_time_seconds=elapsed,
                return_code=None,
                pid=getattr(process, "pid", None),
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd,
                stdout="",
                stderr=f"Execution error: {exc}",
                success=False,
                execution_time_seconds=elapsed,
                return_code=getattr(process, "returncode", None),
                pid=getattr(process, "pid", None),
            )


class ContinueCnAdapter(AgentAdapter):
    """Adapter for Continue CLI (`cn -p ...`)."""

    def __init__(
        self,
        executable: str = "cn",
        *,
        agent_name: Optional[str] = None,
        config_path: Optional[str] = None,
        model_slugs: Optional[List[str]] = None,
        allow_policies: Optional[List[str]] = None,
        extra_args: Optional[List[str]] = None,
    ) -> None:
        self.executable = executable
        self.agent_name = agent_name
        self.config_path = config_path
        self.model_slugs = list(model_slugs or [])
        self.allow_policies = list(allow_policies or [])
        self.extra_args = list(extra_args or [])

    @property
    def agent_id(self) -> str:
        return "continue-cn"

    @property
    def process_name_hint(self) -> str:
        return "cn"

    @classmethod
    def auto_detect(
        cls,
        *,
        agent_name: Optional[str] = None,
        config_path: Optional[str] = None,
        model_slugs: Optional[List[str]] = None,
    ) -> "ContinueCnAdapter":
        found = shutil.which("cn")
        if not found:
            fallback_candidates = [
                Path.home() / ".local" / "bin" / "cn",
                Path("/usr/local/bin/cn"),
                Path("/opt/homebrew/bin/cn"),
            ]
            for candidate in fallback_candidates:
                if candidate.exists():
                    found = str(candidate)
                    break
        if not found:
            raise RuntimeError(
                "Could not find Continue CLI (`cn`). "
                "Install with: npm i -g @continuedev/cli"
            )
        return cls(
            executable=found,
            agent_name=agent_name,
            config_path=config_path,
            model_slugs=model_slugs,
        )

    def build_command(self, request: AgentExecutionRequest) -> List[str]:
        cmd: List[str] = [self.executable]
        if self.config_path:
            cmd.extend(["--config", self.config_path])
        if self.agent_name:
            cmd.extend(["--agent", self.agent_name])
        for model_slug in self.model_slugs:
            cmd.extend(["--model", model_slug])
        for policy in self.allow_policies:
            cmd.extend(["--allow", policy])
        cmd.extend(["-p", request.task_prompt])
        cmd.extend(self.extra_args)
        return cmd

    @staticmethod
    def _append_continue_diagnostics(stderr: str) -> str:
        """Attach actionable hints for known Continue CLI failure signatures."""
        base = stderr or ""
        normalized = base.lower()
        hints: List[str] = []

        if "interceptors did not return an alternative response" in normalized:
            hints.append(
                "Hint: Continue runtime is configured but no working model/auth path handled this request. "
                "Run `cn login` and/or provide `--config` + provider credentials."
            )
        if "response returned an error code" in normalized:
            hints.append(
                "Hint: Continue upstream returned a non-2xx response. "
                "Check provider API key, model availability, and organization configuration."
            )
        if "no credits remaining" in normalized:
            hints.append(
                "Hint: Continue account credits are exhausted. "
                "Top up billing or switch to your own provider config."
            )
        if "fetch failed" in normalized:
            hints.append(
                "Hint: Continue CLI could not reach its remote service. "
                "Check network/proxy/firewall and retry `cn login`."
            )

        if not hints:
            return base
        if base:
            return f"{base}\n{chr(10).join(hints)}"
        return "\n".join(hints)

    def run(
        self,
        request: AgentExecutionRequest,
        on_process_start: Optional[Callable[[int], None]] = None,
    ) -> AgentExecutionResult:
        cmd = self.build_command(request)
        start = time.time()
        process = None

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=request.workspace,
            )
            if on_process_start and process.pid is not None:
                try:
                    on_process_start(process.pid)
                except Exception:
                    pass

            try:
                stdout, stderr = process.communicate(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                elapsed = time.time() - start
                timeout_msg = f"Task timed out after {request.timeout_seconds} seconds"
                stderr_with_timeout = f"{stderr}\n{timeout_msg}" if stderr else timeout_msg
                return AgentExecutionResult(
                    command=cmd,
                    stdout=stdout or "",
                    stderr=stderr_with_timeout,
                    success=False,
                    execution_time_seconds=elapsed,
                    return_code=process.returncode,
                    pid=process.pid,
                    timed_out=True,
                )

            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd,
                stdout=stdout or "",
                stderr=self._append_continue_diagnostics(stderr or ""),
                success=process.returncode == 0,
                execution_time_seconds=elapsed,
                return_code=process.returncode,
                pid=process.pid,
            )

        except FileNotFoundError as exc:
            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd,
                stdout="",
                stderr=self._append_continue_diagnostics(f"Execution error: {exc}"),
                success=False,
                execution_time_seconds=elapsed,
                return_code=None,
                pid=getattr(process, "pid", None),
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd,
                stdout="",
                stderr=self._append_continue_diagnostics(f"Execution error: {exc}"),
                success=False,
                execution_time_seconds=elapsed,
                return_code=getattr(process, "returncode", None),
                pid=getattr(process, "pid", None),
            )
