from __future__ import annotations

import abc
import errno
import glob
import json
import os
import pty
import select
import subprocess
import time
from typing import Callable, Dict, List, Optional, Set, Tuple
import shutil
from pathlib import Path

from .models import AgentExecutionRequest, AgentExecutionResult


_SUPPORTED_TRANSPORTS = {"pipe", "pty"}


def _normalize_transport(transport: Optional[str]) -> str:
    candidate = str(transport or "pipe").strip().lower()
    if candidate not in _SUPPORTED_TRANSPORTS:
        expected = ", ".join(sorted(_SUPPORTED_TRANSPORTS))
        raise ValueError(f"Unsupported transport '{transport}'. Expected one of: {expected}.")
    return candidate


def _decode_pty_output(chunks: List[bytes]) -> str:
    text = b"".join(chunks).decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_trace_log_paths(paths: Optional[List[str]]) -> List[str]:
    if not paths:
        return []
    normalized: List[str] = []
    for item in paths:
        candidate = str(item or "").strip()
        if candidate:
            normalized.append(candidate)
    return normalized


def _request_template_context(request: AgentExecutionRequest) -> Dict[str, str]:
    return {
        "workspace": request.workspace,
        "task_prompt": request.task_prompt,
        "timeout_seconds": str(request.timeout_seconds),
    }


def _render_template_value(template: str, context: Dict[str, str]) -> str:
    try:
        return template.format(**context)
    except KeyError:
        return template


def _resolve_trace_log_candidates(
    *,
    templates: List[str],
    context: Dict[str, str],
) -> List[str]:
    resolved: List[str] = []
    for template in templates:
        rendered = _render_template_value(template, context)
        expanded = os.path.expanduser(rendered)
        if any(symbol in expanded for symbol in ("*", "?", "[")):
            matches = sorted(glob.glob(expanded))
            if matches:
                resolved.extend(matches)
            else:
                resolved.append(expanded)
        else:
            resolved.append(expanded)
    unique: List[str] = []
    seen = set()
    for path in resolved:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _snapshot_log_offsets(paths: List[str]) -> Dict[str, int]:
    offsets: Dict[str, int] = {}
    for path in paths:
        try:
            offsets[path] = os.path.getsize(path)
        except OSError:
            offsets[path] = 0
    return offsets


def _tail_lines(text: str, max_lines: int) -> str:
    if max_lines <= 0:
        return text
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def _capture_trace_log_chunks(
    *,
    paths: List[str],
    offsets: Dict[str, int],
    max_bytes: int,
    tail_lines: int,
) -> List[Dict[str, str]]:
    chunks: List[Dict[str, str]] = []
    byte_limit = max(1024, int(max_bytes))
    for path in paths:
        try:
            current_size = os.path.getsize(path)
        except OSError:
            continue
        start_offset = max(0, int(offsets.get(path, 0)))
        read_from = min(start_offset, current_size)
        if read_from >= current_size:
            continue
        try:
            with open(path, "rb") as handle:
                handle.seek(read_from)
                blob = handle.read()
                if len(blob) > byte_limit:
                    blob = blob[-byte_limit:]
            text = blob.decode("utf-8", errors="replace")
        except OSError:
            continue
        text = _tail_lines(text, max(0, int(tail_lines))).strip()
        if not text:
            continue
        chunks.append(
            {
                "path": path,
                "text": text,
            }
        )
    return chunks


def _capture_trace_log_tail(
    *,
    paths: List[str],
    max_bytes: int,
    tail_lines: int,
) -> List[Dict[str, str]]:
    chunks: List[Dict[str, str]] = []
    byte_limit = max(1024, int(max_bytes))
    for path in paths:
        try:
            with open(path, "rb") as handle:
                blob = handle.read()
                if len(blob) > byte_limit:
                    blob = blob[-byte_limit:]
            text = blob.decode("utf-8", errors="replace")
        except OSError:
            continue
        text = _tail_lines(text, max(0, int(tail_lines))).strip()
        if not text:
            continue
        chunks.append({"path": path, "text": text})
    return chunks


def _workspace_trace_tokens(workspace: str) -> Tuple[Set[str], Set[str]]:
    """
    Build workspace tokens for trace fallback filtering.

    Strong tokens are full-path variants (including /private normalization on macOS).
    Weak tokens are short directory names used only as a fallback.
    """
    raw_workspace = str(workspace or "").strip()
    if not raw_workspace:
        return set(), set()

    variants: Set[str] = set()

    def _add_variant(value: str) -> None:
        candidate = str(value or "").strip().rstrip("/")
        if candidate:
            variants.add(candidate)

    _add_variant(raw_workspace)
    _add_variant(os.path.abspath(raw_workspace))
    _add_variant(os.path.realpath(raw_workspace))

    for value in list(variants):
        if value.startswith("/private/"):
            _add_variant(value[len("/private"):])
        elif value.startswith("/"):
            _add_variant(f"/private{value}")

    strong_tokens: Set[str] = set()
    weak_tokens: Set[str] = set()
    for value in variants:
        if "/" in value:
            strong_tokens.add(value)
        leaf = Path(value).name.strip()
        if leaf:
            weak_tokens.add(leaf)

    return strong_tokens, weak_tokens


def _filter_trace_chunks_for_workspace(
    *,
    chunks: List[Dict[str, str]],
    workspace: str,
) -> List[Dict[str, str]]:
    strong_tokens, weak_tokens = _workspace_trace_tokens(workspace)
    if not chunks or (not strong_tokens and not weak_tokens):
        return []

    strong_matches: List[Dict[str, str]] = []
    weak_matches: List[Dict[str, str]] = []

    for chunk in chunks:
        text = str(chunk.get("text", ""))
        if not text:
            continue
        if any(token and token in text for token in strong_tokens):
            strong_matches.append(chunk)
            continue
        if any(token and token in text for token in weak_tokens):
            weak_matches.append(chunk)

    # Prefer precise full-path matches; only fall back to weaker basename matching.
    return strong_matches or weak_matches


def _collect_trace_chunks_with_fallback(
    *,
    paths: List[str],
    offsets: Dict[str, int],
    workspace: str,
    max_bytes: int,
    tail_lines: int,
) -> Tuple[List[Dict[str, str]], str]:
    trace_chunks = _capture_trace_log_chunks(
        paths=paths,
        offsets=offsets,
        max_bytes=max_bytes,
        tail_lines=tail_lines,
    )
    if trace_chunks:
        return trace_chunks, "delta"

    if not paths:
        return [], "none"

    fallback_chunks = _capture_trace_log_tail(
        paths=paths,
        max_bytes=max_bytes,
        tail_lines=tail_lines,
    )
    filtered = _filter_trace_chunks_for_workspace(
        chunks=fallback_chunks,
        workspace=workspace,
    )
    if filtered:
        return filtered, "tail_fallback"

    # Continue often writes a single shared verbose log where the tail may no
    # longer contain the temporary workspace path even though it still contains
    # tool-call chunks from the just-finished run. In the single-log case,
    # prefer returning the unfiltered tail over dropping trace evidence
    # entirely.
    if len(paths) == 1 and len(fallback_chunks) == 1:
        return fallback_chunks, "tail_fallback_unfiltered"

    return [], "none"


def _run_command_pipe(
    *,
    cmd: List[str],
    cwd: Optional[str],
    env: Optional[Dict[str, str]],
    timeout_seconds: float,
    success_codes: List[int],
    on_process_start: Optional[Callable[[int], None]] = None,
) -> AgentExecutionResult:
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
            cwd=cwd,
            env=env,
        )
        if on_process_start and process.pid is not None:
            try:
                on_process_start(process.pid)
            except Exception:
                pass

        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            elapsed = time.time() - start
            timeout_msg = f"Task timed out after {timeout_seconds} seconds"
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
                metadata={"transport": "pipe", "merged_output": False},
            )

        elapsed = time.time() - start
        return AgentExecutionResult(
            command=cmd,
            stdout=stdout or "",
            stderr=stderr or "",
            success=process.returncode in success_codes,
            execution_time_seconds=elapsed,
            return_code=process.returncode,
            pid=process.pid,
            metadata={"transport": "pipe", "merged_output": False},
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
            metadata={"transport": "pipe", "merged_output": False},
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
            metadata={"transport": "pipe", "merged_output": False},
        )


def _run_command_pty(
    *,
    cmd: List[str],
    cwd: Optional[str],
    env: Optional[Dict[str, str]],
    timeout_seconds: float,
    success_codes: List[int],
    on_process_start: Optional[Callable[[int], None]] = None,
) -> AgentExecutionResult:
    start = time.time()
    process = None
    master_fd = None
    slave_fd = None
    output_chunks: List[bytes] = []
    timed_out = False

    def _read_available_output(fd: int) -> None:
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError as exc:
                if exc.errno in {errno.EIO, errno.EBADF}:
                    break
                raise
            if not chunk:
                break
            output_chunks.append(chunk)
            if len(chunk) < 4096:
                break

    try:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=env,
            close_fds=True,
        )
        os.close(slave_fd)
        slave_fd = None

        if on_process_start and process.pid is not None:
            try:
                on_process_start(process.pid)
            except Exception:
                pass

        while True:
            if process.poll() is None and (time.time() - start) > timeout_seconds:
                timed_out = True
                process.kill()

            if process.poll() is not None:
                _read_available_output(master_fd)
                break

            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if ready:
                _read_available_output(master_fd)

        elapsed = time.time() - start
        stdout = _decode_pty_output(output_chunks)
        stderr = ""
        if timed_out:
            timeout_msg = f"Task timed out after {timeout_seconds} seconds"
            stderr = timeout_msg

        return AgentExecutionResult(
            command=cmd,
            stdout=stdout,
            stderr=stderr,
            success=(process.returncode in success_codes) and (not timed_out),
            execution_time_seconds=elapsed,
            return_code=process.returncode,
            pid=process.pid,
            timed_out=timed_out,
            metadata={"transport": "pty", "merged_output": True},
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
            metadata={"transport": "pty", "merged_output": True},
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
            metadata={"transport": "pty", "merged_output": True},
        )
    finally:
        if slave_fd is not None:
            try:
                os.close(slave_fd)
            except OSError:
                pass
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass


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
        transport: str = "pipe",
        trace_log_paths: Optional[List[str]] = None,
        trace_log_tail_lines: int = 800,
        trace_log_max_bytes: int = 512000,
    ) -> None:
        self._agent_id = agent_id
        self._configured_process_name_hint = process_name_hint
        self.command = list(command or [])
        self.executable = executable
        self.env = dict(env or {})
        self.cwd = cwd
        self.success_codes = list(success_codes or [0])
        self.extra_args = list(extra_args or [])
        self.transport = _normalize_transport(transport)
        self.trace_log_paths = _normalize_trace_log_paths(trace_log_paths)
        self.trace_log_tail_lines = max(0, int(trace_log_tail_lines))
        self.trace_log_max_bytes = max(1024, int(trace_log_max_bytes))

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
        transport: str = "pipe",
        trace_log_paths: Optional[List[str]] = None,
        trace_log_tail_lines: int = 800,
        trace_log_max_bytes: int = 512000,
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
            transport=transport,
            trace_log_paths=trace_log_paths,
            trace_log_tail_lines=trace_log_tail_lines,
            trace_log_max_bytes=trace_log_max_bytes,
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
        context = self._template_context(request)
        resolved_trace_logs = _resolve_trace_log_candidates(
            templates=self.trace_log_paths,
            context=context,
        )
        trace_offsets = _snapshot_log_offsets(resolved_trace_logs)
        cmd = self.build_command(request)
        runner = _run_command_pty if self.transport == "pty" else _run_command_pipe
        result = runner(
            cmd=cmd,
            cwd=self._resolve_cwd(request),
            env=self._build_env(request),
            timeout_seconds=request.timeout_seconds,
            success_codes=self.success_codes,
            on_process_start=on_process_start,
        )
        trace_chunks, trace_capture_mode = _collect_trace_chunks_with_fallback(
            paths=resolved_trace_logs,
            offsets=trace_offsets,
            workspace=request.workspace,
            max_bytes=self.trace_log_max_bytes,
            tail_lines=self.trace_log_tail_lines,
        )
        if trace_chunks:
            result.metadata["trace_log_chunks"] = trace_chunks
            result.metadata["trace_log_paths"] = [item["path"] for item in trace_chunks]
        result.metadata["trace_log_capture_mode"] = trace_capture_mode
        return result


class MiniAgentAdapter(AgentAdapter):
    """Adapter for Mini-Agent CLI (`mini-agent --workspace --task ...`)."""

    def __init__(
        self,
        executable: str = "mini-agent",
        *,
        conda_env: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        transport: str = "pipe",
        trace_log_paths: Optional[List[str]] = None,
        trace_log_tail_lines: int = 800,
        trace_log_max_bytes: int = 512000,
    ) -> None:
        self.executable = executable
        self.conda_env = conda_env
        self.extra_args = list(extra_args or [])
        self.transport = _normalize_transport(transport)
        self.trace_log_paths = _normalize_trace_log_paths(trace_log_paths)
        self.trace_log_tail_lines = max(0, int(trace_log_tail_lines))
        self.trace_log_max_bytes = max(1024, int(trace_log_max_bytes))

    @property
    def agent_id(self) -> str:
        return "mini-agent"

    @property
    def process_name_hint(self) -> str:
        return "mini-agent"

    @classmethod
    def auto_detect(
        cls,
        conda_env: str = "mini-agent",
        transport: str = "pipe",
        trace_log_paths: Optional[List[str]] = None,
        trace_log_tail_lines: int = 800,
        trace_log_max_bytes: int = 512000,
    ) -> "MiniAgentAdapter":
        """Best-effort runtime discovery with a deterministic fallback strategy."""

        found = shutil.which("mini-agent")
        if found:
            return cls(
                executable=found,
                transport=transport,
                trace_log_paths=trace_log_paths,
                trace_log_tail_lines=trace_log_tail_lines,
                trace_log_max_bytes=trace_log_max_bytes,
            )

        try:
            probe = subprocess.run(
                ["conda", "run", "-n", conda_env, "mini-agent", "--version"],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                return cls(
                    executable="mini-agent",
                    conda_env=conda_env,
                    transport=transport,
                    trace_log_paths=trace_log_paths,
                    trace_log_tail_lines=trace_log_tail_lines,
                    trace_log_max_bytes=trace_log_max_bytes,
                )
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
        resolved_trace_logs = _resolve_trace_log_candidates(
            templates=self.trace_log_paths,
            context=_request_template_context(request),
        )
        trace_offsets = _snapshot_log_offsets(resolved_trace_logs)
        cmd = self.build_command(request)
        runner = _run_command_pty if self.transport == "pty" else _run_command_pipe
        result = runner(
            cmd=cmd,
            cwd=request.workspace,
            env=None,
            timeout_seconds=request.timeout_seconds,
            success_codes=[0],
            on_process_start=on_process_start,
        )
        trace_chunks, trace_capture_mode = _collect_trace_chunks_with_fallback(
            paths=resolved_trace_logs,
            offsets=trace_offsets,
            workspace=request.workspace,
            max_bytes=self.trace_log_max_bytes,
            tail_lines=self.trace_log_tail_lines,
        )
        if trace_chunks:
            result.metadata["trace_log_chunks"] = trace_chunks
            result.metadata["trace_log_paths"] = [item["path"] for item in trace_chunks]
        result.metadata["trace_log_capture_mode"] = trace_capture_mode
        return result


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
        yolo: bool = True,
        exit_immediately: bool = True,
        output_filename: str = "mini_swe_run.traj.json",
        extra_args: Optional[List[str]] = None,
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
            yolo=yolo,
            exit_immediately=exit_immediately,
            output_filename=output_filename,
            extra_args=extra_args,
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
        return ""

    @staticmethod
    def _infer_tool_name_from_action(action: Dict[str, object]) -> str:
        explicit_tool = action.get("tool") or action.get("name")
        if isinstance(explicit_tool, str) and explicit_tool and explicit_tool != "bash":
            return explicit_tool

        command = str(action.get("command") or "").strip().lower()
        if not command:
            return "bash"

        write_markers = (
            ">",
            ">>",
            "tee ",
            "cat <<",
            "printf ",
            "echo ",
            "touch ",
            "cp ",
            "mv ",
        )
        edit_markers = (
            "sed -i",
            "perl -0pi",
            "perl -pi",
            "python -c",
            "python3 -c",
            "apply_patch",
            "ed ",
            "ex ",
        )
        read_prefixes = (
            "cat ",
            "ls",
            "find ",
            "rg ",
            "grep ",
            "wc ",
            "hexdump ",
            "head ",
            "tail ",
            "nl ",
        )

        if any(marker in command for marker in edit_markers):
            return "edit_file"

        if any(command.startswith(prefix) for prefix in read_prefixes):
            return "read_file"

        if (
            any(marker in command for marker in write_markers)
            and not command.startswith(("python ", "python3 ", "bash ", "sh ", "./"))
        ):
            return "write_file"

        return "bash"

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
        typed_messages = [message for message in messages if isinstance(message, dict)]
        steps = cls._group_messages_into_steps(typed_messages)
        total_steps = max(len(steps), 1)

        log_lines: List[str] = []
        for idx, step_messages in enumerate(steps, start=1):
            log_lines.append(f"Step {idx}/{total_steps}")
            for message in step_messages:
                role = str(message.get("role") or "").lower()
                text = cls._message_text(message).strip()
                if role == "assistant":
                    if text:
                        log_lines.append("thinking: planning next action")
                        log_lines.append(f"assistant: {text}")
                    extra = message.get("extra")
                    actions = extra.get("actions") if isinstance(extra, dict) else None
                    if isinstance(actions, list):
                        for action in actions:
                            if not isinstance(action, dict):
                                continue
                            tool_name = cls._infer_tool_name_from_action(action)
                            log_lines.append(f"Tool Call: {tool_name}")
                            result_text = cls._message_text(action).strip()
                            if result_text:
                                log_lines.append(f"Result: {result_text}")
                elif role in {"user", "system"}:
                    continue
                elif text:
                    log_lines.append(text)

        return "\n".join(log_lines).strip()

    @classmethod
    def _trajectory_to_structured_timeline(
        cls,
        trajectory_data: Dict[str, object],
    ) -> List[Dict[str, object]]:
        messages_raw = trajectory_data.get("messages")
        messages = messages_raw if isinstance(messages_raw, list) else []
        typed_messages = [message for message in messages if isinstance(message, dict)]
        steps = cls._group_messages_into_steps(typed_messages)
        timeline: List[Dict[str, object]] = []
        for step_idx, step_messages in enumerate(steps, start=1):
            for message in step_messages:
                role = str(message.get("role") or "").lower()
                text = cls._message_text(message).strip()
                if role == "assistant":
                    if text:
                        timeline.append(
                            {
                                "event_type": "thinking",
                                "step": step_idx,
                                "content": "planning next action",
                            }
                        )
                        timeline.append(
                            {
                                "event_type": "assistant_response",
                                "step": step_idx,
                                "content": text,
                            }
                        )
                    extra = message.get("extra")
                    actions = extra.get("actions") if isinstance(extra, dict) else None
                    if isinstance(actions, list):
                        for action in actions:
                            if not isinstance(action, dict):
                                continue
                            tool_name = cls._infer_tool_name_from_action(action)
                            timeline.append(
                                {
                                    "event_type": "tool_call",
                                    "step": step_idx,
                                    "tool_name": tool_name,
                                }
                            )
                            result_text = cls._message_text(action).strip()
                            if result_text:
                                timeline.append(
                                    {
                                        "event_type": "tool_result",
                                        "step": step_idx,
                                        "tool_name": tool_name,
                                        "content": result_text,
                                    }
                                )
                elif role not in {"user", "system"} and text:
                    timeline.append({"event_type": "message", "step": step_idx, "content": text})
        return timeline

    @classmethod
    def _load_trajectory_artifacts(
        cls,
        trajectory_path: Path,
    ) -> Tuple[str, List[Dict[str, object]]]:
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
        result = _run_command_pipe(
            cmd=self.build_command(request),
            cwd=request.workspace,
            env=None,
            timeout_seconds=request.timeout_seconds,
            success_codes=[0],
            on_process_start=on_process_start,
        )
        synthetic_log, structured_timeline = self._load_trajectory_artifacts(
            self._trajectory_path(request)
        )
        if synthetic_log:
            merged_stdout = "\n".join(part for part in [synthetic_log, result.stdout] if part).strip()
            result.stdout = f"{merged_stdout}\n" if merged_stdout else ""
            result.metadata["stream_trace_mode"] = "mini_swe_trajectory"
        if structured_timeline:
            result.metadata["structured_timeline"] = structured_timeline
        if result.success and not synthetic_log:
            result.stderr = (
                f"{result.stderr}\n" if result.stderr else ""
            ) + (
                "mini-swe-agent finished without a trajectory file. "
                "Check model configuration and mini-swe-agent setup."
            )
            result.success = False
        return result


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
        transport: str = "pipe",
        trace_log_paths: Optional[List[str]] = None,
        trace_log_tail_lines: int = 800,
        trace_log_max_bytes: int = 512000,
    ) -> None:
        self.executable = executable
        self.agent_name = agent_name
        self.config_path = config_path
        self.model_slugs = list(model_slugs or [])
        self.allow_policies = list(allow_policies or [])
        self.extra_args = list(extra_args or [])
        self.transport = _normalize_transport(transport)
        self.trace_log_paths = _normalize_trace_log_paths(trace_log_paths)
        self.trace_log_tail_lines = max(0, int(trace_log_tail_lines))
        self.trace_log_max_bytes = max(1024, int(trace_log_max_bytes))

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
        transport: str = "pipe",
        trace_log_paths: Optional[List[str]] = None,
        trace_log_tail_lines: int = 800,
        trace_log_max_bytes: int = 512000,
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
            transport=transport,
            trace_log_paths=trace_log_paths,
            trace_log_tail_lines=trace_log_tail_lines,
            trace_log_max_bytes=trace_log_max_bytes,
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
        cmd.extend(self.extra_args)
        cmd.extend(["-p", request.task_prompt])
        return cmd

    @staticmethod
    def _append_continue_diagnostics(stderr: str, *, passthrough: bool = True) -> str:
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
            return base if passthrough else ""
        if base:
            return f"{base}\n{chr(10).join(hints)}"
        return "\n".join(hints)

    def run(
        self,
        request: AgentExecutionRequest,
        on_process_start: Optional[Callable[[int], None]] = None,
    ) -> AgentExecutionResult:
        resolved_trace_logs = _resolve_trace_log_candidates(
            templates=self.trace_log_paths,
            context=_request_template_context(request),
        )
        trace_offsets = _snapshot_log_offsets(resolved_trace_logs)
        cmd = self.build_command(request)
        runner = _run_command_pty if self.transport == "pty" else _run_command_pipe
        result = runner(
            cmd=cmd,
            cwd=request.workspace,
            env=None,
            timeout_seconds=request.timeout_seconds,
            success_codes=[0],
            on_process_start=on_process_start,
        )

        if self.transport == "pty":
            if result.success:
                result.stderr = ""
            else:
                fallback_source = result.stdout if not result.stderr.strip() else result.stderr
                result.stderr = self._append_continue_diagnostics(
                    fallback_source,
                    passthrough=False,
                )
        else:
            result.stderr = self._append_continue_diagnostics(result.stderr or "")
        trace_chunks, trace_capture_mode = _collect_trace_chunks_with_fallback(
            paths=resolved_trace_logs,
            offsets=trace_offsets,
            workspace=request.workspace,
            max_bytes=self.trace_log_max_bytes,
            tail_lines=self.trace_log_tail_lines,
        )
        if trace_chunks:
            result.metadata["trace_log_chunks"] = trace_chunks
            result.metadata["trace_log_paths"] = [item["path"] for item in trace_chunks]
        result.metadata["trace_log_capture_mode"] = trace_capture_mode
        return result
