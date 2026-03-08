import sys
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.models import AgentExecutionResult
from advanced_evaluation_system import EvaluationCriteria, EvaluationResult
from enhanced_comprehensive_evaluation import EnhancedAgentEvaluator, EnhancedTestResult
from integrated_agent_evaluation import TestCaseDefinition
from realtime_system_monitor import PerformanceAnalysis


def make_performance_analysis() -> PerformanceAnalysis:
    return PerformanceAnalysis(
        monitoring_duration=2.0,
        sample_count=10,
        avg_cpu_percent=15.0,
        max_cpu_percent=40.0,
        cpu_bottleneck_duration=0.0,
        cpu_core_imbalance=2.0,
        avg_memory_percent=55.0,
        max_memory_percent=60.0,
        memory_growth_rate=0.2,
        swap_usage_detected=False,
        total_disk_read_mb=2.0,
        total_disk_write_mb=1.0,
        avg_disk_throughput_mbps=1.5,
        disk_bottleneck_detected=False,
        total_network_mb=0.5,
        avg_network_throughput_mbps=0.25,
        network_pattern="steady",
        process_peak_memory_mb=128.0,
        process_avg_cpu=10.0,
        process_thread_growth=1,
        primary_bottleneck="balanced",
        bottleneck_confidence=0.4,
        bottleneck_details={},
    )


class EnhancedPipelineInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_single_test_attaches_monitor_to_spawned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = EnhancedAgentEvaluator(results_dir=tmp)
            test_case = TestCaseDefinition(
                name="unit_case",
                category="reasoning",
                complexity="simple",
                description="desc",
                task_prompt="prompt",
                evaluation_criteria=EvaluationCriteria(efficiency_weight=0.0, execution_weight=0.0),
                max_time_seconds=30,
            )

            fake_monitor = MagicMock()
            fake_monitor.stop_monitoring.return_value = make_performance_analysis()
            execution = AgentExecutionResult(
                command=["mini-agent", "--workspace", "/tmp/ws", "--task", test_case.task_prompt],
                stdout="assistant output",
                stderr="",
                success=True,
                execution_time_seconds=2.5,
                return_code=0,
                pid=4321,
            )

            eval_result = EvaluationResult(
                overall_score=0.8,
                passed=True,
                confidence=0.9,
                correctness_score=0.8,
                completeness_score=0.8,
                reasoning_score=0.8,
                efficiency_score=1.0,
                execution_score=1.0,
                failed_criteria=[],
                reasoning="ok",
            )

            callback_invoked = {"value": False}

            def run_side_effect(request, on_process_start=None):
                if on_process_start:
                    on_process_start(execution.pid)
                    callback_invoked["value"] = True
                return execution

            with patch("enhanced_comprehensive_evaluation.RealTimeSystemMonitor", return_value=fake_monitor), \
                 patch.object(evaluator.agent_adapter, "run", side_effect=run_side_effect) as run_mock, \
                 patch.object(evaluator.evaluator, "evaluate_response", return_value=eval_result):
                result = await evaluator._run_enhanced_single_test(test_case)

        request = run_mock.call_args.args[0]
        self.assertEqual(request.task_prompt, test_case.task_prompt)
        self.assertEqual(request.timeout_seconds, test_case.max_time_seconds)
        self.assertIn("on_process_start", run_mock.call_args.kwargs)
        self.assertTrue(callback_invoked["value"])
        fake_monitor.start_monitoring.assert_called_with("mini-agent")
        fake_monitor.set_target_pid.assert_called_with(4321)
        self.assertTrue(result.execution_success)
        self.assertEqual(result.agent_output, "assistant output")
        self.assertEqual(result.resource_bottleneck, "balanced")

    async def test_save_enhanced_result_includes_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = EnhancedAgentEvaluator(results_dir=tmp)
            test_case = TestCaseDefinition(
                name="unit_case",
                category="reasoning",
                complexity="simple",
                description="desc",
                task_prompt="prompt",
                evaluation_criteria=EvaluationCriteria(efficiency_weight=0.0, execution_weight=0.0),
                max_time_seconds=30,
            )
            perf = make_performance_analysis()
            eval_result = EvaluationResult(
                overall_score=0.8,
                passed=True,
                confidence=0.9,
                correctness_score=0.8,
                completeness_score=0.8,
                reasoning_score=0.8,
                efficiency_score=1.0,
                execution_score=1.0,
                failed_criteria=[],
                reasoning="ok",
            )
            result = EnhancedTestResult(
                test_case=test_case,
                total_execution_time=1.0,
                agent_output="out",
                agent_error=None,
                execution_success=True,
                evaluation_result=eval_result,
                overall_success=True,
                confidence_score=0.9,
                performance_analysis=perf,
                resource_bottleneck="balanced",
                bottleneck_confidence=0.4,
                llm_inference_pattern="light",
                tool_usage_intensity="moderate",
                reasoning_quality_category="good",
            )
            await evaluator._save_enhanced_result(result)

            saved = list(Path(tmp).glob("enhanced_*.json"))
            self.assertTrue(saved)
            payload = json.loads(saved[0].read_text())

        self.assertEqual(payload["schema_version"], "phase2.v3")

    async def test_run_enhanced_evaluation_handles_empty_filtered_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = EnhancedAgentEvaluator(results_dir=tmp)
            test_case = TestCaseDefinition(
                name="unit_case",
                category="reasoning",
                complexity="simple",
                description="desc",
                task_prompt="prompt",
                evaluation_criteria=EvaluationCriteria(efficiency_weight=0.0, execution_weight=0.0),
                max_time_seconds=30,
            )

            with patch.object(evaluator, "create_enhanced_test_suite", return_value=[test_case]), \
                 patch.object(evaluator, "_generate_enhanced_analysis", AsyncMock()) as gen_mock:
                results = await evaluator.run_enhanced_evaluation(test_categories=["non-existent"])

        self.assertEqual(results, [])
        gen_mock.assert_awaited_once_with([])

    async def test_run_single_test_stops_monitor_when_agent_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = EnhancedAgentEvaluator(results_dir=tmp)
            test_case = TestCaseDefinition(
                name="unit_case",
                category="reasoning",
                complexity="simple",
                description="desc",
                task_prompt="prompt",
                evaluation_criteria=EvaluationCriteria(efficiency_weight=0.0, execution_weight=0.0),
                max_time_seconds=30,
            )

            fake_monitor = MagicMock()
            fake_monitor.stop_monitoring.return_value = make_performance_analysis()
            eval_result = EvaluationResult(
                overall_score=0.2,
                passed=False,
                confidence=0.7,
                correctness_score=0.0,
                completeness_score=0.0,
                reasoning_score=0.0,
                efficiency_score=1.0,
                execution_score=0.0,
                failed_criteria=[],
                reasoning="failed",
            )

            with patch("enhanced_comprehensive_evaluation.RealTimeSystemMonitor", return_value=fake_monitor), \
                 patch.object(evaluator.agent_adapter, "run", side_effect=RuntimeError("boom")), \
                 patch.object(evaluator.evaluator, "evaluate_response", return_value=eval_result):
                result = await evaluator._run_enhanced_single_test(test_case)

        fake_monitor.start_monitoring.assert_called_once()
        fake_monitor.stop_monitoring.assert_called_once()
        self.assertFalse(result.execution_success)
        self.assertIn("Execution error: boom", result.agent_error or "")


if __name__ == "__main__":
    unittest.main()
