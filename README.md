# Team28 Evaluation Pipeline

This repo runs a 3-phase evaluation pipeline for different agent runtimes.

Supported agents (current):
- `mini-agent`
- `continue`
- `mini-swe-agent` (aliases: `mini-swe`, `mswe`)

Agent runtime profiles are in:
- `agentic_sys/config/config.yaml`

## 1) Enter project

```bash
cd agentic_sys
```

Unless noted otherwise, shell commands below assume you are inside `agentic_sys/`.
File references keep repo-root paths such as `agentic_sys/docs/...` so they stay
unambiguous when discussed from the top-level README.

## 2) Continue setup (team API key mode)

If you use Continue with team credits, follow:
- `agentic_sys/docs/continue_setup.md`

That guide includes:
- CLI install
- `CONTINUE_API_KEY` setup
- health checks
- phase1/2/3 commands

## 2a) Mini-Agent setup

For install, PATH notes, non-billing healthcheck, and recommended phase3 run:
- `agentic_sys/docs/mini_agent_setup.md`

## 2b) V2 evaluation workflow (config-driven)

For the full end-to-end V2 scoring workflow (config fields, core suite policy,
comparability/provisional rules, multi-run aggregation, outputs):
- `agentic_sys/docs/evaluation_workflow_v2.md`

## 2c) Mini-SWE-Agent setup

Install the CLI in the same Python environment used for this repo:

```bash
pip install mini-swe-agent
```

For install notes and health checks:
- `agentic_sys/docs/mini_swe_setup.md`

## 2d) Unified non-billing healthchecks

Check every installed agent CLI from one place:

```bash
python verify_agent_setup.py
```

Check a single agent:

```bash
python verify_agent_setup.py --agent mini-agent
python verify_agent_setup.py --agent continue
python verify_agent_setup.py --agent mini-swe-agent
```

## 3) Run pipeline

### Phase 1 (basic integrated evaluation)

```bash
python integrated_agent_evaluation.py --agent mini-agent
python integrated_agent_evaluation.py --agent continue
python integrated_agent_evaluation.py --agent mini-swe-agent
```

### Phase 2 (enhanced monitoring + bottleneck analysis)

```bash
python enhanced_comprehensive_evaluation.py --agent mini-agent
python enhanced_comprehensive_evaluation.py --agent continue
python enhanced_comprehensive_evaluation.py --agent mini-swe-agent
```

### Phase 3 (CLEAR framework evaluation)

```bash
python clear_evaluation_system.py --agent mini-agent --refresh-capability-profile
python clear_evaluation_system.py --agent continue --refresh-capability-profile
python clear_evaluation_system.py --agent mini-swe-agent --refresh-capability-profile
```

`mini-swe-agent` declares expected trace/process support in YAML.
Run phase3 with refreshed capability profiles so those signals are confirmed
from the local CLI setup before full comparability is granted.

### Single smoke test

```bash
python run_single_test.py --agent mini-agent
python run_single_test.py --agent continue
python run_single_test.py --agent mini-swe-agent
```

## 4) Results directories (default)

All outputs are written under `agentic_sys/artifacts/`.

Mini-agent:
- phase1: `artifacts/mini-agent/phase1/`
- phase2: `artifacts/mini-agent/phase2/`
- phase3: `artifacts/mini-agent/phase3/`
- single test: `artifacts/mini-agent/phase3/single_test/`

Continue:
- phase1: `artifacts/continue/phase1/`
- phase2: `artifacts/continue/phase2/`
- phase3: `artifacts/continue/phase3/`
- single test: `artifacts/continue/phase3/single_test/`

Mini-SWE-Agent:
- phase1: `artifacts/mini-swe-agent/phase1/`
- phase2: `artifacts/mini-swe-agent/phase2/`
- phase3: `artifacts/mini-swe-agent/phase3/`
- single test: `artifacts/mini-swe-agent/phase3/single_test/`

## 5) Visualize Phase 3 Results

Generate the latest phase3 dashboard for a configured agent:

```bash
python visualize_results.py --agent mini-agent
python visualize_results.py --agent continue
python visualize_results.py --agent mini-swe-agent
```

Generate dashboards for all JSON results in a directory:

```bash
python visualize_results.py "artifacts/mini-agent/phase3/*.json"
python visualize_results.py "artifacts/continue/phase3/*.json"
python visualize_results.py "artifacts/mini-swe-agent/phase3/*.json"
```

Each input JSON produces a sibling PNG, and multi-file runs also generate
`comparison_dashboard.png` in the target directory.

## 6) Add a new agent (YAML-only)

Follow:
- `agentic_sys/docs/new_agent_onboarding.md`

You only need to add a profile in `agentic_sys/config/config.yaml`, then run with:

```bash
python run_single_test.py --agent <new-agent-name-or-alias>
```

## 7) Notes

- Use `--agent` explicitly in all scripts.
- Do not commit API keys/secrets.
- Continue defaults (workspace/model) are controlled in `agentic_sys/config/config.yaml`.
- Non-billing adapter health checks are available in `agentic_sys/agent_runtime/safe_healthcheck.py`.

## 8) Read Reports Carefully

- CLEAR reports separate actionable issues from reporting caveats.
- Estimated cost is advisory only unless the runtime exposes provider-reported cost.
- Production-readiness status is a summary for the evaluated suite, not a blanket deployment guarantee.
- Repeated-run time breakdowns may use an observed subset when one phase is only visible in part of the run set.

## 9) Unit Tests (Required)

Before you submit changes, ensure unit tests pass at minimum.

From repo root:

```bash
python -m unittest discover -s agentic_sys/tests
```

Or from `agentic_sys/`:

```bash
python -m unittest discover -s tests
```
