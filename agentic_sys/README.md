# agentic_sys

Evaluation scripts and runtime adapters for multi-agent benchmarking.

## Start Here

- V2 scoring and comparability contract: `docs/evaluation_workflow_v2.md`
- New agent onboarding (YAML-only path): `docs/new_agent_onboarding.md`
- Mini-Agent setup: `docs/mini_agent_setup.md`
- Continue runtime setup: `docs/continue_setup.md`
- Mini-SWE-Agent setup: `docs/mini_swe_setup.md`

## Python Prerequisites

The evaluation scripts expect these Python packages in the active environment:

```bash
pip install pyyaml
```

Optional extras by script:
- phase2 monitoring: `pip install psutil`
- visualization: `pip install matplotlib numpy`

The repo currently uses a documented local/manual workflow. There is no
checked-in GitHub Actions workflow under `.github/workflows/`.

## Unified Non-Billing Health Checks

Run all installed agent CLI checks from one place:

```bash
python verify_agent_setup.py
```

Run a single agent:

```bash
python verify_agent_setup.py --agent mini-agent
python verify_agent_setup.py --agent continue
python verify_agent_setup.py --agent mini-swe-agent
```

These checks do not send model prompts:
- `mini-agent` uses `mini-agent --version`
- `continue` uses `cn --version`
- `mini-swe-agent` uses `mini --help`

## Quick Run

From `agentic_sys/`:

```bash
python clear_evaluation_system.py --agent mini-agent
python clear_evaluation_system.py --agent continue
python clear_evaluation_system.py --agent mini-swe-agent
```

Outputs are written under `artifacts/<agent>/phase3/`:
- per-task JSON
- markdown report
- core/full leaderboard CSV

Capability profiles are stored separately under:
- `config/artifacts/capability_profiles/<agent>.json`

## Fair Comparison (Recommended)

Run all configured agents with refreshed capability profiles before side-by-side comparison:

```bash
python clear_evaluation_system.py --agent mini-agent --refresh-capability-profile
python clear_evaluation_system.py --agent continue --refresh-capability-profile
python clear_evaluation_system.py --agent mini-swe-agent --refresh-capability-profile
```

Then compare the latest files under:
- `artifacts/mini-agent/phase3/`
- `artifacts/continue/phase3/`
- `artifacts/mini-swe-agent/phase3/`

## Visualize Results

Generate the latest phase3 dashboard using the configured results dir for an agent:

```bash
python visualize_results.py --agent mini-agent
python visualize_results.py --agent continue
python visualize_results.py --agent mini-swe-agent
```

Generate dashboards for all JSON results in a phase3 folder:

```bash
python visualize_results.py "artifacts/mini-agent/phase3/*.json"
python visualize_results.py "artifacts/continue/phase3/*.json"
python visualize_results.py "artifacts/mini-swe-agent/phase3/*.json"
```

Per-file PNGs are written next to the input JSON files. Multi-file runs also
generate the configured comparison image name (default:
`comparison_dashboard.png`) in that directory.

## Capability Profile Behavior (Phase3)

- A capability profile is generated only when probe is triggered:
  - `--probe-agent`
  - `--probe-only`
  - `--refresh-capability-profile`
  - or `evaluation.v2.capability_probe.enabled: true` in config.
- `mini-swe-agent` declares trace/process support in YAML, but full comparability
  still requires probe to observe those signals in the local runtime.
- If `config/artifacts/capability_profiles/<agent>.json` already exists, phase3 loads it by default.
- Generated profiles include `profile_metadata` and `generated_at_utc` (`AUTO-GENERATED`, `DO NOT EDIT MANUALLY`).
- If a profile exists but all probe runs in it failed, it is treated as unusable and evaluator falls back to declared YAML capabilities.
- After changing `evaluation_capabilities` or parser settings, refresh profile to avoid stale resolved capabilities:

```bash
python clear_evaluation_system.py --agent continue --refresh-capability-profile
python clear_evaluation_system.py --agent mini-swe-agent --refresh-capability-profile
```

Mode semantics:
- `--refresh-capability-profile`: probe first, then run full evaluation.
- `--probe-agent`: same behavior as `--refresh-capability-profile`.
- `--probe-only`: probe only, no evaluation tasks.

## Interpreting CLEAR Reports

- `Most Critical Issues` lists actionable problems found in the evaluated suite.
- `Reporting Caveats` lists limitations in evidence quality or unsupported dimensions, such as estimated cost.
- `Ready for Deployment` is advisory for the evaluated tasks only. It is not a substitute for staging, security review, or production load validation.
- Time-breakdown tables may use a consistent observed subset of repeated runs when a phase is only visible in part of the run set.

## Known Limitations

- Latest phase3 artifacts are suitable for comparing checker-backed outcomes and supported trace/process dimensions.
- `cost_efficiency` and `token_efficiency` remain advisory until the runtime exposes provider cost and token/session statistics in the evaluated run, not just in a capability profile.
- Noisy parser classifications can still weaken process-level interpretation even when a task remains formally `COMPARABLE`.

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
