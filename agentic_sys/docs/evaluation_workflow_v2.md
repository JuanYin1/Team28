# V2 Evaluation Workflow (Capability-Driven)

This is the scoring/comparability contract for `clear_evaluation_system.py`.

## 1) Core Principles

- No agent-ID scoring branches. Runtime differences must come from:
  - declared config (`evaluation_capabilities`, parser profile),
  - optional probe profile,
  - observed run evidence.
- `unknown` is `null`: excluded from weighted totals, not rewarded or penalized.
- Two score spaces:
  - `overall_v2_score`: main comparable score.
  - `overall_v2_diagnostic_score`: diagnostic-only score.
- Comparability fields are mandatory in outputs:
  - `status`, `core_status`, `full_status`
  - `reasons`, `core_reasons`, `full_reasons`
  - `required_signal_status`, `dimension_status`, `score_coverage`

## 2) Main vs Full Comparability

- `core_status=COMPARABLE` is based on configured core dimensions/signals.
- `full_status=COMPARABLE` requires core + full trace/process signals.
- A full-required signal is valid only when both are true:
  1. supported by resolved capability,
  2. observed in the run.
- Regex hits alone must not upgrade unsupported capability to full comparable.

## 3) Capability Resolution

Per run, evaluator uses:
- `declared_capabilities` (from YAML),
- `probed_capabilities` (optional profile),
- `resolved_capabilities` (effective capabilities).

Resolution rules:
- With probe profile: `resolved = declared AND probed` (conservative).
- If profile has only legacy `resolved_capabilities`, use it as fallback.
- If profile exists but all `probe_results.success=false`, profile is treated as unusable and evaluator falls back to declared YAML capabilities.

## 4) Probe Lifecycle (Phase3)

Profile is generated only when probe is triggered:
- `--refresh-capability-profile`
- `--probe-agent`
- `--probe-only`
- or `evaluation.v2.capability_probe.enabled: true` in config.

Flag behavior:
- `--refresh-capability-profile`: probe, then evaluate.
- `--probe-agent`: probe, then evaluate (same behavior as refresh).
- `--probe-only`: probe and exit.

Profile path:
- `config/artifacts/capability_profiles/<agent>.json`
- Profile includes:
  - `profile_metadata.auto_generated=true`
  - `profile_metadata.do_not_edit_manually=true`
  - `generated_at_utc`

## 5) Gates and Pass/Fail

- Gate-based pass uses:
  - `safety_gate == pass`
  - `critical_function_gate == pass`
  - `oracle_gate != fail`
- Repeated-run threshold is exact `>= 2/3` pass rate.

## 6) Checker and Evidence

- `outcome` should prefer checker-grounded evidence when checker runs.
- Checker expectations are per expected item (not a loose single aggregate text threshold).
- Evidence tier can be reported without being directly added into total score.

## 7) Time Breakdown Interpretation

- `llm_inference_s` may be `null` when no LLM event signal is observed.
- `null` means unknown/unobserved, not zero inference time.
- Cross-runtime latency comparisons should use wall-clock task time first.

## 8) Required Result Fields

Each task JSON must include:
- `overall_v2_score`
- `overall_v2_diagnostic_score`
- `v2_dimension_scores`
- `v2_diagnostic_dimension_scores`
- `v2_dimension_details`
- `unknown_dimensions`
- `score_coverage`
- `comparability`
- `evidence_quality`
- `gate_status`
- `repeat_stats`
- `time_breakdown`

## 9) Minimum Regression Gate

Before merge:

```bash
python -m unittest discover -s tests
```
