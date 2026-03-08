from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AgentExecutionRequest:
    """Normalized request sent to any agent adapter."""

    task_prompt: str
    workspace: str
    timeout_seconds: float


@dataclass
class AgentExecutionResult:
    """Normalized execution result returned by any agent adapter."""

    command: List[str]
    stdout: str
    stderr: str
    success: bool
    execution_time_seconds: float
    return_code: Optional[int] = None
    pid: Optional[int] = None
    timed_out: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTraceEvent:
    """A single parsed event extracted from agent logs."""

    event_type: str
    step: Optional[int] = None
    line: Optional[int] = None
    tool_name: Optional[str] = None
    text: str = ""


@dataclass
class AgentTraceSummary:
    """Parser output that is intentionally agent-agnostic."""

    total_steps: int = 0
    tools_used: List[str] = field(default_factory=list)
    tool_call_count: int = 0
    thinking_blocks: int = 0
    assistant_responses: int = 0
    errors_encountered: int = 0
    successful_operations: int = 0
    events: List[AgentTraceEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentPipelineRun:
    """Combined execution + parsed trace for a task run."""

    execution: AgentExecutionResult
    trace: Optional[AgentTraceSummary] = None
    trace_error: Optional[str] = None
