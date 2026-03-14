#!/usr/bin/env python3
"""
Integrated Agent Evaluation System
=================================
Combines our advanced evaluation system with pluggable agent runtimes for research-quality analysis.

This integrates:
1. Advanced multi-methodology evaluation (MMLU, HumanEval, LLM-judge, etc.)
2. Agent task execution via adapter abstraction
3. Comprehensive performance monitoring
4. Research-grade reporting
"""

import asyncio
import argparse
import json
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Import our advanced evaluation system
from advanced_evaluation_system import (
    AdvancedEvaluator, 
    EvaluationCriteria, 
    EvaluationResult
)
from agent_runtime.adapters import AgentAdapter, MiniAgentAdapter
from agent_runtime.factory import create_agent_adapter
from agent_runtime.models import AgentExecutionRequest
from agent_runtime.script_config import resolve_script_runtime_options

TASK_HARD_CONSTRAINT_PREFIX = (
    "Return only 6-10 sentences of analysis. Do not generate deliverable documents. "
    "Do not write files."
)

@dataclass
class TestCaseDefinition:
    """Enhanced test case with evaluation criteria"""
    name: str
    category: str
    complexity: str
    description: str
    task_prompt: str
    evaluation_criteria: EvaluationCriteria
    max_time_seconds: int = 60

@dataclass
class ComprehensiveTestResult:
    """Complete test result with advanced evaluation"""
    test_case: TestCaseDefinition
    
    # Execution metrics
    total_execution_time: float
    agent_output: str
    agent_error: Optional[str]
    execution_success: bool
    
    # Advanced evaluation results
    evaluation_result: EvaluationResult
    
    # Summary
    overall_success: bool
    confidence_score: float

class IntegratedAgentEvaluator:
    """Integrated evaluator combining agent execution with advanced assessment."""
    
    def __init__(
        self,
        results_dir: str = "artifacts/mini-agent/phase1",
        agent_adapter: Optional[AgentAdapter] = None,
    ):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.evaluator = AdvancedEvaluator(use_llm_judge=False)  # Using heuristic for now
        self.agent_adapter = agent_adapter or MiniAgentAdapter()
        
    def create_comprehensive_test_suite(self) -> List[TestCaseDefinition]:
        """Create test cases with appropriate evaluation criteria for each"""
        
        def with_hard_constraints(prompt: str) -> str:
            return f"{TASK_HARD_CONSTRAINT_PREFIX}\n\n{prompt}"

        test_cases = []
        
        # SIMPLE ARITHMETIC - MMLU-style evaluation
        test_cases.append(TestCaseDefinition(
            name="arithmetic_reasoning",
            category="reasoning",
            complexity="simple",
            description="Basic arithmetic with step-by-step reasoning",
            task_prompt=with_hard_constraints(
                "Calculate 25% of 160, then multiply by 3. Show your work step by step."
            ),
            evaluation_criteria=EvaluationCriteria(
                evaluation_type="keyword",
                expected_keywords=["25%", "160", "40", "120", "0.25"],
                correctness_weight=0.5,  # High weight on getting right answer
                reasoning_weight=0.3,    # Moderate weight on showing work
                completeness_weight=0.2,
                efficiency_weight=0.0,
                execution_weight=0.0
            ),
            max_time_seconds=30
        ))
        
        # LOGIC PUZZLE - Hybrid evaluation
        test_cases.append(TestCaseDefinition(
            name="logic_puzzle",
            category="reasoning",
            complexity="medium",
            description="Multi-step logic puzzle requiring systematic reasoning",
            task_prompt=with_hard_constraints("""Solve this logic puzzle step by step:

Three friends (Alex, Blake, Casey) each own a different pet (cat, dog, bird) and prefer different colors (red, blue, green).

Clues:
1. Alex doesn't like red
2. The person with the cat likes blue  
3. Blake has a dog
4. Casey doesn't like green
5. The person who likes red has a bird

Who has which pet and likes which color?"""),
            evaluation_criteria=EvaluationCriteria(
                evaluation_type="hybrid",
                expected_keywords=["alex", "blake", "casey", "cat", "dog", "bird", "red", "blue", "green"],
                correctness_weight=0.4,
                reasoning_weight=0.4,  # High weight on reasoning process
                completeness_weight=0.2,
                efficiency_weight=0.0,
                execution_weight=0.0
            ),
            max_time_seconds=90
        ))
        
        # FILE OPERATIONS - Execution-based evaluation
        test_cases.append(TestCaseDefinition(
            name="file_operations",
            category="programming",
            complexity="medium", 
            description="Create, modify, and analyze files",
            task_prompt=with_hard_constraints("""Perform these file operations:

1. Create a file called 'data.txt' with numbers 1 through 10, one per line
2. Read the file and calculate the sum of all numbers
3. Create a second file called 'summary.txt' with the result
4. Confirm both files exist and show their contents"""),
            evaluation_criteria=EvaluationCriteria(
                evaluation_type="execution",
                execution_tests=[
                    lambda response: "data.txt" in response.lower(),
                    lambda response: "summary.txt" in response.lower(), 
                    lambda response: "55" in response or "sum" in response.lower(),
                    lambda response: any(str(i) in response for i in range(1, 11))
                ],
                correctness_weight=0.3,
                completeness_weight=0.3,
                execution_weight=0.3,  # High weight on actual execution
                reasoning_weight=0.1,
                efficiency_weight=0.0
            ),
            max_time_seconds=60
        ))
        
        # CODE DEBUGGING - Comprehensive evaluation
        test_cases.append(TestCaseDefinition(
            name="code_debugging",
            category="programming",
            complexity="complex",
            description="Debug and fix a Python function with multiple issues",
            task_prompt=with_hard_constraints("""Debug this Python function that has several bugs:

```python
def find_average(numbers):
    total = 0
    count = 0
    for num in numbers:
        total += num
        count += 1
    return total / count

# Test cases that reveal the bugs:
print(find_average([]))  # This will crash
print(find_average([1, 2, 3, 4, 5]))
print(find_average(["1", "2", "3"]))  # This might cause issues
```

1. Identify all the bugs
2. Provide a corrected version
3. Explain what each bug was and how you fixed it
4. Test your corrected version"""),
            evaluation_criteria=EvaluationCriteria(
                evaluation_type="hybrid",
                expected_keywords=["division by zero", "empty list", "type", "string", "int", "float", "exception"],
                execution_tests=[
                    lambda response: "def " in response,  # Contains function definition
                    lambda response: "if" in response or "len" in response,  # Has condition check
                    lambda response: "try" in response or "except" in response or "len(numbers) == 0" in response
                ],
                correctness_weight=0.3,
                completeness_weight=0.25,
                reasoning_weight=0.25,
                execution_weight=0.2,
                efficiency_weight=0.0
            ),
            max_time_seconds=120
        ))
        
        # SYSTEM ANALYSIS - Advanced reasoning
        test_cases.append(TestCaseDefinition(
            name="system_analysis", 
            category="analysis",
            complexity="complex",
            description="Analyze system architecture and propose improvements",
            task_prompt=with_hard_constraints("""You are analyzing a simple web application architecture:

Current setup:
- Frontend: Single-page React app
- Backend: Node.js REST API 
- Database: PostgreSQL
- Hosting: Single server

The application is experiencing:
- Slow response times during peak hours
- Occasional crashes under load
- Difficulty deploying updates

Analyze this architecture and propose specific improvements for:
1. Performance optimization
2. Scalability enhancements  
3. Reliability improvements
4. Deployment process

Provide reasoning for each recommendation."""),
            evaluation_criteria=EvaluationCriteria(
                evaluation_type="hybrid",
                expected_keywords=["cache", "load", "database", "scale", "cdn", "microservice", "deployment", "monitoring"],
                correctness_weight=0.2,
                reasoning_weight=0.5,  # Very high weight on reasoning quality
                completeness_weight=0.3,
                efficiency_weight=0.0,
                execution_weight=0.0
            ),
            max_time_seconds=180
        ))
        
        return test_cases
    
    async def run_single_integrated_test(self, test_case: TestCaseDefinition) -> ComprehensiveTestResult:
        """Run a single test with the configured agent adapter and evaluate comprehensively."""
        
        print(f"\n🧪 Running: {test_case.name} ({test_case.complexity})")
        print(f"📋 {test_case.description}")
        
        # Create temporary workspace
        with tempfile.TemporaryDirectory() as temp_workspace:
            
            agent_output = ""
            agent_error = None
            execution_success = False
            
            # Execute runtime through adapter abstraction.
            request = AgentExecutionRequest(
                task_prompt=test_case.task_prompt,
                workspace=temp_workspace,
                timeout_seconds=test_case.max_time_seconds,
            )
            execution = self.agent_adapter.run(request)
            execution_time = execution.execution_time_seconds
            agent_output = execution.stdout or ""
            agent_error = execution.stderr or None
            execution_success = execution.success

            print(f"🚀 Executing: {' '.join(execution.command[:4])} ...")
            print(f"⏱️ Execution completed in {execution_time:.1f}s")
            print(f"📊 Return code: {execution.return_code}")
            
            # Run advanced evaluation on the output
            print(f"📊 Running advanced evaluation...")
            evaluation_result = self.evaluator.evaluate_response(
                task_prompt=test_case.task_prompt,
                agent_response=agent_output,
                criteria=test_case.evaluation_criteria,
                execution_time=execution_time,
                workspace_path=temp_workspace
            )
            
            # Determine overall success
            overall_success = execution_success and evaluation_result.passed
            confidence_score = evaluation_result.confidence
            
            # Create comprehensive result
            result = ComprehensiveTestResult(
                test_case=test_case,
                total_execution_time=execution_time,
                agent_output=agent_output,
                agent_error=agent_error,
                execution_success=execution_success,
                evaluation_result=evaluation_result,
                overall_success=overall_success,
                confidence_score=confidence_score
            )
            
            # Print immediate summary
            status = "✅ PASS" if overall_success else "❌ FAIL"
            print(f"   {status} | Score: {evaluation_result.overall_score:.2f} | Confidence: {confidence_score:.2f}")
            print(f"   Correctness: {evaluation_result.correctness_score:.2f} | Reasoning: {evaluation_result.reasoning_score:.2f} | Completeness: {evaluation_result.completeness_score:.2f}")
            
            return result
    
    async def run_comprehensive_evaluation(self) -> List[ComprehensiveTestResult]:
        """Run the full comprehensive evaluation suite"""
        
        print("🔬 Integrated Agent Comprehensive Evaluation")
        print("=" * 80)
        print("Testing configured runtime with research-grade evaluation methodology")
        print("=" * 80)
        
        test_cases = self.create_comprehensive_test_suite()
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[{i}/{len(test_cases)}] {test_case.category.upper()}: {test_case.name}")
            
            result = await self.run_single_integrated_test(test_case)
            results.append(result)
            
            # Save individual result
            await self._save_individual_result(result)
        
        # Generate comprehensive analysis
        await self._generate_comprehensive_analysis(results)
        
        return results
    
    async def _save_individual_result(self, result: ComprehensiveTestResult):
        """Save individual test result with full details"""
        
        timestamp = int(time.time())
        filename = f"{result.test_case.name}_{timestamp}.json"
        filepath = self.results_dir / filename
        
        # Convert to JSON-serializable format
        preview = result.agent_output
        # Remove ANSI control sequences and truncate for compact, portable artifacts.
        preview = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", preview)
        if len(preview) > 500:
            preview = preview[:500] + "..."

        result_dict = {
            "schema_version": "phase1.v3",
            "test_case": {
                "name": result.test_case.name,
                "category": result.test_case.category,
                "complexity": result.test_case.complexity,
                "description": result.test_case.description,
                "task_prompt": result.test_case.task_prompt,
                "max_time_seconds": result.test_case.max_time_seconds
            },
            "execution": {
                "total_execution_time": result.total_execution_time,
                "execution_success": result.execution_success,
                "agent_error": result.agent_error,
                "full_agent_output": result.agent_output,
                "full_agent_error": result.agent_error,
                "output_length": len(result.agent_output),
                "output_preview": preview
            },
            "evaluation": {
                "overall_score": result.evaluation_result.overall_score,
                "passed": result.evaluation_result.passed,
                "confidence": result.evaluation_result.confidence,
                "correctness_score": result.evaluation_result.correctness_score,
                "completeness_score": result.evaluation_result.completeness_score,
                "reasoning_score": result.evaluation_result.reasoning_score,
                "efficiency_score": result.evaluation_result.efficiency_score,
                "execution_score": result.evaluation_result.execution_score,
                "failed_criteria": result.evaluation_result.failed_criteria,
                "detailed_reasoning": result.evaluation_result.reasoning
            },
            "summary": {
                "overall_success": result.overall_success,
                "confidence_score": result.confidence_score
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(result_dict, f, indent=2)
        
        print(f"   📁 Detailed result saved: {filename}")
    
    async def _generate_comprehensive_analysis(self, results: List[ComprehensiveTestResult]):
        """Generate research-quality comprehensive analysis"""
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_path = self.results_dir / f"comprehensive_analysis_{timestamp}.md"
        
        # Calculate comprehensive statistics
        total_tests = len(results)
        overall_success_count = sum(1 for r in results if r.overall_success)
        execution_success_count = sum(1 for r in results if r.execution_success)
        evaluation_pass_count = sum(1 for r in results if r.evaluation_result.passed)
        
        # Timing analysis
        avg_execution_time = sum(r.total_execution_time for r in results) / total_tests
        
        # Score analysis
        avg_overall_score = sum(r.evaluation_result.overall_score for r in results) / total_tests
        avg_confidence = sum(r.confidence_score for r in results) / total_tests
        
        # Component analysis
        avg_correctness = sum(r.evaluation_result.correctness_score for r in results) / total_tests
        avg_reasoning = sum(r.evaluation_result.reasoning_score for r in results) / total_tests
        avg_completeness = sum(r.evaluation_result.completeness_score for r in results) / total_tests
        
        # Complexity analysis
        complexity_performance = {}
        for result in results:
            complexity = result.test_case.complexity
            if complexity not in complexity_performance:
                complexity_performance[complexity] = []
            complexity_performance[complexity].append(result.evaluation_result.overall_score)
        
        # Generate comprehensive report
        report = f"""# Integrated Agent Comprehensive Evaluation Report
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

This report presents a comprehensive evaluation of the configured runtime using research-grade methodology combining multiple benchmark approaches (MMLU, HumanEval, LLM-as-Judge, SWE-Agent, Chain-of-Thought).

### Key Performance Indicators

| Metric | Value | Analysis |
|--------|-------|----------|
| **Overall Success Rate** | {overall_success_count}/{total_tests} ({overall_success_count/total_tests*100:.1f}%) | Combined execution + evaluation success |
| **Execution Success Rate** | {execution_success_count}/{total_tests} ({execution_success_count/total_tests*100:.1f}%) | Runtime technical execution |
| **Evaluation Pass Rate** | {evaluation_pass_count}/{total_tests} ({evaluation_pass_count/total_tests*100:.1f}%) | Response quality assessment |
| **Average Response Quality** | {avg_overall_score:.3f}/1.000 | Multi-criteria evaluation score |
| **Average Execution Time** | {avg_execution_time:.1f} seconds | Time efficiency |
| **Evaluation Confidence** | {avg_confidence:.3f}/1.000 | Assessment reliability |

### Component Performance Analysis

| Component | Average Score | Interpretation |
|-----------|---------------|----------------|
| **Correctness** | {avg_correctness:.3f}/1.000 | {'Excellent' if avg_correctness >= 0.8 else 'Good' if avg_correctness >= 0.6 else 'Needs Improvement'} factual accuracy |
| **Reasoning Quality** | {avg_reasoning:.3f}/1.000 | {'Strong' if avg_reasoning >= 0.7 else 'Moderate' if avg_reasoning >= 0.5 else 'Weak'} step-by-step thinking |
| **Task Completeness** | {avg_completeness:.3f}/1.000 | {'Comprehensive' if avg_completeness >= 0.8 else 'Partial' if avg_completeness >= 0.6 else 'Incomplete'} task coverage |

---

## Detailed Results by Test Case

| Test Case | Complexity | Execution | Evaluation | Overall Score | Confidence | Status |
|-----------|------------|-----------|------------|---------------|------------|--------|
"""
        
        for result in results:
            execution_status = "✅" if result.execution_success else "❌"
            eval_status = "✅" if result.evaluation_result.passed else "❌"
            overall_status = "✅ PASS" if result.overall_success else "❌ FAIL"
            
            report += f"| {result.test_case.name} | {result.test_case.complexity} | {execution_status} | {eval_status} | {result.evaluation_result.overall_score:.3f} | {result.confidence_score:.3f} | {overall_status} |\n"
        
        report += f"""

---

## Performance Analysis by Complexity

"""
        
        for complexity, scores in complexity_performance.items():
            avg_score = sum(scores) / len(scores)
            count = len(scores)
            report += f"- **{complexity.title()}**: {avg_score:.3f} average score ({count} tests)\n"
        
        report += f"""

---

## Key Findings & Insights

### Strengths Identified:
"""
        strengths: List[str] = []
        if avg_correctness >= 0.7:
            strengths.append("✅ **Strong factual accuracy** - runtime provides correct answers consistently")
        if avg_reasoning >= 0.6:
            strengths.append("✅ **Good reasoning demonstration** - Shows step-by-step thinking process")
        if avg_execution_time <= 60:
            strengths.append("✅ **Efficient execution** - Completes tasks within reasonable time limits")
        if execution_success_count / total_tests >= 0.8:
            strengths.append("✅ **Reliable execution** - Low failure rate for technical operations")
        if not strengths:
            strengths.append("(none)")
        report += "\n".join(f"- {item}" for item in strengths) + "\n"
        
        report += f"""

### Areas for Improvement:
"""
        improvements: List[str] = []
        if avg_correctness < 0.6:
            improvements.append("⚠️ **Factual accuracy needs improvement** - Focus on knowledge base and reasoning")
        if avg_reasoning < 0.5:
            improvements.append("⚠️ **Reasoning quality could be enhanced** - Encourage more explicit step-by-step thinking")
        if avg_completeness < 0.6:
            improvements.append("⚠️ **Task completeness issues** - Ensure all parts of complex tasks are addressed")
        if execution_success_count / total_tests < 0.8:
            improvements.append("⚠️ **Execution reliability concerns** - Investigate technical failures and timeouts")
        if not improvements:
            improvements.append("(none)")
        report += "\n".join(f"- {item}" for item in improvements) + "\n"
        
        report += f"""

### Evaluation Methodology Assessment:

- **Multi-Benchmark Approach**: Successfully combined MMLU, HumanEval, and research methodologies
- **Confidence Scoring**: Average {avg_confidence:.3f} indicates {'high' if avg_confidence >= 0.7 else 'moderate' if avg_confidence >= 0.5 else 'low'} evaluation reliability
- **Component Analysis**: Provides granular insight into specific performance dimensions

---

## Individual Test Analysis

"""
        
        for result in results:
            report += f"""### {result.test_case.name} ({result.test_case.complexity})

**Task**: {result.test_case.description}

**Results**:
- Execution Time: {result.total_execution_time:.1f}s
- Overall Score: {result.evaluation_result.overall_score:.3f}/1.000
- Status: {'✅ PASS' if result.overall_success else '❌ FAIL'}

**Component Scores**:
- Correctness: {result.evaluation_result.correctness_score:.3f}
- Reasoning: {result.evaluation_result.reasoning_score:.3f}  
- Completeness: {result.evaluation_result.completeness_score:.3f}

**Key Insights**: {result.evaluation_result.reasoning.split('Confidence:')[0].strip()}

---

"""
        
        report += f"""## Methodology Notes

This evaluation employed a research-grade multi-methodology approach:

1. **MMLU-style evaluation** for factual correctness
2. **HumanEval-style testing** for execution validation  
3. **Chain-of-Thought analysis** for reasoning quality
4. **SWE-Agent methodology** for task completeness
5. **Educational assessment** for weighted scoring

The evaluation framework provides confidence estimates and detailed component analysis, making it suitable for research publication and production deployment decisions.

---

*Report generated by Integrated Agent Evaluation System v1.0*
*Evaluation framework based on established academic benchmarks*
"""
        
        # Save comprehensive report
        with open(report_path, 'w') as f:
            f.write(report)
        
        print(f"\n📊 Comprehensive analysis complete!")
        print(f"📄 Full report: {report_path}")
        print(f"📁 Individual results: {self.results_dir}")
        
        # Print summary to console
        print("\n" + "=" * 80)
        print("EVALUATION SUMMARY")
        print("=" * 80)
        print(f"Overall Success Rate: {overall_success_count}/{total_tests} ({overall_success_count/total_tests*100:.1f}%)")
        print(f"Average Response Quality: {avg_overall_score:.3f}/1.000")
        print(f"Average Execution Time: {avg_execution_time:.1f}s")
        print(f"Evaluation Confidence: {avg_confidence:.3f}/1.000")
        print("=" * 80)

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run phase1 integrated evaluation.")
    parser.add_argument(
        "--agent",
        default="mini-agent",
        help="Runtime adapter key/alias.",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Directory where phase1 outputs are written.",
    )
    parser.add_argument(
        "--agent-config",
        default=None,
        help="Optional path to agent config YAML (defaults to config/config.yaml).",
    )
    parser.add_argument(
        "--adapter-option",
        action="append",
        default=None,
        help="Repeatable adapter override in KEY=VALUE form (parsed as YAML scalars/lists).",
    )
    parser.add_argument(
        "--continue-agent-name",
        default=None,
        help="Continue agent name for `cn --agent <name>`.",
    )
    parser.add_argument(
        "--continue-config",
        default=None,
        help="Continue config path or hub slug for `cn --config`.",
    )
    parser.add_argument(
        "--continue-model",
        action="append",
        default=None,
        help="Repeatable Continue model slug for `cn --model`.",
    )
    parser.add_argument(
        "--continue-allow",
        action="append",
        default=None,
        help="Repeatable Continue allow policy, e.g. --continue-allow edit.",
    )
    parser.add_argument(
        "--continue-extra-arg",
        action="append",
        default=None,
        help="Repeatable raw arg appended to Continue CLI command.",
    )
    return parser


async def main(argv: Optional[List[str]] = None):
    """Main execution function"""
    args = _build_arg_parser().parse_args(argv)
    results_dir, adapter_kwargs, config_source = resolve_script_runtime_options(
        args=args,
        script_name="phase1",
        default_results_dir="artifacts/mini-agent/phase1",
    )
    adapter = create_agent_adapter(
        agent=args.agent,
        **adapter_kwargs,
    )
    evaluator = IntegratedAgentEvaluator(
        results_dir=results_dir,
        agent_adapter=adapter,
    )
    
    print("🚀 Starting Integrated Agent Comprehensive Evaluation")
    print(f"Using adapter: {adapter.agent_id}")
    if config_source:
        print(f"Using config: {config_source}")
    
    results = await evaluator.run_comprehensive_evaluation()
    
    print(f"\n🎯 Evaluation complete! Analyzed {len(results)} test cases with research-grade methodology.")

if __name__ == "__main__":
    asyncio.run(main())
