import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.continue_healthcheck import (
    diagnose_continue_result,
    run_continue_healthcheck,
    run_continue_login,
)
from agent_runtime.models import AgentExecutionResult


class ContinueHealthcheckTests(unittest.TestCase):
    def test_diagnose_success(self):
        result = AgentExecutionResult(
            command=["cn", "-p", "ok"],
            stdout="OK",
            stderr="",
            success=True,
            execution_time_seconds=1.0,
            return_code=0,
        )
        self.assertEqual(diagnose_continue_result(result), "ok")

    def test_diagnose_interceptor_error(self):
        result = AgentExecutionResult(
            command=["cn", "-p", "ok"],
            stdout="",
            stderr="interceptors did not return an alternative response",
            success=False,
            execution_time_seconds=1.0,
            return_code=1,
        )
        self.assertEqual(diagnose_continue_result(result), "auth_or_model_not_configured")

    def test_diagnose_interceptor_error_from_stdout_json(self):
        result = AgentExecutionResult(
            command=["cn", "-p", "ok"],
            stdout='{"status":"error","message":"The request failed and the interceptors did not return an alternative response"}',
            stderr="",
            success=False,
            execution_time_seconds=1.0,
            return_code=1,
        )
        self.assertEqual(diagnose_continue_result(result), "auth_or_model_not_configured")

    def test_diagnose_credit_exhaustion(self):
        result = AgentExecutionResult(
            command=["cn", "-p", "ok"],
            stdout="",
            stderr='402 "You have no credits remaining on your Continue account."',
            success=False,
            execution_time_seconds=1.0,
            return_code=1,
        )
        self.assertEqual(diagnose_continue_result(result), "account_credits_exhausted")

    def test_healthcheck_returns_binary_not_found(self):
        with patch("agent_runtime.continue_healthcheck.ContinueCnAdapter.auto_detect", side_effect=RuntimeError("not found")):
            report = run_continue_healthcheck()

        self.assertFalse(report.success)
        self.assertEqual(report.diagnosis, "binary_not_found")

    def test_run_continue_login_treats_ttyless_post_login_error_as_success(self):
        fake_completed = type(
            "Completed",
            (),
            {
                "returncode": 1,
                "stdout": "✅ Success!\nSuccessfully logged in!\nStarting Continue CLI...",
                "stderr": "Fatal error: Cannot start TUI in TTY-less environment.",
            },
        )()
        with patch("agent_runtime.continue_healthcheck.subprocess.run", return_value=fake_completed):
            report = run_continue_login(executable="cn", timeout_seconds=10)

        self.assertTrue(report.success)
        self.assertEqual(report.diagnosis, "ok")
        self.assertEqual(report.return_code, 1)

    def test_run_continue_login_detects_network_error(self):
        fake_completed = type(
            "Completed",
            (),
            {
                "returncode": 1,
                "stdout": "Device authorization error: fetch failed",
                "stderr": "",
            },
        )()
        with patch("agent_runtime.continue_healthcheck.subprocess.run", return_value=fake_completed):
            report = run_continue_login(executable="cn", timeout_seconds=10)

        self.assertFalse(report.success)
        self.assertEqual(report.diagnosis, "network_or_proxy_error")


@unittest.skipUnless(
    os.getenv("RUN_CONTINUE_LIVE_TESTS") == "1",
    "Skipped by default: this live Continue test sends a real model request and may consume tokens/credits. Set RUN_CONTINUE_LIVE_TESTS=1 to run it.",
)
class ContinueLiveSmokeTests(unittest.TestCase):
    def test_continue_can_serve_real_request(self):
        extra_args = os.getenv("CONTINUE_CN_EXTRA_ARGS", "--auto").strip().split()
        model_slugs = [item.strip() for item in os.getenv("CONTINUE_CN_MODELS", "").split(",") if item.strip()]
        allow_policies = [item.strip() for item in os.getenv("CONTINUE_CN_ALLOW", "").split(",") if item.strip()]
        report = run_continue_healthcheck(
            executable=os.getenv("CONTINUE_CN_EXECUTABLE") or None,
            agent_name=os.getenv("CONTINUE_CN_AGENT") or None,
            config_path=os.getenv("CONTINUE_CN_CONFIG") or None,
            model_slugs=model_slugs or None,
            allow_policies=allow_policies or None,
            extra_args=extra_args,
            prompt=os.getenv("CONTINUE_CN_SMOKE_PROMPT", "Reply with exactly OK and nothing else."),
            timeout_seconds=float(os.getenv("CONTINUE_CN_TIMEOUT", "60")),
        )

        self.assertTrue(
            report.success,
            f"Continue live request failed. diagnosis={report.diagnosis}, stderr={report.stderr}",
        )
        self.assertTrue(report.stdout.strip())


if __name__ == "__main__":
    unittest.main()
