# Continue Setup (Headless CLI)

Repository defaults:
- workspace: `zhiruis-workspace-2`
- config: `continuedev/default-cli-config`
- model: `anthropic/claude-haiku-4-5`

Run the commands below from `agentic_sys/` unless noted otherwise.

## 1) Install

```bash
npm i -g @continuedev/cli
which cn
cn --version
```

If needed:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Success looks like:
- `which cn` prints a real path,
- `cn --version` exits cleanly,
- the same shell can run repo scripts and `cn`.

## 2) Configure API Key

```bash
echo 'export CONTINUE_API_KEY="<ORG_SCOPED_KEY>"' >> ~/.zshrc
source ~/.zshrc
```

Minimum requirement:
- `CONTINUE_API_KEY` must be available in the shell where you run evaluation commands.

## 3) Quick Health Check

Non-billing CLI check:

```bash
python verify_agent_setup.py --agent continue
```

Optional live request check:

```bash
cn -p "Reply with exactly OK and nothing else." --auto
python verify_continue_setup.py
```

Expected result:
- `verify_agent_setup.py --agent continue` should pass without sending a model request,
- the optional live request should return `OK`,
- `verify_continue_setup.py` should confirm the CLI can complete a real prompt.

## 4) Recommended Evaluation Run

```bash
python clear_evaluation_system.py --agent continue --refresh-capability-profile
python clear_evaluation_system.py --agent continue
```

Mode notes:
- `--refresh-capability-profile`: probe then evaluate.
- `--probe-agent`: same as refresh.
- `--probe-only`: probe only.

Expected artifacts after phase3:
- `artifacts/continue/phase3/*_run_manifest_*.json`
- `artifacts/continue/phase3/*_clear_report_*.md`
- `artifacts/continue/phase3/*_leaderboard_*.csv`

## 5) Full Comparability Expectations

`continue` reaches `full_status=COMPARABLE` only when all are true:
- declared trace capabilities are enabled in YAML,
- probe observes matching trace signals,
- parser extracts those signals in real tasks.

Check task JSON/report field:
- `comparability.required_signal_status`

## 6) Troubleshooting

- `auth_or_model_not_configured`
  - check `CONTINUE_API_KEY`, config, model availability.
- `cn: command not found`
  - fix PATH.
- live prompt health check hangs or fails
  - verify the CLI can access the configured workspace/model from your account.
- `full comparable` still low
  - rerun `--refresh-capability-profile`.
  - inspect `config/artifacts/capability_profiles/continue.json`.
  - confirm `probe_results` are not all failed.
- profile exists but probe failed
  - evaluator will ignore that profile and use declared YAML capabilities.

## 7) Security

- never commit keys,
- never paste keys in logs/issues,
- rotate immediately if leaked.

## 8) Tests Before Merge

```bash
python -m unittest discover -s tests
```
