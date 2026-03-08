# New Agent Onboarding (YAML-Only)

Goal: add a new agent without writing Python adapter/registry code.

You only edit `config/config.yaml`, then run scripts with `--agent <name-or-alias>`.

If the agent uses org-level credits (for example Continue), set the org slug in adapter `extra_args` so teammates share the same billing workspace.

## Quick Start

1. Add a new `agents.<your-agent>` profile in `config/config.yaml` (template below).
2. Run:

```bash
python run_single_test.py --agent <your-agent>
python integrated_mini_agent_evaluation.py --agent <your-agent>
python enhanced_comprehensive_evaluation.py --agent <your-agent>
python mini_agent_clear_evaluation_system.py --agent <your-agent>
```

3. Check agent-specific result directories.

## Step 1: Runtime Requirements

Your CLI runtime must:

- accept task/prompt input,
- run non-interactively,
- produce deterministic exit codes,
- print useful stdout/stderr.

## Step 2: Understand Placeholder Contract

`generic-cli` supports these placeholders:

- `{workspace}`
- `{task_prompt}`
- `{timeout_seconds}`

They can be used in:

- `adapter.command`
- `adapter.cwd`
- `adapter.env` values
- `adapter.extra_args`

## Step 3: Copy This YAML Template

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

## Step 4: Minimum Required Fields

- `agents.<name>.adapter.type: generic-cli`
- `agents.<name>.adapter.command` (recommended) or equivalent executable definition

## Step 5: Recommended Fields

- `aliases` for shorter CLI usage
- `scripts.*.results_dir` to isolate outputs per agent
- `process_name_hint` for better process metric binding in phase2/phase3
- `extra_args` for default org/model/runtime flags shared by all scripts

Continue example (workspace credit via org slug):

```yaml
adapter:
  type: continue-cn
  config_path: continuedev/default-cli-config
  extra_args: [--org, zhiruis-workspace-2, --auto]
```

## Step 6: Validate in Order

From `agentic_sys/`:

### 6.1 Smoke

```bash
python run_single_test.py --agent my-agent
```

### 6.2 Phase1

```bash
python integrated_mini_agent_evaluation.py --agent my-agent
```

### 6.3 Phase2

```bash
python enhanced_comprehensive_evaluation.py --agent my-agent
```

### 6.4 Phase3

```bash
python mini_agent_clear_evaluation_system.py --agent my-agent
```

Alias also works:

```bash
python run_single_test.py --agent my
```

## Step 7: Override Adapter Fields from CLI (Optional)

No YAML edits needed for temporary changes:

```bash
python run_single_test.py \
  --agent my-agent \
  --adapter-option 'extra_args=["--verbose"]' \
  --adapter-option 'env={"MY_FLAG":"1"}'
```

## Common Patterns

### Workspace-aware CLI (recommended)

```yaml
adapter:
  type: generic-cli
  command: [my-agent, --workspace, "{workspace}", --task, "{task_prompt}"]
  cwd: "{workspace}"
  success_codes: [0]
```

### Prompt-only CLI

```yaml
adapter:
  type: generic-cli
  command: [my-agent, -p, "{task_prompt}"]
  cwd: "{workspace}"
  success_codes: [0]
```

### Multiple success codes

```yaml
adapter:
  type: generic-cli
  command: [my-agent, "{task_prompt}"]
  success_codes: [0, 2]
```

## Troubleshooting

- `Unsupported placeholder ...`
  - Use only `{workspace}`, `{task_prompt}`, `{timeout_seconds}`.
- `Unsupported agent ...`
  - Ensure profile exists and `--agent` matches name/alias.
- `Execution error: [Errno 2] ...`
  - Executable not found; use absolute path in `command[0]`.
- Phase3 metrics look coarse
  - Runtime lacks structured step/tool traces; system uses fair coarse attribution mode.

## Adapter Types

- `mini-agent`
- `continue-cn`
- `generic-cli`

For most new runtimes, start with `generic-cli`.
Only add custom Python adapter if your runtime cannot be expressed as a CLI command template.

## Team Checklist

1. Profile added in `config/config.yaml`.
2. Smoke test completed.
3. Phase1/2/3 completed.
4. Agent-specific result directories confirmed.
5. Required secrets/env documented outside repo.
