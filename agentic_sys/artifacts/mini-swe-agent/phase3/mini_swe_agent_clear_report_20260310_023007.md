# Agent CLEAR Framework Evaluation Report

Generated: 2026-03-10 02:38:45

## Executive Summary

This report presents comprehensive evaluation results for the `mini-swe-agent` runtime using the Multi-Dimensional CLEAR Framework.

### 🎯 Overall Performance

| Metric | Value | Assessment |
|--------|-------|------------|
| **Success Rate** | 4/4 (100.0%) | Overall task completion |
| **Average CLEAR Score** | 1.000/1.000 | Main comparable score alias |
| **Average V2 Main Score** | 1.000/1.000 | Comparable dimensions only |
| **Average V2 Run Mean** | 1.000/1.000 | Mean of per-run main scores |
| **Average V2 Diagnostic Score** | 0.901/1.000 | Diagnostic dimensions only |
| **Average Score Coverage** | 1.000 | Main-dimension observability coverage |
| **Average Cost per Task** | $0.008 USD | Estimated cost snapshot |
| **Average Task Time** | 42.9 seconds | Execution speed |
| **Average Steps** | 4.0 steps | Task efficiency |
| **Average Accuracy** | 1.000/1.000 | Output quality |
| **Core Comparable Tasks** | 4/4 | Outcome-focused strict comparability |
| **Full Comparable Tasks** | 4/4 | Process + trace strict comparability |
| **Main Leaderboard Eligible** | 4/4 | Core comparable + non-provisional |
| **Full Leaderboard Eligible** | 4/4 | Full comparable + non-provisional |
| **Provisional Tasks** | 0/4 | Evidence coverage below threshold |
| **Average Runs per Task** | 3.0 | Multi-run robustness protocol |

---

## 📊 CLEAR Dimension Analysis

### 💰 Cost Dimension
- **Cost basis**: Estimated from token/call heuristics
- **Average cost per task**: $0.008 USD
- **Strict comparability**: Cost is advisory only in this run set

### ⚡ Latency Dimension  
- **Task completion speed**: 42.9 seconds average
- **User experience**: Good

### 📈 Efficiency Dimension
- **Average steps to completion**: 4.0 steps
- **Average tool selection accuracy**: 0.750/1.000
- **Resource attribution**: Estimated from timeline/resource snapshots

### ✅ Assurance Dimension
- **Task completion accuracy**: 1.000/1.000
- **Checker-backed outcomes**: All evaluated tasks passed checker-backed outcome validation
- **Average reasoning coherence**: 0.800/1.000

### 🛠️ Reliability Dimension
- **Threshold-gated pass rate**: 4/4
- **Average error recovery effectiveness**: 1.000/1.000
- **Repeat-run protocol**: 3.0 runs per task

---

## 📋 Detailed Test Results

| Test Case | Category | Main V2 | Run Mean | Diag V2 | Coverage | Cost | Time | Steps | Core Cmp | Full Cmp | Provisional | Status |
|-----------|----------|---------|----------|---------|----------|------|------|-------|----------|----------|-------------|--------|
| simple_file_operations | file_operations | 1.000 | 1.000 | 1.000 | 1.00 | $0.006 | 17.7s | 3 | COMPARABLE | COMPARABLE | no | ✅ PASS |
| python_coding_task | coding | 1.000 | 1.000 | 0.989 | 1.00 | $0.012 | 47.8s | 6 | COMPARABLE | COMPARABLE | no | ✅ PASS |
| data_analysis_task | analysis | 1.000 | 1.000 | 0.823 | 1.00 | $0.007 | 55.0s | 3 | COMPARABLE | COMPARABLE | no | ✅ PASS |
| error_handling_test | reasoning | 1.000 | 1.000 | 0.791 | 1.00 | $0.008 | 51.1s | 4 | COMPARABLE | COMPARABLE | no | ✅ PASS |

---

## ⏱️ Execution Time Breakdown

> Time is partitioned into three phases using timeline-weighted analysis
> (method: `multi_run_mean`).
> If no LLM events are detected in a runtime trace, LLM time is reported as `n/a` (unknown).
> For repeated runs, phase means use a consistent run subset per task. If a phase is
> observed in only part of the run set, this section uses that observed subset rather
> than mixing incompatible averages.

### Aggregate (across all tasks)

| Phase | Avg Time (s) | Avg % of Total |
|-------|-------------|----------------|
| 🧠 LLM Inference | 29.50s | 65.0% |
| 🔧 Tool Execution | 12.12s | 26.7% |
| 🔄 Coordination | 3.77s | 8.3% |
| **Total** | **45.38s** | **100%** |

### Per-Task Breakdown

| Test Case | LLM (s) | LLM % | Tool (s) | Tool % | Coord (s) | Coord % | Total (s) |
|-----------|---------|-------|----------|--------|-----------|---------|-----------|
| simple_file_operations | 11.82 | 66.7% | 3.94 | 22.2% | 1.97 | 11.1% | 17.74 |
| python_coding_task | 33.98 | 71.2% | 11.37 | 23.8% | 2.40 | 5.0% | 47.75 |
| data_analysis_task | 38.41 | 69.9% | 11.48 | 20.9% | 5.08 | 9.2% | 54.96 |
| error_handling_test | 33.79 | 55.3% | 21.67 | 35.5% | 5.63 | 9.2% | 61.09 |

Observed-subset notes:

- `error_handling_test`: LLM phase observed in 2/3 runs; phase means in the table below use the observed subset to stay self-consistent.

---

## 🔍 Per-Step Resource Attribution

Resource usage (CPU %, Memory MB) is estimated by interpolating each timeline event's
position in the log against wall-clock timestamps captured by the resource monitor.

### simple_file_operations (file_operations)

| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |
|---|------------|-----------------|-------|-------------|
| 1 | thinking | 2.88 | 0.0 | 172.9 |
| 2 | assistant_response | 4.32 | 0.0 | 172.9 |
| 3 | tool_call | 8.65 | 0.0 | 172.6 |
| 4 | tool_call | 17.29 | 1.2 | 176.7 |

### python_coding_task (coding)

| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |
|---|------------|-----------------|-------|-------------|
| 1 | tool_call | 2.68 | 1.9 | 172.8 |
| 2 | thinking | 10.70 | 0.0 | 173.1 |
| 3 | assistant_response | 12.04 | 0.0 | 173.1 |
| 4 | tool_call | 13.38 | 0.4 | 175.0 |
| 5 | thinking | 21.41 | 0.0 | 175.0 |
| 6 | assistant_response | 22.75 | 0.0 | 175.0 |
| 7 | tool_call | 24.09 | 0.1 | 173.3 |
| 8 | tool_call | 32.11 | 0.3 | 149.8 |

### data_analysis_task (analysis)

| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |
|---|------------|-----------------|-------|-------------|
| 1 | thinking | 9.18 | 0.0 | 172.9 |
| 2 | assistant_response | 13.77 | 0.0 | 172.9 |
| 3 | tool_call | 27.53 | 0.0 | 172.6 |
| 4 | tool_call | 55.07 | 1.4 | 151.8 |

### error_handling_test (reasoning)

| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |
|---|------------|-----------------|-------|-------------|
| 1 | thinking | 3.76 | 0.0 | 174.0 |
| 2 | assistant_response | 5.64 | 0.0 | 139.8 |
| 3 | tool_call | 11.28 | 0.0 | 139.8 |
| 4 | tool_call | 22.56 | 0.0 | 139.8 |
| 5 | tool_call | 33.84 | 0.0 | 142.7 |
| 6 | tool_call | 45.11 | 0.0 | 142.7 |
| 7 | tool_call | 56.39 | 0.0 | 143.0 |
| 8 | tool_call | 67.67 | 0.0 | 143.0 |



---

## 💡 Key Insights & Recommendations

### 🔥 Most Critical Issues:
- **(1x)** 🔧 Improve tool selection - accuracy 0.44
- **(1x)** 🔧 Improve tool selection - accuracy 0.56


### ✅ System Strengths:
- ✅ All evaluated tasks passed threshold gates
- ✅ Checker-backed outcome validation passed on all evaluated tasks
- ✅ Full comparability observed on all evaluated tasks

### ⚠️ Areas for Improvement:
- 🔧 Improve tool selection - accuracy 0.44
- 🔧 Improve tool selection - accuracy 0.56

### 📝 Reporting Caveats:
- **(4x)** 💲 Cost is estimated (not provider-reported) and excluded from strict scoring
- **(4x)** 📉 Unknown dimensions: cost_efficiency, token_efficiency

---

## 🚀 Production Readiness

### Ready for Deployment: ⚠️ READY WITH CAVEATS

### Next Steps:
1. Validate on a broader task suite before treating this as production-ready
2. Fix the highest-frequency actionable issues in the report
3. Treat cost conclusions as advisory until provider-reported cost is available
4. Establish deployment SLAs using checker-backed pass rate and comparability fields

Production-readiness status is advisory for the evaluated task suite only. It is
not a substitute for larger-scale staging, security review, or workload-specific validation.

---

*Report generated by Agent CLEAR Framework Evaluation System*
*Evaluation Path: mini*
