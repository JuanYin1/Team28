from __future__ import annotations

import tempfile
from typing import Optional

from .adapters import AgentAdapter
from .models import AgentExecutionRequest, AgentPipelineRun
from .parsers import TraceParser


class AgentPipelineRunner:
    """Small orchestrator that binds adapter execution with optional log parsing."""

    def __init__(self, adapter: AgentAdapter, parser: Optional[TraceParser] = None) -> None:
        self.adapter = adapter
        self.parser = parser

    def run_task(
        self,
        *,
        task_prompt: str,
        timeout_seconds: float,
        workspace: Optional[str] = None,
    ) -> AgentPipelineRun:
        if workspace:
            request = AgentExecutionRequest(
                task_prompt=task_prompt,
                workspace=workspace,
                timeout_seconds=timeout_seconds,
            )
            execution = self.adapter.run(request)
            return self._build_pipeline_result(execution)

        with tempfile.TemporaryDirectory() as temp_workspace:
            request = AgentExecutionRequest(
                task_prompt=task_prompt,
                workspace=temp_workspace,
                timeout_seconds=timeout_seconds,
            )
            execution = self.adapter.run(request)
            return self._build_pipeline_result(execution)

    def _build_pipeline_result(self, execution) -> AgentPipelineRun:
        if not self.parser:
            return AgentPipelineRun(execution=execution)

        combined_log = f"{execution.stdout}\n{execution.stderr}".strip()
        if not combined_log:
            return AgentPipelineRun(execution=execution)

        try:
            trace = self.parser.parse(combined_log)
            return AgentPipelineRun(execution=execution, trace=trace)
        except Exception as exc:  # pragma: no cover - defensive fallback
            return AgentPipelineRun(execution=execution, trace_error=str(exc))
