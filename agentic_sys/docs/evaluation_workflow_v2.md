# V2 评估 Workflow（配置驱动）

本文档描述当前 `refactor` 分支下，V2 评估体系的端到端流程。目标是：
- 跨数据集/跨 agent 可比
- 主分不依赖单一 heuristic
- 可追溯、可审计、可复现

## 1. 入口与配置

评估默认从 `agentic_sys/config/config.yaml` 读取，不需要新增 CLI 参数。

关键配置块：

```yaml
evaluation:
  shared:
    scoring_version: v2
    runs_per_task: 3
    include_runtime_extension_suite: false
    minimum_high_supervision_coverage: 0.40
    main_leaderboard_core_suite_only: true
  v2:
    evidence_quality:
      include_in_total_score: false
      provisional_if_below_high_supervision_coverage: 0.40
    comparability:
      hard_requirements:
        checker_must_run: true
    normalization:
      mode: task_family_baseline
      baseline_by_task_type: ...
    gate_caps:
      safety: 0.20
      critical: 0.45
      oracle: 0.60
```

说明：
- `EvidenceQuality` 只作为可信度与准入信息，不进入总分。
- `include_runtime_extension_suite: false` 时默认只跑 core comparable suite。
- `runs_per_task` 控制每题重复运行次数（用于稳健性统计）。

## 2. 运行方式

在 `agentic_sys/` 下执行：

```bash
python clear_evaluation_system.py --agent mini-agent
python clear_evaluation_system.py --agent continue
```

运行时会同时加载：
- runtime 配置（`resolve_script_runtime_options`）
- evaluation 配置（`resolve_evaluation_settings`）

## 3. 单题评估流程（Phase3）

`evaluate_agent_test()` 的主要步骤：

1. 执行任务并采集 stdout/stderr  
2. 解析日志轨迹（steps/tool_call/errors/timeline）  
3. 计算基础 CLEAR 指标（cost/latency/efficiency/assurance/reliability）  
4. 计算 V2 五维：
   - `outcome`：高监督优先（oracle/exact > soft > llm_judge > heuristic）
   - `process`：轨迹质量（工具命中、重试/循环、恢复、步数纪律等）
   - `efficiency`：相对 task-family baseline 的时延/成本/步数/内存
   - `robustness`：单次默认走稳定性代理，多次运行时用方差与通过率
   - `safety`：策略/错误密度/执行成功率
5. 应用 gate（safety/critical/oracle）对总分封顶  
6. 计算 comparability（`COMPARABLE/SOFT_NON_COMPARABLE/HARD_NON_COMPARABLE`）  
7. 标记 `is_provisional`（高监督覆盖率低于阈值）

## 4. 多次运行聚合（runs_per_task）

`run_comprehensive_evaluation()` 会对每个 test case 跑 `runs_per_task` 次，并聚合：
- `overall_v2_mean/std/ci95`
- `pass_rate`
- 聚合后的 `v2_dimension_scores`
- 聚合 gate/comparability/evidence_quality

输出字段：`repeat_stats`。

## 4.1 分数解释风险（必须知晓）

在当前实现里，聚合后的 `performance.overall_v2_score` 可能高于（或低于）`repeat_stats.overall_v2_mean`，两者不保证相等。

原因：
- `overall_v2_mean` 是各次 run 的 `overall_v2_score` 直接均值。
- 聚合阶段会基于 `pass_rate/std` 重新计算 `robustness` 维度，再用五维权重重新合成最终 `overall_v2_score`。
- 因为“先均值后重算维度”与“每次先算总分再均值”不是同一个运算，所以可能出现数值差异。

解读建议：
- 报告稳定性时优先看 `repeat_stats.overall_v2_mean/std/ci95`。
- 排名与门控判断看 `performance.overall_v2_score`（聚合后的主分）。
- 对外发布时应同时展示这两个值，避免“均值与总分不一致”带来的误读。

## 5. 主榜资格判定

主榜资格由以下条件共同决定：
- `comparability.status == COMPARABLE`
- `is_provisional == false`
- 若开启 `main_leaderboard_core_suite_only`，则题目必须 `core_comparable == true`

注意：`passed_all_thresholds` 与 comparability 解耦，comparability 影响的是“是否可横向严格比较/是否入主榜”。

## 6. 产物与字段

每个 case 会生成 JSON（`phase3.v3`），核心字段：
- `performance.overall_v2_score`
- `performance.v2_dimension_scores`
- `evidence_quality`
- `comparability`
- `gate_status`
- `repeat_stats`
- `time_breakdown`
- `step_resource_profiles`

同时生成汇总 Markdown 报告，包含：
- 通过率、平均分、成本、时延、步骤
- comparable/provisional/main-eligible 统计
- 每题详细表格和时间分解

## 7. 测试保障

单测覆盖包括：
- 配置解析（runtime + evaluation）
- V2 评分关键逻辑（trajectory process、outcome 监督优先、repeat 聚合）
- 结果落盘 schema 与关键字段
- phase3 回归与全量测试

建议回归命令：

```bash
python -m unittest discover -s agentic_sys/tests
```
