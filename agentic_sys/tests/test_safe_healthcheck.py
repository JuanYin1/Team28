import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.adapters import ContinueCnAdapter, MiniAgentAdapter, MiniSweAgentAdapter
from agent_runtime.safe_healthcheck import (
    build_safe_healthcheck_command,
    run_safe_healthcheck,
)


class SafeHealthcheckTests(unittest.TestCase):
    def test_build_safe_command_for_mini_agent_uses_version_without_task_prompt(self):
        adapter = MiniAgentAdapter(executable="mini-agent")
        cmd = build_safe_healthcheck_command(adapter)
        self.assertEqual(cmd, ["mini-agent", "--version"])
        self.assertNotIn("--task", cmd)
        self.assertNotIn("-p", cmd)

    def test_build_safe_command_for_continue_uses_version_without_prompt(self):
        adapter = ContinueCnAdapter(executable="cn")
        cmd = build_safe_healthcheck_command(adapter)
        self.assertEqual(cmd, ["cn", "--version"])
        self.assertNotIn("--task", cmd)
        self.assertNotIn("-p", cmd)

    def test_build_safe_command_for_mini_swe_uses_help_without_model_request(self):
        adapter = MiniSweAgentAdapter(executable="mini", model_name="openai/gpt-5")
        cmd = build_safe_healthcheck_command(adapter)
        self.assertEqual(cmd, ["mini", "--help"])
        self.assertNotIn("--task", cmd)
        self.assertNotIn("-m", cmd)

    def test_run_safe_healthcheck_returns_success_on_zero_exit(self):
        adapter = ContinueCnAdapter(executable="cn")

        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "1.2.3"
        proc.stderr = ""

        with patch("agent_runtime.safe_healthcheck.subprocess.run", return_value=proc):
            report = run_safe_healthcheck(adapter)

        self.assertTrue(report.success)
        self.assertEqual(report.command, ["cn", "--version"])
        self.assertEqual(report.return_code, 0)

    def test_run_safe_healthcheck_supports_mini_swe(self):
        adapter = MiniSweAgentAdapter(executable="mini")

        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "Usage: mini [OPTIONS]"
        proc.stderr = ""

        with patch("agent_runtime.safe_healthcheck.subprocess.run", return_value=proc):
            report = run_safe_healthcheck(adapter)

        self.assertTrue(report.success)
        self.assertEqual(report.command, ["mini", "--help"])
        self.assertEqual(report.return_code, 0)


if __name__ == "__main__":
    unittest.main()
