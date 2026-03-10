# New Agent Onboarding (YAML-Only)

Goal: add a new runtime without changing evaluator scoring code.

## 1) What You Change

From `agentic_sys/`, edit only `config/config.yaml`
(repo-root path: `agentic_sys/config/config.yaml`):
- `agents.<agent>.adapter`
- `agents.<agent>.evaluation_capabilities`
- `agents.<agent>.evaluation_trace_parser` (required for strong trace comparability)
- `agents.<agent>.scripts.*.results_dir`

## 2) Runtime Requirements

Your CLI should support:
- non-interactive task execution,
- stable exit code,
- readable stdout/stderr,
- optional trace log file output.

## 3) Capability Strategy (Conservative)

Start conservative and promote only after evidence is stable:
1. `tool_trace`
2. `step_trace`
3. `timeline_events`
4. `session_stats` / `token_usage`
5. `provider_cost` only when runtime returns provider-reported cost (not estimation)

`full_status=COMPARABLE` requires both capability support and observed trace signals.

## 4) Parser Strategy

For evolving toolsets:
- keep `tool_aliases` for canonical mapping,
- set `enforce_known_tools: false` to avoid dropping unseen tool names.

## 5) Probe/Profile Workflow

```bash
python clear_evaluation_system.py --agent <agent> --refresh-capability-profile
python clear_evaluation_system.py --agent <agent>
```

Notes:
- `--probe-agent` has same behavior as `--refresh-capability-profile`.
- `--probe-only` only refreshes profile and exits.
- If a profile exists but all probe runs failed, evaluator ignores that profile and falls back to declared YAML capabilities.
- Profiles are written under `config/artifacts/capability_profiles/<agent>.json`.

## 6) Comparability Checklist

Before claiming cross-agent fairness:
- `core_status` should be comparable on all core tasks.
- `full_status` should be comparable on tasks where you claim process-level fairness.
- inspect `required_signal_status` for missing full signals.

## 7) Common Debug Cases

- `Full Comparable = 0/N`:
  - missing capability declaration,
  - or signals not observed,
  - or stale profile not refreshed.
- config changed but result unchanged:
  - rerun with `--refresh-capability-profile`.
- probe succeeds slowly/noisy:
  - use `--probe-only` first to isolate profile refresh.

## 8) Validation

```bash
python -m unittest discover -s tests
```
