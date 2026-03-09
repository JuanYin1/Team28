# V2 Evaluation Workflow (Capability-Driven, Config-First)

This document is the implementation contract for `evaluation v2`.
Code changes must follow this document directly. Scoring/comparability behavior must not rely on hidden runtime branches.

## 1) Hard Rules

### 1.1 Unknown Semantics
- `unknown` is represented as `null`.
- `null` does not add score and does not subtract score.
- Weighted totals are re-normalized over observed dimensions only.
- Output must include `unknown_dimensions`.

### 1.2 Two Score Spaces
- `overall_v2_score`: main leaderboard score, from `comparable_dimensions`.
- `overall_v2_diagnostic_score`: diagnostic score, from `diagnostic_dimensions`.

### 1.3 Comparability Output Is Required
- `comparability.status`
- `comparability.core_status`
- `comparability.full_status`
- `comparability.reasons/core_reasons/full_reasons`
- `comparability.dimension_status`
- `comparability.required_signal_status`
- `score_coverage`

### 1.4 No Agent-ID Scoring Branches
Scoring must not branch on:
- `agent_id`
- runtime name
- adapter class

Differences must come from:
1. declared config (`evaluation_capabilities` / parser profile),
2. optional probe profile,
3. observed runtime evidence.

## 2) Config Field Reference (`config/config.yaml`)

This section explains every V2 scoring-related field and what it means.

### 2.1 `evaluation.shared`

| Field | Meaning |
|---|---|
| `scoring_version` | Scoring pipeline selector, should be `v2`. |
| `runs_per_task` | Number of repeated runs per task for robustness stats. |
| `include_runtime_extension_suite` | Whether to include runtime-specific extension tasks (for example skills tasks). |
| `minimum_high_supervision_coverage` | Coverage threshold used by provisional logic. |
| `main_leaderboard_core_suite_only` | If `true`, only core suite tasks are eligible for leaderboard outputs. |

### 2.2 `evaluation.v2`

#### 2.2.1 Evidence and Provisional
| Field | Meaning |
|---|---|
| `evidence_quality.include_in_total_score` | Whether evidence tier score is included directly in totals (normally `false`). |
| `evidence_quality.provisional_if_below_high_supervision_coverage` | Mark run as provisional when high-supervision coverage is below this value. |

#### 2.2.2 Dimension Sets
| Field | Meaning |
|---|---|
| `comparable_dimensions` | Main leaderboard dimensions. |
| `diagnostic_dimensions` | Diagnostics-only dimensions. |

Default comparable dimensions:
- `outcome`: checker-grounded completion quality.
- `safety`: policy/error-density/success stability.
- `robustness`: repeatability across runs.
- `basic_efficiency`: wall-clock efficiency against task baseline.

Default diagnostic dimensions:
- `process`: retry discipline / loop avoidance / precondition handling.
- `tool_efficiency`: expected tool selection quality.
- `cost_efficiency`: cost against task-family baseline.
- `token_efficiency`: token usage against task-family baseline.
- `trace_quality`: quality/completeness of structured runtime signals.

#### 2.2.3 Required Signals for Main Comparability
| Field | Meaning |
|---|---|
| `required_signals_for_comparable` | Per-dimension required signals that must be present for core comparability. |

Common signals:
- `checker_executed`
- `repeated_runs`
- `wall_clock_time`
- `structured_trace`
- `tool_trace`
- `step_trace`
- `timeline_events`
- `session_stats`
- `provider_cost`
- `token_usage`

#### 2.2.4 Weights
| Field | Meaning |
|---|---|
| `dimension_weights_main` | Weights for `comparable_dimensions`. |
| `dimension_weights_diagnostic` | Weights for `diagnostic_dimensions`. |

#### 2.2.5 Full Comparability
| Field | Meaning |
|---|---|
| `full_comparability.required_signals` | Extra signals required for `full_status=COMPARABLE`. |
| `full_comparability.required_dimensions` | Dimensions that must be supported and observed for full comparability. |

#### 2.2.6 Comparability Gate
| Field | Meaning |
|---|---|
| `comparability.hard_requirements.checker_must_run` | If `true`, checker absence is hard non-comparable. |
| `comparability.minimum_score_coverage_for_comparable` | Minimum observed-weight coverage for comparable status. |

#### 2.2.7 Capability Probe
| Field | Meaning |
|---|---|
| `capability_probe.enabled` | Enable automatic probe path. |
| `capability_probe.auto_refresh` | Refresh profile even when profile already exists. |
| `capability_probe.profile_dir` | Output directory of capability profiles. |

#### 2.2.8 Baseline Normalization
| Field | Meaning |
|---|---|
| `normalization.mode` | Baseline scoring mode (default `task_family_baseline`). |
| `normalization.baseline_by_task_type.<type>.latency_seconds` | Baseline latency for ratio scoring. |
| `normalization.baseline_by_task_type.<type>.cost_usd` | Baseline cost for ratio scoring. |
| `normalization.baseline_by_task_type.<type>.steps` | Baseline step count for ratio scoring. |
| `normalization.baseline_by_task_type.<type>.memory_mb` | Baseline memory usage for ratio scoring. |

#### 2.2.9 Gate Caps
| Field | Meaning |
|---|---|
| `gate_caps.safety` | Max total score cap when safety gate fails. |
| `gate_caps.critical` | Max total score cap when critical function gate fails. |
| `gate_caps.oracle` | Max total score cap when oracle gate fails. |

### 2.3 `agents.<agent_key>` (Onboarding Surface)

#### 2.3.1 Scripts
| Field | Meaning |
|---|---|
| `scripts.<phase>.results_dir` | Output directory per script/phase. |

#### 2.3.2 Adapter (Runtime Integration)
Common:
- `adapter.type`: `mini-agent` / `continue-cn` / `generic-cli`
- `adapter.transport`: `pipe` or `pty`
- `adapter.trace_log_paths`: optional supplemental log file paths/globs
- `adapter.trace_log_tail_lines` / `adapter.trace_log_max_bytes`: ingestion caps

Continue-specific:
- `executable`, `agent_name`, `config_path`, `model_slugs`, `allow_policies`, `extra_args`

Generic CLI:
- `agent_id`, `process_name_hint`, `command`, `extra_args`, `env`, `cwd`, `success_codes`

#### 2.3.3 Capabilities (Declares What Is Measurable)
| Field | Meaning |
|---|---|
| `evaluation_capabilities.structured_trace` | Runtime can provide structured process trace. |
| `evaluation_capabilities.tool_trace` | Tool calls are observable. |
| `evaluation_capabilities.step_trace` | Step progression is observable. |
| `evaluation_capabilities.timeline_events` | Timeline event stream is observable. |
| `evaluation_capabilities.session_stats` | Session counters are observable. |
| `evaluation_capabilities.provider_cost` | Provider-reported cost is available (not estimated). |
| `evaluation_capabilities.token_usage` | Token usage is available from runtime/session stats. |
| `evaluation_capabilities.skills_runtime` | Runtime supports skills extension suite. |
| `evaluation_capabilities.checker_support.*` | Checker-side evidence channels available for this runtime. |

#### 2.3.4 Trace Parser Profile
Defines runtime-specific regex extraction:
- `tool_call_patterns`
- `step_patterns`
- `thinking_patterns`
- `assistant_patterns`
- `error_patterns`
- `tool_result_patterns`
- `log_file_patterns`
- `detailed_log_tool_patterns`
- `tool_aliases`
- `session_stats_pattern`
- `session_duration_pattern`
- `enforce_known_tools`

## 3) Capability Resolution

For each run, evaluator consumes:
- `declared_capabilities` from YAML
- optional probe profile (`probed_capabilities`)
- `resolved_capabilities` (conservative effective capabilities)

When probe is present, effective capabilities must not be optimistic.

## 4) Per-Task Data Flow

1. Execute runtime task and capture stdout/stderr/exit.
2. Ingest supplemental trace logs (if configured).
3. Parse runtime signals (tools/steps/timeline/session stats).
4. Run checker and sub-checkers (agent-agnostic).
5. Build per-dimension detail:
   - `score`
   - `supported`
   - `observed`
   - `evidence_sources`
   - `missing_reasons`
6. Compute:
   - `overall_v2_score`
   - `overall_v2_diagnostic_score`
   - `unknown_dimensions`
   - `score_coverage`
7. Apply gates and comparability classification.

## 5) Comparability Semantics

- `core_status=COMPARABLE` requires all configured core conditions.
- `full_status=COMPARABLE` requires core plus full-comparability conditions.
- `SOFT_NON_COMPARABLE`: non-fatal missing coverage/signals.
- `HARD_NON_COMPARABLE`: hard requirement violated.

High score without comparability is allowed in diagnostics but must not be treated as strict leaderboard superiority.

## 6) Required Per-Result Fields

Each saved JSON must include:
- `performance.overall_v2_score`
- `performance.overall_v2_diagnostic_score`
- `performance.v2_dimension_scores`
- `performance.v2_diagnostic_dimension_scores`
- `performance.v2_dimension_details`
- `performance.unknown_dimensions`
- `performance.score_coverage`
- `comparability`
- `evidence_quality`
- `gate_status`
- `repeat_stats`

## 7) Regression Expectations

Tests must lock:
- no agent-id scoring branches,
- unknown-as-null behavior,
- strict comparability gating,
- checker-gated high supervision tiering,
- config-only onboarding path,
- stable trace ingestion path for non-stdout runtimes.
