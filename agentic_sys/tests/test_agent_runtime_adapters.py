import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.adapters import ContinueCnAdapter, GenericCLIAdapter, MiniAgentAdapter, MiniSweAgentAdapter
from agent_runtime.models import AgentExecutionRequest, AgentExecutionResult


class MiniAgentAdapterTests(unittest.TestCase):
    def test_build_command_direct_mode(self):
        adapter = MiniAgentAdapter(executable="/opt/bin/mini-agent")
        request = AgentExecutionRequest(task_prompt="do work", workspace="/tmp/ws", timeout_seconds=30)
        self.assertEqual(
            adapter.build_command(request),
            ["/opt/bin/mini-agent", "--workspace", "/tmp/ws", "--task", "do work"],
        )

    def test_build_command_conda_mode(self):
        adapter = MiniAgentAdapter(executable="mini-agent", conda_env="mini-agent")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)
        self.assertEqual(
            adapter.build_command(request),
            ["conda", "run", "-n", "mini-agent", "mini-agent", "--workspace", "/tmp/ws", "--task", "task"],
        )

    def test_run_success_returns_normalized_result(self):
        adapter = MiniAgentAdapter(executable="mini-agent")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)

        fake_process = MagicMock()
        fake_process.pid = 123
        fake_process.communicate.return_value = ("stdout", "stderr")
        fake_process.returncode = 0

        with patch("agent_runtime.adapters.subprocess.Popen", return_value=fake_process):
            result = adapter.run(request)

        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "stdout")
        self.assertEqual(result.stderr, "stderr")
        self.assertEqual(result.return_code, 0)
        self.assertEqual(result.pid, 123)
        self.assertFalse(result.timed_out)

    def test_run_timeout_kills_process_and_marks_timed_out(self):
        adapter = MiniAgentAdapter(executable="mini-agent")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=1)

        fake_process = MagicMock()
        fake_process.pid = 456
        fake_process.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["mini-agent"], timeout=1),
            ("partial", "stderr"),
        ]
        fake_process.returncode = -9

        with patch("agent_runtime.adapters.subprocess.Popen", return_value=fake_process):
            result = adapter.run(request)

        fake_process.kill.assert_called_once()
        self.assertTrue(result.timed_out)
        self.assertFalse(result.success)
        self.assertEqual(result.stdout, "partial")
        self.assertIn("Task timed out", result.stderr)

    def test_run_handles_missing_binary(self):
        adapter = MiniAgentAdapter(executable="missing-mini-agent")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=1)

        with patch("agent_runtime.adapters.subprocess.Popen", side_effect=FileNotFoundError("not found")):
            result = adapter.run(request)

        self.assertFalse(result.success)
        self.assertIn("Execution error", result.stderr)

    def test_run_uses_pty_transport_when_configured(self):
        adapter = MiniAgentAdapter(executable="mini-agent", transport="pty")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)
        fake_result = AgentExecutionResult(
            command=["mini-agent", "--workspace", "/tmp/ws", "--task", "task"],
            stdout="out",
            stderr="",
            success=True,
            execution_time_seconds=0.5,
            return_code=0,
            pid=777,
            metadata={"transport": "pty", "merged_output": True},
        )

        with patch("agent_runtime.adapters._run_command_pty", return_value=fake_result) as pty_runner:
            result = adapter.run(request)

        self.assertEqual(result.metadata.get("transport"), "pty")
        pty_runner.assert_called_once()

    def test_run_appends_trace_log_chunks_to_metadata(self):
        adapter = MiniAgentAdapter(
            executable="mini-agent",
            trace_log_paths=["{workspace}/logs/agent.log"],
        )
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)
        fake_result = AgentExecutionResult(
            command=["mini-agent", "--workspace", "/tmp/ws", "--task", "task"],
            stdout="out",
            stderr="",
            success=True,
            execution_time_seconds=0.5,
            return_code=0,
            pid=777,
            metadata={"transport": "pipe"},
        )

        with patch("agent_runtime.adapters._run_command_pipe", return_value=fake_result), \
             patch("agent_runtime.adapters._snapshot_log_offsets", return_value={}), \
             patch(
                 "agent_runtime.adapters._capture_trace_log_chunks",
                 return_value=[{"path": "/tmp/ws/logs/agent.log", "text": "trace-line"}],
             ):
            result = adapter.run(request)

        self.assertIn("trace_log_chunks", result.metadata)
        self.assertEqual(result.metadata["trace_log_paths"], ["/tmp/ws/logs/agent.log"])

    def test_auto_detect_prefers_path_lookup(self):
        with patch("agent_runtime.adapters.shutil.which", return_value="/usr/local/bin/mini-agent"):
            adapter = MiniAgentAdapter.auto_detect()

        self.assertEqual(adapter.executable, "/usr/local/bin/mini-agent")
        self.assertIsNone(adapter.conda_env)

    def test_auto_detect_falls_back_to_conda(self):
        probe = MagicMock()
        probe.returncode = 0
        with patch("agent_runtime.adapters.shutil.which", return_value=None), \
             patch("agent_runtime.adapters.subprocess.run", return_value=probe):
            adapter = MiniAgentAdapter.auto_detect()

        self.assertEqual(adapter.executable, "mini-agent")
        self.assertEqual(adapter.conda_env, "mini-agent")

    def test_auto_detect_raises_when_unavailable(self):
        with patch("agent_runtime.adapters.shutil.which", return_value=None), \
             patch("agent_runtime.adapters.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(RuntimeError):
                MiniAgentAdapter.auto_detect()


class ContinueCnAdapterTests(unittest.TestCase):
    def test_build_command_with_agent_and_allow_policies(self):
        adapter = ContinueCnAdapter(
            executable="/usr/local/bin/cn",
            agent_name="my-org/my-agent",
            config_path="team/agent-config",
            model_slugs=["owner/model-a", "owner/model-b"],
            allow_policies=["read", "edit"],
            extra_args=["--auto"],
        )
        request = AgentExecutionRequest(task_prompt="do work", workspace="/tmp/ws", timeout_seconds=30)
        self.assertEqual(
            adapter.build_command(request),
            [
                "/usr/local/bin/cn",
                "--config",
                "team/agent-config",
                "--agent",
                "my-org/my-agent",
                "--model",
                "owner/model-a",
                "--model",
                "owner/model-b",
                "--allow",
                "read",
                "--allow",
                "edit",
                "--auto",
                "-p",
                "do work",
            ],
        )

    def test_run_success_returns_normalized_result(self):
        adapter = ContinueCnAdapter(executable="cn")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)

        fake_process = MagicMock()
        fake_process.pid = 789
        fake_process.communicate.return_value = ("stdout", "stderr")
        fake_process.returncode = 0

        with patch("agent_runtime.adapters.subprocess.Popen", return_value=fake_process):
            result = adapter.run(request)

        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "stdout")
        self.assertEqual(result.stderr, "stderr")
        self.assertEqual(result.return_code, 0)
        self.assertEqual(result.pid, 789)
        self.assertFalse(result.timed_out)

    def test_run_timeout_kills_process_and_marks_timed_out(self):
        adapter = ContinueCnAdapter(executable="cn")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=1)

        fake_process = MagicMock()
        fake_process.pid = 654
        fake_process.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["cn"], timeout=1),
            ("partial", "stderr"),
        ]
        fake_process.returncode = -9

        with patch("agent_runtime.adapters.subprocess.Popen", return_value=fake_process):
            result = adapter.run(request)

        fake_process.kill.assert_called_once()
        self.assertTrue(result.timed_out)
        self.assertFalse(result.success)
        self.assertEqual(result.stdout, "partial")
        self.assertIn("Task timed out", result.stderr)

    def test_auto_detect_raises_when_continue_cli_unavailable(self):
        with patch("agent_runtime.adapters.shutil.which", return_value=None), \
             patch("agent_runtime.adapters.Path.exists", return_value=False):
            with self.assertRaises(RuntimeError):
                ContinueCnAdapter.auto_detect(agent_name="x/y")

    def test_auto_detect_uses_path_lookup(self):
        with patch("agent_runtime.adapters.shutil.which", return_value="/usr/local/bin/cn"):
            adapter = ContinueCnAdapter.auto_detect(agent_name="x/y")

        self.assertEqual(adapter.executable, "/usr/local/bin/cn")
        self.assertEqual(adapter.agent_name, "x/y")

    def test_auto_detect_falls_back_to_standard_install_paths(self):
        with patch("agent_runtime.adapters.shutil.which", return_value=None), \
             patch("agent_runtime.adapters.Path.exists", return_value=True):
            adapter = ContinueCnAdapter.auto_detect(agent_name="x/y")

        self.assertEqual(adapter.executable, str((Path.home() / ".local" / "bin" / "cn")))

    def test_run_adds_actionable_hint_for_interceptor_error(self):
        adapter = ContinueCnAdapter(executable="cn")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)

        fake_process = MagicMock()
        fake_process.pid = 321
        fake_process.communicate.return_value = ("", "The request failed and the interceptors did not return an alternative response")
        fake_process.returncode = 1

        with patch("agent_runtime.adapters.subprocess.Popen", return_value=fake_process):
            result = adapter.run(request)

        self.assertFalse(result.success)
        self.assertIn("Hint:", result.stderr)

    def test_run_adds_credit_hint_for_no_credits_error(self):
        adapter = ContinueCnAdapter(executable="cn", config_path="continuedev/default-cli-config")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)

        fake_process = MagicMock()
        fake_process.pid = 322
        fake_process.communicate.return_value = ("", "402 You have no credits remaining on your Continue account.")
        fake_process.returncode = 1

        with patch("agent_runtime.adapters.subprocess.Popen", return_value=fake_process):
            result = adapter.run(request)

        self.assertFalse(result.success)
        self.assertIn("credits are exhausted", result.stderr)

    def test_run_uses_pty_transport_when_configured(self):
        adapter = ContinueCnAdapter(executable="cn", transport="pty")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)
        fake_result = AgentExecutionResult(
            command=["cn", "-p", "task"],
            stdout="trace output",
            stderr="",
            success=False,
            execution_time_seconds=0.6,
            return_code=1,
            pid=778,
            metadata={"transport": "pty", "merged_output": True},
        )

        with patch("agent_runtime.adapters._run_command_pty", return_value=fake_result) as pty_runner:
            result = adapter.run(request)

        self.assertEqual(result.metadata.get("transport"), "pty")
        self.assertTrue(
            ("Hint:" in result.stderr) or (result.stderr == "")
        )
        pty_runner.assert_called_once()

    def test_run_collects_trace_logs_when_configured(self):
        adapter = ContinueCnAdapter(
            executable="cn",
            trace_log_paths=["~/.continue/logs/cn.log"],
        )
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)
        fake_result = AgentExecutionResult(
            command=["cn", "-p", "task"],
            stdout="ok",
            stderr="",
            success=True,
            execution_time_seconds=0.6,
            return_code=0,
            pid=778,
            metadata={"transport": "pipe"},
        )

        with patch("agent_runtime.adapters._run_command_pipe", return_value=fake_result), \
             patch("agent_runtime.adapters._snapshot_log_offsets", return_value={}), \
             patch(
                 "agent_runtime.adapters._capture_trace_log_chunks",
                 return_value=[{"path": "/Users/x/.continue/logs/cn.log", "text": "trace-line"}],
             ):
            result = adapter.run(request)

        self.assertIn("trace_log_chunks", result.metadata)
        self.assertEqual(result.metadata["trace_log_paths"], ["/Users/x/.continue/logs/cn.log"])
        self.assertEqual(result.metadata["trace_log_capture_mode"], "delta")

    def test_run_uses_workspace_filtered_fallback_tail_when_delta_empty(self):
        adapter = ContinueCnAdapter(
            executable="cn",
            trace_log_paths=["~/.continue/logs/cn.log"],
        )
        request = AgentExecutionRequest(
            task_prompt="task",
            workspace="/tmp/ws_123",
            timeout_seconds=30,
        )
        fake_result = AgentExecutionResult(
            command=["cn", "-p", "task"],
            stdout="ok",
            stderr="",
            success=True,
            execution_time_seconds=0.6,
            return_code=0,
            pid=778,
            metadata={"transport": "pipe"},
        )

        fallback_chunks = [
            {"path": "/Users/x/.continue/logs/cn.log", "text": "old unrelated line"},
            {
                "path": "/Users/x/.continue/logs/cn.log",
                "text": 'Executing tool {"toolName":"Write","arguments":{"filepath":"/private/tmp/ws_123/a.txt"}}',
            },
        ]
        with patch("agent_runtime.adapters._run_command_pipe", return_value=fake_result), \
             patch("agent_runtime.adapters._snapshot_log_offsets", return_value={}), \
             patch("agent_runtime.adapters._capture_trace_log_chunks", return_value=[]), \
             patch("agent_runtime.adapters._capture_trace_log_tail", return_value=fallback_chunks):
            result = adapter.run(request)

        self.assertIn("trace_log_chunks", result.metadata)
        self.assertEqual(len(result.metadata["trace_log_chunks"]), 1)
        self.assertIn("ws_123", result.metadata["trace_log_chunks"][0]["text"])
        self.assertEqual(result.metadata["trace_log_capture_mode"], "tail_fallback")

    def test_workspace_filter_prefers_strong_path_match_over_weak_basename_match(self):
        adapter = ContinueCnAdapter(
            executable="cn",
            trace_log_paths=["~/.continue/logs/cn.log"],
        )
        request = AgentExecutionRequest(
            task_prompt="task",
            workspace="/tmp/tmp",
            timeout_seconds=30,
        )
        fake_result = AgentExecutionResult(
            command=["cn", "-p", "task"],
            stdout="ok",
            stderr="",
            success=True,
            execution_time_seconds=0.6,
            return_code=0,
            pid=778,
            metadata={"transport": "pipe"},
        )
        fallback_chunks = [
            {
                "path": "/Users/x/.continue/logs/cn.log",
                "text": 'tool {"toolName":"Write","arguments":{"filepath":"/private/tmp/other/a.txt"}}',
            },
            {
                "path": "/Users/x/.continue/logs/cn.log",
                "text": 'tool {"toolName":"Write","arguments":{"filepath":"/private/tmp/tmp/b.txt"}}',
            },
        ]

        with patch("agent_runtime.adapters._run_command_pipe", return_value=fake_result), \
             patch("agent_runtime.adapters._snapshot_log_offsets", return_value={}), \
             patch("agent_runtime.adapters._capture_trace_log_chunks", return_value=[]), \
             patch("agent_runtime.adapters._capture_trace_log_tail", return_value=fallback_chunks):
            result = adapter.run(request)

        self.assertIn("trace_log_chunks", result.metadata)
        self.assertEqual(len(result.metadata["trace_log_chunks"]), 1)
        self.assertIn("/private/tmp/tmp/b.txt", result.metadata["trace_log_chunks"][0]["text"])
        self.assertEqual(result.metadata["trace_log_capture_mode"], "tail_fallback")

    def test_run_uses_unfiltered_fallback_tail_for_single_trace_log(self):
        adapter = ContinueCnAdapter(
            executable="cn",
            trace_log_paths=["~/.continue/logs/cn.log"],
        )
        request = AgentExecutionRequest(
            task_prompt="task",
            workspace="/tmp/ws_missing_token",
            timeout_seconds=30,
        )
        fake_result = AgentExecutionResult(
            command=["cn", "-p", "task"],
            stdout="ok",
            stderr="",
            success=True,
            execution_time_seconds=0.6,
            return_code=0,
            pid=778,
            metadata={"transport": "pipe"},
        )
        fallback_chunks = [
            {
                "path": "/Users/x/.continue/logs/cn.log",
                "text": 'Received chunk {"function":{"name":"Write"}}',
            }
        ]

        with patch("agent_runtime.adapters._run_command_pipe", return_value=fake_result), \
             patch("agent_runtime.adapters._snapshot_log_offsets", return_value={}), \
             patch("agent_runtime.adapters._capture_trace_log_chunks", return_value=[]), \
             patch("agent_runtime.adapters._capture_trace_log_tail", return_value=fallback_chunks):
            result = adapter.run(request)

        self.assertIn("trace_log_chunks", result.metadata)
        self.assertEqual(result.metadata["trace_log_chunks"], fallback_chunks)
        self.assertEqual(result.metadata["trace_log_capture_mode"], "tail_fallback_unfiltered")


class GenericCLIAdapterTests(unittest.TestCase):
    def test_invalid_transport_raises_value_error(self):
        with self.assertRaises(ValueError):
            GenericCLIAdapter(agent_id="a", command=["/bin/echo", "{task_prompt}"], transport="unknown")

    def test_build_command_renders_templates(self):
        adapter = GenericCLIAdapter(
            agent_id="my-agent",
            command=["my-agent", "--workspace", "{workspace}", "--task", "{task_prompt}"],
            cwd="{workspace}",
            env={"RUN_TIMEOUT": "{timeout_seconds}"},
        )
        request = AgentExecutionRequest(
            task_prompt="solve task",
            workspace="/tmp/ws",
            timeout_seconds=45,
        )

        self.assertEqual(
            adapter.build_command(request),
            ["my-agent", "--workspace", "/tmp/ws", "--task", "solve task"],
        )

    def test_run_success_with_custom_success_codes(self):
        adapter = GenericCLIAdapter(
            agent_id="my-agent",
            command=["my-agent", "{task_prompt}"],
            success_codes=[0, 3],
            cwd="{workspace}",
            env={"PROMPT": "{task_prompt}"},
        )
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)

        fake_process = MagicMock()
        fake_process.pid = 998
        fake_process.communicate.return_value = ("stdout", "stderr")
        fake_process.returncode = 3

        with patch("agent_runtime.adapters.subprocess.Popen", return_value=fake_process) as popen_mock:
            result = adapter.run(request)

        self.assertTrue(result.success)
        self.assertEqual(result.return_code, 3)
        self.assertEqual(popen_mock.call_args.kwargs["cwd"], "/tmp/ws")
        self.assertEqual(popen_mock.call_args.kwargs["env"]["PROMPT"], "task")

    def test_run_timeout_kills_process_and_marks_timed_out(self):
        adapter = GenericCLIAdapter(
            agent_id="my-agent",
            command=["my-agent", "{task_prompt}"],
        )
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=1)

        fake_process = MagicMock()
        fake_process.pid = 654
        fake_process.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["my-agent"], timeout=1),
            ("partial", "stderr"),
        ]
        fake_process.returncode = -9

        with patch("agent_runtime.adapters.subprocess.Popen", return_value=fake_process):
            result = adapter.run(request)

        fake_process.kill.assert_called_once()
        self.assertTrue(result.timed_out)
        self.assertFalse(result.success)
        self.assertEqual(result.stdout, "partial")
        self.assertIn("Task timed out", result.stderr)

    def test_run_real_command_end_to_end(self):
        adapter = GenericCLIAdapter(
            agent_id="echo-agent",
            command=["/bin/echo", "{task_prompt}"],
            cwd=None,
        )
        request = AgentExecutionRequest(task_prompt="hello-world", workspace="/tmp/ws", timeout_seconds=5)

        result = adapter.run(request)

        self.assertTrue(result.success)
        self.assertEqual(result.return_code, 0)
        self.assertIn("hello-world", result.stdout.strip())

    def test_run_uses_pty_transport_when_configured(self):
        adapter = GenericCLIAdapter(
            agent_id="my-agent",
            command=["my-agent", "{task_prompt}"],
            transport="pty",
        )
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)
        fake_result = AgentExecutionResult(
            command=["my-agent", "task"],
            stdout="out",
            stderr="",
            success=True,
            execution_time_seconds=0.7,
            return_code=0,
            pid=779,
            metadata={"transport": "pty", "merged_output": True},
        )

        with patch("agent_runtime.adapters._run_command_pty", return_value=fake_result) as pty_runner:
            result = adapter.run(request)

        self.assertEqual(result.metadata.get("transport"), "pty")
        pty_runner.assert_called_once()

    def test_generic_adapter_collects_trace_logs_when_configured(self):
        adapter = GenericCLIAdapter(
            agent_id="my-agent",
            command=["my-agent", "{task_prompt}"],
            trace_log_paths=["{workspace}/logs/agent.log"],
        )
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)
        fake_result = AgentExecutionResult(
            command=["my-agent", "task"],
            stdout="out",
            stderr="",
            success=True,
            execution_time_seconds=0.7,
            return_code=0,
            pid=779,
            metadata={"transport": "pipe"},
        )

        with patch("agent_runtime.adapters._run_command_pipe", return_value=fake_result), \
             patch("agent_runtime.adapters._snapshot_log_offsets", return_value={}), \
             patch(
                 "agent_runtime.adapters._capture_trace_log_chunks",
                 return_value=[{"path": "/tmp/ws/logs/agent.log", "text": "trace-line"}],
             ):
            result = adapter.run(request)

        self.assertIn("trace_log_chunks", result.metadata)
        self.assertEqual(result.metadata["trace_log_paths"], ["/tmp/ws/logs/agent.log"])
        self.assertEqual(result.metadata["trace_log_capture_mode"], "delta")

    def test_generic_adapter_uses_filtered_fallback_tail_when_delta_empty(self):
        adapter = GenericCLIAdapter(
            agent_id="my-agent",
            command=["my-agent", "{task_prompt}"],
            trace_log_paths=["{workspace}/logs/agent.log"],
        )
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws_abc", timeout_seconds=30)
        fake_result = AgentExecutionResult(
            command=["my-agent", "task"],
            stdout="out",
            stderr="",
            success=True,
            execution_time_seconds=0.7,
            return_code=0,
            pid=779,
            metadata={"transport": "pipe"},
        )
        fallback_chunks = [
            {"path": "/tmp/ws_abc/logs/agent.log", "text": "unrelated line"},
            {"path": "/tmp/ws_abc/logs/agent.log", "text": "write /private/tmp/ws_abc/out.txt"},
        ]

        with patch("agent_runtime.adapters._run_command_pipe", return_value=fake_result), \
             patch("agent_runtime.adapters._snapshot_log_offsets", return_value={}), \
             patch("agent_runtime.adapters._capture_trace_log_chunks", return_value=[]), \
             patch("agent_runtime.adapters._capture_trace_log_tail", return_value=fallback_chunks):
            result = adapter.run(request)

        self.assertIn("trace_log_chunks", result.metadata)
        self.assertEqual(len(result.metadata["trace_log_chunks"]), 1)
        self.assertIn("ws_abc", result.metadata["trace_log_chunks"][0]["text"])
        self.assertEqual(result.metadata["trace_log_capture_mode"], "tail_fallback")


class MiniSweAgentAdapterTests(unittest.TestCase):
    def test_build_command(self):
        adapter = MiniSweAgentAdapter(
            executable="mini",
            model_name="openai/gpt-5",
            config_specs=["mini.yaml"],
        )
        request = AgentExecutionRequest(task_prompt="solve task", workspace="/tmp/ws", timeout_seconds=30)

        self.assertEqual(
            adapter.build_command(request),
            [
                "mini",
                "-t",
                "solve task",
                "-m",
                "openai/gpt-5",
                "-c",
                "mini.yaml",
                "-y",
                "--exit-immediately",
                "-o",
                "/tmp/ws/mini_swe_run.traj.json",
            ],
        )

    def test_auto_detect_uses_path_lookup(self):
        with patch("agent_runtime.adapters.shutil.which", return_value="/usr/local/bin/mini"):
            adapter = MiniSweAgentAdapter.auto_detect(model_name="openai/gpt-5")

        self.assertEqual(adapter.executable, "/usr/local/bin/mini")
        self.assertEqual(adapter.model_name, "openai/gpt-5")

    def test_auto_detect_raises_when_unavailable(self):
        with patch("agent_runtime.adapters.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                MiniSweAgentAdapter.auto_detect()

    def test_run_merges_trajectory_trace_into_metadata(self):
        adapter = MiniSweAgentAdapter(executable="mini")
        request = AgentExecutionRequest(task_prompt="task", workspace="/tmp/ws", timeout_seconds=30)
        fake_result = AgentExecutionResult(
            command=["mini", "-t", "task"],
            stdout="raw stdout",
            stderr="",
            success=True,
            execution_time_seconds=0.5,
            return_code=0,
            pid=123,
            metadata={},
        )

        with patch("agent_runtime.adapters._run_command_pipe", return_value=fake_result), \
             patch.object(
                 MiniSweAgentAdapter,
                 "_load_trajectory_artifacts",
                 return_value=("Step 1/1\nTool Call: bash", [{"event_type": "tool_call", "tool_name": "bash"}]),
             ):
            result = adapter.run(request)

        self.assertTrue(result.success)
        self.assertIn("Step 1/1", result.stdout)
        self.assertEqual(result.metadata["stream_trace_mode"], "mini_swe_trajectory")
        self.assertEqual(result.metadata["structured_timeline"][0]["tool_name"], "bash")

    def test_trajectory_to_structured_timeline_matches_visualization_event_model(self):
        trajectory = {
            "messages": [
                {
                    "role": "assistant",
                    "content": "I will inspect the workspace.",
                    "extra": {
                        "actions": [
                            {
                                "tool": "bash",
                                "output": "listing complete",
                            }
                        ]
                    },
                }
            ]
        }

        timeline = MiniSweAgentAdapter._trajectory_to_structured_timeline(trajectory)

        self.assertEqual(
            [event["event_type"] for event in timeline],
            ["thinking", "assistant_response", "tool_call", "tool_result"],
        )
        self.assertEqual([event["step"] for event in timeline], [1, 1, 1, 1])
        self.assertEqual(timeline[2]["tool_name"], "bash")
        self.assertEqual(timeline[3]["content"], "listing complete")

    def test_infer_tool_name_from_action_best_effort_maps_file_operations(self):
        self.assertEqual(
            MiniSweAgentAdapter._infer_tool_name_from_action({"command": "cat hello.txt"}),
            "read_file",
        )
        self.assertEqual(
            MiniSweAgentAdapter._infer_tool_name_from_action({"command": "printf hi > hello.txt"}),
            "write_file",
        )
        self.assertEqual(
            MiniSweAgentAdapter._infer_tool_name_from_action({"command": "sed -i '' '1s/a/b/' hello.txt"}),
            "edit_file",
        )
        self.assertEqual(
            MiniSweAgentAdapter._infer_tool_name_from_action({"command": "python script.py"}),
            "bash",
        )

    def test_trajectory_to_structured_timeline_maps_bash_commands_to_normalized_tools(self):
        trajectory = {
            "messages": [
                {
                    "role": "assistant",
                    "content": "I will create and inspect files.",
                    "extra": {
                        "actions": [
                            {"command": "printf hi > hello.txt", "output": "written"},
                            {"command": "cat hello.txt", "output": "hi"},
                        ]
                    },
                }
            ]
        }

        timeline = MiniSweAgentAdapter._trajectory_to_structured_timeline(trajectory)
        tool_calls = [event for event in timeline if event["event_type"] == "tool_call"]
        self.assertEqual([event["tool_name"] for event in tool_calls], ["write_file", "read_file"])


if __name__ == "__main__":
    unittest.main()
