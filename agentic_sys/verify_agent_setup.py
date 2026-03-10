#!/usr/bin/env python3

import argparse
import json
import sys
from typing import Dict, List

from agent_runtime.factory import create_agent_adapter
from agent_runtime.safe_healthcheck import SafeHealthcheckReport, run_safe_healthcheck


SUPPORTED_AGENTS = ["mini-agent", "continue", "mini-swe-agent"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run non-billing health checks for one or more agent CLIs."
    )
    parser.add_argument(
        "--agent",
        choices=["all", *SUPPORTED_AGENTS],
        default="all",
        help="Agent to check. Default runs all supported agents.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report.",
    )
    return parser


def _agent_list(selected: str) -> List[str]:
    if selected == "all":
        return list(SUPPORTED_AGENTS)
    return [selected]


def _run_check(agent_name: str) -> SafeHealthcheckReport:
    adapter = create_agent_adapter(agent=agent_name)
    return run_safe_healthcheck(adapter)


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    reports: Dict[str, Dict[str, object]] = {}
    overall_success = True

    for agent_name in _agent_list(args.agent):
        try:
            report = _run_check(agent_name)
            payload = report.__dict__
            overall_success = overall_success and report.success
        except Exception as exc:
            payload = {
                "success": False,
                "command": [],
                "return_code": None,
                "stdout": "",
                "stderr": f"Execution error: {exc}",
            }
            overall_success = False
        reports[agent_name] = payload

    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for agent_name in _agent_list(args.agent):
            payload = reports[agent_name]
            print(f"{agent_name} setup check")
            print("=" * 60)
            print(f"Success    : {payload['success']}")
            command = payload.get("command") or []
            if command:
                print(f"Command    : {' '.join(str(part) for part in command)}")
            return_code = payload.get("return_code")
            if return_code is not None:
                print(f"ReturnCode : {return_code}")
            stdout = str(payload.get("stdout") or "")
            stderr = str(payload.get("stderr") or "")
            if stdout:
                print(f"Stdout     : {stdout[:500]}")
            if stderr:
                print(f"Stderr     : {stderr[:500]}")
            if agent_name != _agent_list(args.agent)[-1]:
                print()

    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
