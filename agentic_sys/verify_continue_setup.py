#!/usr/bin/env python3

import argparse
import json
import sys

from agent_runtime.continue_healthcheck import run_continue_healthcheck


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Continue CLI is installed and can serve a real request."
    )
    parser.add_argument("--cn-path", default=None, help="Override Continue executable path.")
    parser.add_argument("--agent", default=None, help="Continue hub agent slug.")
    parser.add_argument(
        "--config",
        default="continuedev/default-cli-config",
        help="Continue config file path or hub slug.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Repeatable Continue model slug (`--model owner/package`).",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        help="Repeatable allow policy passed to Continue.",
    )
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Repeatable raw argument appended to Continue command.",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly OK and nothing else.",
        help="Prompt used for the live probe.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Timeout in seconds for the probe request.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report for automation.",
    )
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    report = run_continue_healthcheck(
        executable=args.cn_path,
        agent_name=args.agent,
        config_path=args.config,
        model_slugs=args.model,
        allow_policies=args.allow,
        extra_args=args.extra_arg,
        prompt=args.prompt,
        timeout_seconds=args.timeout,
    )

    if args.json:
        print(json.dumps(report.__dict__, indent=2))
    else:
        print("Continue setup check")
        print("=" * 60)
        print(f"Success    : {report.success}")
        print(f"Diagnosis  : {report.diagnosis}")
        print(f"Executable : {report.executable or '(not found)'}")
        if report.command:
            print(f"Command    : {' '.join(report.command)}")
        if report.return_code is not None:
            print(f"ReturnCode : {report.return_code}")
        if report.stdout:
            print(f"Stdout     : {report.stdout[:500]}")
        if report.stderr:
            print(f"Stderr     : {report.stderr[:500]}")

    return 0 if report.success else 1


if __name__ == "__main__":
    sys.exit(main())
