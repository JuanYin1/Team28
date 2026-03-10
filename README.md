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

## 2) Continue setup (team API key mode)

If you use Continue with team credits, follow:
- `agentic_sys/docs/continue_setup.md`

That guide includes:
- CLI install
- `CONTINUE_API_KEY` setup
- health checks
- phase1/2/3 commands

## 2a) Mini-SWE-Agent setup

Install CLI (same Python env used to run this repo scripts):

```bash
pip install mini-swe-agent
```

Set Mini-SWE-Agent global config/API key:
- Run `mini-extra config setup` (or edit `%LOCALAPPDATA%/mini-swe-agent/mini-swe-agent/.env`)
- Configure at least model + provider key (example: `MSWEA_MODEL_NAME`, `OPENAI_API_KEY`)

Quick check:

```bash
mini --help
```

If Windows terminal encoding fails on emoji output, use:

```bash
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
```

## 2b) V2 evaluation workflow (config-driven)

For the full end-to-end V2 scoring workflow (config fields, core suite policy,
comparability/provisional rules, multi-run aggregation, outputs):
- `docs/evaluation_workflow_v2.md`

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
python clear_evaluation_system.py --agent mini-agent
python clear_evaluation_system.py --agent continue
python clear_evaluation_system.py --agent mini-swe-agent
```

### Single smoke test

```bash
python run_single_test.py --agent mini-agent
python run_single_test.py --agent continue
python run_single_test.py --agent mini-swe-agent
```

Optional runtime override (without editing YAML):

```bash
python integrated_agent_evaluation.py --agent mini-swe-agent --adapter-option "model_name=openai/gpt-5-mini"
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

## 5) Visualize Phase 3 Results (execution graph + dashboards)

Script:
- `agentic_sys/visualize_results.py`

Install plotting deps once if needed:

```bash
python3.12 -m pip install matplotlib numpy
```

From `agentic_sys/`, generate charts for all phase3 tasks of each agent:

```bash
python3.12 visualize_results.py "artifacts/mini-agent/phase3/*.json"
python3.12 visualize_results.py "artifacts/continue/phase3/*.json"
python3.12 visualize_results.py "artifacts/mini-swe-agent/phase3/*.json"
```

What gets generated:
- One dashboard PNG per task JSON (includes execution time breakdown, CLEAR radar, per-step timeline/execution graph, event distribution, memory/CPU curves).
- One `comparison_dashboard.png` per phase3 folder when multiple JSON files are provided.

Single-task visualization example:

```bash
python3.12 visualize_results.py artifacts/continue/phase3/continue_cn_simple_file_operations_1773112304.json
```

Default behavior (no file args):
- Script visualizes only the latest JSON in `artifacts/mini-agent/phase3/` unless you pass `--results-dir`.

## 6) Add a new agent (YAML-only)

Follow:
- `docs/new_agent_onboarding.md`

You only need to add a profile in `config/config.yaml`, then run with:

```bash
python run_single_test.py --agent <new-agent-name-or-alias>
```

## 7) Notes

- Use `--agent` explicitly in all scripts.
- Do not commit API keys/secrets.
- Continue defaults (workspace/model) are controlled in `config/config.yaml`.
- Non-billing adapter health checks are available in `agent_runtime/safe_healthcheck.py`.

## 8) Unit Tests (Required)

Before you submit changes, ensure unit tests pass at minimum.

From repo root:

```bash
python -m unittest discover -s agentic_sys/tests
```

Or from `agentic_sys/`:

```bash
python -m unittest discover -s tests
```
