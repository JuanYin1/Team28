# Multi-Agent Refactor Plan

## Goals
- Decouple evaluation pipeline from Mini-Agent specific runtime assumptions.
- Keep scoring logic and reports stable while execution/runtime becomes pluggable.
- Ensure each module is independently testable and edge-case resilient.

## Scope
- Phase1 (`integrated_mini_agent_evaluation.py`) execution path.
- Phase2 (`enhanced_comprehensive_evaluation.py`) execution + monitor attachment.
- Phase3 (`mini_agent_clear_evaluation_system.py`) execution path for CLEAR pipeline.
- New shared runtime abstraction layer under `agent_runtime/`.

## Target Architecture
- `agent_runtime/models.py`
  - Normalized request/result models for execution and trace.
- `agent_runtime/adapters.py`
  - `AgentAdapter` interface.
  - `MiniAgentAdapter` implementation.
- `agent_runtime/parsers.py`
  - `TraceParser` interface.
  - `MiniAgentTraceParser` implementation.
- `agent_runtime/runner.py`
  - `AgentPipelineRunner` orchestrator (adapter + optional parser).

## Migration Strategy
1. Introduce new runtime modules without modifying scoring rules.
2. Inject adapter into existing evaluators with defaults preserving behavior.
3. Route subprocess execution through adapter in all three phases.
4. Add unit tests for module-level correctness and cross-module collaboration.
5. Keep existing JSON/report schemas intact.

## Non-Goals (This Iteration)
- Rewriting CLEAR scoring formulas.
- Changing benchmark prompts or expected outputs.
- Introducing framework-heavy dependency injection.

## Risks and Mitigation
- Runtime behavior drift:
  - Mitigation: preserve command/timeout semantics and keep previous tests green.
- Parser overfitting:
  - Mitigation: parser is isolated and covered by focused tests.
- Over-engineering:
  - Mitigation: simple interfaces and small modules only.

## Completion Criteria
- Phase1/2/3 execution paths use adapter abstraction.
- New runtime modules have direct unit tests.
- Existing tests remain green.
- Edge cases covered: timeout, missing binary, parser failure, unknown tool names.

## Current Status (Refactor Branch)
- Phase1 complete: adapter-based runtime + schema-safe outputs + tests.
- Phase2 complete: adapter runtime + monitor PID binding + tests.
- Phase3 complete for pluggable runtime:
  - accepts external adapter without forcing mini-agent path detection.
  - script-level `--agent` selection wired.
  - CLEAR output schema remains stable.
- Continue CLI adapter integrated:
  - `ContinueCnAdapter` added.
  - shared adapter factory + script flags added (`--continue-config`, `--continue-model` included).
  - healthcheck utility added for real-request validation.
  - unit tests cover Continue command construction, timeout/error paths, factory behavior, and optional live request smoke.
