# Continue CLI Setup and Team Repro Guide

This guide explains how to install Continue CLI (`cn`), verify it end to end, and run phase1/2/3 evaluation scripts with the `continue` agent profile.

All commands below assume you are inside `agentic_sys/` unless explicitly stated.

## 1. Prerequisites

- Node.js and npm are installed.
- Python environment for this repo is ready.
- Internet access is available for Continue login/model calls.

## 2. Install Continue CLI

```bash
npm i -g @continuedev/cli
```

Verify:

```bash
which cn
cn --version
```

If `cn` is not found, add your user bin to `PATH` and reopen shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## 3. Authenticate Continue

Recommended:

```bash
cn login
```

Complete the browser device-code flow.

Notes:
- If your team will use Continue credits later, login still needs to succeed now.
- If you use your own provider config, you can skip credits but still need valid model/provider credentials.

## 4. Quick Health Check (Real Request)

Run a direct probe first:

```bash
cn -p "Reply with exactly OK and nothing else." --auto
```

Then run project health check:

```bash
python verify_continue_setup.py --extra-arg=--auto
```

Optional JSON output:

```bash
python verify_continue_setup.py --extra-arg=--auto --json
```

Expected:
- `Success: True` and non-empty `stdout`, or
- `Diagnosis: account_credits_exhausted` if account is valid but out of credits.

`account_credits_exhausted` still confirms binary/auth/request path wiring is correct.

## 5. Continue Profile in config.yaml

The default Continue profile is in `config/config.yaml`:

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
      extra_args: []
```

## 6. Run Evaluation Scripts with Continue

Single smoke test:

```bash
python run_single_test.py --agent continue
```

Phase1:

```bash
python integrated_mini_agent_evaluation.py --agent continue
```

Phase2:

```bash
python enhanced_comprehensive_evaluation.py --agent continue
```

Phase3:

```bash
python mini_agent_clear_evaluation_system.py --agent continue
```

If using a non-default config file:

```bash
python run_single_test.py --agent continue --agent-config /path/to/config.yaml
```

## 7. Optional Continue Overrides (All Scripts)

All evaluation scripts accept these Continue-specific flags:

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
  --continue-model openai/gpt-4.1-mini \
  --continue-extra-arg --auto
```

## 8. Live Continue Unit Test

This test sends a real request and is disabled by default.

```bash
RUN_CONTINUE_LIVE_TESTS=1 \
CONTINUE_CN_EXTRA_ARGS="--auto" \
python -m unittest tests/test_continue_healthcheck.py
```

Optional env vars:
- `CONTINUE_CN_EXECUTABLE`
- `CONTINUE_CN_AGENT`
- `CONTINUE_CN_CONFIG`
- `CONTINUE_CN_MODELS` (comma-separated)
- `CONTINUE_CN_ALLOW` (comma-separated)
- `CONTINUE_CN_SMOKE_PROMPT`
- `CONTINUE_CN_TIMEOUT`

## 9. Troubleshooting Matrix

- Symptom: `cn: command not found`
  - Fix: reinstall CLI, ensure npm global bin in `PATH`, restart shell.

- Symptom: `interceptors did not return an alternative response`
  - Cause: runtime reachable, but no working model/auth path.
  - Fix: run `cn login`, or provide valid `--continue-config` + provider credentials.

- Symptom: `fetch failed`
  - Cause: network/proxy/firewall connectivity issue.
  - Fix: verify outbound access and retry.

- Symptom: `Response returned an error code`
  - Cause: provider/model/org misconfiguration or upstream rejection.
  - Fix: verify API keys, model slug, org selection, quota.

- Symptom: `no credits remaining`
  - Cause: Continue account credits exhausted.
  - Fix: top up credits or switch to self-managed provider config.

## 10. What to Share with Teammates

For reproducibility, share:
- the exact `config/config.yaml` profile used,
- the exact command line used (`--agent`, overrides),
- healthcheck output (`diagnosis`, `command`, `return_code`),
- output directory (`phase1_continue`, `phase2_continue`, `phase3_continue`, etc.).
