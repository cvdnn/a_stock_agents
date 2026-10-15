# 整合架构参考 — AI-Platform A股 Skills × TradingAgents-astock

## 为什么要整合

| | AI-Platform A股 Skills | TradingAgents-astock |
|---|---|---|
| 架构哲学 | 单体专家技能（一个skill做一件事） | 多Agent辩论管道（7分析师协作） |
| 数据层 | 4层降级，腾讯/新浪/东财/proxy-patch + 终局备选 | 单链路 mootdx + 腾讯/东财直连 |
| 量化策略 | 100分制评分、趋势回踩策略引擎 | 无（纯LLM推理） |
| 执行层 | HTTP模拟盘服务（下单/持仓/成交） | 文本交易方案（不落地） |
| 监控层 | no_agent cron + 多信道推送 | 无 |
| 质量验证 | 用户断言验证、账户限制过滤 | Quality Gate（硬检查+LLM审核） |
| UI | 纯 CLI | Streamlit Web + PDF导出 |

**核心洞察**：两者在管道中是上下游关系，不是竞争关系。TradingAgents 提供"多视角LLM分析 + 结构化辩论"，AI-Platform 提供"可靠数据 + 量化验证 + 工程执行"。合并后产出可信、可验证、可执行的投研闭环。

## 管道映射

```
TradingAgents 原始管道              AI-Platform 注入
────────────────────────           ──────────────
                                    Phase 1: 数据准备 & 预筛
                                     ├─ a-share-data: 4层降级获取
                                     ├─ trading-combo: 100分评分
                                     └─ 过滤不可交易板块

7 Analysts (市场/舆情/新闻/基本面)   Phase 2a: 分析师
  + 政策/游资/解禁 (A股特化)          → 数据源替换为 AI-Platform 链路
                                      → 持仓验证: user-feedback-verification

Quality Gate                         → 加入账户限制检查
                                      → 加入数据源时效验证

Bull vs Bear Debate                  → 保留（保持英文推理质量）
  ↓
Research Manager                     → 注入 trading-combo 评分作为参考
  ↓
Trader                               Phase 2b: 执行方案
                                      → 替换为 a-share-paper-trading 下单
                                      → T+1/涨跌停/手数规则
  ↓
三方风险辩论                          → 注入 T0/T1/T2 三级止损框架
  ↓
Portfolio Manager                    → 注入四维评分 (a-share-investment-expert)
  ↓
[输出文本报告]                         Phase 3: 执行 & 监控
                                      ├─ a-share-paper-trading 模拟下单
                                      ├─ cron 止损监控部署
                                      ├─ 入场条件检测
                                      └─ 被套诊断（Sell时触发）
```

## 关键注入点（代码级）

### 1. 数据获取降级

**文件**：`tradingagents/dataflows/a_stock.py`

修改 `get_stock_data()` / `get_indicators()` 等方法，加入降级链：

```python
# 现有代码走 mootdx TCP（不稳定）
# 加入降级：
try:
    return _via_mootdx(symbol)
except (TimeoutError, ConnectionError):
    logger.warning("mootdx 不可用，降级到 AI-Platform a-share-data")
    return _via_AI-Platform_data_skill(symbol)
```

### 2. 量化评分注入

**文件**：`tradingagents/agents/managers/research_manager.py`

在 prompt 中加入评分上下文：

```python
# Research Manager 的 system_prompt 中追加
AI-Platform_SCORE_CONTEXT = """
[AI-Platform Quantitative Reference]
Composite Score: {total}/100 (Rating: {rating})
  MA Structure: {ma}/25
  MACD Momentum: {macd}/40
  Volume-Price: {vp}/15
  Sector Resonance: {sector}/20
Cyq Analysis: {cyq_interpretation}

Note: This is a quantitative reference, not a replacement for your analysis.
The final decision should synthesize both LLM reasoning and quantitative signals.
"""
```

### 3. 模拟盘对接

**文件**：`tradingagents/agents/trader/trader.py`

在 `generate_trade_plan()` 输出后，自动通过 HTTP 下单：

```python
def execute_plan(self, plan: dict) -> dict:
    """将文本交易计划落地到模拟盘"""
    if plan["action"] == "BUY":
        resp = requests.post(TRADE_API, json={
            "account_id": "alpha",
            "symbol": plan["ticker"],
            "side": "buy",
            "qty": plan["shares"],
            "order_type": "limit",
            "limit_price": plan["price"],
        })
        return resp.json()
```

### 4. 监控部署

**文件**：`tradingagents/agents/managers/portfolio_manager.py`

在最终决策输出后：

```python
if decision["action"] == "BUY":
    _deploy_stop_monitor(
        ticker=state["company_of_interest"],
        entry_price=decision.get("price", 0),
        stop_price=decision.get("stop_loss", 0),
        shares=decision.get("shares", 0),
    )
```

## 数据源优先级

| 优先级 | 数据源 | 提供内容 | 延迟 | 稳定性 |
|:------:|--------|---------|:----:|:------:|
| 1 | AI-Platform proxy-patch (东财) | 日K线、资金流、板块排行、筹码 | ~0.4s | ⚠️ 需 TOKEN |
| 2 | AI-Platform 新浪/腾讯脚本 | 日K线、实时行情、tick | ~3-4s | ✅ 稳定 |
| 3 | TradingAgents mootdx TCP | OHLCV K线、财务快照、F10 | ~1s | ⚠️ 断连风险 |
| 4 | AI-Platform akshare 直连 | 所有接口 | 不定 | ⚠️ 反爬封锁 |
| 5 | 腾讯 qt.gtimg.cn (终局) | 实时行情、指数 | ~2s | ✅ 最稳定 ⭐ |

## 依赖关系

```
ta-multi-agent-analysis
  ├─ TradingAgents-astock (GitHub clone)
  │   ├─ tradingagents/graph/        LangGraph 图编排
  │   ├─ tradingagents/agents/       7分析师 + 辩论 + 风控
  │   ├─ tradingagents/dataflows/    数据 vendor（可选替换）
  │   └─ tradingagents/llm_clients/  LLM 供应商适配
  │
  ├─ AI-Platform a-share-data             数据层（Phase 1 预筛 + 降级）
  ├─ AI-Platform a-share-paper-trading    执行层（Phase 3 下单）
  ├─ AI-Platform trading-combo            量化评分（Phase 1 评分）
  ├─ AI-Platform macd-trend-resonance     MACD 技术评分（Phase 1）
  ├─ AI-Platform a-share-strategy         趋势回踩策略（Phase 1）
  └─ AI-Platform a-share-investment-expert 四维评分（Phase 2 补充）
```

## 2026-07-09 整合优化（P0-P5）

已实现的优化升级：

| # | 优化项 | 涉及文件 | 状态 |
|---|--------|---------|:----:|
| P0 | TA结果自动写回股池 | `ta_analyze.py` → `pool_manager.py` | ✅ 已实现 |
| P1 | 融合评分矩阵 | `ta_analyze.py` `_consensus_rating()` | ✅ 已实现 |
| P2 | 统一数据字段 | `pool_manager.py` CSV 新增 `ta_decision` / `ta_analysis_date` | ✅ 已实现 |
| P3 | 三合一监控 | `templates/ta_entry_monitor.py`（entry/stop/all 模式） | ✅ 模板就绪 |
| P4 | 事件驱动调度 | `scripts/ta_orchestrator.py`（daily-batch/reanalyze/check-pool） | ✅ 已实现 |
| P5 | 反馈闭环 | `ta_analyze.py` → SELL时自动从股池移除 | ✅ 已实现 |

### 融合评分矩阵详表

```
trading-combo 量化分 (100分制)  ×  TA LLM 决策  →  共识评级
─────────────────────────────────────────────────────────────
A (>=80)         +  BUY  →  强烈买入 ⭐⭐⭐⭐  (仓位30-40%)
A (>=80)         +  HOLD →  持有观望 ⭐⭐⭐    (维持现有)
B (65-79)        +  BUY  →  谨慎买入 ⭐⭐⭐    (仓位15-25%)
B (65-79)        +  HOLD →  继续观察 ⭐⭐      (不加仓)
C (50-64)        +  BUY  →  评分分歧 ⭐        (轻仓5-10%)
C/D              +  HOLD →  量化偏弱           (仅观察)
任一方SELL       +  —    →  一致离场           (清仓)
```

### ta_orchestrator 工作流

```
ta_orchestrator --mode daily-batch
  │
  ├─ 1. 读取 selected_pool.csv
  ├─ 2. 检查 ta_analysis_date，筛选过时标的
  ├─ 3. 批量调用 ta_analyze.py（并发或串行）
  ├─ 4. 融合评分自动写回股池
  └─ 5. 输出摘要（成功/失败数）

ta_orchestrator --mode check-pool
  │
  ├─ 统计各池数量
  ├─ 识别需要更新的标的
  └─ 给出操作建议
```

### 新 CLI 参数

`ta_analyze.py` 新增：

| 参数 | 默认 | 说明 |
|------|:----:|------|
| `--sync-pool` | True | 分析结果自动同步到自选股池 |
| `--no-sync-pool` | False | 关闭股池同步 |

`ta_orchestrator.py`（新增）：

| 参数 | 说明 |
|------|------|
| `--mode daily-batch` | 每日批量分析股池 |
| `--mode reanalyze` | 单只重新分析 |
| `--mode check-pool` | 检查股池状态 |
| `--pool selected\|watch` | 目标股池 |
| `--ticker CODE` | 单只代码 |
| `--max-age N` | N天未分析视为过时（默认7天） |

## 常见问题

### Q1: 两个项目的 Python 依赖冲突怎么办？
A: TradingAgents 需要 `langchain>=0.3` / `langgraph>=0.4` / `akshare`。AI-Platform 脚本通常不依赖这些。建议在 TA 项目 venv 中安装 `pip install -e .`，AI-Platform 脚本用同一 venv 或系统 Python 3.10+ 即可。

### Q2: 一定要跑 7 个分析师吗？太贵了。
A: `ta_analyze.py` 支持 `--phase 1 --pre-score` 仅跑量化评分（0 LLM 调用），或 `--phase 2 --brief` 仅跑分析师（减少 debate 轮数）。在 `config` 中设置 `max_debate_rounds=1` 和 `max_risk_discuss_rounds=1` 可将 LLM 调用降至 ~20 次。

### Q3: 模拟盘和 TradingAgents 怎么通信？
A: AI-Platform `a-share-paper-trading` 运行在 `127.0.0.1:18765` 的 HTTP 服务。ta_analyze.py 的 `phase3_execute()` 通过 `requests` 发 POST 到 `/orders` 接口。无需共享内存或数据库。

### Q4: 如果 TradingAgents 上游更新了怎么办？
A: Bridge 层（`ta_analyze.py` + AI-Platform 注入点）设计为插件式，不修改 TradingAgents 核心代码。上游更新后，只需确保 `.env` 和 `pip install -e .` 更新即可。Bridge 层的调用接口（`TradingAgentsGraph.propagate()`）是稳定的。
