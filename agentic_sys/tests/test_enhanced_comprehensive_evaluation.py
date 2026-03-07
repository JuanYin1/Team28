import sys
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advanced_evaluation_system import EvaluationCriteria, EvaluationResult
from enhanced_comprehensive_evaluation import EnhancedMiniAgentEvaluator, EnhancedTestResult
from integrated_mini_agent_evaluation import TestCaseDefinition
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
            evaluator = EnhancedMiniAgentEvaluator(results_dir=tmp)
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

            fake_process = MagicMock()
            fake_process.pid = 4321
            fake_process.communicate.return_value = ("assistant output", "")
            fake_process.returncode = 0

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

            with patch("enhanced_comprehensive_evaluation.RealTimeSystemMonitor", return_value=fake_monitor), \
                 patch("enhanced_comprehensive_evaluation.subprocess.Popen", return_value=fake_process) as popen_mock, \
                 patch.object(evaluator.evaluator, "evaluate_response", return_value=eval_result):
                result = await evaluator._run_enhanced_single_test(test_case)

        kwargs = popen_mock.call_args.kwargs
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "replace")
        fake_monitor.start_monitoring.assert_called_with("mini-agent")
        fake_monitor.set_target_pid.assert_called_with(4321)
        self.assertTrue(result.execution_success)
        self.assertEqual(result.mini_agent_output, "assistant output")
        self.assertEqual(result.resource_bottleneck, "balanced")

    async def test_save_enhanced_result_includes_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = EnhancedMiniAgentEvaluator(results_dir=tmp)
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
                mini_agent_output="out",
                mini_agent_error=None,
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

        self.assertEqual(payload["schema_version"], "phase2.v2")


if __name__ == "__main__":
    unittest.main()
