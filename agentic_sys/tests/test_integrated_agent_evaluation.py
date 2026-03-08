import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.models import AgentExecutionResult
from advanced_evaluation_system import EvaluationCriteria, EvaluationResult
from integrated_agent_evaluation import (
    ComprehensiveTestResult,
    IntegratedAgentEvaluator,
    TestCaseDefinition,
)


class IntegratedOutputContractTests(unittest.TestCase):
    def test_saved_output_preview_is_sanitized_and_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = IntegratedAgentEvaluator(results_dir=tmp)
            long_output = "\x1b[32mSUCCESS\x1b[0m " + ("x" * 800)

            result = ComprehensiveTestResult(
                test_case=TestCaseDefinition(
                    name="case",
                    category="reasoning",
                    complexity="simple",
                    description="d",
                    task_prompt="p",
                    evaluation_criteria=EvaluationCriteria(efficiency_weight=0.0, execution_weight=0.0),
                    max_time_seconds=30,
                ),
                total_execution_time=1.0,
                agent_output=long_output,
                agent_error=None,
                execution_success=True,
                evaluation_result=EvaluationResult(
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
                ),
                overall_success=True,
                confidence_score=0.9,
            )

            asyncio.run(evaluator._save_individual_result(result))
            files = list(Path(tmp).glob("*.json"))
            self.assertEqual(len(files), 1)
            payload = json.loads(files[0].read_text())

        preview = payload["execution"]["output_preview"]
        self.assertEqual(payload["schema_version"], "phase1.v3")
        self.assertNotIn("\x1b[", preview)
        self.assertLessEqual(len(preview), 503)

    def test_run_single_test_builds_expected_adapter_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = IntegratedAgentEvaluator(results_dir=tmp)
            case = evaluator.create_comprehensive_test_suite()[0]
            execution = AgentExecutionResult(
                command=["mini-agent", "--workspace", "/tmp/ws", "--task", case.task_prompt],
                stdout="ok",
                stderr="",
                success=True,
                execution_time_seconds=1.23,
                return_code=0,
                pid=42,
            )

            with patch.object(evaluator.agent_adapter, "run", return_value=execution) as run_mock, \
                 patch.object(evaluator.evaluator, "evaluate_response") as eval_mock:
                eval_mock.return_value = EvaluationResult(
                    overall_score=0.8,
                    passed=True,
                    confidence=0.8,
                    correctness_score=0.8,
                    completeness_score=0.8,
                    reasoning_score=0.8,
                    efficiency_score=1.0,
                    execution_score=1.0,
                    failed_criteria=[],
                    reasoning="ok",
                )
                asyncio.run(evaluator.run_single_integrated_test(case))

            request = run_mock.call_args.args[0]
            self.assertEqual(request.task_prompt, case.task_prompt)
            self.assertEqual(request.timeout_seconds, case.max_time_seconds)


if __name__ == "__main__":
    unittest.main()
