# Agent CLEAR Framework Evaluation Report

Generated: 2026-03-10 02:32:13

## Executive Summary

This report presents comprehensive evaluation results for the `continue-cn` runtime using the Multi-Dimensional CLEAR Framework.

### 🎯 Overall Performance

| Metric | Value | Assessment |
|--------|-------|------------|
| **Success Rate** | 4/4 (100.0%) | Overall task completion |
| **Average CLEAR Score** | 0.960/1.000 | Main comparable score alias |
| **Average V2 Main Score** | 0.960/1.000 | Comparable dimensions only |
| **Average V2 Run Mean** | 0.827/1.000 | Mean of per-run main scores |
| **Average V2 Diagnostic Score** | 0.795/1.000 | Diagnostic dimensions only |
| **Average Score Coverage** | 1.000 | Main-dimension observability coverage |
| **Average Cost per Task** | $0.032 USD | Estimated cost snapshot |
| **Average Task Time** | 17.0 seconds | Execution speed |
| **Average Steps** | 5.2 steps | Task efficiency |
| **Average Accuracy** | 0.875/1.000 | Output quality |
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
- **Average cost per task**: $0.032 USD
- **Strict comparability**: Cost is advisory only in this run set

### ⚡ Latency Dimension  
- **Task completion speed**: 17.0 seconds average
- **User experience**: Excellent

### 📈 Efficiency Dimension
- **Average steps to completion**: 5.2 steps
- **Average tool selection accuracy**: 0.625/1.000
- **Resource attribution**: Estimated from timeline/resource snapshots

### ✅ Assurance Dimension
- **Task completion accuracy**: 0.875/1.000
- **Checker-backed outcomes**: All evaluated tasks passed checker-backed outcome validation
- **Average reasoning coherence**: 0.750/1.000

### 🛠️ Reliability Dimension
- **Threshold-gated pass rate**: 4/4
- **Average error recovery effectiveness**: 0.373/1.000
- **Repeat-run protocol**: 3.0 runs per task

---

## 📋 Detailed Test Results

| Test Case | Category | Main V2 | Run Mean | Diag V2 | Coverage | Cost | Time | Steps | Core Cmp | Full Cmp | Provisional | Status |
|-----------|----------|---------|----------|---------|----------|------|------|-------|----------|----------|-------------|--------|
| simple_file_operations | file_operations | 0.960 | 0.827 | 0.751 | 1.00 | $0.032 | 10.8s | 5 | COMPARABLE | COMPARABLE | no | ✅ PASS |
| python_coding_task | coding | 0.960 | 0.827 | 0.809 | 1.00 | $0.032 | 10.9s | 5 | COMPARABLE | COMPARABLE | no | ✅ PASS |
| data_analysis_task | analysis | 0.960 | 0.827 | 0.812 | 1.00 | $0.032 | 30.0s | 5 | COMPARABLE | COMPARABLE | no | ✅ PASS |
| error_handling_test | reasoning | 0.961 | 0.829 | 0.807 | 1.00 | $0.033 | 16.2s | 6 | COMPARABLE | COMPARABLE | no | ✅ PASS |

---

## ⏱️ Execution Time Breakdown

> Time is partitioned into three phases using timeline-weighted analysis
> (method: `multi_run_mean_no_llm_events`).
> If no LLM events are detected in a runtime trace, LLM time is reported as `n/a` (unknown).
> For repeated runs, phase means use a consistent run subset per task. If a phase is
> observed in only part of the run set, this section uses that observed subset rather
> than mixing incompatible averages.

### Aggregate (across all tasks)

| Phase | Avg Time (s) | Avg % of Total |
|-------|-------------|----------------|
| 🧠 LLM Inference | n/a | n/a |
| 🔧 Tool Execution | 6.32s | 37.2% |
| 🔄 Coordination | 10.69s | 62.8% |
| **Total** | **17.00s** | **100%** |

### Per-Task Breakdown

| Test Case | LLM (s) | LLM % | Tool (s) | Tool % | Coord (s) | Coord % | Total (s) |
|-----------|---------|-------|----------|--------|-----------|---------|-----------|
| simple_file_operations | n/a | n/a | 3.50 | 32.3% | 7.35 | 67.7% | 10.85 |
| python_coding_task | n/a | n/a | 4.30 | 39.3% | 6.64 | 60.7% | 10.94 |
| data_analysis_task | n/a | n/a | 9.69 | 32.3% | 20.34 | 67.7% | 30.02 |
| error_handling_test | n/a | n/a | 7.79 | 48.1% | 8.42 | 51.9% | 16.21 |

---

## 🔍 Per-Step Resource Attribution

Resource usage (CPU %, Memory MB) is estimated by interpolating each timeline event's
position in the log against wall-clock timestamps captured by the resource monitor.

### simple_file_operations (file_operations)

| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |
|---|------------|-----------------|-------|-------------|
| 1 | error | 0.25 | 2.3 | 3.7 |
| 2 | error | 0.78 | 2.6 | 190.1 |
| 3 | error | 0.80 | 2.6 | 190.1 |
| 4 | error | 0.89 | 3.3 | 269.2 |
| 5 | error | 2.35 | 0.6 | 304.0 |
| 6 | error | 2.35 | 0.6 | 304.0 |
| 7 | error | 2.38 | 0.6 | 304.0 |
| 8 | tool_call | 2.39 | 0.6 | 304.0 |
| 9 | error | 2.39 | 0.6 | 304.0 |
| 10 | tool_call | 2.66 | 0.6 | 304.0 |
| 11 | error | 2.91 | 0.3 | 305.5 |
| 12 | error | 3.11 | 0.3 | 305.5 |
| 13 | error | 3.67 | 0.6 | 312.8 |
| 14 | error | 3.70 | 0.6 | 312.8 |
| 15 | error | 3.78 | 0.6 | 312.8 |
| 16 | tool_call | 6.07 | 0.4 | 318.6 |
| 17 | tool_call | 6.11 | 0.4 | 318.6 |
| 18 | tool_call | 6.49 | 0.0 | 318.6 |
| 19 | error | 7.25 | 0.1 | 319.0 |
| 20 | error | 7.27 | 0.1 | 319.0 |
| 21 | error | 7.36 | 0.1 | 319.0 |
| 22 | error | 9.46 | 0.9 | 211.1 |
| 23 | error | 9.49 | 0.9 | 211.1 |
| 24 | error | 9.57 | 0.9 | 211.1 |

### python_coding_task (coding)

| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |
|---|------------|-----------------|-------|-------------|
| 1 | error | 0.06 | 2.3 | 2.9 |
| 2 | error | 0.07 | 2.3 | 2.9 |
| 3 | error | 0.13 | 2.3 | 2.9 |
| 4 | error | 0.34 | 2.5 | 184.9 |
| 5 | error | 0.87 | 3.2 | 264.0 |
| 6 | error | 0.90 | 3.2 | 264.0 |
| 7 | error | 0.98 | 3.2 | 264.0 |
| 8 | error | 2.47 | 0.1 | 304.4 |
| 9 | error | 2.47 | 0.1 | 304.4 |
| 10 | error | 2.50 | 0.1 | 304.4 |
| 11 | tool_call | 2.51 | 0.1 | 304.4 |
| 12 | error | 2.51 | 0.1 | 304.4 |
| 13 | success | 2.52 | 0.1 | 304.4 |
| 14 | success | 2.53 | 0.1 | 304.4 |
| 15 | tool_call | 2.78 | 0.1 | 304.4 |
| 16 | success | 2.80 | 0.1 | 304.4 |
| 17 | success | 2.80 | 0.1 | 304.4 |
| 18 | success | 2.82 | 0.6 | 308.1 |
| 19 | error | 3.04 | 0.6 | 308.1 |
| 20 | error | 3.24 | 0.6 | 308.1 |
| 21 | error | 3.81 | 0.2 | 312.8 |
| 22 | error | 3.84 | 0.1 | 313.2 |
| 23 | error | 3.92 | 0.1 | 313.2 |
| 24 | tool_call | 6.24 | 0.5 | 317.2 |
| 25 | tool_call | 6.29 | 0.5 | 317.2 |
| 26 | success | 6.29 | 0.5 | 317.2 |
| 27 | success | 6.31 | 0.5 | 317.2 |
| 28 | success | 6.32 | 0.5 | 317.2 |
| 29 | success | 6.34 | 0.5 | 317.2 |
| 30 | tool_call | 6.67 | 0.0 | 317.4 |
| 31 | success | 6.68 | 0.0 | 317.4 |
| 32 | success | 6.69 | 0.0 | 317.4 |
| 33 | success | 6.71 | 0.0 | 317.4 |
| 34 | error | 7.44 | 0.2 | 318.5 |
| 35 | error | 7.46 | 0.2 | 318.5 |
| 36 | error | 7.55 | 0.2 | 318.5 |
| 37 | error | 9.68 | 1.1 | 281.5 |
| 38 | error | 9.71 | 1.1 | 281.5 |
| 39 | error | 9.79 | 1.1 | 281.5 |
| 40 | error | 10.43 | 0.1 | 282.1 |

### data_analysis_task (analysis)

| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |
|---|------------|-----------------|-------|-------------|
| 1 | error | 0.57 | 2.5 | 181.4 |
| 2 | error | 1.77 | 1.9 | 283.6 |
| 3 | error | 1.83 | 0.8 | 302.1 |
| 4 | error | 2.02 | 0.8 | 302.1 |
| 5 | error | 5.35 | 0.0 | 311.7 |
| 6 | error | 5.37 | 0.0 | 311.7 |
| 7 | error | 5.42 | 0.0 | 311.7 |
| 8 | tool_call | 5.44 | 0.0 | 311.7 |
| 9 | error | 5.44 | 0.0 | 311.7 |
| 10 | tool_call | 6.05 | 0.0 | 311.9 |
| 11 | error | 6.64 | 0.4 | 312.4 |
| 12 | error | 7.10 | 0.6 | 315.7 |
| 13 | error | 8.37 | 0.4 | 318.5 |
| 14 | error | 8.43 | 0.4 | 318.5 |
| 15 | error | 8.62 | 0.4 | 318.5 |
| 16 | tool_call | 13.83 | 0.0 | 281.5 |
| 17 | tool_call | 13.93 | 0.0 | 281.5 |
| 18 | tool_call | 14.78 | 0.0 | 281.5 |
| 19 | error | 16.52 | 0.0 | 281.6 |
| 20 | error | 16.57 | 0.0 | 281.6 |
| 21 | error | 16.76 | 0.0 | 281.6 |
| 22 | error | 21.56 | 0.0 | 282.6 |
| 23 | error | 21.61 | 0.0 | 282.6 |
| 24 | error | 21.80 | 0.0 | 282.6 |

### error_handling_test (reasoning)

| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |
|---|------------|-----------------|-------|-------------|
| 1 | error | 0.05 | 2.2 | 2.9 |
| 2 | error | 0.09 | 2.2 | 2.9 |
| 3 | error | 0.23 | 2.2 | 2.9 |
| 4 | error | 0.24 | 2.2 | 2.9 |
| 5 | error | 0.62 | 2.5 | 208.8 |
| 6 | error | 1.46 | 1.9 | 310.4 |
| 7 | error | 1.50 | 1.9 | 310.4 |
| 8 | error | 1.63 | 1.9 | 310.4 |
| 9 | error | 3.97 | 0.2 | 325.8 |
| 10 | error | 3.98 | 0.2 | 325.8 |
| 11 | error | 4.02 | 0.2 | 325.8 |
| 12 | tool_call | 4.04 | 0.2 | 325.8 |
| 13 | error | 4.04 | 0.2 | 325.8 |
| 14 | success | 4.05 | 0.2 | 325.8 |
| 15 | success | 4.08 | 0.2 | 325.8 |
| 16 | tool_call | 4.47 | 0.3 | 327.9 |
| 17 | success | 4.49 | 0.3 | 327.9 |
| 18 | success | 4.51 | 0.3 | 327.9 |
| 19 | success | 4.53 | 0.3 | 327.9 |
| 20 | error | 4.88 | 0.2 | 329.0 |
| 21 | error | 5.20 | 0.2 | 329.0 |
| 22 | error | 6.10 | 0.3 | 329.3 |
| 23 | error | 6.14 | 0.3 | 329.3 |
| 24 | error | 6.27 | 0.3 | 329.3 |
| 25 | tool_call | 9.93 | 0.0 | 254.7 |
| 26 | tool_call | 10.00 | 0.0 | 254.7 |
| 27 | success | 10.01 | 0.0 | 254.7 |
| 28 | success | 10.04 | 0.0 | 254.7 |
| 29 | success | 10.05 | 0.0 | 254.7 |
| 30 | success | 10.08 | 0.0 | 254.7 |
| 31 | tool_call | 10.60 | 0.8 | 254.1 |
| 32 | success | 10.63 | 0.8 | 254.1 |
| 33 | success | 10.64 | 0.8 | 254.1 |
| 34 | success | 10.67 | 0.8 | 254.1 |
| 35 | error | 11.82 | 0.5 | 258.9 |
| 36 | error | 11.86 | 0.5 | 258.9 |
| 37 | error | 11.99 | 0.1 | 242.8 |
| 38 | error | 15.36 | 0.0 | 207.1 |
| 39 | error | 15.40 | 0.0 | 207.1 |
| 40 | error | 15.54 | 0.0 | 207.1 |



---

## 💡 Key Insights & Recommendations

### 🔥 Most Critical Issues:
- **(4x)** 🔄 Improve error recovery - better adaptation to failures
- **(3x)** 🔧 Improve tool selection - accuracy 0.67
- **(1x)** 🔧 Improve tool selection - accuracy 0.50


### ✅ System Strengths:
- ✅ All evaluated tasks passed threshold gates
- ✅ Checker-backed outcome validation passed on all evaluated tasks
- ✅ Full comparability observed on all evaluated tasks
- ✅ Fast execution times on the evaluated suite

### ⚠️ Areas for Improvement:
- 🔄 Improve error recovery - better adaptation to failures
- 🔧 Improve tool selection - accuracy 0.67
- 🔧 Improve tool selection - accuracy 0.50

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
*Evaluation Path: /Users/Raymond/.local/bin/cn*
