# agentic_sys

Evaluation scripts and runtime adapters for multi-agent benchmarking.

## Start Here

- V2 scoring and comparability contract: `docs/evaluation_workflow_v2.md`
- New agent onboarding (YAML-only path): `docs/new_agent_onboarding.md`
- Continue runtime setup: `docs/continue_setup.md`

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
