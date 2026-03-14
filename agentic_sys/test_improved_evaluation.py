#!/usr/bin/env python3
"""
Test script for the improved agent evaluation system.
"""

import asyncio
import logging
from clear_evaluation_system import AgentCLEAREvaluator, AgentTestCase, AgentTestCriteria

async def test_simple_case():
    """Test the improved evaluation system with a simple case"""
    
    # Configure logging to see debug info
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Create evaluator
    evaluator = AgentCLEAREvaluator()
    
    # Create a simple test case
    test_case = AgentTestCase(
        name="test_file_operations",
        category="file_operations", 
        description="Simple file creation test",
        task_prompt="Create a file called 'hello.txt' with content 'Hello World' and then read it back.",
        evaluation_criteria=AgentTestCriteria(
            task_type="file_ops",
            complexity="simple",
            expected_tools=["write_file", "read_file"],
            max_steps=5,
            max_task_time_seconds=30.0
        ),
        expected_outputs=["hello.txt", "Hello World"],
        expected_file_changes=["hello.txt"],
        success_indicators=["created", "content"]
    )
    
    print("🧪 Testing improved evaluation system...")
    print(f"Test case: {test_case.name}")
    print(f"Expected tools: {test_case.evaluation_criteria.expected_tools}")
    
    # Run evaluation
    result = await evaluator.evaluate_agent_test(test_case)
    
    print("\n📊 Results:")
    print(f"Tools detected: {result.tools_used}")
    print(f"Tool executions: {result.clear_metrics.tool_executions}")
    print(f"Tool selection accuracy: {result.clear_metrics.tool_selection_accuracy:.2f}")
    print(f"Total tokens: {result.clear_metrics.total_tokens_used}")
    print(f"Steps completed: {result.clear_metrics.steps_to_completion}")
    print(f"Overall CLEAR score: {result.overall_clear_score:.3f}")
    print(f"Passed thresholds: {result.passed_all_thresholds}")
    
    print("\n💡 Recommendations:")
    for rec in result.recommendations:
        print(f"  - {rec}")
    
    return result

if __name__ == "__main__":
    result = asyncio.run(test_simple_case())
    
    if result.clear_metrics.tool_executions > 0:
        print("\n✅ SUCCESS: Tool calls detected correctly!")
    else:
        print("\n❌ ISSUE: Still not detecting tool calls")
        print("Check the log analysis patterns and session statistics extraction.")
