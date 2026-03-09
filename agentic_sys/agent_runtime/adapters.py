from __future__ import annotations

import abc
import json
import os
import re
import subprocess
import time
import threading
from typing import Callable, Dict, List, Optional
import shutil
from pathlib import Path
from datetime import datetime

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


class MiniSweAgentAdapter(AgentAdapter):
    """Adapter for mini-swe-agent CLI (`mini -t ...`)."""

    def __init__(
        self,
        executable: str = "mini",
        *,
        model_name: Optional[str] = None,
        config_specs: Optional[List[str]] = None,
        yolo: bool = True,
        exit_immediately: bool = True,
        output_filename: str = "mini_swe_run.traj.json",
        extra_args: Optional[List[str]] = None,
    ) -> None:
        self.executable = executable
        self.model_name = model_name
        self.config_specs = list(config_specs or [])
        self.yolo = bool(yolo)
        self.exit_immediately = bool(exit_immediately)
        self.output_filename = output_filename
        self.extra_args = list(extra_args or [])

    @property
    def agent_id(self) -> str:
        return "mini-swe-agent"

    @property
    def process_name_hint(self) -> str:
        return "mini"

    @classmethod
    def auto_detect(
        cls,
        *,
        model_name: Optional[str] = None,
        config_specs: Optional[List[str]] = None,
    ) -> "MiniSweAgentAdapter":
        found = shutil.which("mini")
        if not found:
            raise RuntimeError(
                "Could not find mini-swe-agent executable (`mini`). "
                "Install with: pip install mini-swe-agent"
            )
        return cls(
            executable=found,
            model_name=model_name,
            config_specs=config_specs,
        )

    def _trajectory_path(self, request: AgentExecutionRequest) -> Path:
        return Path(request.workspace) / self.output_filename

    def build_command(self, request: AgentExecutionRequest) -> List[str]:
        cmd: List[str] = [self.executable, "-t", request.task_prompt]
        if self.model_name:
            cmd.extend(["-m", self.model_name])
        for config_spec in self.config_specs:
            cmd.extend(["-c", config_spec])
        if self.yolo:
            cmd.append("-y")
        if self.exit_immediately:
            cmd.append("--exit-immediately")
        cmd.extend(["-o", str(self._trajectory_path(request))])
        cmd.extend(self.extra_args)
        return cmd

    @staticmethod
    def _message_text(message: Dict[str, object]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        texts.append(text)
            return "\n".join(texts)
        output = message.get("output")
        if isinstance(output, str):
            return output
        if isinstance(output, list):
            texts: List[str] = []
            for item in output:
                if isinstance(item, dict):
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if isinstance(c, dict) and isinstance(c.get("text"), str):
                                texts.append(c["text"])
            return "\n".join(texts)
        return ""

    @staticmethod
    def _group_messages_into_steps(messages: List[Dict[str, object]]) -> List[List[Dict[str, object]]]:
        steps: List[List[Dict[str, object]]] = []
        current_step: List[Dict[str, object]] = []
        for message in messages:
            extra = message.get("extra")
            actions = extra.get("actions") if isinstance(extra, dict) else None
            role = str(message.get("role") or "")
            if actions or role == "assistant":
                if current_step:
                    steps.append(current_step)
                current_step = [message]
            else:
                current_step.append(message)
        if current_step:
            steps.append(current_step)
        return steps

    @classmethod
    def _trajectory_to_synthetic_log(cls, trajectory_data: Dict[str, object]) -> str:
        messages_raw = trajectory_data.get("messages")
        messages = messages_raw if isinstance(messages_raw, list) else []
        typed_messages = [m for m in messages if isinstance(m, dict)]
        steps = cls._group_messages_into_steps(typed_messages)
        total_steps = max(len(steps), 1)

        log_lines: List[str] = []
        tool_calls = 0
        assistant_replies = 0
        for idx, step_messages in enumerate(steps, start=1):
            log_lines.append(f"Step {idx}/{total_steps}")
            for message in step_messages:
                role = str(message.get("role") or "").lower()
                text = cls._message_text(message).strip()
                if role == "assistant":
                    assistant_replies += 1
                    if text:
                        log_lines.append("thinking: planning next action")
                        log_lines.append(f"assistant: {text}")

                    extra = message.get("extra")
                    actions = extra.get("actions") if isinstance(extra, dict) else None
                    if isinstance(actions, list):
                        for action in actions:
                            if not isinstance(action, dict):
                                continue
                            tool_name = action.get("tool") or action.get("name")
                            if not isinstance(tool_name, str) or not tool_name:
                                tool_name = "bash" if action.get("command") else "action"
                            normalized = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name)
                            if not normalized:
                                normalized = "action"
                            log_lines.append(f"Tool Call: {normalized}")
                            tool_calls += 1
                elif role in {"tool", "observation"}:
                    log_lines.append("Result")

        info = trajectory_data.get("info") if isinstance(trajectory_data, dict) else {}
        model_stats = info.get("model_stats") if isinstance(info, dict) else {}
        api_calls = model_stats.get("api_calls", assistant_replies)
        tokens_used = 0

        log_lines.extend(
            [
                "",
                "Session Statistics:",
                f"  Total Messages: {len(typed_messages)}",
                f"  Tool Calls: {tool_calls}",
                f"  API Tokens Used: {tokens_used}",
            ]
        )

        return "\n".join(log_lines).strip() + "\n"

    @staticmethod
    def _parse_timestamp(raw: object) -> Optional[float]:
        if isinstance(raw, (int, float)):
            return float(raw)
        if not isinstance(raw, str):
            return None
        value = raw.strip()
        if not value:
            return None
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return None

    @classmethod
    def _message_timestamp(cls, message: Dict[str, object]) -> Optional[float]:
        for key in ("timestamp", "created_at", "time", "createdAt"):
            parsed = cls._parse_timestamp(message.get(key))
            if parsed is not None:
                return parsed
        return None

    @classmethod
    def _trajectory_to_structured_timeline(
        cls,
        trajectory_data: Dict[str, object],
    ) -> List[Dict[str, object]]:
        messages_raw = trajectory_data.get("messages")
        messages = messages_raw if isinstance(messages_raw, list) else []
        typed_messages = [m for m in messages if isinstance(m, dict)]
        if not typed_messages:
            return []

        absolute_times = [
            timestamp
            for timestamp in (cls._message_timestamp(msg) for msg in typed_messages)
            if timestamp is not None
        ]
        base_time = min(absolute_times) if absolute_times else None

        steps = cls._group_messages_into_steps(typed_messages)
        timeline: List[Dict[str, object]] = []
        line_no = 0

        def _offset(message: Dict[str, object]) -> Optional[float]:
            if base_time is None:
                return None
            ts = cls._message_timestamp(message)
            if ts is None:
                return None
            return max(0.0, ts - base_time)

        for step_idx, step_messages in enumerate(steps, start=1):
            for message in step_messages:
                role = str(message.get("role") or "").lower()
                offset = _offset(message)

                if role == "assistant":
                    thinking_event: Dict[str, object] = {
                        "event_type": "thinking",
                        "step": step_idx,
                        "line": line_no,
                    }
                    line_no += 1
                    if offset is not None:
                        thinking_event["time_offset_s"] = round(offset, 6)
                    timeline.append(thinking_event)

                    response_event: Dict[str, object] = {
                        "event_type": "assistant_response",
                        "step": step_idx,
                        "line": line_no,
                    }
                    line_no += 1
                    if offset is not None:
                        response_event["time_offset_s"] = round(offset, 6)
                    timeline.append(response_event)

                    extra = message.get("extra")
                    actions = extra.get("actions") if isinstance(extra, dict) else None
                    if isinstance(actions, list):
                        for action_idx, action in enumerate(actions):
                            if not isinstance(action, dict):
                                continue
                            tool_name = action.get("tool") or action.get("name")
                            if not isinstance(tool_name, str) or not tool_name:
                                tool_name = "bash" if action.get("command") else "action"
                            normalized = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name) or "action"
                            event: Dict[str, object] = {
                                "event_type": "tool_call",
                                "step": step_idx,
                                "line": line_no,
                                "tool_name": normalized,
                            }
                            line_no += 1
                            if offset is not None:
                                event["time_offset_s"] = round(offset + (action_idx * 0.001), 6)
                            timeline.append(event)

                elif role in {"tool", "observation"}:
                    event = {
                        "event_type": "tool_result",
                        "step": step_idx,
                        "line": line_no,
                    }
                    line_no += 1
                    if offset is not None:
                        event["time_offset_s"] = round(offset, 6)
                    timeline.append(event)

        return timeline

    @classmethod
    def _load_trajectory_artifacts(
        cls,
        trajectory_path: Path,
    ) -> tuple[str, List[Dict[str, object]]]:
        if not trajectory_path.exists():
            return "", []
        try:
            data = json.loads(trajectory_path.read_text(encoding="utf-8"))
        except Exception:
            return "", []

        payload: Dict[str, object]
        if isinstance(data, list):
            payload = {"messages": data}
        elif isinstance(data, dict):
            payload = data
        else:
            return "", []

        return (
            cls._trajectory_to_synthetic_log(payload),
            cls._trajectory_to_structured_timeline(payload),
        )

    def run(
        self,
        request: AgentExecutionRequest,
        on_process_start: Optional[Callable[[int], None]] = None,
    ) -> AgentExecutionResult:
        cmd = self.build_command(request)
        start = time.time()
        process = None

        def _build_env() -> Dict[str, str]:
            env = dict(os.environ)
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")
            return env

        def _run_with_pipes() -> AgentExecutionResult:
            nonlocal process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=request.workspace,
                env=_build_env(),
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

        def _needs_console_fallback(stderr_text: str) -> bool:
            normalized = (stderr_text or "").lower()
            return (
                os.name == "nt"
                and (
                    "noconsolescreenbuffererror" in normalized
                    or "are you running cmd.exe?" in normalized
                )
            )

        def _run_with_inherited_console() -> AgentExecutionResult:
            """
            Retry mode for mini-swe-agent on Windows.

            mini-swe-agent uses prompt_toolkit for input handling, and when stdout/stderr are
            captured through pipes on Windows it may fail with NoConsoleScreenBufferError.
            In this mode we inherit the parent console handles and reconstruct logs from the
            output trajectory file.
            """
            nonlocal process
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            process = subprocess.Popen(
                cmd,
                stdout=None,
                stderr=None,
                text=True,
                cwd=request.workspace,
                env=_build_env(),
                creationflags=creationflags,
            )
            if on_process_start and process.pid is not None:
                try:
                    on_process_start(process.pid)
                except Exception:
                    pass
            timed_out = False
            stderr_text = ""
            try:
                process.wait(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait()
                stderr_text = f"Task timed out after {request.timeout_seconds} seconds"

            elapsed = time.time() - start
            trajectory_log, structured_timeline = self._load_trajectory_artifacts(
                self._trajectory_path(request)
            )
            if not trajectory_log and not timed_out:
                stderr_text = (
                    f"{stderr_text}\n"
                    if stderr_text
                    else ""
                ) + (
                    "mini-swe-agent finished without a trajectory file. "
                    "Check model configuration and mini-swe-agent global setup."
                )
            return AgentExecutionResult(
                command=cmd,
                stdout=trajectory_log,
                stderr=stderr_text,
                success=(process.returncode == 0 and bool(trajectory_log) and not timed_out),
                execution_time_seconds=elapsed,
                return_code=process.returncode,
                pid=process.pid,
                timed_out=timed_out,
                metadata={
                    "stream_trace_mode": "mini_swe_trajectory",
                    "structured_timeline": structured_timeline,
                },
            )

        try:
            initial = _run_with_pipes()
            if _needs_console_fallback(initial.stderr):
                fallback = _run_with_inherited_console()
                if initial.stderr:
                    fallback.stderr = (
                        f"{fallback.stderr}\n"
                        if fallback.stderr
                        else ""
                    ) + "[initial pipe-mode error]\n" + initial.stderr
                return fallback

            trajectory_log, structured_timeline = self._load_trajectory_artifacts(
                self._trajectory_path(request)
            )
            if trajectory_log:
                merged_stdout = f"{trajectory_log}\n{initial.stdout}".strip()
                initial.stdout = merged_stdout + "\n"
            if structured_timeline:
                initial.metadata["stream_trace_mode"] = "mini_swe_trajectory"
                initial.metadata["structured_timeline"] = structured_timeline
            return initial
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
        prompt = request.task_prompt
        # On Windows, `cn.CMD` is a batch wrapper and multiline args can be truncated.
        # Flattening newlines keeps prompt semantics while avoiding cmd parsing issues.
        if os.name == "nt" and str(self.executable).lower().endswith(".cmd"):
            prompt = " ".join(line.strip() for line in prompt.splitlines() if line.strip())
        cmd.extend(["-p", prompt])
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

            stdout_chunks: List[str] = []
            stderr_chunks: List[str] = []
            stream_timing: Dict[str, Optional[float]] = {
                "first_stdout_s": None,
                "last_stdout_s": None,
                "first_stderr_s": None,
                "last_stderr_s": None,
            }

            def _read_stream(
                stream,
                sink: List[str],
                first_key: str,
                last_key: str,
            ) -> None:
                if stream is None:
                    return
                try:
                    for chunk in iter(stream.readline, ""):
                        now_s = max(0.0, time.time() - start)
                        if stream_timing[first_key] is None:
                            stream_timing[first_key] = now_s
                        stream_timing[last_key] = now_s
                        sink.append(chunk)
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass

            stdout_thread = threading.Thread(
                target=_read_stream,
                args=(process.stdout, stdout_chunks, "first_stdout_s", "last_stdout_s"),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_read_stream,
                args=(process.stderr, stderr_chunks, "first_stderr_s", "last_stderr_s"),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            try:
                process.wait(timeout=request.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                stdout_thread.join(timeout=1.0)
                stderr_thread.join(timeout=1.0)
                stdout = "".join(stdout_chunks)
                stderr = "".join(stderr_chunks)
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
                    metadata={
                        "stream_timing": stream_timing,
                        "stream_trace_mode": "line_buffered_subprocess",
                    },
                )

            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)
            stdout = "".join(stdout_chunks)
            stderr = "".join(stderr_chunks)
            elapsed = time.time() - start
            return AgentExecutionResult(
                command=cmd,
                stdout=stdout or "",
                stderr=self._append_continue_diagnostics(stderr or ""),
                success=process.returncode == 0,
                execution_time_seconds=elapsed,
                return_code=process.returncode,
                pid=process.pid,
                metadata={
                    "stream_timing": stream_timing,
                    "stream_trace_mode": "line_buffered_subprocess",
                },
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
