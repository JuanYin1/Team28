import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visualize_results import (
    _is_visualizable_result_payload,
    _resolve_visualization_settings,
    latest_result,
    latest_run_manifest,
    result_files_from_manifest,
)


class VisualizeResultsConfigTests(unittest.TestCase):
    def test_resolve_visualization_settings_reads_agent_phase3_dir_and_filename(self):
        config_yaml = """
visualization:
  comparison_filename: compare.png
agents:
  demo-agent:
    aliases: [demo]
    scripts:
      phase3:
        results_dir: artifacts/demo/phase3
"""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            cfg.write_text(config_yaml, encoding="utf-8")

            class Args:
                agent = "demo"
                agent_config = str(cfg)
                results_dir = None
                adapter_option = None
                continue_agent_name = None
                continue_config = None
                continue_model = None
                continue_allow = None
                continue_extra_arg = None

            results_dir, comparison_filename = _resolve_visualization_settings(Args())

        self.assertEqual(results_dir, "artifacts/demo/phase3")
        self.assertEqual(comparison_filename, "compare.png")

    def test_latest_result_skips_run_manifest_and_selects_task_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_dir = Path(tmp)
            manifest = results_dir / "mini_agent_run_manifest_20260310_010000.json"
            manifest.write_text(
                '{"schema_version":"phase3.run_manifest.v1","run_id":"20260310_010000"}',
                encoding="utf-8",
            )
            task_result = results_dir / "mini_agent_case_1773000000.json"
            task_result.write_text(
                (
                    '{"schema_version":"phase3.v3","test_case":{"name":"case"},'
                    '"performance":{"overall_clear_score":1.0}}'
                ),
                encoding="utf-8",
            )

            selected = latest_result(results_dir)

        self.assertEqual(selected, task_result)

    def test_visualizable_payload_requires_task_and_performance_sections(self):
        self.assertFalse(_is_visualizable_result_payload({"schema_version": "phase3.run_manifest.v1"}))
        self.assertTrue(
            _is_visualizable_result_payload(
                {
                    "schema_version": "phase3.v3",
                    "test_case": {"name": "case"},
                    "performance": {"overall_clear_score": 0.9},
                }
            )
        )

    def test_latest_run_manifest_prefers_newest_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_dir = Path(tmp)
            older = results_dir / "mini_agent_run_manifest_20260310_000000.json"
            newer = results_dir / "mini_agent_run_manifest_20260310_010000.json"
            older.write_text("{}", encoding="utf-8")
            newer.write_text("{}", encoding="utf-8")

            selected = latest_run_manifest(results_dir)

        self.assertEqual(selected, newer)

    def test_result_files_from_manifest_filters_to_visualizable_task_jsons(self):
        with tempfile.TemporaryDirectory() as tmp:
            results_dir = Path(tmp)
            task = results_dir / "mini_agent_case_1773000000.json"
            task.write_text(
                (
                    '{"schema_version":"phase3.v3","test_case":{"name":"case"},'
                    '"performance":{"overall_clear_score":1.0}}'
                ),
                encoding="utf-8",
            )
            report = results_dir / "mini_agent_report.md"
            report.write_text("report", encoding="utf-8")
            manifest = results_dir / "mini_agent_run_manifest_20260310_010000.json"
            manifest.write_text(
                (
                    '{"schema_version":"phase3.run_manifest.v1","artifacts":['
                    '"mini_agent_case_1773000000.json","mini_agent_report.md"]}'
                ),
                encoding="utf-8",
            )

            resolved = result_files_from_manifest(manifest)

        self.assertEqual(resolved, [task.resolve()])


if __name__ == "__main__":
    unittest.main()
