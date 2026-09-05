# 架构决策与历史审计归档 (Architecture Decision Records & Historical Audits)

本目录遵循 **不可变架构决策记录 (ADR) 范式**，集中归档 A-Stock Agents 演进历程中的阶段性差距分析、回测引擎逐行审计报告与模型重构日志。

> **提示**：本目录文档属于历史追溯资产。现役系统的操作指南与避坑铁律请直接参阅上级目录的活文档（Living Documentation，如 `morning-auction-review-sop.md`、`trade-history-audit-workflow.md`）。

---

## 历史审计与决策索引 (ADR Index)

| 编号 | 日期 | 文档名 | 核心议题与决策成果 |
|:---|:---|:---|:---|
| **ADR-20260731-01** | 2026-07-31 | [`ADR-20260731-quant-strategy-gap-analysis.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/skills/astock-knowledge-tips/references/archive/ADR-20260731-quant-strategy-gap-analysis.md) | 量化策略模块差距分析：系统梳理多因子打分、均值回归、网格等 6 大模块的实现空缺 |
| **ADR-20260731-02** | 2026-07-31 | [`ADR-20260731-quant-strategy-modules-impl.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/skills/astock-knowledge-tips/references/archive/ADR-20260731-quant-strategy-modules-impl.md) | 量化策略模块补全实施记录：补全回测与指标计算基础依赖 |
| **ADR-20260731-03** | 2026-07-31 | [`ADR-20260731-backtest-engine-audit.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/skills/astock-knowledge-tips/references/archive/ADR-20260731-backtest-engine-audit.md) | 回测引擎逐行审查报告：成本模型修正、撮合状态机与前视偏差（Look-ahead Bias）排查 |
| **ADR-20260812-01** | 2026-08-12 | [`ADR-20260812-multi-dim-model-v2-design.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/skills/astock-knowledge-tips/references/archive/ADR-20260812-multi-dim-model-v2-design.md) | 多维选股模型 v2 设计：五维共振评分、权重分配与初始风控规则 |
| **ADR-20260812-02** | 2026-08-12 | [`ADR-20260812-multi-dim-model-v3-design.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/skills/astock-knowledge-tips/references/archive/ADR-20260812-multi-dim-model-v3-design.md) | 多维共振旋转引擎 v3 设计：双层门控（上证>MA20 + 健康度）与多股旋转机制融合 |
| **ADR-20260813-01** | 2026-08-13 | [`ADR-20260813-v31-audit-fixes.md`](file:///c:/Users/cvdnn/coding/a_stock_agents/skills/astock-knowledge-tips/references/archive/ADR-20260813-v31-audit-fixes.md) | 选股引擎系统审查 8 项缺陷修复日志：恢复堆量特征、强化样本外（OOS）衰减检验 |
