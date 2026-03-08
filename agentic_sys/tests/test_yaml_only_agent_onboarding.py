import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.factory import create_agent_adapter
from agent_runtime.models import AgentExecutionRequest
from agent_runtime.script_config import resolve_script_runtime_options


class YamlOnlyAgentOnboardingTests(unittest.TestCase):
    def test_custom_agent_can_run_via_yaml_without_registry_change(self):
        config_yaml = """
agents:
  echo-agent:
    aliases: [echo]
    scripts:
      run_single_test:
        results_dir: phase3_echo
    adapter:
      type: generic-cli
      process_name_hint: echo
      command: [/bin/echo, "{task_prompt}"]
      cwd: "{workspace}"
      success_codes: [0]
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            args = Namespace(
                agent="echo",
                agent_config=str(cfg),
                results_dir=None,
                continue_agent_name=None,
                continue_config=None,
                continue_model=None,
                continue_allow=None,
                continue_extra_arg=None,
                adapter_option=None,
            )
            results_dir, adapter_kwargs, _ = resolve_script_runtime_options(
                args=args,
                script_name="run_single_test",
                default_results_dir="artifacts/mini-agent/phase3/single_test",
            )
            adapter = create_agent_adapter(agent=args.agent, auto_detect=False, **adapter_kwargs)

            request = AgentExecutionRequest(
                task_prompt="yaml-only-onboarding",
                workspace=tmp,
                timeout_seconds=5,
            )
            execution = adapter.run(request)

        self.assertEqual(results_dir, "phase3_echo")
        self.assertEqual(adapter.agent_id, "echo-agent")
        self.assertEqual(adapter.process_name_hint, "echo")
        self.assertTrue(execution.success)
        self.assertEqual(execution.return_code, 0)
        self.assertIn("yaml-only-onboarding", execution.stdout)


if __name__ == "__main__":
    unittest.main()
