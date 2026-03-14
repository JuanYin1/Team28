import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import verify_agent_setup


class VerifyAgentSetupTests(unittest.TestCase):
    def test_agent_list_expands_all(self):
        self.assertEqual(
            verify_agent_setup._agent_list("all"),
            ["mini-agent", "continue", "mini-swe-agent"],
        )

    def test_main_json_reports_requested_agent(self):
        fake_report = type(
            "Report",
            (),
            {
                "success": True,
                "command": ["mini", "--help"],
                "return_code": 0,
                "stdout": "ok",
                "stderr": "",
                "__dict__": {
                    "success": True,
                    "command": ["mini", "--help"],
                    "return_code": 0,
                    "stdout": "ok",
                    "stderr": "",
                },
            },
        )()

        buf = io.StringIO()
        with patch("verify_agent_setup._run_check", return_value=fake_report), redirect_stdout(buf):
            code = verify_agent_setup.main(["--agent", "mini-swe-agent", "--json"])

        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn('"mini-swe-agent"', output)
        self.assertIn('"success": true', output.lower())


if __name__ == "__main__":
    unittest.main()
