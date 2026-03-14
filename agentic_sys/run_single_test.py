#!/usr/bin/env python3
"""
Single-test runner for the CLEAR evaluation system.
Runs only the simplest test case (simple_file_operations) and prints results.

Examples (from agentic_sys/ directory):
    python run_single_test.py
    python run_single_test.py --agent continue
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Make sure we can import from the same directory
sys.path.insert(0, str(Path(__file__).parent))

from clear_evaluation_system import AgentCLEAREvaluator
from agent_runtime.factory import create_agent_adapter
from agent_runtime.script_config import resolve_script_runtime_options


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run phase3 single test.")
    parser.add_argument(
        "--agent",
        default="mini-agent",
        help="Runtime adapter key/alias.",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Directory where results are written.",
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


async def main(argv=None):
    args = _build_arg_parser().parse_args(argv)
    results_dir, adapter_kwargs, config_source = resolve_script_runtime_options(
        args=args,
        script_name="run_single_test",
        default_results_dir="artifacts/mini-agent/phase3/single_test",
    )
    adapter = create_agent_adapter(
        agent=args.agent,
        **adapter_kwargs,
    )
    print("=" * 70)
    print("Agent Single Test Runner — simple_file_operations")
    print(f"Adapter: {adapter.agent_id}")
    if config_source:
        print(f"Config : {config_source}")
    print("=" * 70)

    evaluator = AgentCLEAREvaluator(results_dir=results_dir, agent_adapter=adapter)
    test_cases = evaluator.create_agent_test_suite()

    # Run only the first (simplest) test
    test_case = test_cases[0]
    print(f"\nTest : {test_case.name}")
    print(f"Category : {test_case.category}")
    print(f"Timeout  : {test_case.evaluation_criteria.max_task_time_seconds}s")
    print(f"Expected tools: {test_case.evaluation_criteria.expected_tools}")
    print()

    result = await evaluator.evaluate_agent_test(test_case)

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
    await evaluator._save_result(result)
    print(f"\n✅ Done. Result saved to {results_dir}/")


if __name__ == "__main__":
    asyncio.run(main())
