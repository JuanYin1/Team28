import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_runtime.parsers import MiniAgentTraceParser


class MiniAgentTraceParserTests(unittest.TestCase):
    def test_parse_tracks_steps_and_tool_calls(self):
        parser = MiniAgentTraceParser(known_tools=["write_file", "bash"])
        log = """
Step 1/100
🧠 Thinking:
🤖 Assistant:
🔧 Tool Call: write_file
✓ Result: wrote file
🔧 Tool Call: write_file
✓ Result: wrote file
❌ Error: command failed
Step 2/100
"""
        summary = parser.parse(log)

        self.assertEqual(summary.total_steps, 2)
        self.assertEqual(summary.tools_used, ["write_file"])
        self.assertEqual(summary.tool_call_count, 2)
        self.assertEqual(summary.successful_operations, 2)
        self.assertEqual(summary.thinking_blocks, 1)
        self.assertEqual(summary.assistant_responses, 1)
        self.assertEqual(summary.errors_encountered, 1)

    def test_parse_ignores_unknown_tools_when_whitelist_provided(self):
        parser = MiniAgentTraceParser(known_tools=["write_file"])
        summary = parser.parse("🔧 Tool Call: custom_tool")

        self.assertEqual(summary.tool_call_count, 0)
        self.assertEqual(summary.tools_used, [])

    def test_parse_accepts_unknown_tools_without_whitelist(self):
        parser = MiniAgentTraceParser()
        summary = parser.parse("🔧 Tool Call: custom_tool")

        self.assertEqual(summary.tool_call_count, 1)
        self.assertEqual(summary.tools_used, ["custom_tool"])

    def test_parse_handles_empty_logs(self):
        parser = MiniAgentTraceParser()
        summary = parser.parse("")

        self.assertEqual(summary.total_steps, 0)
        self.assertEqual(summary.events, [])
        self.assertEqual(summary.tool_call_count, 0)


if __name__ == "__main__":
    unittest.main()
