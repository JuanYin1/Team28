from __future__ import annotations

import abc
import re
from typing import List, Optional

from .models import AgentTraceEvent, AgentTraceSummary


class TraceParser(abc.ABC):
    """Abstract parser for converting raw logs into normalized events."""

    @abc.abstractmethod
    def parse(self, log_text: str) -> AgentTraceSummary:
        raise NotImplementedError


class MiniAgentTraceParser(TraceParser):
    """Regex-based parser for Mini-Agent stdout/stderr streams."""

    TOOL_CALL_PATTERN = re.compile(r"(?:🔧\s*)?Tool Call:\s*([a-zA-Z_][a-zA-Z0-9_]*)")
    TOOL_RESULT_PATTERN = re.compile(r"(?:✓|✅)\s*Result:")
    STEP_PATTERN = re.compile(r"Step\s+(\d+)/\d+")
    THINKING_PATTERN = re.compile(r"🧠\s*Thinking:")
    ASSISTANT_PATTERN = re.compile(r"🤖\s*Assistant:")
    ERROR_PATTERN = re.compile(r"(?:❌|✗)\s*(?:Error:)?")

    def __init__(self, known_tools: Optional[List[str]] = None) -> None:
        self.known_tools = set(known_tools or [])

    def parse(self, log_text: str) -> AgentTraceSummary:
        summary = AgentTraceSummary()
        unique_tools: List[str] = []
        current_step: Optional[int] = None

        for line_no, line in enumerate(log_text.splitlines()):
            step_match = self.STEP_PATTERN.search(line)
            if step_match:
                current_step = int(step_match.group(1))
                summary.total_steps = max(summary.total_steps, current_step)

            tool_match = self.TOOL_CALL_PATTERN.search(line)
            if tool_match:
                tool_name = tool_match.group(1)
                if not self.known_tools or tool_name in self.known_tools:
                    summary.tool_call_count += 1
                    if tool_name not in unique_tools:
                        unique_tools.append(tool_name)
                    summary.events.append(
                        AgentTraceEvent(
                            event_type="tool_call",
                            step=current_step,
                            line=line_no,
                            tool_name=tool_name,
                            text=line.strip(),
                        )
                    )

            if self.TOOL_RESULT_PATTERN.search(line):
                summary.successful_operations += 1
                summary.events.append(
                    AgentTraceEvent(
                        event_type="tool_result",
                        step=current_step,
                        line=line_no,
                        text=line.strip(),
                    )
                )

            if self.THINKING_PATTERN.search(line):
                summary.thinking_blocks += 1
                summary.events.append(
                    AgentTraceEvent(
                        event_type="thinking",
                        step=current_step,
                        line=line_no,
                        text=line.strip(),
                    )
                )

            if self.ASSISTANT_PATTERN.search(line):
                summary.assistant_responses += 1
                summary.events.append(
                    AgentTraceEvent(
                        event_type="assistant_response",
                        step=current_step,
                        line=line_no,
                        text=line.strip(),
                    )
                )

            if self.ERROR_PATTERN.search(line):
                summary.errors_encountered += 1
                summary.events.append(
                    AgentTraceEvent(
                        event_type="error",
                        step=current_step,
                        line=line_no,
                        text=line.strip(),
                    )
                )

        summary.tools_used = unique_tools
        return summary
