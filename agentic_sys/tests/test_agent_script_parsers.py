import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enhanced_comprehensive_evaluation import _build_arg_parser as build_phase2_parser
from integrated_mini_agent_evaluation import _build_arg_parser as build_phase1_parser
from mini_agent_clear_evaluation_system import _build_arg_parser as build_phase3_parser
from run_single_test import _build_arg_parser as build_single_parser


class AgentScriptParserTests(unittest.TestCase):
    def test_all_phase_scripts_accept_yaml_defined_agent_name(self):
        for build_parser in (
            build_phase1_parser,
            build_phase2_parser,
            build_phase3_parser,
            build_single_parser,
        ):
            parser = build_parser()
            args = parser.parse_args(["--agent", "custom-from-yaml"])
            self.assertEqual(args.agent, "custom-from-yaml")


if __name__ == "__main__":
    unittest.main()
