# agentic_sys

Evaluation scripts and runtime adapters for multi-agent benchmarking.

## Start Here

- V2 scoring and comparability contract: `docs/evaluation_workflow_v2.md`
- New agent onboarding (YAML-only path): `docs/new_agent_onboarding.md`
- Continue runtime setup: `docs/continue_setup.md`

## Quick Run

From `agentic_sys/`:

```bash
python clear_evaluation_system.py --agent mini-agent
python clear_evaluation_system.py --agent continue
```

Outputs are written under `artifacts/<agent>/phase3/`:
- per-task JSON
- markdown report
- core/full leaderboard CSV

## Fair Comparison (Recommended)

Run both agents with refreshed capability profiles before side-by-side comparison:

```bash
python clear_evaluation_system.py --agent mini-agent --refresh-capability-profile
python clear_evaluation_system.py --agent continue --refresh-capability-profile
```

Then compare the latest files under:
- `artifacts/mini-agent/phase3/`
- `artifacts/continue/phase3/`

## Capability Profile Behavior (Phase3)

- A capability profile is generated only when probe is triggered:
  - `--probe-agent`
  - `--probe-only`
  - `--refresh-capability-profile`
  - or `evaluation.v2.capability_probe.enabled: true` in config.
- If `config/artifacts/capability_profiles/<agent>.json` already exists, phase3 loads it by default.
- Generated profiles include `profile_metadata` and `generated_at_utc` (`AUTO-GENERATED`, `DO NOT EDIT MANUALLY`).
- If a profile exists but all probe runs in it failed, it is treated as unusable and evaluator falls back to declared YAML capabilities.
- After changing `evaluation_capabilities` or parser settings, refresh profile to avoid stale resolved capabilities:

```bash
python clear_evaluation_system.py --agent continue --refresh-capability-profile
```

Mode semantics:
- `--refresh-capability-profile`: probe first, then run full evaluation.
- `--probe-agent`: same behavior as `--refresh-capability-profile`.
- `--probe-only`: probe only, no evaluation tasks.

## Run Unit Tests (Required)

At minimum, all unit tests should pass before submitting changes.

From `agentic_sys/`:

```bash
python -m unittest discover -s tests
```

From repo root:

```bash
python -m unittest discover -s agentic_sys/tests
```
