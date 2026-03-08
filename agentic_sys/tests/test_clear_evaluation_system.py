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

from agent_runtime.models import AgentExecutionResult
from advanced_evaluation_system import EvaluationResult
from clear_evaluation_system import (
    AgentCLEARMetrics,
    AgentCLEAREvaluator,
    AgentEvaluationResult,
    AgentLogAnalyzer,
    AgentTestCase,
    AgentTestCriteria,
)


class AgentLogAnalyzerTests(unittest.TestCase):
    def test_tool_call_count_tracks_total_calls_and_ignores_startup_success_noise(self):
        analyzer = AgentLogAnalyzer()
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

    def test_tool_call_count_falls_back_to_session_stats_when_timeline_missing(self):
        analyzer = AgentLogAnalyzer()
        log_text = """
Total Messages: 12
Tool Calls: 3
API Tokens Used: 1,234
"""
        analysis = analyzer.analyze_execution_log(log_text)

        self.assertEqual(analysis["tool_call_count"], 3)
        self.assertEqual(analysis["tool_call_count_source"], "session_stats")

    def test_tool_call_count_uses_tools_lower_bound_for_detailed_log_only(self):
        analyzer = AgentLogAnalyzer()
        with tempfile.TemporaryDirectory() as tmp:
            detailed = Path(tmp) / "detailed.log"
            detailed.write_text('{"tool_name": "write_file"}\n{"tool_name": "read_file"}', encoding="utf-8")
            analysis = analyzer.analyze_execution_log("", log_file_path=str(detailed))

        self.assertEqual(analysis["tools_used"], ["write_file", "read_file"])
        self.assertEqual(analysis["tool_call_count"], 2)
        self.assertEqual(analysis["tool_call_count_source"], "tools_used_lower_bound")


class AgentClearEvaluatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_task_uses_adapter_and_binds_monitor_pid(self):
        class DummyAdapter:
            conda_env = "mini-agent"

            def __init__(self):
                self.requests = []

            def run(self, request, on_process_start=None):
                self.requests.append(request)
                if on_process_start:
                    on_process_start(9876)
                return AgentExecutionResult(
                    command=["mini-agent", "--workspace", request.workspace, "--task", request.task_prompt],
                    stdout="ok",
                    stderr="",
                    success=True,
                    execution_time_seconds=1.0,
                    return_code=0,
                    pid=9876,
                )

        with tempfile.TemporaryDirectory() as tmp:
            adapter = DummyAdapter()
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent", agent_adapter=adapter)
            test_case = AgentTestCase(
                name="case",
                category="file_operations",
                description="d",
                task_prompt="p",
                expected_file_changes=[],
                evaluation_criteria=AgentTestCriteria(),
            )

            with patch.object(evaluator, "_bind_monitor_target_pid") as bind_pid:
                stdout, stderr, success, execution_time = await evaluator.execute_agent_task(test_case)

        self.assertEqual(stdout, "ok")
        self.assertEqual(stderr, "")
        self.assertTrue(success)
        self.assertEqual(execution_time, 1.0)
        self.assertEqual(len(adapter.requests), 1)
        bind_pid.assert_called_with(9876, conda_mode=True)

    async def test_non_mini_agent_semantics_do_not_penalize_missing_tool_step_signals(self):
        class ContinueLikeAdapter:
            agent_id = "continue-cn"
            process_name_hint = "continue-cli"

            def run(self, request, on_process_start=None):
                if on_process_start:
                    on_process_start(2468)
                return AgentExecutionResult(
                    command=["cn", "-p", request.task_prompt],
                    stdout="answer",
                    stderr="",
                    success=True,
                    execution_time_seconds=5.0,
                    return_code=0,
                    pid=2468,
                )

        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, agent_adapter=ContinueLikeAdapter())
            test_case = AgentTestCase(
                name="case",
                category="analysis",
                description="d",
                task_prompt="p",
                evaluation_criteria=AgentTestCriteria(expected_tools=["write_file", "read_file"]),
            )

            fake_log_analysis = {
                "total_steps": 0,
                "tools_used": [],
                "tool_call_count": 0,
                "thinking_blocks": 0,
                "assistant_responses": 0,
                "errors_encountered": 0,
                "successful_operations": 0,
                "step_breakdown": [],
                "execution_timeline": [],
                "session_stats": {},
                "log_sources": ["stdout"],
                "session_duration": {},
                "tool_timings": [],
                "detailed_timeline": [],
                "has_structured_trace": False,
                "trace_signal_quality": 0.5,
            }
            eval_result = EvaluationResult(
                overall_score=0.9,
                passed=True,
                confidence=0.9,
                correctness_score=0.9,
                completeness_score=0.9,
                reasoning_score=0.9,
                efficiency_score=1.0,
                execution_score=1.0,
                failed_criteria=[],
                reasoning="ok",
            )

            with patch.object(evaluator.resource_monitor, "start_monitoring"), \
                 patch.object(evaluator.resource_monitor, "stop_monitoring", return_value=(5.0, 64.0, 10.0)), \
                 patch.object(evaluator.resource_monitor, "get_resource_at", return_value=(64.0, 10.0)), \
                 patch.object(evaluator.log_analyzer, "analyze_execution_log", return_value=fake_log_analysis), \
                 patch.object(evaluator.advanced_evaluator, "evaluate_response", return_value=eval_result):
                result = await evaluator.evaluate_agent_test(test_case)

        self.assertEqual(result.clear_metrics.tool_selection_accuracy, 1.0)
        self.assertEqual(result.clear_metrics.task_efficiency_score, 0.5)
        self.assertEqual(result.clear_metrics.llm_api_calls, 1)
        self.assertEqual(result.clear_metrics.steps_to_completion, 1)
        self.assertEqual(result.time_breakdown["method"], "coarse_no_structured_trace")
        self.assertTrue(result.clear_metrics.cost_is_estimated)

    async def test_evaluate_clamps_output_quality_and_preserves_tool_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            test_case = AgentTestCase(
                name="case",
                category="file_operations",
                description="d",
                task_prompt="p",
                evaluation_criteria=AgentTestCriteria(expected_tools=["write_file", "read_file"]),
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

            with patch.object(evaluator, "execute_agent_task", AsyncMock(return_value=("stdout", "", True, 10.0))), \
                 patch.object(evaluator.resource_monitor, "start_monitoring"), \
                 patch.object(evaluator.resource_monitor, "stop_monitoring", return_value=(10.0, 128.0, 15.0)), \
                 patch.object(evaluator.resource_monitor, "get_resource_at", return_value=(128.0, 15.0)), \
                 patch.object(evaluator.log_analyzer, "analyze_execution_log", return_value=fake_log_analysis), \
                 patch.object(evaluator.advanced_evaluator, "evaluate_response", return_value=eval_result):
                result = await evaluator.evaluate_agent_test(test_case)

        self.assertEqual(result.clear_metrics.output_quality_score, 1.0)
        self.assertEqual(result.tools_used, ["write_file", "read_file"])

    async def test_failed_execution_is_hard_gate_for_threshold_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            test_case = AgentTestCase(
                name="case",
                category="analysis",
                description="d",
                task_prompt="p",
                evaluation_criteria=AgentTestCriteria(),
            )

            fake_log_analysis = {
                "total_steps": 1,
                "tools_used": [],
                "tool_call_count": 0,
                "thinking_blocks": 0,
                "assistant_responses": 1,
                "errors_encountered": 0,
                "successful_operations": 1,
                "step_breakdown": [],
                "execution_timeline": [],
                "session_stats": {},
                "log_sources": ["stdout"],
                "session_duration": {},
                "tool_timings": [],
                "detailed_timeline": [],
                "has_structured_trace": False,
                "trace_signal_quality": 0.5,
            }
            eval_result = EvaluationResult(
                overall_score=0.95,
                passed=True,
                confidence=0.9,
                correctness_score=0.95,
                completeness_score=0.95,
                reasoning_score=0.95,
                efficiency_score=1.0,
                execution_score=1.0,
                failed_criteria=[],
                reasoning="ok",
            )

            with patch.object(evaluator, "execute_agent_task", AsyncMock(return_value=("stdout", "stderr", False, 3.0))), \
                 patch.object(evaluator.resource_monitor, "start_monitoring"), \
                 patch.object(evaluator.resource_monitor, "stop_monitoring", return_value=(3.0, 64.0, 5.0)), \
                 patch.object(evaluator.resource_monitor, "get_resource_at", return_value=(64.0, 5.0)), \
                 patch.object(evaluator.log_analyzer, "analyze_execution_log", return_value=fake_log_analysis), \
                 patch.object(evaluator.advanced_evaluator, "evaluate_response", return_value=eval_result):
                result = await evaluator.evaluate_agent_test(test_case)

        self.assertEqual(result.clear_metrics.execution_success_rate, 0.0)
        self.assertFalse(result.passed_all_thresholds)

    async def test_estimated_cost_does_not_hard_fail_thresholds(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            test_case = AgentTestCase(
                name="case",
                category="analysis",
                description="d",
                task_prompt="p",
                evaluation_criteria=AgentTestCriteria(max_cost_per_task=0.000001),
            )

            fake_log_analysis = {
                "total_steps": 1,
                "tools_used": [],
                "tool_call_count": 0,
                "thinking_blocks": 0,
                "assistant_responses": 1,
                "errors_encountered": 0,
                "successful_operations": 1,
                "step_breakdown": [],
                "execution_timeline": [],
                "session_stats": {},
                "log_sources": ["stdout"],
                "session_duration": {},
                "tool_timings": [],
                "detailed_timeline": [],
                "has_structured_trace": False,
                "trace_signal_quality": 0.5,
            }
            eval_result = EvaluationResult(
                overall_score=0.9,
                passed=True,
                confidence=0.9,
                correctness_score=0.9,
                completeness_score=0.9,
                reasoning_score=0.9,
                efficiency_score=1.0,
                execution_score=1.0,
                failed_criteria=[],
                reasoning="ok",
            )

            with patch.object(evaluator, "execute_agent_task", AsyncMock(return_value=("stdout", "", True, 2.0))), \
                 patch.object(evaluator.resource_monitor, "start_monitoring"), \
                 patch.object(evaluator.resource_monitor, "stop_monitoring", return_value=(2.0, 64.0, 5.0)), \
                 patch.object(evaluator.resource_monitor, "get_resource_at", return_value=(64.0, 5.0)), \
                 patch.object(evaluator.log_analyzer, "analyze_execution_log", return_value=fake_log_analysis), \
                 patch.object(evaluator.advanced_evaluator, "evaluate_response", return_value=eval_result), \
                 patch.object(evaluator, "_estimate_cost", return_value=99.0):
                result = await evaluator.evaluate_agent_test(test_case)

        self.assertTrue(result.clear_metrics.cost_is_estimated)
        self.assertTrue(result.passed_all_thresholds)

    async def test_monitor_is_stopped_when_execute_task_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            test_case = AgentTestCase(
                name="case",
                category="analysis",
                description="d",
                task_prompt="p",
                evaluation_criteria=AgentTestCriteria(),
            )

            with patch.object(evaluator.resource_monitor, "start_monitoring"), \
                 patch.object(evaluator.resource_monitor, "stop_monitoring", return_value=(0.0, 0.0, 0.0)) as stop_mock, \
                 patch.object(evaluator, "execute_agent_task", AsyncMock(side_effect=RuntimeError("boom"))):
                result = await evaluator.evaluate_agent_test(test_case)

        stop_mock.assert_called_once()
        self.assertFalse(result.passed_all_thresholds)
        self.assertIn("Evaluation error", result.agent_error_output)

    async def test_save_result_contains_schema_and_phase3_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            result = AgentEvaluationResult(
                test_case=AgentTestCase(
                    name="case",
                    category="analysis",
                    description="d",
                    task_prompt="prompt",
                    evaluation_criteria=AgentTestCriteria(),
                ),
                clear_metrics=AgentCLEARMetrics(total_task_time=1.0, steps_to_completion=1),
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

            await evaluator._save_result(result)
            saved = list(Path(tmp).glob("*.json"))
            self.assertEqual(len(saved), 1)
            payload = json.loads(saved[0].read_text())

        self.assertEqual(payload["schema_version"], "phase3.v2")
        self.assertIn("time_breakdown", payload)
        self.assertIn("step_resource_profiles", payload)

    async def test_generated_report_uses_none_placeholder_for_empty_improvements(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            result = AgentEvaluationResult(
                test_case=AgentTestCase(
                    name="case",
                    category="analysis",
                    description="d",
                    task_prompt="prompt",
                    evaluation_criteria=AgentTestCriteria(),
                ),
                clear_metrics=AgentCLEARMetrics(
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

            await evaluator._generate_report([result])
            reports = list(Path(tmp).glob("mini_agent_clear_report_*.md"))
            self.assertEqual(len(reports), 1)
            report_text = reports[0].read_text()

        self.assertIn("### ⚠️ Areas for Improvement:\n- (none)", report_text)

    def test_runtime_autodetect_failure_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("clear_evaluation_system.MiniAgentAdapter.auto_detect", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    AgentCLEAREvaluator(results_dir=tmp)

    def test_custom_adapter_skips_mini_agent_auto_detection(self):
        class DummyAdapter:
            agent_id = "continue-cn"
            executable = "/usr/local/bin/cn"

            def run(self, request):
                raise AssertionError("run should not be called")

        with tempfile.TemporaryDirectory() as tmp:
            with patch("clear_evaluation_system.MiniAgentAdapter.auto_detect") as auto_detect:
                evaluator = AgentCLEAREvaluator(
                    results_dir=tmp,
                    agent_adapter=DummyAdapter(),
                )

        auto_detect.assert_not_called()
        self.assertEqual(evaluator.runtime_path, "/usr/local/bin/cn")
        self.assertEqual(evaluator.agent_adapter.agent_id, "continue-cn")

    def test_non_mini_runtime_suite_excludes_skills_extension(self):
        class ContinueLikeAdapter:
            agent_id = "continue-cn"
            process_name_hint = "cn"
            executable = "cn"

            def run(self, request, on_process_start=None):
                raise AssertionError("run should not be called")

        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, agent_adapter=ContinueLikeAdapter())
            tests = evaluator.create_agent_test_suite()

        self.assertEqual(len(tests), 4)
        self.assertNotIn("skills_usage", [t.category for t in tests])

    def test_mini_runtime_suite_includes_skills_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            tests = evaluator.create_agent_test_suite()

        self.assertIn("skills_usage", [t.category for t in tests])

    def test_bind_monitor_target_pid_prefers_mini_agent_child_in_conda_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")

        child = MagicMock()
        child.pid = 5678
        child.name.return_value = "mini-agent"
        child.cmdline.return_value = ["mini-agent", "--workspace", "/tmp/ws"]

        launcher = MagicMock()
        launcher.children.return_value = [child]

        with patch("clear_evaluation_system.psutil.Process", return_value=launcher), \
             patch("clear_evaluation_system.PSUTIL_AVAILABLE", True), \
             patch.object(evaluator.resource_monitor, "set_target_pid") as set_pid:
            evaluator._bind_monitor_target_pid(launcher_pid=1234, conda_mode=True)

        set_pid.assert_called_with(5678)

    def test_bind_monitor_target_pid_matches_mini_agent_underscore_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")

        child = MagicMock()
        child.pid = 6789
        child.name.return_value = "mini_agent"
        child.cmdline.return_value = ["mini_agent", "--workspace", "/tmp/ws"]

        launcher = MagicMock()
        launcher.children.return_value = [child]

        with patch("clear_evaluation_system.psutil.Process", return_value=launcher), \
             patch("clear_evaluation_system.PSUTIL_AVAILABLE", True), \
             patch.object(evaluator.resource_monitor, "set_target_pid") as set_pid:
            evaluator._bind_monitor_target_pid(launcher_pid=1234, conda_mode=True)

        set_pid.assert_called_with(6789)

    def test_bind_monitor_target_pid_matches_python_module_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")

        child = MagicMock()
        child.pid = 7890
        child.name.return_value = "python"
        child.cmdline.return_value = ["python", "-m", "mini_agent", "--task", "do x"]

        launcher = MagicMock()
        launcher.children.return_value = [child]

        with patch("clear_evaluation_system.psutil.Process", return_value=launcher), \
             patch("clear_evaluation_system.PSUTIL_AVAILABLE", True), \
             patch.object(evaluator.resource_monitor, "set_target_pid") as set_pid:
            evaluator._bind_monitor_target_pid(launcher_pid=1234, conda_mode=True)

        set_pid.assert_called_with(7890)


class AgentTimeBreakdownTests(unittest.TestCase):
    def test_time_breakdown_counts_tool_result_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")

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
