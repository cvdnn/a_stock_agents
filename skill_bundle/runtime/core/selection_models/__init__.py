# -*- coding: utf-8 -*-
"""智能选股系统（ISS）核心引擎包（批次一 / M-02）。

本包为 SSOT `SPEC-ALGO-ISS-001` §19 规划的 `scripts/core/selection_models/` 落地起点：

- `schemas`：v2 定义 Schema 与 v1 → v2 内存迁移器（A1）
- `hash`：规范化 JSON + SHA-256（`definition_hash` / `plan_hash`，A2）
- `rule_registry`：规则参数 Schema 与 UI 注解（A7）
- `model_type_registry`：模型类型注册中心（A5）
- `model_compiler`：统一层级中间结构 `CompiledSelectionPlan` 编译器（A4）
- `definition_repository` / `version_repository` / `file_lock`：草稿、悲观锁与版本仓库（A6）
- `orchestrator`：按依赖执行整条层级漏斗（`run-all`，A8）
- `paths`：落盘目录规范唯一派生点（B6 / §13.10）
- `run_lock`：运行锁，粒度 `model_id + trade_date`（B2 / O-02）
- `run_repository`：当日可恢复状态、运行元数据、候选/信号落盘与淘汰（B4/B6 / O-04）
- `signal_latch`：`converge_at_window_end` 窗口收敛锁存（B3 / §10.5）
- `scheduler`：Scheduler Tick / daemon + `TradeCalendar` 门控（B1 / O-01）
- `market_view`：阶段 E 行情视图与统计基元（Bar 归一、涨跌停、MFE/MAE、未来数据检测、T+N）
- `position_policy`：可回测建仓与持股策略 `PositionPolicy`（E2 / §12.3）
- `backtest_service`：信号标记分析与事件驱动策略回测（E2 / §12.2）
- `result_assessment`：结果个股研究评估 `ResultAssessment`（E1 / §12.1）
- `tracking_service` / `tracker_scheduler`：`TrackingPlan`/`TrackingObservation` 与 Tracker Tick（E3 / §12.4）
- `model_evaluator`：模型综合评估 `ModelEvaluation`（E4 / §12.5）
- `optimization_advisor`：只读优化建议 `OptimizationSuggestion`（E5 / §12.6）

层级漏斗执行内核仍为 `core.strategy.funnel_engine`（就地升级为受限 AND/OR/NOT AST，A3）。
数据装配与覆盖率门禁由 `core.data.data_assembler` 提供（B5 / R-03 / A-05）。
"""