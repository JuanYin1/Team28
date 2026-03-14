import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.script_config import (
    read_agent_config,
    resolve_evaluation_settings,
    resolve_script_runtime_options,
)


class ScriptConfigResolutionTests(unittest.TestCase):
    def test_read_agent_config_returns_source_path(self):
        config_yaml = "version: 2\n"
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            config, source = read_agent_config(str(cfg))

        self.assertEqual(config.get("version"), 2)
        self.assertEqual(source, cfg)

    def test_resolve_evaluation_settings_merges_shared_and_script_specific(self):
        config_yaml = """
evaluation:
  shared:
    scoring_version: v2
    runs_per_task: 3
  scripts:
    phase3:
      runs_per_task: 5
      include_runtime_extension_suite: false
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            settings, source = resolve_evaluation_settings(
                config_path=str(cfg),
                script_name="phase3",
            )

        self.assertEqual(source, cfg)
        self.assertEqual(settings["scoring_version"], "v2")
        self.assertEqual(settings["runs_per_task"], 5)
        self.assertFalse(settings["include_runtime_extension_suite"])

    def test_resolve_evaluation_settings_loads_agent_capabilities(self):
        config_yaml = """
evaluation:
  v2:
    capability_probe:
      profile_dir: artifacts/capability_profiles
agents:
  demo-agent:
    aliases: [demo]
    evaluation_capabilities:
      structured_trace: true
      tool_trace: true
      step_trace: false
      checker_support:
        file_artifacts: true
        stdout_capture: true
        exit_code: true
        behavior_validation: false
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            settings, _ = resolve_evaluation_settings(
                config_path=str(cfg),
                script_name="phase3",
                agent="demo",
                use_capability_profile=True,
            )

        self.assertEqual(settings["evaluation_agent_id"], "demo-agent")
        self.assertTrue(settings["declared_capabilities"]["structured_trace"])
        self.assertTrue(settings["resolved_capabilities"]["tool_trace"])
        self.assertFalse(settings["resolved_capabilities"]["step_trace"])
        self.assertFalse(settings["resolved_capabilities"]["checker_support"]["behavior_validation"])

    def test_probe_profile_is_merged_into_resolved_capabilities(self):
        config_yaml = """
evaluation:
  v2:
    capability_probe:
      profile_dir: artifacts/capability_profiles
agents:
  demo-agent:
    aliases: [demo]
    evaluation_capabilities:
      structured_trace: true
      tool_trace: true
      step_trace: true
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            profile_dir = Path(tmp) / "artifacts" / "capability_profiles"
            profile_dir.mkdir(parents=True, exist_ok=True)
            profile_path = profile_dir / "demo-agent.json"
            profile_path.write_text(
                """{
  "agent_id": "demo-agent",
  "probed_capabilities": {
    "structured_trace": true,
    "tool_trace": false,
    "step_trace": true
  }
}""",
                encoding="utf-8",
            )

            settings, _ = resolve_evaluation_settings(
                config_path=str(cfg),
                script_name="phase3",
                agent="demo",
                use_capability_profile=True,
            )

        self.assertTrue(settings["declared_capabilities"]["tool_trace"])
        self.assertFalse(settings["resolved_capabilities"]["tool_trace"])
        self.assertTrue(settings["resolved_capabilities"]["step_trace"])
        self.assertEqual(Path(settings["capability_profile_path"]).name, "demo-agent.json")
        self.assertTrue(settings["capability_profile_applied"])

    def test_probe_profile_prefers_declared_and_probed_over_stale_resolved_payload(self):
        config_yaml = """
evaluation:
  v2:
    capability_probe:
      profile_dir: artifacts/capability_profiles
agents:
  demo-agent:
    aliases: [demo]
    evaluation_capabilities:
      structured_trace: true
      tool_trace: true
      step_trace: true
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            profile_dir = Path(tmp) / "artifacts" / "capability_profiles"
            profile_dir.mkdir(parents=True, exist_ok=True)
            profile_path = profile_dir / "demo-agent.json"
            profile_path.write_text(
                """{
  "agent_id": "demo-agent",
  "probed_capabilities": {
    "structured_trace": true,
    "tool_trace": false,
    "step_trace": true
  },
  "resolved_capabilities": {
    "structured_trace": true,
    "tool_trace": true,
    "step_trace": true
  }
}""",
                encoding="utf-8",
            )

            settings, _ = resolve_evaluation_settings(
                config_path=str(cfg),
                script_name="phase3",
                agent="demo",
                use_capability_profile=True,
            )

        self.assertFalse(
            settings["resolved_capabilities"]["tool_trace"],
            "Resolved capabilities should be recomputed from declared/probed and ignore stale profile-resolved flags.",
        )

    def test_probe_profile_is_not_applied_unless_enabled(self):
        config_yaml = """
evaluation:
  v2:
    capability_probe:
      profile_dir: artifacts/capability_profiles
agents:
  demo-agent:
    aliases: [demo]
    evaluation_capabilities:
      structured_trace: true
      tool_trace: true
      step_trace: true
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            profile_dir = Path(tmp) / "artifacts" / "capability_profiles"
            profile_dir.mkdir(parents=True, exist_ok=True)
            profile_path = profile_dir / "demo-agent.json"
            profile_path.write_text(
                """{
  "agent_id": "demo-agent",
  "probed_capabilities": {
    "structured_trace": true,
    "tool_trace": false,
    "step_trace": false
  }
}""",
                encoding="utf-8",
            )

            settings, _ = resolve_evaluation_settings(
                config_path=str(cfg),
                script_name="phase3",
                agent="demo",
            )

        self.assertTrue(settings["resolved_capabilities"]["tool_trace"])
        self.assertTrue(settings["resolved_capabilities"]["step_trace"])
        self.assertFalse(settings["capability_profile_applied"])

    def test_failed_probe_profile_is_ignored_and_declared_capabilities_are_used(self):
        config_yaml = """
evaluation:
  v2:
    capability_probe:
      profile_dir: artifacts/capability_profiles
agents:
  demo-agent:
    aliases: [demo]
    evaluation_capabilities:
      structured_trace: true
      tool_trace: true
      step_trace: true
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            profile_dir = Path(tmp) / "artifacts" / "capability_profiles"
            profile_dir.mkdir(parents=True, exist_ok=True)
            profile_path = profile_dir / "demo-agent.json"
            profile_path.write_text(
                """{
  "agent_id": "demo-agent",
  "probed_capabilities": {
    "structured_trace": false,
    "tool_trace": false,
    "step_trace": false
  },
  "resolved_capabilities": {
    "structured_trace": false,
    "tool_trace": false,
    "step_trace": false
  },
  "probe_results": [
    {"success": false, "return_code": 1},
    {"success": false, "return_code": 1}
  ]
}""",
                encoding="utf-8",
            )

            settings, _ = resolve_evaluation_settings(
                config_path=str(cfg),
                script_name="phase3",
                agent="demo",
                use_capability_profile=True,
            )

        self.assertFalse(settings["capability_profile_applied"])
        self.assertFalse(settings["capability_profile_usable"])
        self.assertTrue(settings["resolved_capabilities"]["tool_trace"])
        self.assertTrue(settings["resolved_capabilities"]["step_trace"])

    def test_trace_parser_profile_is_loaded_from_agent_config(self):
        config_yaml = """
agents:
  demo-agent:
    aliases: [demo]
    evaluation_trace_parser:
      step_patterns:
        - 'STEP-(\\d+)'
      tool_call_patterns:
        - 'TOOL=([a-z_]+)'
      log_file_patterns:
        - 'logfile:\\s*(.+\\.log)'
      tool_aliases:
        Write: write_file
      enforce_known_tools: false
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent_profiles.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")
            settings, _ = resolve_evaluation_settings(
                config_path=str(cfg),
                script_name="phase3",
                agent="demo",
            )

        parser_profile = settings.get("trace_parser_profile", {})
        self.assertEqual(parser_profile["step_patterns"], ["STEP-(\\d+)"])
        self.assertEqual(parser_profile["tool_call_patterns"], ["TOOL=([a-z_]+)"])
        self.assertEqual(parser_profile["log_file_patterns"], ["logfile:\\s*(.+\\.log)"])
        self.assertEqual(parser_profile["tool_aliases"], {"Write": "write_file"})
        self.assertFalse(parser_profile["enforce_known_tools"])

    def test_continue_defaults_are_loaded_from_yaml(self):
        config_yaml = """
agents:
  continue:
    scripts:
      run_single_test:
        results_dir: phase3_from_yaml
    adapter:
      transport: pty
      trace_log_paths:
        - ~/.continue/logs/cn.log
      trace_log_tail_lines: 1200
      trace_log_max_bytes: 256000
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
        self.assertEqual(adapter_kwargs["transport"], "pty")
        self.assertEqual(adapter_kwargs["trace_log_paths"], ["~/.continue/logs/cn.log"])
        self.assertEqual(adapter_kwargs["trace_log_tail_lines"], 1200)
        self.assertEqual(adapter_kwargs["trace_log_max_bytes"], 256000)
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
