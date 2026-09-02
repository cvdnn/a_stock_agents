---
name: ashare-quant-engine
version: "1.0.0"
author: "ai_platform Quant Team"
description: A股工业级全流程量化工程引擎 — 截面量价因子(动量/反转/突破/波动率/筹码) + 非结构化舆情数值因子(半衰期衰减) + MAD去极值与Z-score截面Rank合成 + 目标波动率与分数凯利仓位管理 + A股T+1状态机与ATR阶梯止盈止损 + 摩擦成本事件驱动回测验证。
tags: [A股, 量化工程, 多因子, 截面排序, 舆情量化, 仓位管理, 目标波动率, T+1风控, 移动止损, 阶梯止盈, 事件驱动回测]
related_skills: [a-stocks, a-share-data, a-share-paper-trading, a-share-dashboard, ta-multi-agent-analysis, a-share-model-validation]
---

# ashare-quant-engine — A股全流程量化工程引擎

## 定位与核心价值

**ashare-quant-engine** 是专为 A股市场打造的工业级量化投研、选股与风控执行引擎。不同于传统的单股价格点预测或离散定性打分，本技能遵循量化对冲基金标准最佳实践：
1. **截面相对超额排序 (Cross-Sectional Rank Alpha)**：通过 MAD 去极值与 Z-Score 消除大盘涨跌噪声，专注捕捉个股相对收益。
2. **多模态因子数值化与半衰期衰减**：将财经公告/新闻转化为连续舆情因子（-1.0 ~ +1.0），并融合 3 日指数半衰期时间衰减。
3. **数学严谨的仓位管理**：自上而下目标波动率（年化 15% 动态缩放总仓位）+ 自下而上风险平价与 1/3 分数凯利分配单股头寸（100 股一手对齐，双创板/主板硬上限）。
4. **高保真 T+1 状态机与动态风控**：当日买入冻结约束、ATR 移动跟踪止损、盈利超 +5% 保本跳变锁定成本、阶梯分批止盈（+5% 减 1/3，+10% 再减 1/3）。
5. **零外部重依赖**：纯 Python 标准库实现，秒级完成全市场截面计算与历史逐日事件驱动回测。

---

## 架构与数据流

```
┌─────────────────────────────────────────────────────────────┐
│ 1. data_layer.py (行情接入与缓存)                            │
│    - 腾讯 L1 实时快照 + 前复权日K线直连                      │
│    - ST / 停牌过滤 + 健壮除权除息嵌套解析                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ 2. pv_factors.py             │   │ 3. unstructured_factors.py   │
│    量价 Alpha 因子 (15+维)    │   │    非结构化与舆情量化因子    │
│    - 动量/BIAS/MACD/RSI/KDJ  │   │    - 金融敏感词典多空打分    │
│    - 放量突破/VWAP/ATR/筹码  │   │    - 重大事件类型分类加权    │
└──────────────┬───────────────┘   │    - 3日指数半衰期时间衰减   │
               │                   └──────────────┬───────────────┘
               └──────────────────┬───────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. factor_synthesizer.py (截面标准化与多因子合成)            │
│    - MAD 中位数绝对偏差去极值 + Z-Score 标准化               │
│    - 方向对齐 + Percentile Rank 0~100 排序 + Top-K 选股      │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. risk_position_manager.py (风控与仓位中枢)                 │
│    - 目标波动率 (Volatility Targeting) 动态总仓位调节        │
│    - 风险平价 + 分数凯利单股头寸 (100股一手取整)             │
│    - A股 T+1 状态机 (当日冻结，次日解冻)                     │
│    - ATR 移动跟踪止损 + 保本跳变 (盈利超 +5% 锁成本价)       │
│    - 阶梯分批止盈 (+5% 减 1/3, +10% 减 1/3, 尾仓跟踪)       │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. backtest_engine.py / run_quant_pipeline.py               │
│    - 逐日事件驱动回测 (印花税0.05%, 佣金万2.5, 滑点0.1%)     │
│    - 输出: CAGR、MaxDD、Sharpe、Calmar、胜率、盈亏比         │
└─────────────────────────────────────────────────────────────┘
```

---

## 快速使用命令 (CLI)

所有脚本位于 `scripts/` 目录中，支持通过 Python 3 直接调用：

### 1. 股票池截面扫描与今日选股决策
```bash
py -3 scripts/run_quant_pipeline.py scan --top 4
```
**输出示例**：
```
代码       名称       现价(元)     综合Alpha    分位Rank    建议仓位       建议股数     ATR止损价     保本价       止盈目标(+5%)
---------------------------------------------------------------------------------------------------------
600519   贵州茅台     1307.88   0.457      100.0%     13.1%      100        1254.46    1311.80   1373.27
600760   中航沈飞     43.53     0.345      91.7%      14.8%      3400       41.35      43.66     45.71
000333   美的集团     84.72     0.330      83.3%      14.4%      1700       81.21      84.97     88.96
600036   招商银行     39.15     0.316      75.0%      14.9%      3800       37.84      39.27     41.11
```

### 2. 自定义股票池扫描
```bash
py -3 scripts/run_quant_pipeline.py scan --universe "600519,000858,300750,601318,688981" --top 3
```

### 3. 单股量化因子与风控诊断
```bash
py -3 scripts/run_quant_pipeline.py analyze 600519
```

### 4. 运行历史多标的事件驱动回测
```bash
py -3 scripts/run_quant_pipeline.py backtest --days 250 --top 4
```

### 5. 运行完整自动化测试套件
```bash
py -3 -m unittest scripts/test_quant_engine.py
```

---

## 模块代码与 API 参考

| 脚本文件 | 类名 | 主要方法 / API |
| :--- | :--- | :--- |
| `data_layer.py` | `DataLayer` | `get_realtime_quote(symbol)`<br>`get_kline_history(symbol, num_days)`<br>`get_batch_quotes(symbols)` |
| `pv_factors.py` | `PVFactors` | `extract_factors(klines)`<br>`calculate_atr(klines, period)`<br>`calculate_boll(closes)`<br>`calculate_kdj(klines)` |
| `unstructured_factors.py` | `UnstructuredFactors` | `score_text(text)`<br>`apply_decay(score, days_elapsed, half_life_days)`<br>`aggregate_news_sentiment(news_items)` |
| `factor_synthesizer.py` | `FactorSynthesizer` | `synthesize_universe(universe_factors, custom_weights)`<br>`select_top_k(ranked_universe, top_k)` |
| `risk_position_manager.py` | `PositionSizer`<br>`AccountPortfolio`<br>`RiskEngine` | `calculate_portfolio_target_weight(vol)`<br>`calculate_stock_allocation(sym, p, atr, equity)`<br>`buy()`, `sell()`, `end_of_day_settlement()`<br>`evaluate_position_risk(pos, p, atr, date)` |
| `backtest_engine.py` | `BacktestEngine` | `run(num_days)` -> `{metrics, equity_curve, trade_history}` |
