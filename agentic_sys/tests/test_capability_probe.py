import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.capability_probe import (  # noqa: E402
    load_capability_profile,
    run_capability_probe,
)
from agent_runtime.models import AgentExecutionResult  # noqa: E402


class _ProbeAdapter:
    agent_id = "probe-agent"
    process_name_hint = "probe-agent"

    def __init__(self, *, rich_output: bool):
        self.rich_output = rich_output

    def run(self, request, on_process_start=None):
        if on_process_start:
            on_process_start(9999)

        workspace = Path(request.workspace)
        stdout = ""
        if self.rich_output:
            if "probe_artifact.txt" in request.task_prompt:
                (workspace / "probe_artifact.txt").write_text("probe-ok", encoding="utf-8")
                stdout = "Step 1: create file. Tool: write_file. Step 2: read file."
            elif "multiple explicit steps" in request.task_prompt:
                stdout = "Step 1 done. Step 2 done. Tool: read_file."
            elif "invalid command" in request.task_prompt:
                stdout = "error triggered then fixed with retry success"
            else:
                stdout = "Total Messages: 2 Tool Calls: 1 API Tokens Used: 321"
        else:
            if "probe_artifact.txt" in request.task_prompt:
                stdout = "done"
            elif "invalid command" in request.task_prompt:
                stdout = "done"
            else:
                stdout = "ok"

        return AgentExecutionResult(
            command=["fake-agent"],
            stdout=stdout,
            stderr="",
            success=True,
            execution_time_seconds=0.01,
            return_code=0,
            pid=9999,
        )


class _TraceOnlyProbeAdapter:
    agent_id = "probe-agent"
    process_name_hint = "probe-agent"

    def run(self, request, on_process_start=None):
        if on_process_start:
            on_process_start(9999)
        trace_text = (
            '{"toolName":"Write"}\n'
            '{"step":1}\n'
            'assistant: completed\n'
        )
        return AgentExecutionResult(
            command=["fake-agent"],
            stdout="ok",
            stderr="",
            success=True,
            execution_time_seconds=0.01,
            return_code=0,
            pid=9999,
            metadata={
                "trace_log_chunks": [
                    {"path": "/tmp/fake.log", "text": trace_text},
                ]
            },
        )


class CapabilityProbeTests(unittest.TestCase):
    def test_probe_generates_profile_and_resolved_capabilities(self):
        declared = {
            "structured_trace": True,
            "tool_trace": True,
            "step_trace": True,
            "session_stats": True,
            "token_usage": True,
            "provider_cost": False,
            "checker_support": {
                "file_artifacts": True,
                "stdout_capture": True,
                "exit_code": True,
                "behavior_validation": True,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            profile = run_capability_probe(
                adapter=_ProbeAdapter(rich_output=True),
                agent_id="probe-agent",
                declared_capabilities=declared,
                profile_dir=str(Path(tmp) / "profiles"),
                timeout_seconds=5.0,
            )
            saved = load_capability_profile("probe-agent", str(Path(tmp) / "profiles"))

        self.assertIsNotNone(saved)
        self.assertEqual(saved["agent_id"], "probe-agent")
        self.assertTrue(saved["profile_metadata"]["auto_generated"])
        self.assertTrue(saved["profile_metadata"]["do_not_edit_manually"])
        self.assertIn("DO NOT EDIT MANUALLY", saved["profile_metadata"]["notice"])
        self.assertTrue(str(saved["generated_at_utc"]).endswith("Z"))
        self.assertTrue(profile["probed_capabilities"]["step_trace"])
        self.assertTrue(profile["resolved_capabilities"]["tool_trace"])
        self.assertTrue(profile["resolved_capabilities"]["token_usage"])
        self.assertFalse(profile["resolved_capabilities"]["provider_cost"])

    def test_probe_uses_conservative_declared_and_probed_merge(self):
        declared = {
            "structured_trace": True,
            "tool_trace": True,
            "step_trace": True,
            "session_stats": True,
            "token_usage": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            profile = run_capability_probe(
                adapter=_ProbeAdapter(rich_output=False),
                agent_id="probe-agent-low",
                declared_capabilities=declared,
                profile_dir=str(Path(tmp) / "profiles"),
                timeout_seconds=5.0,
            )
            saved_path = Path(tmp) / "profiles" / "probe-agent-low.json"
            payload = json.loads(saved_path.read_text(encoding="utf-8"))

        self.assertFalse(profile["probed_capabilities"]["tool_trace"])
        self.assertFalse(profile["resolved_capabilities"]["tool_trace"])
        self.assertFalse(profile["resolved_capabilities"]["step_trace"])
        self.assertEqual(payload["agent_id"], "probe-agent-low")

    def test_probe_reads_trace_log_chunks_from_adapter_metadata(self):
        declared = {
            "structured_trace": True,
            "tool_trace": True,
            "step_trace": True,
            "timeline_events": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            profile = run_capability_probe(
                adapter=_TraceOnlyProbeAdapter(),
                agent_id="probe-agent-trace",
                declared_capabilities=declared,
                profile_dir=str(Path(tmp) / "profiles"),
                timeout_seconds=5.0,
            )

        self.assertTrue(profile["probed_capabilities"]["tool_trace"])
        self.assertTrue(profile["probed_capabilities"]["step_trace"])
        self.assertTrue(profile["probed_capabilities"]["structured_trace"])
        self.assertTrue(profile["resolved_capabilities"]["timeline_events"])


if __name__ == "__main__":
    unittest.main()
