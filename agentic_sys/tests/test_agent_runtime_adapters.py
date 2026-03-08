import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.adapters import ContinueCnAdapter, GenericCLIAdapter, MiniAgentAdapter
from agent_runtime.models import AgentExecutionRequest


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
                "-p",
                "do work",
                "--auto",
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


class GenericCLIAdapterTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
