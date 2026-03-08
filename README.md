# Team28 Evaluation Pipeline

This repo runs a 3-phase evaluation pipeline for different agent runtimes.

Supported agents (current):
- `mini-agent`
- `continue`

Agent runtime profiles are in:
- `agentic_sys/config/config.yaml`

## 1) Enter project

```bash
cd agentic_sys
```

## 2) Continue setup (team API key mode)

If you use Continue with team credits, follow:
- `docs/continue_setup.md`

That guide includes:
- CLI install
- `CONTINUE_API_KEY` setup
- health checks
- phase1/2/3 commands

## 3) Run pipeline

### Phase 1 (basic integrated evaluation)

```bash
python integrated_agent_evaluation.py --agent mini-agent
python integrated_agent_evaluation.py --agent continue
```

### Phase 2 (enhanced monitoring + bottleneck analysis)

```bash
python enhanced_comprehensive_evaluation.py --agent mini-agent
python enhanced_comprehensive_evaluation.py --agent continue
```

### Phase 3 (CLEAR framework evaluation)

```bash
python clear_evaluation_system.py --agent mini-agent
python clear_evaluation_system.py --agent continue
```

### Single smoke test

```bash
python run_single_test.py --agent mini-agent
python run_single_test.py --agent continue
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

## 5) Add a new agent (YAML-only)

Follow:
- `docs/new_agent_onboarding.md`

You only need to add a profile in `config/config.yaml`, then run with:

```bash
python run_single_test.py --agent <new-agent-name-or-alias>
```

## 6) Notes

- Use `--agent` explicitly in all scripts.
- Do not commit API keys/secrets.
- Continue defaults (workspace/model) are controlled in `config/config.yaml`.
- Non-billing adapter health checks are available in `agent_runtime/safe_healthcheck.py`.

## 7) Unit Tests (Required)

Before you submit changes, ensure unit tests pass at minimum.

From repo root:

```bash
python -m unittest discover -s agentic_sys/tests
```

Or from `agentic_sys/`:

```bash
python -m unittest discover -s tests
```
