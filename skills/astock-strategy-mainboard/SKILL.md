---
name: astock-strategy-mainboard
version: "1.0.0"
author: ""
description: A 股主板流动性池内按趋势回踩（trend_pullback）产出买入候选与持仓卖出信号；另有 realtime_quotes 批量拉取现价快照。供下单前决策；不跑回测、不自动下单。Use when 用户要选股、看实时报价、判断买卖信号或检查持仓是否触发离场条件。
tags: [A股, 策略, 趋势回踩, 买卖信号, 主板]
---

# 主板多波段防御型 · 决策信号

本 skill 核心做三件事：**选股范围**、**买入侧信号**、**卖出侧信号**；并可选使用 **`realtime_quotes.py`** 对指定代码批量拉取**现价类快照**（基于 `MarketDataProvider.get_quote`，腾讯报价 + 分钟 K 聚合）。  
输出的是**决策参考**（结构化列表或 JSON），**不包含**历史回测撮合、**不包含**自动报单；真实下单请用券商或另接 `a-share-paper-trading` 等执行通道。
策略信号定位为**条件有效**：在市场结构与交易成本变化下，信号强度可能衰减，需持续复核。

## 能力边界

| 做 | 不做 |
|----|------|
| 从主板高流动性股票中取前 N 只构成当日股票池 | 分钟级回测、混合回测、收益曲线 |
| 用日线 `trend_pullback` 标出入场/离场条件 | 保证收益或替代投顾 |
| 给出两类「买入参考」列表（见下） | 直接向交易所或模拟盘服务下单 |
| 可选：读取持仓列表文件，标出「策略离场」标的 | 替你保存实盘持仓（除非你自建文件） |
| 批量拉取多只股票现价、涨跌幅、涨跌停参考价等（`realtime_quotes.py`） | 替代 `a-share-data` 的全市场实时板块、资金流等重接口 |

## 策略逻辑（与参数）

默认参数见 `scripts/strategy_lab/strategy_params.py`（均线快慢、回踩幅度、RSI 区间与离场 RSI 等）。  
信号计算在 `scripts/strategy_lab/strategies.py` 的 `trend_pullback`。
脚本会额外应用两层过滤：

- **成本过滤**：按 `--roundtrip-cost-bps` 估算往返成本，只有 `edge_after_cost > 0` 的候选才进入最终买入列表。
- **鲁棒性过滤**：在 `ROBUSTNESS_PARAM_GRID` 参数邻域内计算 `entry_consensus_ratio`，低于 `--entry-consensus-min` 的候选会被过滤。

**买入参考（两组，请区分语义）：**

- **`from_previous_day_close`**：上一根已收盘日线满足 `entry`。与「前一日收盘后出信号、当日再执行」的习惯一致，**更贴近事前计划**。
- **`from_last_close`**：最新一根日线也满足 `entry`，偏**形态展示**；若与上一日重复，请避免重复计数。

列表内按策略内 **`score`（均线强弱）** 降序；默认**每种买入列表最多保留 5 只**（`strategy_params.MAX_BUY_CANDIDATES`），与「同时关注仓位不宜过多」一致。需要更多或全部时加 `--max-buys 0` 表示不截断，或 `--max-buys 10` 等。

**卖出参考：**  
对 `--holdings` 文件中的代码，若**最新一根日线**满足 `exit`（破慢线或 RSI 过高等规则内条件），则列入卖出参考。文件格式：一行一只代码，可含注释行（`#` 开头）。

**风控参考（仅文档与 JSON 字段）：**  
`REFERENCE_INTRADAY_STOP_PCT` 表示历史上与策略文档一致的**日内止损比例参考**，本脚本**不**替你监控盘中止损，需自行在下单软件中设置。

## 环境与依赖

```bash
pip install akshare pandas numpy requests
```

## 运行

```bash
SKILL_DIR="<本 skill 绝对路径>"
python3 "$SKILL_DIR/scripts/daily_decisions.py" --json
```

常用参数：

- `--top-n`：股票池大小，默认 120  
- `--max-buys`：买入侧列表在排序后最多保留几条，默认 5；传 `0` 不截断  
- `--holdings`：持仓代码文件路径  
- `--workers`：拉日线并发数  
- `--json`：输出一份 JSON，便于程序消费（JSON 内含截断前数量 `*_total`）  
- `--roundtrip-cost-bps`：往返交易成本估计（单位 bps），默认 45  
- `--entry-consensus-min`：参数邻域入场一致性阈值，默认 0.67  
- `--disable-robust-check`：关闭参数邻域一致性过滤（仅在调试时使用）  

示例：

```bash
python3 "$SKILL_DIR/scripts/daily_decisions.py" --top-n 120 --holdings "$HOME/my_holdings.txt"
```

JSON 输出中会同时包含原始候选与过滤后候选：

- `from_previous_day_close_raw` / `from_last_close_raw`：仅满足信号的原始候选
- `from_previous_day_close` / `from_last_close`：通过成本与鲁棒过滤后的候选
- 单条候选附带 `entry_consensus_ratio`、`edge_after_cost`、`cost_filter_passed`、`consensus_filter_passed`
- `todo_confirm_items`：当前采用口径的记录项（roundtrip=45bps、consensus=0.67、RSI 区间偏移）

### 实时行情快照（增强）

对**已知代码列表**批量取报价（并发），可与 `daily_decisions` 输出的代码配合使用：

```bash
python3 "$SKILL_DIR/scripts/realtime_quotes.py" 600519 000001 601318 --json
python3 "$SKILL_DIR/scripts/realtime_quotes.py" -f "$HOME/my_holdings.txt" --workers 10
```

- `--json`：输出统一 JSON（含 `quotes` 与逐条 `details`）  
- `--intraday`：额外拉取**最后一根**分钟 K（`--intraday-freq` 默认 `5m`），便于核对与日线快照的时间对齐  
- 数据来自 `paper_trading/market_data.py`：与全市场深度行情相比为**轻量快照**，盘中价格随最新分钟 K 更新  

## 脚本布局

| 路径 | 作用 |
|------|------|
| `scripts/daily_decisions.py` | 入口：拉池、算信号、打印或 `--json` |
| `scripts/realtime_quotes.py` | 批量现价快照，可选附带最后一根分钟 K |
| `scripts/paper_trading/market_data.py` | 行情与 `get_mainboard_universe` |
| `scripts/strategy_lab/strategies.py` | `trend_pullback` |
| `scripts/strategy_lab/indicators.py` | 均线、RSI |
| `scripts/strategy_lab/strategy_params.py` | 默认参数与策略名 |

## 集成评估：策略候选 → ABC评级 → 入场优先级

`daily_decisions.py` 产出的是策略层面的买入候选（基于趋势回踩+成本+鲁棒性过滤）。要让候选落地为可执行操作，需与其下游的 `macd-trend-resonance-stock-picker` 评分框架配合：

### 1. 获取候选 + 实时报价

```bash
# 1a. 跑策略得到候选列表（去重合并 from_previous_day_close + from_last_close）
VENV_PY="python3"
SKILL_DIR="./.AI-Platform/skills/stocks/a-share-strategy-mainboard-multi-swing-defensive"
"$VENV_PY" "$SKILL_DIR/scripts/daily_decisions.py" --top-n 300 --max-buys 30 --json 2>/dev/null

# 1b. 批量拉实时行情（配合 realtime_quotes.py）
"$VENV_PY" "$SKILL_DIR/scripts/realtime_quotes.py" 600498 600487 002281 --json
```

### 2. 技术面评分（100分制，来自 macd-trend-resonance-stock-picker）

| 维度 | 满分 | 评分方式 |
|------|:----:|----------|
| 均线结构 | 25 | MA5>MA10+股价>MA20=25; 仅股价>MA20=15; <MA20=0 |
| MACD状态 | 40 | 轴上金叉+红柱↑=40; 轴上中立=20; 轴下金叉修复=10; 轴下死叉=0 |
| 量价(距MA20) | 15 | 距MA20<3%且价在上方=15; 价>MA20=10; 价<MA20但距<5%=8 |
| 板块共振 | 20 | 板块涨>0%+TOP10=20; 板块>-1%+TOP10=15; TOP10但领跌=10 |

**评分代码模板**：
```python
ma_s = 25 if (ma5 > ma10 and last > ma20) else (15 if last > ma20 else 0)
if dif > 0 and dif > dea and bar > 0: macd_s = 40
elif dif > 0: macd_s = 20
elif dif > dea: macd_s = 10
else: macd_s = 0
pct_ma20 = abs(price - ma20) / ma20 * 100
vol_s = 15 if (price > ma20 and pct_ma20 < 3) else (10 if price > ma20 else 8 if pct_ma20 < 5 else 5)
if board_chg > 0 and board_top10: bd_s = 20
elif board_chg > -1 and board_top10: bd_s = 15
elif board_top10: bd_s = 10
else: bd_s = 5
total = ma_s + macd_s + vol_s + bd_s
rating = "A" if total >= 80 else ("B" if total >= 65 else ("C" if total >= 50 else "D"))
```

### 3. 按"距MA20距离"定入场优先级（三档框架）

基于**缩量回踩MA20买入**核心策略，按当前价距MA20的百分比排优先级：

| 档位 | 距MA20 | 操作 | 示例(2026-06-29) |
|:----:|:------:|------|:-----------------|
| **第一档** | <1% | **今日即可关注**，回踩充分，止损紧 | 章源钨业0.2%✅ 圣泉集团0.2%✅ |
| **第二档** | 1~3% | **等待1~2日候低**，短期很可能回调到MA20 | 亨通光电2.8%✓ 博敏电子1.1%✓ |
| **第三档** | >5% | **需更大回调或放弃**，距均线太远盈亏比差 | 烽火通信8.2% 盛和资源6.3% |

**注意**：今日大幅回调（-5%~-10%）不必然意味着好入场——优先看**距MA20的距离**。距MA20>5%可能说明趋势加速后回调尚未充分，需等待。

### 4. 常见陷阱

- 策略score高（如诺德股份0.1745）但均线已MA5<MA10短空 → 不列强候选
- 今日跌幅大不代表回踩到位——必须同时满足距MA20<3%才算"缩量回踩"
- fetch_patched.py（proxy-patch → 东财）常超时；获取日线数据优先用 `fetch_history.py` 直接调用（venv python，单只≤30s超时）

## 与执行层衔接

若要将信号落到模拟盘，可在 Agent 中组合使用 **`a-share-paper-trading`**：先读本 skill 输出，再调用模拟盘 CLI 或 HTTP API 下单；本 skill **不**依赖模拟盘进程。
