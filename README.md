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
python integrated_mini_agent_evaluation.py --agent mini-agent
python integrated_mini_agent_evaluation.py --agent continue
```

### Phase 2 (enhanced monitoring + bottleneck analysis)

```bash
python enhanced_comprehensive_evaluation.py --agent mini-agent
python enhanced_comprehensive_evaluation.py --agent continue
```

### Phase 3 (CLEAR framework evaluation)

```bash
python mini_agent_clear_evaluation_system.py --agent mini-agent
python mini_agent_clear_evaluation_system.py --agent continue
```

### Single smoke test

```bash
python run_single_test.py --agent mini-agent
python run_single_test.py --agent continue
```

## 4) Results directories (default)

Mini-agent:
- phase1: `integrated_evaluation_results/`
- phase2: `enhanced_evaluation_results/`
- phase3: `agent_evaluation_results/`

Continue:
- phase1: `phase1_continue/`
- phase2: `phase2_continue/`
- phase3: `phase3_continue/`
- single test: `phase3_continue_single/`

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
