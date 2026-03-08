# New Agent Onboarding Guide (YAML-Only)

You can onboard a new agent without writing adapter code or editing registry code.
Add a profile in `config/config.yaml`, then run scripts with `--agent <name-or-alias>`.

## 1. Preconditions

Your agent must support non-interactive execution from CLI.

At minimum, the command should:
- accept a prompt/task text,
- exit with a stable return code,
- print useful output to stdout/stderr,
- run without manual UI interaction.

## 2. Runtime Contract Used by Pipeline

For `generic-cli`, the pipeline builds command/env/cwd from templates.

Supported placeholders:
- `{workspace}`
- `{task_prompt}`
- `{timeout_seconds}`

They can be used in:
- `adapter.command` (list of tokens)
- `adapter.cwd`
- `adapter.env` values
- `adapter.extra_args`

## 3. Add a New Agent Profile in config.yaml

```yaml
agents:
  my-agent:
    aliases: [my, my-cli]
    scripts:
      phase1:
        results_dir: phase1_my_agent
      phase2:
        results_dir: phase2_my_agent
      phase3:
        results_dir: phase3_my_agent
      run_single_test:
        results_dir: phase3_my_agent_single
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

### Required fields

- `agents.<name>.adapter.type: generic-cli`
- `agents.<name>.adapter.command` (or `executable`, but `command` is recommended)

### Recommended fields

- `aliases` for short CLI names
- `scripts.*.results_dir` to separate outputs by agent
- `process_name_hint` for better process monitoring in phase2/phase3

## 4. Minimal Validation Flow

From `agentic_sys/`:

1. Smoke test:

```bash
python run_single_test.py --agent my-agent
```

2. Phase1:

```bash
python integrated_mini_agent_evaluation.py --agent my-agent
```

3. Phase2:

```bash
python enhanced_comprehensive_evaluation.py --agent my-agent
```

4. Phase3:

```bash
python mini_agent_clear_evaluation_system.py --agent my-agent
```

You can also use alias:

```bash
python run_single_test.py --agent my
```

## 5. Optional Overrides Without Editing YAML

Use repeatable `--adapter-option KEY=VALUE` (YAML parsed value):

```bash
python run_single_test.py \
  --agent my-agent \
  --adapter-option 'extra_args=["--verbose"]' \
  --adapter-option 'env={"MY_FLAG":"1"}'
```

## 6. Common Profile Patterns

### A) Workspace-aware agent (recommended)

```yaml
adapter:
  type: generic-cli
  command: [my-agent, --workspace, "{workspace}", --task, "{task_prompt}"]
  cwd: "{workspace}"
  success_codes: [0]
```

### B) Prompt-only CLI agent

```yaml
adapter:
  type: generic-cli
  command: [my-agent, -p, "{task_prompt}"]
  cwd: "{workspace}"
  success_codes: [0]
```

### C) Non-zero success code agent

```yaml
adapter:
  type: generic-cli
  command: [my-agent, "{task_prompt}"]
  success_codes: [0, 2]
```

## 7. Troubleshooting

- Error: `Unsupported placeholder ...`
  - Fix: only use `{workspace}`, `{task_prompt}`, `{timeout_seconds}`.

- Error: `Unsupported agent ...`
  - Fix: ensure `agents.<name>` exists and `--agent` matches name or alias.

- Error: `Execution error: [Errno 2] ...`
  - Fix: executable not found in `PATH`; use full binary path in `command[0]`.

- Agent runs but phase3 step/tool metrics look coarse
  - Cause: runtime logs are not structured like step/tool traces.
  - Result: phase3 uses coarse attribution mode for fairness.

## 8. Built-In Adapter Types

- `mini-agent`
- `continue-cn`
- `generic-cli`

For new agents, use `generic-cli` first.  
Only add custom Python adapter when your runtime is not expressible as a CLI command template (for example, direct SDK/API-only flow with complex streaming protocol).

## 9. Team Onboarding Checklist

- [ ] profile added to `config/config.yaml`
- [ ] smoke test (`run_single_test.py`) passes or produces expected failure mode
- [ ] phase1/2/3 run end to end
- [ ] output directories are agent-specific and documented
- [ ] any required env vars/secrets documented outside repo
