import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.script_config import resolve_script_runtime_options


class ScriptConfigResolutionTests(unittest.TestCase):
    def test_continue_defaults_are_loaded_from_yaml(self):
        config_yaml = """
agents:
  continue:
    scripts:
      run_single_test:
        results_dir: phase3_from_yaml
    adapter:
      agent_name: demo/agent
      config_path: demo/config
      model_slugs:
        - openai/gpt-4.1-mini
      allow_policies:
        - edit
      extra_args:
        - --auto
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            args = Namespace(
                agent="continue",
                agent_config=str(cfg),
                results_dir=None,
                continue_agent_name=None,
                continue_config=None,
                continue_model=None,
                continue_allow=None,
                continue_extra_arg=None,
                adapter_option=None,
            )
            results_dir, adapter_kwargs, source = resolve_script_runtime_options(
                args=args,
                script_name="run_single_test",
                default_results_dir="artifacts/mini-agent/phase3/single_test",
            )

        self.assertEqual(results_dir, "phase3_from_yaml")
        self.assertEqual(adapter_kwargs["agent_name"], "demo/agent")
        self.assertEqual(adapter_kwargs["config_path"], "demo/config")
        self.assertEqual(adapter_kwargs["model_slugs"], ["openai/gpt-4.1-mini"])
        self.assertEqual(adapter_kwargs["allow_policies"], ["edit"])
        self.assertEqual(adapter_kwargs["extra_args"], ["--auto"])
        self.assertIsNotNone(source)

    def test_cli_values_override_yaml_defaults(self):
        config_yaml = """
agents:
  continue:
    scripts:
      phase2:
        results_dir: phase2_from_yaml
    adapter:
      continue_agent_name: yaml/agent
      continue_config_path: yaml/config
      continue_model_slugs: [yaml/model]
      continue_allow_policies: [edit]
      continue_extra_args: [--auto]
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            args = Namespace(
                agent="continue",
                agent_config=str(cfg),
                results_dir="phase2_from_cli",
                continue_agent_name="cli/agent",
                continue_config="cli/config",
                continue_model=["cli/model"],
                continue_allow=["bash"],
                continue_extra_arg=["--silent"],
                adapter_option=None,
            )
            results_dir, adapter_kwargs, _ = resolve_script_runtime_options(
                args=args,
                script_name="phase2",
                default_results_dir="artifacts/mini-agent/phase2",
            )

        self.assertEqual(results_dir, "phase2_from_cli")
        self.assertEqual(adapter_kwargs["agent_name"], "cli/agent")
        self.assertEqual(adapter_kwargs["config_path"], "cli/config")
        self.assertEqual(adapter_kwargs["model_slugs"], ["cli/model"])
        self.assertEqual(adapter_kwargs["allow_policies"], ["bash"])
        self.assertEqual(adapter_kwargs["extra_args"], ["--silent"])

    def test_agent_alias_resolves_profile_by_yaml_aliases(self):
        config_yaml = """
agents:
  continue-cn:
    aliases: [continue, cn]
    scripts:
      phase3:
        results_dir: phase3_alias
    adapter:
      config_path: team/config
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            args = Namespace(
                agent="cn",
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
                script_name="phase3",
                default_results_dir="artifacts/mini-agent/phase3",
            )

        self.assertEqual(results_dir, "phase3_alias")
        self.assertEqual(adapter_kwargs["config_path"], "team/config")

    def test_unknown_agent_profile_can_be_resolved_from_yaml_only(self):
        config_yaml = """
agents:
  my-custom:
    aliases: [my]
    scripts:
      run_single_test:
        results_dir: phase3_my_custom
    adapter:
      type: generic-cli
      command: [my-agent, --task, "{task_prompt}"]
      process_name_hint: my-agent
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            args = Namespace(
                agent="my",
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

        self.assertEqual(results_dir, "phase3_my_custom")
        self.assertEqual(adapter_kwargs["adapter_type"], "generic-cli")
        self.assertEqual(adapter_kwargs["agent_id"], "my-custom")
        self.assertEqual(adapter_kwargs["command"], ["my-agent", "--task", "{task_prompt}"])

    def test_adapter_option_supports_generic_overrides(self):
        args = Namespace(
            agent="mini-agent",
            agent_config="/tmp/definitely-missing-agent-profiles.yaml",
            results_dir=None,
            continue_agent_name=None,
            continue_config=None,
            continue_model=None,
            continue_allow=None,
            continue_extra_arg=None,
            adapter_option=["executable=/tmp/custom-agent", "extra_args=[\"--json\"]", "enable_trace=true"],
        )
        _, adapter_kwargs, _ = resolve_script_runtime_options(
            args=args,
            script_name="phase1",
            default_results_dir="artifacts/mini-agent/phase1",
        )
        self.assertEqual(adapter_kwargs["executable"], "/tmp/custom-agent")
        self.assertEqual(adapter_kwargs["extra_args"], ["--json"])
        self.assertEqual(adapter_kwargs["enable_trace"], True)

    def test_missing_yaml_falls_back_to_builtin_defaults(self):
        args = Namespace(
            agent="mini-agent",
            agent_config="/tmp/definitely-missing-agent-profiles.yaml",
            results_dir=None,
            continue_agent_name=None,
            continue_config=None,
            continue_model=None,
            continue_allow=None,
            continue_extra_arg=None,
            adapter_option=None,
        )
        results_dir, adapter_kwargs, source = resolve_script_runtime_options(
            args=args,
            script_name="phase1",
            default_results_dir="artifacts/mini-agent/phase1",
        )

        self.assertEqual(results_dir, "artifacts/mini-agent/phase1")
        self.assertIsNone(source)
        self.assertEqual(adapter_kwargs, {})


if __name__ == "__main__":
    unittest.main()
