import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.adapters import (
    ContinueCnAdapter,
    GenericCLIAdapter,
    MiniAgentAdapter,
    MiniSweAgentAdapter,
)
from agent_runtime.factory import create_agent_adapter, supported_agent_cli_choices


class AgentFactoryTests(unittest.TestCase):
    def test_supported_agent_cli_choices_are_stable(self):
        self.assertEqual(supported_agent_cli_choices(), ["mini-agent", "continue", "mini-swe-agent"])

    def test_create_mini_agent_adapter_with_alias(self):
        adapter = create_agent_adapter(agent="mini", auto_detect=False)
        self.assertIsInstance(adapter, MiniAgentAdapter)
        self.assertEqual(adapter.executable, "mini-agent")

    def test_create_continue_adapter_with_alias(self):
        adapter = create_agent_adapter(
            agent="cn",
            auto_detect=False,
            agent_name="org/agent",
            config_path="team/config",
            model_slugs=["owner/model"],
        )
        self.assertIsInstance(adapter, ContinueCnAdapter)
        self.assertEqual(adapter.agent_name, "org/agent")
        self.assertEqual(adapter.config_path, "team/config")
        self.assertEqual(adapter.model_slugs, ["owner/model"])

    def test_create_mini_swe_adapter_with_alias(self):
        adapter = create_agent_adapter(
            agent="mini-swe",
            auto_detect=False,
            model_name="openrouter/auto",
            config_specs=["mini.yaml"],
        )
        self.assertIsInstance(adapter, MiniSweAgentAdapter)
        self.assertEqual(adapter.model_name, "openrouter/auto")
        self.assertEqual(adapter.config_specs, ["mini.yaml"])

    def test_create_continue_adapter_auto_detects_executable(self):
        with patch("agent_runtime.adapters.ContinueCnAdapter.auto_detect") as detect:
            detect.return_value = ContinueCnAdapter(executable="/usr/local/bin/cn")
            adapter = create_agent_adapter(agent="continue", agent_name="org/agent")

        self.assertIsInstance(adapter, ContinueCnAdapter)
        self.assertEqual(adapter.executable, "/usr/local/bin/cn")
        self.assertEqual(adapter.agent_name, "org/agent")
        self.assertEqual(adapter.config_path, "continuedev/default-cli-config")

    def test_create_continue_adapter_uses_default_cli_config_when_not_provided(self):
        adapter = create_agent_adapter(agent="continue", auto_detect=False)
        self.assertIsInstance(adapter, ContinueCnAdapter)
        self.assertEqual(adapter.config_path, "continuedev/default-cli-config")

    def test_legacy_prefixed_kwargs_are_still_normalized(self):
        adapter = create_agent_adapter(
            agent="continue",
            auto_detect=False,
            continue_agent_name="legacy/agent",
            continue_config_path="legacy/config",
        )
        self.assertEqual(adapter.agent_name, "legacy/agent")
        self.assertEqual(adapter.config_path, "legacy/config")

    def test_create_agent_adapter_raises_for_unknown_agent(self):
        with self.assertRaises(ValueError):
            create_agent_adapter(agent="unknown")

    def test_create_unknown_agent_with_generic_cli_type(self):
        adapter = create_agent_adapter(
            agent="my-agent",
            auto_detect=False,
            adapter_type="generic-cli",
            agent_id="my-agent",
            command=["my-agent", "--task", "{task_prompt}"],
            process_name_hint="my-agent",
        )
        self.assertIsInstance(adapter, GenericCLIAdapter)
        self.assertEqual(adapter.agent_id, "my-agent")
        self.assertEqual(adapter.process_name_hint, "my-agent")

    def test_unknown_agent_without_registry_uses_generic_when_command_provided(self):
        adapter = create_agent_adapter(
            agent="unregistered-agent",
            auto_detect=False,
            command=["agent-binary", "{task_prompt}"],
        )
        self.assertIsInstance(adapter, GenericCLIAdapter)
        self.assertEqual(adapter.agent_id, "unregistered-agent")


if __name__ == "__main__":
    unittest.main()
