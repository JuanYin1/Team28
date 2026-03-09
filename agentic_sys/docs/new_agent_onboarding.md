# New Agent Onboarding (YAML-Only, Comparable by Design)

This guide answers two questions:
1. New agent接入到底要改什么？
2. 怎么保证接入后在 V2 里可比、鲁棒、且不侵入核心评测逻辑？

## 1) Minimum Goal

For normal onboarding, only edit `config/config.yaml`:
- `agents.<new_agent>.adapter`
- `agents.<new_agent>.evaluation_capabilities`
- `agents.<new_agent>.evaluation_trace_parser` (recommended for full comparability)
- `agents.<new_agent>.scripts.*.results_dir`

No evaluator scoring code changes should be required.

## 2) Runtime Preconditions

Your CLI must support non-interactive execution:
- accepts task input from command args
- deterministic exit codes
- readable stdout/stderr
- optional: structured logs in file/console for tool/step/timeline extraction

## 3) YAML Template (Copy/Paste)

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
      transport: pipe
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
      trace_log_paths: []
      trace_log_tail_lines: 800
      trace_log_max_bytes: 512000

    evaluation_capabilities:
      structured_trace: false
      tool_trace: false
      step_trace: false
      timeline_events: false
      session_stats: false
      provider_cost: false
      token_usage: false
      skills_runtime: false
      checker_support:
        file_artifacts: true
        stdout_capture: true
        exit_code: true
        behavior_validation: true

    evaluation_trace_parser:
      tool_call_patterns:
        - "\"tool(?:Name|_name)\"\\s*:\\s*\"([a-zA-Z_][a-zA-Z0-9_\\-]*)\""
      step_patterns:
        - "(?:\\bStep\\s+(\\d+)\\b|\"step\"\\s*:\\s*(\\d+))"
      log_file_patterns:
        - "(?i)log file:\\s*(.+\\.log)"
```

## 4) Fields You Must Understand

### 4.1 `adapter`
- `type`:
  - `generic-cli`: preferred for new agents.
  - `continue-cn`/`mini-agent`: built-in adapters.
- `transport`:
  - `pipe`: default.
  - `pty`: use when CLI only emits rich trace in TTY mode.
- `trace_log_paths`:
  - supplemental logs (e.g. `~/.continue/logs/cn.log`) injected into evaluator parsing path.

### 4.2 `evaluation_capabilities`
Declares expected observability. This affects which dimensions can be supported/observed.
Important: full comparability requires both capability support and observed runtime signals.
Regex hits in logs cannot substitute for missing capability declarations.

### 4.3 `evaluation_trace_parser`
Regex extractor for runtime-specific logs.
If parser quality is weak, full comparability usually drops even if task outcomes pass.

## 5) Continue Workflow (Headless + `cn.log`)

Recommended config shape:

```yaml
adapter:
  type: continue-cn
  transport: pty
  trace_log_paths: [~/.continue/logs/cn.log]
  trace_log_tail_lines: 1200
  config_path: continuedev/default-cli-config
  model_slugs: [anthropic/claude-haiku-4-5]
  extra_args: [--verbose, --org, <org>, --auto]
```

Why:
- headless output can be sparse;
- `cn.log` often contains tool/timeline/session internals needed for process scoring.

## 6) Comparability Checklist (Before Claiming Fair Comparison)

Run outputs must show:
- `Core Comparable Tasks = 4/4` for core suite
- `Full Comparable Tasks = 4/4` if you claim full process comparability
- `Main/Full Leaderboard Eligible` aligned with above
- `unknown_dimensions` understood and acceptable

If only core comparable is satisfied, only claim outcome-level fairness.

## 7) Validation Commands

```bash
python run_single_test.py --agent my-agent
python integrated_agent_evaluation.py --agent my-agent
python enhanced_comprehensive_evaluation.py --agent my-agent
python clear_evaluation_system.py --agent my-agent
```

Optional probe flow:

```bash
python clear_evaluation_system.py --agent my-agent --probe-agent
python clear_evaluation_system.py --agent my-agent --probe-only
```

If `artifacts/capability_profiles/<agent>.json` already exists, phase3 will load it by default.

## 8) Debugging Quick Map

- `Unsupported agent ...`
  - alias/profile mismatch in YAML.
- `Execution error: [Errno 2] ...`
  - executable not found.
- `Full Comparable = 0/N`
  - parser/capability signals missing, not necessarily outcome failure.
- high score but wrong comparability interpretation
  - check `comparability.core_status/full_status` instead of only `overall_v2_score`.

## 9) Unit Test Gate (Required)

```bash
python -m unittest discover -s tests
```

This is mandatory before merge for config-only onboarding claims.
