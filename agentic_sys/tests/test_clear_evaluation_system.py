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

    def test_custom_parser_profile_extracts_step_and_tool_signals(self):
        analyzer = AgentLogAnalyzer(
            runtime_profile="custom",
            parser_profile={
                "step_patterns": [r"STEP-(\d+)"],
                "tool_call_patterns": [r"TOOL=([a-z_]+)"],
                "thinking_patterns": [r"THINKING:"],
                "assistant_patterns": [r"ASSISTANT:"],
                "tool_result_patterns": [r"RESULT:"],
                "error_patterns": [r"ERR:"],
                "enforce_known_tools": False,
            },
        )
        log_text = """
STEP-1
THINKING: planning
TOOL=compile
RESULT: ok
ASSISTANT: done
"""
        analysis = analyzer.analyze_execution_log(log_text)

        self.assertEqual(analysis["total_steps"], 1)
        self.assertEqual(analysis["tools_used"], ["compile"])
        self.assertEqual(analysis["tool_call_count"], 1)
        self.assertTrue(analysis["has_structured_trace"])
        self.assertGreaterEqual(analysis["trace_signal_quality"], 0.8)

    def test_steps_are_derived_from_tool_calls_when_step_markers_absent(self):
        analyzer = AgentLogAnalyzer(
            runtime_profile="custom",
            parser_profile={
                "tool_call_patterns": [r"toolName\":\"([A-Za-z_][A-Za-z0-9_]*)"],
                "enforce_known_tools": False,
            },
        )
        log_text = """
{"event":"Executing tool","toolName":"Write"}
{"event":"Executing tool","toolName":"Read"}
"""
        analysis = analyzer.analyze_execution_log(log_text)

        self.assertEqual(analysis["tool_call_count"], 2)
        self.assertEqual(analysis["total_steps"], 2)

    def test_tool_aliases_normalize_continue_tool_names_for_scoring(self):
        analyzer = AgentLogAnalyzer(
            runtime_profile="custom",
            parser_profile={
                "tool_call_patterns": [r'"toolName":"([A-Za-z_][A-Za-z0-9_]*)"'],
                "tool_aliases": {
                    "Write": "write_file",
                    "Read": "read_file",
                },
                "enforce_known_tools": True,
            },
        )
        log_text = """
{"event":"Executing tool","toolName":"Write"}
{"event":"Executing tool","toolName":"Read"}
"""
        analysis = analyzer.analyze_execution_log(log_text)

        self.assertEqual(analysis["tools_used"], ["write_file", "read_file"])
        self.assertEqual(analysis["tool_call_count"], 2)

    def test_streamed_tool_call_chunks_are_not_overcounted_when_execution_events_exist(self):
        analyzer = AgentLogAnalyzer(
            runtime_profile="custom",
            parser_profile={
                "tool_call_patterns": [
                    r'"toolName":"([A-Za-z_][A-Za-z0-9_]*)"',
                    r'"function"\s*:\s*\{\s*"name"\s*:\s*"([A-Za-z_][A-Za-z0-9_]*)"',
                ],
                "tool_result_patterns": [r"(?i)completed"],
                "tool_aliases": {"Write": "write_file"},
                "enforce_known_tools": True,
            },
        )
        log_text = """
2026 [x] [debug]: Received chunk {"chunk":{"choices":[{"delta":{"tool_calls":[{"id":"toolu_abc","function":{"name":"Write","arguments":""}}]}}]}}
2026 [x] [debug]: Received chunk {"chunk":{"choices":[{"delta":{"tool_calls":[{"id":"toolu_abc","function":{"name":"Write","arguments":"{\\"filepath\\":\\"a.txt\\"}"}}]}}]}}
2026 [x] [debug]: Executing tool {"toolName":"Write","arguments":{"filepath":"a.txt"}}
2026 [x] [debug]: Tool execution completed {"toolName":"Write","resultLength":42}
"""
        analysis = analyzer.analyze_execution_log(log_text)

        self.assertEqual(analysis["tools_used"], ["write_file"])
        self.assertEqual(analysis["tool_call_count"], 1)

    def test_trace_log_marker_is_recorded_as_log_source(self):
        analyzer = AgentLogAnalyzer(runtime_profile="custom")
        log_text = """
assistant: ok
[TRACE_LOG:/tmp/continue.log]
Executing tool {"toolName":"Write"}
[/TRACE_LOG]
"""
        analysis = analyzer.analyze_execution_log(log_text)

        self.assertIn("trace_log", analysis["log_sources"])
        self.assertIn("/tmp/continue.log", analysis["trace_log_paths"])

    def test_unstructured_trace_quality_is_runtime_neutral(self):
        mini = AgentLogAnalyzer(runtime_profile="mini-agent")
        generic = AgentLogAnalyzer(runtime_profile="custom")
        log_text = "final answer without structured trace"

        mini_analysis = mini.analyze_execution_log(log_text)
        generic_analysis = generic.analyze_execution_log(log_text)

        self.assertEqual(mini_analysis["trace_signal_quality"], 0.5)
        self.assertEqual(generic_analysis["trace_signal_quality"], 0.5)


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

    async def test_execute_task_includes_adapter_trace_log_chunks(self):
        class DummyAdapter:
            conda_env = None

            def run(self, request, on_process_start=None):
                if on_process_start:
                    on_process_start(5555)
                return AgentExecutionResult(
                    command=["dummy"],
                    stdout="primary",
                    stderr="",
                    success=True,
                    execution_time_seconds=1.0,
                    return_code=0,
                    pid=5555,
                    metadata={
                        "trace_log_chunks": [
                            {"path": "/tmp/agent.log", "text": "toolName\":\"Write\""}
                        ]
                    },
                )

        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, agent_adapter=DummyAdapter())
            test_case = AgentTestCase(
                name="case",
                category="file_operations",
                description="d",
                task_prompt="p",
                expected_file_changes=[],
                evaluation_criteria=AgentTestCriteria(),
            )
            stdout, _, success, _ = await evaluator.execute_agent_task(test_case)

        self.assertTrue(success)
        self.assertIn("[TRACE_LOG:/tmp/agent.log]", stdout)
        self.assertIn("toolName", stdout)

    async def test_non_mini_agent_missing_trace_is_unknown_not_rewarded(self):
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

        self.assertEqual(result.clear_metrics.tool_selection_accuracy, 0.0)
        self.assertEqual(result.clear_metrics.task_efficiency_score, 0.0)
        self.assertEqual(result.clear_metrics.llm_api_calls, 1)
        self.assertEqual(result.clear_metrics.steps_to_completion, 0)
        self.assertIn("process", result.unknown_dimensions)
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

    async def test_v2_pass_is_not_blocked_by_legacy_absolute_step_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            test_case = AgentTestCase(
                name="case",
                category="analysis",
                description="d",
                task_prompt="p",
                evaluation_criteria=AgentTestCriteria(max_acceptable_steps=1),
            )

            fake_log_analysis = {
                "total_steps": 6,
                "tools_used": ["write_file", "bash"],
                "tool_call_count": 2,
                "thinking_blocks": 1,
                "assistant_responses": 1,
                "errors_encountered": 0,
                "successful_operations": 2,
                "step_breakdown": [],
                "execution_timeline": [],
                "session_stats": {},
                "log_sources": ["stdout"],
                "session_duration": {},
                "tool_timings": [],
                "detailed_timeline": [],
                "has_structured_trace": True,
                "trace_signal_quality": 1.0,
            }
            eval_result = EvaluationResult(
                overall_score=0.95,
                passed=True,
                confidence=0.95,
                correctness_score=0.95,
                completeness_score=0.95,
                reasoning_score=0.95,
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
                 patch.object(evaluator.advanced_evaluator, "evaluate_response", return_value=eval_result):
                result = await evaluator.evaluate_agent_test(test_case)

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

        self.assertEqual(payload["schema_version"], "phase3.v3")
        self.assertIn("time_breakdown", payload)
        self.assertIn("step_resource_profiles", payload)
        self.assertIn("evidence_quality", payload)
        self.assertIn("comparability", payload)
        self.assertIn("gate_status", payload)
        self.assertIn("repeat_stats", payload)

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

    def test_skills_extension_is_disabled_by_default_without_declared_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")
            tests = evaluator.create_agent_test_suite()

        self.assertNotIn("skills_usage", [t.category for t in tests])

    def test_skills_extension_is_enabled_when_capability_declared(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(
                results_dir=tmp,
                runtime_path="mini-agent",
                evaluation_settings={
                    "resolved_capabilities": {
                        "skills_runtime": True,
                    },
                },
            )
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


class AgentV2ScoringTests(unittest.TestCase):
    def test_process_dimension_penalizes_redundant_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")

        criteria = AgentTestCriteria(max_acceptable_steps=10)
        base_metrics = AgentCLEARMetrics(
            execution_success_rate=1.0,
            tool_selection_accuracy=1.0,
            error_recovery_effectiveness=1.0,
            steps_to_completion=6,
        )
        clean_log = {
            "detailed_timeline": [
                {"event_type": "tool_call", "tool_name": "read_file"},
                {"event_type": "tool_call", "tool_name": "write_file"},
            ],
            "raw_text": "",
            "total_steps": 6,
        }
        retry_log = {
            "detailed_timeline": [
                {"event_type": "tool_call", "tool_name": "read_file"},
                {"event_type": "tool_call", "tool_name": "read_file"},
                {"event_type": "tool_call", "tool_name": "read_file"},
                {"event_type": "tool_call", "tool_name": "write_file"},
            ],
            "raw_text": "",
            "total_steps": 6,
        }

        clean_score = evaluator._calculate_process_dimension_v2(
            clear_metrics=base_metrics,
            log_analysis=clean_log,
            criteria=criteria,
        )
        retry_score = evaluator._calculate_process_dimension_v2(
            clear_metrics=base_metrics,
            log_analysis=retry_log,
            criteria=criteria,
        )

        self.assertGreater(clean_score, retry_score)

    def test_outcome_dimension_prefers_checker_signal_over_heuristic(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")

        test_case = AgentTestCase(
            name="case",
            category="file_operations",
            description="d",
            task_prompt="p",
            expected_file_changes=["result.txt"],
            expected_outputs=["result.txt", "15"],
            success_indicators=["sum", "created"],
            evaluation_criteria=AgentTestCriteria(),
        )
        clear_metrics = AgentCLEARMetrics(execution_success_rate=1.0)
        eval_result = EvaluationResult(overall_score=0.2, correctness_score=0.2)
        score, evidence = evaluator._calculate_outcome_dimension_v2(
            test_case=test_case,
            stdout="Created result.txt with value 15",
            stderr="",
            clear_metrics=clear_metrics,
            evaluation_result=eval_result,
            checker_result={
                "checker_executed": True,
                "checker_passed": True,
                "checker_score": 1.0,
                "checker_coverage": 1.0,
                "subchecks": {"file_artifact:result.txt": True},
            },
        )

        self.assertGreater(score, 0.7)
        self.assertEqual(evidence["primary_tier"], "oracle/executable")
        self.assertTrue(evidence["checker_executed"])
        self.assertFalse(evidence["include_in_total_score"])

    def test_repeated_run_aggregation_generates_repeat_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(
                results_dir=tmp,
                runtime_path="mini-agent",
                evaluation_settings={"runs_per_task": 3},
            )

            test_case = AgentTestCase(
                name="case",
                category="analysis",
                description="d",
                task_prompt="p",
                evaluation_criteria=AgentTestCriteria(),
            )

            base_result = AgentEvaluationResult(
                test_case=test_case,
                clear_metrics=AgentCLEARMetrics(total_task_time=2.0, steps_to_completion=3, execution_success_rate=1.0),
                evaluation_result=EvaluationResult(overall_score=0.8, confidence=0.8, passed=True),
                overall_clear_score=0.8,
                overall_v2_score=0.8,
                passed_all_thresholds=True,
                confidence_score=0.8,
                dimension_scores={"cost": 0.8},
                v2_dimension_scores={"outcome": 0.8, "process": 0.8, "efficiency": 0.8, "robustness": 0.8, "safety": 0.8},
                evidence_quality={"high_supervision_coverage": 1.0, "primary_tier": "exact", "tier_scores": {"exact": 0.8}},
                comparability={"status": "COMPARABLE", "reasons": [], "eligible_for_main_leaderboard": True},
                gate_status={
                    "safety_gate": {"status": "pass"},
                    "critical_function_gate": {"status": "pass"},
                    "oracle_gate": {"status": "pass"},
                },
                is_provisional=False,
            )
            second = AgentEvaluationResult(
                test_case=test_case,
                clear_metrics=AgentCLEARMetrics(total_task_time=3.0, steps_to_completion=5, execution_success_rate=0.0),
                evaluation_result=EvaluationResult(overall_score=0.6, confidence=0.6, passed=False),
                overall_clear_score=0.6,
                overall_v2_score=0.6,
                passed_all_thresholds=False,
                confidence_score=0.6,
                dimension_scores={"cost": 0.6},
                v2_dimension_scores={"outcome": 0.6, "process": 0.5, "efficiency": 0.6, "robustness": 0.5, "safety": 0.4},
                evidence_quality={"high_supervision_coverage": 1.0, "primary_tier": "exact", "tier_scores": {"exact": 0.6}},
                comparability={"status": "COMPARABLE", "reasons": [], "eligible_for_main_leaderboard": True},
                gate_status={
                    "safety_gate": {"status": "fail"},
                    "critical_function_gate": {"status": "pass"},
                    "oracle_gate": {"status": "pass"},
                },
                is_provisional=False,
            )

            aggregated = evaluator._aggregate_repeated_results(test_case, [base_result, second])

        self.assertEqual(aggregated.repeat_stats["run_count"], 2)
        self.assertAlmostEqual(aggregated.repeat_stats["pass_rate"], 0.5)
        self.assertLessEqual(aggregated.overall_v2_score, 0.8)
        self.assertIn("overall_v2_std", aggregated.repeat_stats)

    def test_config_can_disable_runtime_extension_suite(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(
                results_dir=tmp,
                runtime_path="mini-agent",
                evaluation_settings={"include_runtime_extension_suite": False},
            )
            tests = evaluator.create_agent_test_suite()

        self.assertNotIn("skills_usage", [t.category for t in tests])

    def test_comparability_classifies_hard_and_soft_non_comparable(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")

        core_case = AgentTestCase(
            name="core_case",
            category="analysis",
            description="d",
            task_prompt="p",
            evaluation_criteria=AgentTestCriteria(),
            core_comparable=True,
        )
        runtime_ext_case = AgentTestCase(
            name="ext_case",
            category="skills_usage",
            description="d",
            task_prompt="p",
            evaluation_criteria=AgentTestCriteria(),
            core_comparable=False,
        )

        hard_cmp = evaluator._classify_comparability_v2(
            test_case=core_case,
            dimension_details={
                "outcome": {"score": None, "supported": True, "observed": False},
                "safety": {"score": 0.9, "supported": True, "observed": True},
                "robustness": {"score": 0.9, "supported": True, "observed": True},
                "basic_efficiency": {"score": 0.9, "supported": True, "observed": True},
            },
            evidence_quality={"checker_executed": False, "primary_tier": "exact"},
            signal_values={
                "checker_executed": False,
                "repeated_runs": True,
                "wall_clock_time": True,
            },
            score_coverage=0.75,
            is_provisional=False,
        )
        self.assertEqual(hard_cmp["status"], "HARD_NON_COMPARABLE")
        self.assertEqual(hard_cmp["core_status"], "HARD_NON_COMPARABLE")
        self.assertEqual(hard_cmp["full_status"], "HARD_NON_COMPARABLE")
        self.assertFalse(hard_cmp["eligible_for_main_leaderboard"])
        self.assertFalse(hard_cmp["eligible_for_full_leaderboard"])

        soft_cmp = evaluator._classify_comparability_v2(
            test_case=runtime_ext_case,
            dimension_details={
                "outcome": {"score": 0.9, "supported": True, "observed": True},
                "safety": {"score": 0.9, "supported": True, "observed": True},
                "robustness": {"score": 0.9, "supported": True, "observed": True},
                "basic_efficiency": {"score": 0.9, "supported": True, "observed": True},
                "process": {"score": None, "supported": False, "observed": False},
            },
            evidence_quality={"checker_executed": True, "primary_tier": "heuristic"},
            signal_values={
                "checker_executed": True,
                "repeated_runs": True,
                "wall_clock_time": True,
            },
            score_coverage=1.0,
            is_provisional=False,
        )
        self.assertEqual(soft_cmp["status"], "SOFT_NON_COMPARABLE")
        self.assertEqual(soft_cmp["core_status"], "SOFT_NON_COMPARABLE")
        self.assertEqual(soft_cmp["full_status"], "SOFT_NON_COMPARABLE")
        self.assertFalse(soft_cmp["eligible_for_main_leaderboard"])
        self.assertFalse(soft_cmp["eligible_for_full_leaderboard"])
        self.assertTrue(any("outside core comparable suite" in r for r in soft_cmp["reasons"]))

    def test_provisional_run_is_excluded_from_main_leaderboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(
                results_dir=tmp,
                runtime_path="mini-agent",
                evaluation_settings={
                    "runs_per_task": 3,
                    "minimum_high_supervision_coverage": 0.40,
                    "v2": {
                        "evidence_quality": {
                            "provisional_if_below_high_supervision_coverage": 0.40,
                        },
                    },
                },
            )

        test_case = AgentTestCase(
            name="case",
            category="analysis",
            description="d",
            task_prompt="p",
            evaluation_criteria=AgentTestCriteria(),
            core_comparable=True,
        )
        clear_metrics = AgentCLEARMetrics(
            execution_success_rate=1.0,
            supports_structured_trace=True,
        )
        eval_result = EvaluationResult(overall_score=0.9, correctness_score=0.9)
        log_analysis = {"raw_text": "", "detailed_timeline": [], "total_steps": 1}

        with patch.object(
            evaluator,
            "_calculate_outcome_dimension_v2",
            return_value=(
                0.9,
                {
                    "primary_tier": "exact",
                    "tier_scores": {"exact": 0.9},
                    "high_supervision_available": True,
                    "high_supervision_score": 0.9,
                    "high_supervision_coverage": 0.2,
                    "checker_executed": True,
                    "include_in_total_score": False,
                },
            ),
        ), patch.object(evaluator, "_calculate_process_dimension_v2", return_value=0.9), \
             patch.object(evaluator, "_calculate_efficiency_dimension_v2", return_value=0.9), \
             patch.object(evaluator, "_calculate_robustness_dimension_v2", return_value=0.9), \
             patch.object(evaluator, "_calculate_safety_dimension_v2", return_value=(0.9, [])):
            scored = evaluator._compute_v2_scoring(
                test_case=test_case,
                stdout="ok",
                stderr="",
                clear_metrics=clear_metrics,
                evaluation_result=eval_result,
                log_analysis=log_analysis,
            )

        self.assertTrue(scored["is_provisional"])
        self.assertEqual(scored["comparability"]["status"], "SOFT_NON_COMPARABLE")
        self.assertFalse(scored["comparability"]["eligible_for_main_leaderboard"])

    def test_gate_cap_applies_boundary_caps_for_safety_critical_and_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(results_dir=tmp, runtime_path="mini-agent")

        criteria = AgentTestCriteria(min_accuracy_threshold=0.7)

        safety_only_gate, safety_only_cap = evaluator._apply_v2_gates(
            outcome_score=0.9,
            safety_score=0.69,
            criteria=criteria,
            clear_metrics=AgentCLEARMetrics(execution_success_rate=1.0),
            evidence_quality={"high_supervision_available": False},
        )
        self.assertEqual(safety_only_gate["safety_gate"]["status"], "fail")
        self.assertAlmostEqual(safety_only_cap, 0.20)

        critical_only_gate, critical_only_cap = evaluator._apply_v2_gates(
            outcome_score=0.69,
            safety_score=1.0,
            criteria=criteria,
            clear_metrics=AgentCLEARMetrics(execution_success_rate=1.0),
            evidence_quality={"high_supervision_available": False},
        )
        self.assertEqual(critical_only_gate["critical_function_gate"]["status"], "fail")
        self.assertAlmostEqual(critical_only_cap, 0.45)

        oracle_only_gate, oracle_only_cap = evaluator._apply_v2_gates(
            outcome_score=1.0,
            safety_score=1.0,
            criteria=criteria,
            clear_metrics=AgentCLEARMetrics(execution_success_rate=1.0),
            evidence_quality={
                "high_supervision_available": True,
                "high_supervision_score": 0.69,
            },
        )
        self.assertEqual(oracle_only_gate["oracle_gate"]["status"], "fail")
        self.assertAlmostEqual(oracle_only_cap, 0.60)


class AgentV2FairnessTests(unittest.TestCase):
    class _StaticAdapter:
        def __init__(self, agent_id: str):
            self.agent_id = agent_id
            self.process_name_hint = agent_id
            self.executable = agent_id

        def run(self, request, on_process_start=None):
            raise AssertionError("run should not be called in scoring-only tests")

    def _make_case(self) -> AgentTestCase:
        return AgentTestCase(
            name="case",
            category="analysis",
            description="d",
            task_prompt="p",
            expected_outputs=["ok"],
            expected_file_changes=["out.txt"],
            success_indicators=["ok"],
            evaluation_criteria=AgentTestCriteria(task_type="analysis"),
        )

    def _base_metrics(self) -> AgentCLEARMetrics:
        return AgentCLEARMetrics(
            execution_success_rate=1.0,
            total_task_time=12.0,
            estimated_cost_usd=0.1,
            total_tokens_used=1200,
            supports_structured_trace=False,
            trace_signal_quality=0.0,
            cost_is_estimated=True,
            steps_to_completion=0,
            tool_selection_accuracy=0.0,
            task_efficiency_score=0.0,
            memory_usage_mb=64.0,
            system_stability=1.0,
            error_recovery_effectiveness=1.0,
        )

    def _base_log(self) -> dict:
        return {
            "total_steps": 0,
            "errors_encountered": 0,
            "successful_operations": 1,
            "detailed_timeline": [],
            "session_stats": {},
            "tool_call_count": 0,
            "tools_used": [],
            "has_structured_trace": False,
            "raw_text": "ok",
        }

    def test_same_evidence_different_agent_ids_have_same_score(self):
        settings = {
            "runs_per_task": 3,
            "resolved_capabilities": {
                "structured_trace": False,
                "tool_trace": False,
                "step_trace": False,
                "timeline_events": False,
                "session_stats": False,
                "provider_cost": False,
                "token_usage": False,
                "checker_support": {
                    "file_artifacts": True,
                    "stdout_capture": True,
                    "exit_code": True,
                    "behavior_validation": True,
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            eva = AgentCLEAREvaluator(
                results_dir=tmp,
                agent_adapter=self._StaticAdapter("agent-a"),
                evaluation_settings=settings,
            )
            evb = AgentCLEAREvaluator(
                results_dir=tmp,
                agent_adapter=self._StaticAdapter("agent-b"),
                evaluation_settings=settings,
            )

        case = self._make_case()
        metrics = self._base_metrics()
        log = self._base_log()
        eval_result = EvaluationResult(overall_score=0.8, correctness_score=0.8)

        score_a = eva._compute_v2_scoring(
            test_case=case,
            stdout="[FILE_CONTENT:out.txt]\nok\n[/FILE_CONTENT]",
            stderr="",
            clear_metrics=metrics,
            evaluation_result=eval_result,
            log_analysis=log,
        )
        score_b = evb._compute_v2_scoring(
            test_case=case,
            stdout="[FILE_CONTENT:out.txt]\nok\n[/FILE_CONTENT]",
            stderr="",
            clear_metrics=self._base_metrics(),
            evaluation_result=eval_result,
            log_analysis=self._base_log(),
        )

        self.assertAlmostEqual(score_a["overall_v2_score"], score_b["overall_v2_score"])
        self.assertEqual(score_a["unknown_dimensions"], score_b["unknown_dimensions"])

    def test_missing_process_trace_yields_null_process_dimension(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(
                results_dir=tmp,
                runtime_path="mini-agent",
                evaluation_settings={
                    "runs_per_task": 3,
                    "resolved_capabilities": {
                        "structured_trace": False,
                        "tool_trace": False,
                        "step_trace": False,
                        "timeline_events": False,
                        "session_stats": False,
                        "provider_cost": False,
                        "token_usage": False,
                        "checker_support": {
                            "file_artifacts": True,
                            "stdout_capture": True,
                            "exit_code": True,
                            "behavior_validation": True,
                        },
                    },
                },
            )

        scored = evaluator._compute_v2_scoring(
            test_case=self._make_case(),
            stdout="[FILE_CONTENT:out.txt]\nok\n[/FILE_CONTENT]",
            stderr="",
            clear_metrics=self._base_metrics(),
            evaluation_result=EvaluationResult(overall_score=0.8, correctness_score=0.8),
            log_analysis=self._base_log(),
        )
        self.assertIsNone(scored["dimension_details"]["process"]["score"])
        self.assertIn("process", scored["unknown_dimensions"])
        self.assertGreaterEqual(scored["score_coverage"], 0.99)

    def test_diagnostic_dimensions_do_not_change_main_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(
                results_dir=tmp,
                runtime_path="mini-agent",
                evaluation_settings={
                    "runs_per_task": 3,
                    "resolved_capabilities": {
                        "structured_trace": True,
                        "tool_trace": True,
                        "step_trace": True,
                        "timeline_events": True,
                        "session_stats": False,
                        "provider_cost": False,
                        "token_usage": False,
                        "checker_support": {
                            "file_artifacts": True,
                            "stdout_capture": True,
                            "exit_code": True,
                            "behavior_validation": True,
                        },
                    },
                },
            )

        case = self._make_case()
        eval_result = EvaluationResult(overall_score=0.8, correctness_score=0.8)

        good_metrics = self._base_metrics()
        good_metrics.supports_structured_trace = True
        good_metrics.trace_signal_quality = 1.0
        good_metrics.tool_selection_accuracy = 1.0
        good_metrics.steps_to_completion = 6
        good_metrics.task_efficiency_score = 0.9

        bad_metrics = self._base_metrics()
        bad_metrics.supports_structured_trace = True
        bad_metrics.trace_signal_quality = 0.2
        bad_metrics.tool_selection_accuracy = 0.1
        bad_metrics.steps_to_completion = 20
        bad_metrics.task_efficiency_score = 0.2

        good_log = {
            **self._base_log(),
            "total_steps": 6,
            "tool_call_count": 2,
            "tools_used": ["read_file", "write_file"],
            "has_structured_trace": True,
            "detailed_timeline": [
                {"event_type": "tool_call", "tool_name": "read_file"},
                {"event_type": "tool_call", "tool_name": "write_file"},
            ],
        }
        bad_log = {
            **good_log,
            "total_steps": 20,
            "tool_call_count": 1,
            "tools_used": ["read_file"],
            "detailed_timeline": [
                {"event_type": "tool_call", "tool_name": "read_file"},
                {"event_type": "tool_call", "tool_name": "read_file"},
            ],
        }

        scored_good = evaluator._compute_v2_scoring(
            test_case=case,
            stdout="[FILE_CONTENT:out.txt]\nok\n[/FILE_CONTENT]",
            stderr="",
            clear_metrics=good_metrics,
            evaluation_result=eval_result,
            log_analysis=good_log,
        )
        scored_bad = evaluator._compute_v2_scoring(
            test_case=case,
            stdout="[FILE_CONTENT:out.txt]\nok\n[/FILE_CONTENT]",
            stderr="",
            clear_metrics=bad_metrics,
            evaluation_result=eval_result,
            log_analysis=bad_log,
        )

        self.assertAlmostEqual(scored_good["overall_v2_score"], scored_bad["overall_v2_score"])
        self.assertNotEqual(
            scored_good["overall_v2_diagnostic_score"],
            scored_bad["overall_v2_diagnostic_score"],
        )

    def test_checker_not_executed_cannot_be_high_supervision(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = AgentCLEAREvaluator(
                results_dir=tmp,
                runtime_path="mini-agent",
                evaluation_settings={
                    "runs_per_task": 3,
                    "resolved_capabilities": {
                        "structured_trace": False,
                        "tool_trace": False,
                        "step_trace": False,
                        "timeline_events": False,
                        "session_stats": False,
                        "provider_cost": False,
                        "token_usage": False,
                        "checker_support": {
                            "file_artifacts": False,
                            "stdout_capture": False,
                            "exit_code": False,
                            "behavior_validation": False,
                        },
                    },
                },
            )

        scored = evaluator._compute_v2_scoring(
            test_case=self._make_case(),
            stdout="[FILE_CONTENT:out.txt]\nok\n[/FILE_CONTENT]",
            stderr="",
            clear_metrics=self._base_metrics(),
            evaluation_result=EvaluationResult(overall_score=0.8, correctness_score=0.8),
            log_analysis=self._base_log(),
        )
        self.assertFalse(scored["evidence_quality"]["checker_executed"])
        self.assertIsNone(scored["dimension_details"]["outcome"]["score"])
        self.assertEqual(scored["comparability"]["status"], "HARD_NON_COMPARABLE")


if __name__ == "__main__":
    unittest.main()
