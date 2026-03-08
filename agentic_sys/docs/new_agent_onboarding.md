# New Agent Onboarding (Step-by-Step)

This guide shows teammates how to add a new agent to this repo.
Goal: only edit `config/config.yaml`, no Python adapter code.

## 1) Before you start

Your agent CLI must support non-interactive runs:
- accepts task/prompt input,
- exits with stable return code,
- prints useful stdout/stderr.

## 2) Open project

```bash
cd agentic_sys
```

## 3) Add a new profile in `config/config.yaml`

Copy this template and replace names/command:

```yaml
agents:
  my-agent:
    aliases: [my, my-cli]
    scripts:
      phase1:
        results_dir: artifacts/my-agent/phase1
      phase2:
        results_dir: artifacts/my-agent/phase2
      phase3:
        results_dir: artifacts/my-agent/phase3
      run_single_test:
        results_dir: artifacts/my-agent/phase3/single_test
    adapter:
      type: generic-cli
      agent_id: my-agent
      process_name_hint: my-agent
      command:
        - my-agent
        - --workspace
        - "{workspace}"
        - --task
        - "{task_prompt}"
      extra_args: []
      env: {}
      cwd: "{workspace}"
      success_codes: [0]
```

## 4) Required fields

These must exist:
- `adapter.type: generic-cli`
- `adapter.command`

## 5) Useful optional fields

- `aliases`: short names for `--agent`
- `scripts.*.results_dir`: separate outputs by agent
- `process_name_hint`: better process monitoring in phase2/phase3
- `success_codes`: include all success return codes your CLI uses

## 6) Supported placeholders

You can use these in `command`, `cwd`, `env`, `extra_args`:
- `{workspace}`
- `{task_prompt}`
- `{timeout_seconds}`

## 7) Validate the new agent

Run in this order:

```bash
python run_single_test.py --agent my-agent
python integrated_agent_evaluation.py --agent my-agent
python enhanced_comprehensive_evaluation.py --agent my-agent
python clear_evaluation_system.py --agent my-agent
```

Alias example:

```bash
python run_single_test.py --agent my
```

## 8) Temporary overrides without editing YAML

```bash
python run_single_test.py \
  --agent my-agent \
  --adapter-option 'extra_args=["--verbose"]' \
  --adapter-option 'env={"MY_FLAG":"1"}'
```

## 9) Continue-specific example

If onboarding Continue in team workspace mode:

```yaml
adapter:
  type: continue-cn
  config_path: continuedev/default-cli-config
  model_slugs: [anthropic/claude-haiku-4-5]
  extra_args: [--org, zhiruis-workspace-2, --auto]
```

If using API key mode, teammate also sets:

```bash
export CONTINUE_API_KEY="<ORG_SCOPED_KEY>"
```

## 10) Troubleshooting

- `Unsupported agent ...`
  - profile name/alias does not match `--agent`.
- `Execution error: [Errno 2] ...`
  - command executable not found.
- `Unsupported placeholder ...`
  - only `{workspace}`, `{task_prompt}`, `{timeout_seconds}` are valid.
- Phase3 metrics look coarse
  - runtime has no structured trace; phase3 uses coarse attribution mode.

## 11) Team handoff checklist

1. Profile added in `config/config.yaml`.
2. Smoke test passed (`run_single_test.py`).
3. Phase1/Phase2/Phase3 run end-to-end.
4. Output directories are agent-specific.
5. Required secrets are documented and shared securely.
