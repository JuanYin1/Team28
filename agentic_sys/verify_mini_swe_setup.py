#!/usr/bin/env python3

import sys

import verify_agent_setup


def main(argv=None) -> int:
    args = list(argv or [])
    passthrough = ["--agent", "mini-swe-agent", *args]
    return verify_agent_setup.main(passthrough)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
