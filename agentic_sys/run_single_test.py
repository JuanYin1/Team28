#!/usr/bin/env python3
"""
Single-test runner for the Mini-Agent CLEAR evaluation system.
Runs only the simplest test case (simple_file_operations) and prints results.

Usage (from agentic_sys/ directory, with conda env active):
    conda activate mini-agent
    python run_single_test.py

Or without activating the env:
    conda run -n mini-agent python run_single_test.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Make sure we can import from the same directory
sys.path.insert(0, str(Path(__file__).parent))

from mini_agent_clear_evaluation_system import MiniAgentCLEAREvaluator


async def main():
    print("=" * 70)
    print("Mini-Agent Single Test Runner — simple_file_operations")
    print("=" * 70)

    evaluator = MiniAgentCLEAREvaluator(results_dir="phase3")
    test_cases = evaluator.create_mini_agent_test_suite()

    # Run only the first (simplest) test
    test_case = test_cases[0]
    print(f"\nTest : {test_case.name}")
    print(f"Category : {test_case.category}")
    print(f"Timeout  : {test_case.evaluation_criteria.max_task_time_seconds}s")
    print(f"Expected tools: {test_case.evaluation_criteria.expected_tools}")
    print()

    result = await evaluator.evaluate_mini_agent_test(test_case)

    # ── Summary ──────────────────────────────────────────────────────────────
    status = "PASS" if result.passed_all_thresholds else "FAIL"
    print("\n" + "=" * 70)
    print(f"RESULT: {status}  |  CLEAR Score: {result.overall_clear_score:.3f}")
    print("=" * 70)

    print(f"\n⏱  Total time : {result.clear_metrics.total_task_time:.2f}s")
    print(f"   Steps      : {result.clear_metrics.steps_to_completion}")
    print(f"   Tools used : {result.tools_used}")

    # ── Time Breakdown ────────────────────────────────────────────────────────
    bd = result.time_breakdown
    print(f"\n📊 Execution Time Breakdown  (method: {bd.get('method', 'n/a')})")
    print(f"   🧠 LLM inference  : {bd.get('llm_inference_s', 0):.2f}s  ({bd.get('llm_inference_pct', 0)}%)")
    print(f"   🔧 Tool execution : {bd.get('tool_execution_s', 0):.2f}s  ({bd.get('tool_execution_pct', 0)}%)")
    print(f"   🔄 Coordination   : {bd.get('coordination_s', 0):.2f}s  ({bd.get('coordination_pct', 0)}%)")

    # ── Per-Step Resource Attribution ─────────────────────────────────────────
    profiles = result.step_resource_profiles
    if profiles:
        print(f"\n🔍 Per-Step Resource Attribution ({len(profiles)} events captured)")
        print(f"   {'#':<4} {'Event Type':<22} {'Offset(s)':<12} {'CPU%':<8} {'Mem(MB)'}")
        print(f"   {'-'*60}")
        for i, p in enumerate(profiles, 1):
            print(
                f"   {i:<4} {p['event_type']:<22} "
                f"{p['time_offset_s']:<12.2f} "
                f"{p['cpu_percent']:<8.1f} "
                f"{p['memory_mb']:.1f}"
            )
    else:
        print("\n🔍 Per-Step Resource Attribution: no events captured (log may be empty)")

    # ── CLEAR Dimensions ──────────────────────────────────────────────────────
    print(f"\n📐 CLEAR Dimension Scores")
    for dim, score in result.dimension_scores.items():
        bar = "█" * int(score * 20)
        print(f"   {dim.capitalize():<15} {score:.3f}  {bar}")

    # ── Recommendations ───────────────────────────────────────────────────────
    print(f"\n💡 Recommendations")
    for rec in result.recommendations:
        print(f"   {rec}")

    # ── Save result ───────────────────────────────────────────────────────────
    await evaluator._save_mini_agent_result(result)
    print(f"\n✅ Done. Result saved to phase3/")


if __name__ == "__main__":
    asyncio.run(main())
