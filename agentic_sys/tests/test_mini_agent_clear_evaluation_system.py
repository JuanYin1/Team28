import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advanced_evaluation_system import EvaluationResult
from mini_agent_clear_evaluation_system import (
    MiniAgentCLEARMetrics,
    MiniAgentCLEAREvaluator,
    MiniAgentEvaluationResult,
    MiniAgentLogAnalyzer,
    MiniAgentTestCase,
    MiniAgentTestCriteria,
)


class MiniAgentLogAnalyzerTests(unittest.TestCase):
    def test_tool_call_count_tracks_total_calls_and_ignores_startup_success_noise(self):
        analyzer = MiniAgentLogAnalyzer()
        log_text = """
✅ Loaded Bash tool
Step 1/100
🔧 Tool Call: write_file
✓ Result: wrote file
🔧 Tool Call: write_file
✓ Result: wrote file
"""
        analysis = analyzer.analyze_execution_log(log_text)

        self.assertEqual(analysis["tools_used"], ["write_file"])
        self.assertEqual(analysis["tool_call_count"], 2)
        tool_result_events = [
            e for e in analysis["detailed_timeline"]
            if e.get("event_type") == "tool_result"
        ]
        self.assertEqual(len(tool_result_events), 2)


class MiniAgentClearEvaluatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluate_clamps_output_quality_and_preserves_tool_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = MiniAgentCLEAREvaluator(results_dir=tmp, mini_agent_path="mini-agent")
            test_case = MiniAgentTestCase(
                name="case",
                category="file_operations",
                description="d",
                task_prompt="p",
                evaluation_criteria=MiniAgentTestCriteria(expected_tools=["write_file", "read_file"]),
            )

            fake_log_analysis = {
                "total_steps": 3,
                "tools_used": ["write_file", "read_file", "write_file"],
                "tool_call_count": 3,
                "thinking_blocks": 2,
                "assistant_responses": 1,
                "errors_encountered": 0,
                "successful_operations": 2,
                "step_breakdown": [{"step": 1}],
                "execution_timeline": [],
                "session_stats": {"tokens_used": 120, "tool_calls": 2},
                "log_sources": ["stdout"],
                "session_duration": {},
                "tool_timings": [],
                "detailed_timeline": [
                    {"event_type": "thinking", "step": 1, "line": 1},
                    {"event_type": "assistant_response", "step": 1, "line": 2},
                    {"event_type": "tool_call", "step": 1, "line": 3},
                    {"event_type": "tool_result", "step": 1, "line": 4},
                ],
            }
            eval_result = EvaluationResult(
                overall_score=1.3,
                passed=True,
                confidence=0.9,
                correctness_score=1.0,
                completeness_score=1.0,
                reasoning_score=0.9,
                efficiency_score=1.0,
                execution_score=1.0,
                failed_criteria=[],
                reasoning="ok",
            )

            with patch.object(evaluator, "execute_mini_agent_task", AsyncMock(return_value=("stdout", "", True, 10.0))), \
                 patch.object(evaluator.resource_monitor, "start_monitoring"), \
                 patch.object(evaluator.resource_monitor, "stop_monitoring", return_value=(10.0, 128.0, 15.0)), \
                 patch.object(evaluator.resource_monitor, "get_resource_at", return_value=(128.0, 15.0)), \
                 patch.object(evaluator.log_analyzer, "analyze_execution_log", return_value=fake_log_analysis), \
                 patch.object(evaluator.advanced_evaluator, "evaluate_response", return_value=eval_result):
                result = await evaluator.evaluate_mini_agent_test(test_case)

        self.assertEqual(result.clear_metrics.output_quality_score, 1.0)
        self.assertEqual(result.tools_used, ["write_file", "read_file"])

    async def test_save_result_contains_schema_and_phase3_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = MiniAgentCLEAREvaluator(results_dir=tmp, mini_agent_path="mini-agent")
            result = MiniAgentEvaluationResult(
                test_case=MiniAgentTestCase(
                    name="case",
                    category="analysis",
                    description="d",
                    task_prompt="prompt",
                    evaluation_criteria=MiniAgentTestCriteria(),
                ),
                clear_metrics=MiniAgentCLEARMetrics(total_task_time=1.0, steps_to_completion=1),
                evaluation_result=EvaluationResult(overall_score=0.8, passed=True, confidence=0.8),
                agent_output="ok",
                overall_clear_score=0.8,
                passed_all_thresholds=True,
                confidence_score=0.8,
                dimension_scores={"cost": 0.8, "latency": 0.8, "efficiency": 0.8, "assurance": 0.8, "reliability": 0.8},
                recommendations=["good"],
                time_breakdown={"method": "timeline_weighted"},
                step_resource_profiles=[],
            )

            await evaluator._save_mini_agent_result(result)
            saved = list(Path(tmp).glob("*.json"))
            self.assertEqual(len(saved), 1)
            payload = json.loads(saved[0].read_text())

        self.assertEqual(payload["schema_version"], "phase3.v2")
        self.assertIn("time_breakdown", payload)
        self.assertIn("step_resource_profiles", payload)

    async def test_generated_report_uses_none_placeholder_for_empty_improvements(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = MiniAgentCLEAREvaluator(results_dir=tmp, mini_agent_path="mini-agent")
            result = MiniAgentEvaluationResult(
                test_case=MiniAgentTestCase(
                    name="case",
                    category="analysis",
                    description="d",
                    task_prompt="prompt",
                    evaluation_criteria=MiniAgentTestCriteria(),
                ),
                clear_metrics=MiniAgentCLEARMetrics(
                    estimated_cost_usd=0.01,
                    total_task_time=20.0,
                    steps_to_completion=5,
                    task_completion_accuracy=0.9,
                ),
                evaluation_result=EvaluationResult(overall_score=0.9, passed=True, confidence=0.9),
                agent_output="ok",
                overall_clear_score=0.9,
                passed_all_thresholds=True,
                confidence_score=0.9,
                dimension_scores={"cost": 0.9, "latency": 0.9, "efficiency": 0.9, "assurance": 0.9, "reliability": 0.9},
                recommendations=["✨ Excellent performance across all dimensions!"],
                time_breakdown={"llm_inference_s": 10, "tool_execution_s": 8, "coordination_s": 2, "method": "timeline_weighted"},
                step_resource_profiles=[],
            )

            await evaluator._generate_mini_agent_report([result])
            reports = list(Path(tmp).glob("mini_agent_clear_report_*.md"))
            self.assertEqual(len(reports), 1)
            report_text = reports[0].read_text()

        self.assertIn("### ⚠️ Areas for Improvement:\n- (none)", report_text)

    def test_conda_detection_handles_missing_conda_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("pathlib.Path.exists", return_value=False), \
                 patch("shutil.which", return_value=None), \
                 patch("subprocess.run", side_effect=FileNotFoundError):
                with self.assertRaises(RuntimeError):
                    MiniAgentCLEAREvaluator(results_dir=tmp)

    def test_bind_monitor_target_pid_prefers_mini_agent_child_in_conda_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = MiniAgentCLEAREvaluator(results_dir=tmp, mini_agent_path="mini-agent")

        child = MagicMock()
        child.pid = 5678
        child.name.return_value = "mini-agent"
        child.cmdline.return_value = ["mini-agent", "--workspace", "/tmp/ws"]

        launcher = MagicMock()
        launcher.children.return_value = [child]

        with patch("mini_agent_clear_evaluation_system.psutil.Process", return_value=launcher), \
             patch("mini_agent_clear_evaluation_system.PSUTIL_AVAILABLE", True), \
             patch.object(evaluator.resource_monitor, "set_target_pid") as set_pid:
            evaluator._bind_monitor_target_pid(launcher_pid=1234, conda_mode=True)

        set_pid.assert_called_with(5678)

    def test_bind_monitor_target_pid_matches_mini_agent_underscore_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = MiniAgentCLEAREvaluator(results_dir=tmp, mini_agent_path="mini-agent")

        child = MagicMock()
        child.pid = 6789
        child.name.return_value = "mini_agent"
        child.cmdline.return_value = ["mini_agent", "--workspace", "/tmp/ws"]

        launcher = MagicMock()
        launcher.children.return_value = [child]

        with patch("mini_agent_clear_evaluation_system.psutil.Process", return_value=launcher), \
             patch("mini_agent_clear_evaluation_system.PSUTIL_AVAILABLE", True), \
             patch.object(evaluator.resource_monitor, "set_target_pid") as set_pid:
            evaluator._bind_monitor_target_pid(launcher_pid=1234, conda_mode=True)

        set_pid.assert_called_with(6789)

    def test_bind_monitor_target_pid_matches_python_module_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = MiniAgentCLEAREvaluator(results_dir=tmp, mini_agent_path="mini-agent")

        child = MagicMock()
        child.pid = 7890
        child.name.return_value = "python"
        child.cmdline.return_value = ["python", "-m", "mini_agent", "--task", "do x"]

        launcher = MagicMock()
        launcher.children.return_value = [child]

        with patch("mini_agent_clear_evaluation_system.psutil.Process", return_value=launcher), \
             patch("mini_agent_clear_evaluation_system.PSUTIL_AVAILABLE", True), \
             patch.object(evaluator.resource_monitor, "set_target_pid") as set_pid:
            evaluator._bind_monitor_target_pid(launcher_pid=1234, conda_mode=True)

        set_pid.assert_called_with(7890)


class MiniAgentTimeBreakdownTests(unittest.TestCase):
    def test_time_breakdown_counts_tool_result_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = MiniAgentCLEAREvaluator(results_dir=tmp, mini_agent_path="mini-agent")

        breakdown = evaluator._calculate_time_breakdown(
            {
                "detailed_timeline": [
                    {"event_type": "thinking"},
                    {"event_type": "assistant_response"},
                    {"event_type": "tool_call"},
                    {"event_type": "tool_result"},
                    {"event_type": "error"},
                ]
            },
            execution_time=10.0,
        )

        self.assertEqual(breakdown["tool_events"], 2)
        self.assertGreater(breakdown["tool_execution_s"], 0.0)


if __name__ == "__main__":
    unittest.main()
