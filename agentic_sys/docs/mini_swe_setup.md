# Mini-SWE-Agent Setup

Repository default runtime id:
- `mini-swe-agent`

Run the commands below from `agentic_sys/` unless noted otherwise.

## 1) Install

Install the CLI in the same Python environment used for this repo:

```bash
pip install mini-swe-agent
which mini
mini --help
```

Success looks like:
- `which mini` prints a real path,
- `mini --help` exits cleanly,
- the same shell can run both `mini` and the repo scripts.

## 2) Model Configuration

For stable local runs, keep the global mini-swe config aligned with the project default model:

```bash
sed -n '1,50p' "$HOME/Library/Application Support/mini-swe-agent/.env"
```

Recommended value:

```env
MSWEA_MODEL_NAME='openai/gpt-5-mini'
```

Avoid stale provider overrides such as old MiniMax/OpenAI-compatible base URLs when you want to use OpenAI directly.

Minimum requirement:
- the shell that runs evaluation commands must also have the right model/provider credentials, typically `OPENAI_API_KEY`.

## 3) Non-Billing Health Check

Run the unified setup checker:

```bash
python verify_agent_setup.py --agent mini-swe-agent
```

This uses `mini --help`, so it does not send a model request and does not consume credits.

Expected result:
- `verify_agent_setup.py --agent mini-swe-agent` passes without making a model call.

## 4) Optional Live Smoke Test

This sends a real model request and may consume credits:

```bash
mini -t "Create a file named hello.txt with content hi, then read it back." \
  -m "openai/gpt-5-mini" \
  -y \
  --exit-immediately \
  -o /tmp/mini_swe_smoke.json
```

Success looks like:
- the command exits cleanly,
- `/tmp/mini_swe_smoke.json` is created,
- the output shows the agent can write/read files through its normal workflow.

## 5) Recommended Evaluation Run

```bash
python clear_evaluation_system.py --agent mini-swe-agent --refresh-capability-profile
python clear_evaluation_system.py --agent mini-swe-agent
```

`mini-swe-agent` declares expected trace/process support in YAML. Refresh its
capability profile before treating it as process/full-comparable so the local
runtime actually proves those signals.

Expected artifacts after phase3:
- `artifacts/mini-swe-agent/phase3/*_run_manifest_*.json`
- `artifacts/mini-swe-agent/phase3/*_clear_report_*.md`
- `artifacts/mini-swe-agent/phase3/*_leaderboard_*.csv`

## 6) Troubleshooting

- provider/model auth errors
  - verify `OPENAI_API_KEY` and clear stale base URL overrides.
- command not found
  - reinstall in the active Python environment or fix PATH.
- phase3 shows zero tools/steps
  - rerun the live smoke test and inspect the generated trajectory JSON.
- `mini --help` works but evaluation fails immediately
  - confirm the global mini-swe config is pointing at a valid model/provider for this machine.
