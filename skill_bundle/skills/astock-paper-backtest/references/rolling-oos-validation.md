# 滚动样本外 (Rolling OOS) 检验算法与衰减评估

## 1. 为什么必须执行样本外检验？

量化策略研发中最常见的致命缺陷是**数据窥探偏差 (Data Snooping Bias)** 和**过度参数优化 (Overfitting)**。在样本内（In-Sample, IS）表现惊艳的策略，往往在实盘中迅速失效。

为此，系统内建滚动样本外（Rolling Out-of-Sample）检验引擎，对所有选股与择时模型进行真实时序推演。

---

## 2. 滚动步进窗口机制 (Walk-Forward Analysis)

```mermaid
gantt
    title 滚动样本外 (Rolling OOS) 步进窗口划分
    dateFormat  YYYY-MM
    section 窗口 1
    样本内训练 (IS: 180天)   :a1, 2025-01, 2025-06
    样本外检验 (OOS: 60天)    :after a1, 2025-08
    section 窗口 2
    样本内训练 (IS: 180天)   :a2, 2025-03, 2025-08
    样本外检验 (OOS: 60天)    :after a2, 2025-10
    section 窗口 3
    样本内训练 (IS: 180天)   :a3, 2025-05, 2025-10
    样本外检验 (OOS: 60天)    :after a3, 2025-12
```

1. **时序隔离**：IS 窗口与 OOS 窗口严格按时间顺序排列，禁止任何未来数据泄露；
2. **多期步进**：按固定步长（如 60 交易日）向前滑动，在多个连续且不重叠的 OOS 窗口上测试策略表现；
3. **衰减度计算**：
   $$\text{夏普衰减率 } = \frac{\text{Sharpe}_{IS} - \text{Sharpe}_{OOS}}{\text{Sharpe}_{IS}}$$
   $$\text{年化衰减率 } = \frac{\text{Return}_{IS} - \text{Return}_{OOS}}{\text{Return}_{IS}}$$
