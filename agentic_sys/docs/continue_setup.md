# Continue CLI Setup and Repro Runbook

This runbook is for teammates who need to set up `cn` and run all evaluation phases with `--agent continue`.

Default workspace for this repo: `zhiruis-workspace-2` (configured in `config/config.yaml`).

## Quick Start (5 Minutes)

From `agentic_sys/`:

```bash
npm i -g @continuedev/cli
which cn
cn --version
cn login
cn -p "Reply with exactly OK and nothing else." --auto
python verify_continue_setup.py --extra-arg=--auto
python run_single_test.py --agent continue
```

If all commands above succeed (or healthcheck returns `account_credits_exhausted`), your wiring is correct.
If you use repo defaults, commands run against workspace `zhiruis-workspace-2`.

## Step 1: Preconditions

- Node.js + npm installed.
- Python environment for this repo is available.
- Internet access is available (login + model request).

## Step 2: Install CLI

```bash
npm i -g @continuedev/cli
which cn
cn --version
```

If `cn` is not found:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then reopen shell and re-run `which cn`.

## Step 3: Login

```bash
cn login
```

Complete the browser flow.

## Step 4: Verify End-to-End Request Path

### 4.1 Direct probe

```bash
cn -p "Reply with exactly OK and nothing else." --auto
```

### 4.2 Project healthcheck

```bash
python verify_continue_setup.py --extra-arg=--auto
```

Optional JSON output:

```bash
python verify_continue_setup.py --extra-arg=--auto --json
```

Interpretation:
- `Success: True`: all good.
- `Diagnosis: account_credits_exhausted`: wiring/auth path is still correct; only billing/quota blocks real completions.

## Step 5: Confirm Continue Profile in YAML

Config file: `config/config.yaml`

Expected profile shape:

```yaml
agents:
  continue:
    aliases: [continue-cn, cn]
    scripts:
      phase1:
        results_dir: phase1_continue
      phase2:
        results_dir: phase2_continue
      phase3:
        results_dir: phase3_continue
      run_single_test:
        results_dir: phase3_continue_single
    adapter:
      type: continue-cn
      config_path: continuedev/default-cli-config
      model_slugs: []
      allow_policies: []
      extra_args: [--org, zhiruis-workspace-2, --auto]
```

## Step 6: Run Phase 1/2/3

All commands from `agentic_sys/`.

### Smoke test

```bash
python run_single_test.py --agent continue
```

### Phase1

```bash
python integrated_mini_agent_evaluation.py --agent continue
```

### Phase2

```bash
python enhanced_comprehensive_evaluation.py --agent continue
```

### Phase3

```bash
python mini_agent_clear_evaluation_system.py --agent continue
```

## Step 7: Optional Runtime Overrides (No YAML edits)

All scripts support Continue override flags:

- `--continue-agent-name <owner/agent>`
- `--continue-config <path-or-hub-slug>`
- `--continue-model <owner/model>` (repeatable)
- `--continue-allow <tool>` (repeatable)
- `--continue-extra-arg <arg>` (repeatable)

Example:

```bash
python run_single_test.py \
  --agent continue \
  --continue-config continuedev/default-cli-config \
  --continue-model openai/gpt-4.1-mini
```

If you need to temporarily switch workspace from the default:

```bash
python run_single_test.py \
  --agent continue \
  --continue-extra-arg=--org \
  --continue-extra-arg=<other-org-slug>
```

## Step 8: Optional Live Unit Test

Runs a real request and is disabled by default.

```bash
RUN_CONTINUE_LIVE_TESTS=1 \
CONTINUE_CN_EXTRA_ARGS="--auto" \
python -m unittest tests/test_continue_healthcheck.py
```

Optional env vars:
- `CONTINUE_CN_EXECUTABLE`
- `CONTINUE_CN_AGENT`
- `CONTINUE_CN_CONFIG`
- `CONTINUE_CN_MODELS`
- `CONTINUE_CN_ALLOW`
- `CONTINUE_CN_SMOKE_PROMPT`
- `CONTINUE_CN_TIMEOUT`

## Troubleshooting

- `cn: command not found`
  - Reinstall CLI and fix `PATH`.
- `interceptors did not return an alternative response`
  - Usually auth/model/config issue. Re-run `cn login` and verify config/model.
- `fetch failed`
  - Network/proxy/firewall issue.
- `Response returned an error code`
  - Provider/model/org/quota misconfiguration.
- `no credits remaining`
  - Account credit exhausted. Top up or use self-managed provider config.

## Team Repro Checklist

Share these 4 items for reproducibility:

1. The exact `config/config.yaml` profile.
2. The exact command line used.
3. Healthcheck output (`diagnosis`, `command`, `return_code`).
4. Output directories (`phase1_continue`, `phase2_continue`, `phase3_continue`).
5. Confirm teammate account is a member of workspace `zhiruis-workspace-2`.
