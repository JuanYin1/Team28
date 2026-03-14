import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.models import AgentExecutionResult, AgentTraceSummary
from agent_runtime.runner import AgentPipelineRunner


class _FakeAdapter:
    agent_id = "fake"

    def __init__(self):
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return AgentExecutionResult(
            command=["fake-agent"],
            stdout="stdout",
            stderr="stderr",
            success=True,
            execution_time_seconds=0.5,
            return_code=0,
            pid=99,
            metadata={"workspace_exists": os.path.isdir(request.workspace)},
        )


class _FakeParser:
    def __init__(self):
        self.last_log = None

    def parse(self, log_text):
        self.last_log = log_text
        return AgentTraceSummary(tool_call_count=1)


class _FailingParser:
    def parse(self, _):
        raise ValueError("parse failure")


class AgentPipelineRunnerTests(unittest.TestCase):
    def test_runner_with_explicit_workspace(self):
        adapter = _FakeAdapter()
        parser = _FakeParser()
        runner = AgentPipelineRunner(adapter=adapter, parser=parser)

        run = runner.run_task(task_prompt="task", timeout_seconds=10, workspace="/tmp")

        self.assertEqual(len(adapter.requests), 1)
        self.assertIn("stdout", parser.last_log)
        self.assertIn("stderr", parser.last_log)
        self.assertIsNotNone(run.trace)
        self.assertIsNone(run.trace_error)

    def test_runner_without_workspace_creates_temp_workspace(self):
        adapter = _FakeAdapter()
        runner = AgentPipelineRunner(adapter=adapter)

        run = runner.run_task(task_prompt="task", timeout_seconds=10)

        self.assertEqual(len(adapter.requests), 1)
        self.assertTrue(run.execution.metadata["workspace_exists"])

    def test_runner_captures_parser_errors_without_crashing(self):
        adapter = _FakeAdapter()
        runner = AgentPipelineRunner(adapter=adapter, parser=_FailingParser())

        run = runner.run_task(task_prompt="task", timeout_seconds=10)

        self.assertIsNone(run.trace)
        self.assertEqual(run.trace_error, "parse failure")


if __name__ == "__main__":
    unittest.main()
