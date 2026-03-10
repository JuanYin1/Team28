# Mini-Agent Setup

Repository default runtime id:
- `mini-agent`

Run the commands below from `agentic_sys/` unless noted otherwise.

## 1) Install

Install `mini-agent` in the same Python environment used for this repo.

```bash
pip install mini-agent
which mini-agent
mini-agent --version
```

If the binary lands in `~/.local/bin`, add it to your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Success looks like:
- `which mini-agent` prints a real path,
- `mini-agent --version` exits cleanly,
- the binary is available in the same shell where you run repo scripts.

## 2) Non-Billing Health Check

Run the unified setup checker:

```bash
python verify_agent_setup.py --agent mini-agent
```

This uses `mini-agent --version`, so it does not send a model request and does not consume credits.

Expected result:
- the script reports `mini-agent` as available,
- no model request is sent,
- no auth/billing check is required for this step.

## 3) Recommended Evaluation Run

```bash
python clear_evaluation_system.py --agent mini-agent --refresh-capability-profile
python clear_evaluation_system.py --agent mini-agent
```

Mode notes:
- `--refresh-capability-profile`: probe then evaluate.
- `--probe-agent`: same as refresh.
- `--probe-only`: probe only.

Expected artifacts after phase3:
- `artifacts/mini-agent/phase3/*_run_manifest_*.json`
- `artifacts/mini-agent/phase3/*_clear_report_*.md`
- `artifacts/mini-agent/phase3/*_leaderboard_*.csv`

## 4) Troubleshooting

- `mini-agent: command not found`
  - fix PATH or reinstall in the active Python environment.
- `verify_agent_setup.py` fails but `mini-agent --version` works in another terminal
  - you are likely using a different shell/Python environment than the repo run.
- capability/profile looks stale
  - rerun `--refresh-capability-profile`.
- phase3 tool traces look incomplete
  - inspect the latest task JSON and confirm parser evidence was captured from stdout/detailed logs.
- phase3 completed but no new report is visible
  - inspect `artifacts/mini-agent/phase3/` and sort by timestamp; reports are written with time-stamped filenames.

## 5) Security

- never commit keys or local runtime config,
- rotate credentials immediately if leaked.
