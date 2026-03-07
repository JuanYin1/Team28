import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from advanced_evaluation_system import AdvancedEvaluator, EvaluationCriteria


class AdvancedEvaluatorScoringTests(unittest.TestCase):
    def test_overall_score_is_normalized_when_weights_exceed_one(self):
        evaluator = AdvancedEvaluator(use_llm_judge=False)
        criteria = EvaluationCriteria(
            evaluation_type="hybrid",
            expected_keywords=["alpha"],
            correctness_weight=0.4,
            completeness_weight=0.3,
            reasoning_weight=0.3,
            # Keep default efficiency/execution weights (0.1/0.1),
            # so total configured weights become 1.2.
        )

        with patch.object(evaluator, "_evaluate_correctness", return_value=1.0), \
             patch.object(evaluator, "_evaluate_completeness", return_value=1.0), \
             patch.object(evaluator, "_evaluate_reasoning_quality", return_value=1.0), \
             patch.object(evaluator, "_evaluate_efficiency", return_value=1.0), \
             patch.object(evaluator, "_evaluate_execution_success", return_value=1.0):
            result = evaluator.evaluate_response(
                task_prompt="task",
                agent_response="response",
                criteria=criteria,
                execution_time=1.0,
                workspace_path=None,
            )

        self.assertLessEqual(result.overall_score, 1.0)
        self.assertAlmostEqual(result.overall_score, 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
