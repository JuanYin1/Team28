import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advanced_evaluation_system import EvaluationCriteria, EvaluationResult
from integrated_mini_agent_evaluation import (
    ComprehensiveTestResult,
    IntegratedMiniAgentEvaluator,
    TestCaseDefinition,
)


class IntegratedOutputContractTests(unittest.TestCase):
    def test_saved_output_preview_is_sanitized_and_truncated(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = IntegratedMiniAgentEvaluator(results_dir=tmp)
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
                mini_agent_output=long_output,
                mini_agent_error=None,
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
        self.assertEqual(payload["schema_version"], "phase1.v2")
        self.assertNotIn("\x1b[", preview)
        self.assertLessEqual(len(preview), 503)

    def test_subprocess_uses_utf8_replace_decoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            evaluator = IntegratedMiniAgentEvaluator(results_dir=tmp)
            case = evaluator.create_comprehensive_test_suite()[0]

            process = MagicMock()
            process.stdout = "ok"
            process.stderr = ""
            process.returncode = 0

            with patch("integrated_mini_agent_evaluation.subprocess.run", return_value=process) as run_mock, \
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

            kwargs = run_mock.call_args.kwargs
            self.assertEqual(kwargs["encoding"], "utf-8")
            self.assertEqual(kwargs["errors"], "replace")


if __name__ == "__main__":
    unittest.main()
