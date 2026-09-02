---
name: a-stocks
version: "1.0.0"
author: ""
description: 统一A股全流程分析平台 — 数据桥接(4层降级) + 技术指标(零依赖) + 策略评分(trading-combo 100分) + 被套解套(4种量化策略) + 大盘健康度 + 持仓监控 + HTML报告。独立运行，不依赖TACN/TradingAgents项目。
tags: [A股, 选股, 策略, 技术分析, 解套, 监控, 数据, 全流程]
related_skills: [a-share-data, trading-combo, a-share-paper-trading, a-share-dashboard, a-share-investment-expert, stock-report-html, macd-trend-resonance-stock-picker, a-share-strategy-mainboard-multi-swing-defensive]
---

# aStocks — 统一A股全流程分析平台

## 定位

**独立运行**的A股全流程技能。整合 TACN项目 + AI-Platform A股技能群 的全部前沿功能于一个技能中，不依赖 TACN/TradingAgents 项目代码。

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    aStocks 统一平台                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │ data_bridge  │  │ technical_   │  │ combo_scorer    │    │
│  │ 4层降级数据  │  │ indicators   │  │ 100分策略评分   │    │
│  │ L1腾讯→L4    │  │ 零依赖计算   │  │ 入场/止损判断   │    │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘    │
│         │                │                    │              │
│  ┌──────┴────────────────┴────────────────────┴────────┐    │
│  │              a_stocks.py 统一CLI入口                  │    │
│  │  quote|technical|score|analyze|trapped|market|batch  │    │
│  │  screen|risk|golden-cross|evaluate|backtest           │    │
│  │  multi-factor|mean-reversion|grid|volatility          │    │
│  │  portfolio-risk                                        │    │
│  └──────────────────────────┬───────────────────────────┘    │
│                             │                                │
│  ┌──────────────┐  ┌────────┴────────┐  ┌──────────────┐   │
│  │ market_      │  │ trapped_        │  │ report_       │   │
│  │ assessor     │  │ position        │  │ generator     │   │
│  │ 五维健康度   │  │ 4策略解套       │  │ HTML报告      │   │
│  └──────────────┘  └─────────────────┘  └──────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 🆕 量化策略层                                         │   │
│  │  backtest_engine (夏普/回撤/Calmar/过拟合)            │   │
│  │  multi_factor_scorer (动量/价值/质量/波动率)          │   │
│  │  mean_reversion (RSI+BOLL均值回归)                    │   │
│  │  grid_trading (ATR锚定网格)                           │   │
│  │  volatility_breakout (BOLL收缩+放量突破)              │   │
│  │  portfolio_risk_manager (波动率目标/相关性/回撤控制)  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ monitor_watchdog  ·  全天cron监控  ·  散户行为矫正    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 脚本清单

| 脚本 | 行数 | 功能 | 依赖 |
|:-----|:----:|:-----|:-----|
| `scripts/data_bridge.py` | 368 | **4层降级数据桥接**: L1腾讯/L2新浪/L3 proxy-patch/L4 efinance + **P0新增**: CYQ筹码/个股事件/积分余额/A+H列表/PE查询 | 标准库(urllib)+可选subprocess |
| `scripts/technical_indicators.py` | 441 | **零依赖技术指标**: MA/EMA/MACD/KDJ/RSI/BOLL/ATR + **P1新增**: MACD二次金叉识别 + 跳空分析 | **纯标准库 math** |
| `scripts/combo_scorer.py` | 401 | **完整100分策略评分**: 均线(25)+MACD(20)+量价(15)+**筹码(15)**+**资金(15)**+板块(5)+**PE(5)** +入场判断 | technical_indicators+data_bridge |
| `scripts/market_assessor.py` | 155 | **五维大盘健康度**: 趋势(30)+情绪(20)+量能(20)+结构(15)+资金(15) | data_bridge |
| `scripts/trapped_position.py` | 245 | **被困持仓量化解套**: 诊断画像+凯利公式+4种量化策略+决策树 | technical_indicators+data_bridge |
| `scripts/stock_screener.py` | 275 | **🆕 三层漏斗选股**: 板块→技术→策略评分的端到端流水线 | data_bridge+combo_scorer |
| `scripts/risk_manager.py` | 263 | **🆕 风控管理**: T0/T1/T2三级止损+卖点信号(MACD死叉/顶背离)+回撤控制+K线形态 | technical_indicators+data_bridge |
| `scripts/a_stocks.py` | 552 | **统一CLI**: 14个子命令 | 以上所有 |
| `scripts/monitor_watchdog.py` | 179 | **Cron全天监控**: 三级止损预警+散户行为矫正 | 仅 url lib 标准库 |
| `scripts/report_generator.py` | 203 | **HTML报告生成**: 白色系·涨红跌绿·自包含 | 标准库 |
| `scripts/strategy_evaluator.py` | 285 | **持股策略评估**: 历史策略 vs 实际走势比对, 4维准确率模型 | data_bridge+combo_scorer |
| `scripts/backtest_engine.py` | 966 | **🆕 P0 回测评估引擎**: 夏普/最大回撤/Calmar/盈亏比/胜率/过拟合检测+样本内外分割, 预置SMA交叉+combo评分策略 | data_bridge+technical_indicators+combo_scorer |
| `scripts/multi_factor_scorer.py` | 393 | **🆕 P1 多因子选股**: 动量(20日/60日)+价值(PE/PB)+质量+波动率因子Z-score合成, 截面排序选股 | data_bridge+technical_indicators+combo_scorer |
| `scripts/portfolio_risk_manager.py` | 611 | **🆕 P1 组合风险管理**: 波动率目标(15%目标)/相关性矩阵(>0.7减仓)/三档回撤控制(5%/10%/15%)/行业暴露限制 | data_bridge+technical_indicators |
| `scripts/mean_reversion_strategy.py` | 298 | **🆕 P2 均值回归策略**: RSI<30+BOLL下轨买入, RSI>70+BOLL上轨卖出, 均值回归评分 | data_bridge+technical_indicators |
| `scripts/grid_trading_strategy.py` | 322 | **🆕 P2 网格交易策略**: ATR锚定BOLL区间分档, 网格适合度评估(波动率/带宽/趋势) | data_bridge+technical_indicators |
| `scripts/volatility_breakout_strategy.py` | 644 | **🆕 P3 波动率突破策略**: BOLL带宽收缩(60日20%分位)+放量突破(1.5倍)入场, 收缩检测+突破评分 | data_bridge+technical_indicators |
| `scripts/execution_action_engine.py` | 380 | **🆕 P0 交易反应与执行决策中枢 (EMS 2.0)**: 自然语言意图评估(5大类)+五类下跌精准诊断应对矩阵+6大实战反应战术+万0.85摩擦税费保本计算 | `technical_indicators`+`data_bridge` |
| `setup.sh` | 90+ | **安装脚本**: 自动探测venv, 生成config | bash |
| `config.yaml` | 100+ | **配置文件**: 策略参数+环境变量说明+数据源注册表 | yaml |

**总计**: 6000+ 行 Python，18 个脚本（含6个量化策略新增模块）

## 快速开始

```bash
# 1. 安装
bash ./.AI-Platform/skills/stocks/a-stocks/setup.sh

# 2. 实时行情
python3 ./.AI-Platform/skills/stocks/a-stocks/scripts/a_stocks.py quote 600519

# 3. 技术指标
python3 ./.AI-Platform/skills/stocks/a-stocks/scripts/a_stocks.py technical 600519

# 4. 策略评分
python3 ./.AI-Platform/skills/stocks/a-stocks/scripts/a_stocks.py score 600519 --board-top10

# 5. 全维度分析 (大盘+技术+评分+入场)
python3 ./.AI-Platform/skills/stocks/a-stocks/scripts/a_stocks.py analyze 600519

# 6. 解套分析
python3 ./.AI-Platform/skills/stocks/a-stocks/scripts/a_stocks.py trapped 600760 --cost 43 --shares 2200

# 7. 大盘健康度
python3 ./.AI-Platform/skills/stocks/a-stocks/scripts/a_stocks.py market

# 8. 批量行情
python3 ./.AI-Platform/skills/stocks/a-stocks/scripts/a_stocks.py batch "600519,000400,002230"

# 9. JSON输出
python3 ./.AI-Platform/skills/stocks/a-stocks/scripts/a_stocks.py analyze 600519 --output json
```

---

## 一、数据桥接层 (`data_bridge.py`) — P0 核心

### 4层降级链

| 层级 | 数据源 | 速度 | 依赖 | 积分 | 数据时效 |
|:----:|:-------|:----:|:----:|:----:|:--------:|
| **L1** | 腾讯 `qt.gtimg.cn` | **~0.14s** 批量10只 | urllib 标准库 | **零** | 实时/收盘 (含时间戳) |
| **L2** | a-share-data 新浪/腾讯脚本 | ~3-5s | Python + akshare | 零 | 实时+历史 |
| **L3** | 东财 proxy-patch | ~0.4-2s | akshare代理补丁 | 消耗积分 | 实时+深度 |
| **L4** | efinance | ~0.2s | efinance | 零 | 基本面/财务 |
| **Fallback** | 腾讯 `ifzq.gtimg.cn` K线 | ~0.18s | 零 | 零 | 日K前复权 |

**数据审计** (2026-07-28 17:57, 周二, 非交易时段):
- L1 行情: 10/10 返回, PE 100% 覆盖, 均含时间戳 ✅
- L1 指数: 4/4 返回 (上证/深证/创业板/科创50) ✅
- L1 K线: `ifzq.gtimg.cn` 0.18s (修复自 `web.ifzq` 的 21s 问题) ✅

### API方法

```python
from data_bridge import DataBridge

bridge = DataBridge()

# 实时行情 (自动降级)
quote = bridge.get_realtime_quote("600519")

# K线数据 (自动降级)
klines = bridge.get_kline("600519", "20260101", "20260728")

# 技术指标 (自动降级, L1原地计算优先)
tech = bridge.get_technical("600519")

# 批量行情 (L1腾讯直连, ~0.1s)
batch = bridge.fetch_batch_snapshot(["600519", "000400", "002230"])

# 大盘指数
index = bridge.index_snapshot()

# 板块排行
boards = bridge.get_board_summary(limit=20)

# 资金流向
fund_flow = bridge.get_fund_flow("600519", days=5)
```

### 独立函数（零依赖，任何Python环境可用）

```python
from data_bridge import batch_quote, index_snapshot

# 批量行情
quotes = batch_quote(["sh600519", "sz000400"])

# 大盘指数
idx = index_snapshot()
```

---

## 二、技术指标计算 (`technical_indicators.py`) — P0 零依赖

**纯Python标准库实现**，不依赖 pandas/akshare/MyTT/curl_cffi。

### 支持指标

| 指标 | 函数 | 所需K线数 |
|:-----|:-----|:--------:|
| MA (简单移动平均) | `ma(closes, n)` | ≥ n |
| EMA (指数移动平均) | `ema(closes, n)` | ≥ 1 |
| MACD | `macd(closes, 12, 26, 9)` | ≥ 26 |
| KDJ | `kdj(klines, 9, 3, 3)` | ≥ 9 |
| RSI | `rsi(closes, 14)` | ≥ 14 |
| BOLL (布林带) | `boll(closes, 20, 2.0)` | ≥ 20 |
| ATR (平均真实波幅) | `atr(klines, 14)` | ≥ 14 |
| 跳空缺口分析 | `gap_analysis(klines)` | ≥ 5 |

### 用法

```python
from data_bridge import DataBridge
from technical_indicators import calc_all, gap_analysis

klines = DataBridge.tencent_kline("600519", 120)
result = calc_all(klines)

# result["latest"]: 所有指标最新值
# result["ma"]: {ma5: [...], ma10: [...], ...}
# result["macd"]: {dif: [...], dea: [...], bar: [...]}
# result["kdj"]: {k: [...], d: [...], j: [...]}
# result["rsi"]: [...]
# result["boll"]: {mid: [...], upper: [...], lower: [...]}

gaps = gap_analysis(klines)
# gaps["gaps"]: 最近10次跳空
# gaps["consecutive_same"]: 连续同向跳空次数
```

---

## 三、策略评分引擎 (`combo_scorer.py`) — P1 trading-combo

### 100分多维评分

| 维度 | 满分 | 评分方式 | 数据源 |
|:-----|:----:|:---------|:------|
| 均线结构 | 25 | MA5>MA10>MA20>MA60=25, 逐级递减 | L1 腾讯K线 |
| MACD状态 | 20 | 轴上金叉+红柱放大=20, 轴下死叉=3 | L1 腾讯K线 |
| 量价关系 | 15 | 缩量回踩MA20=15, 放量下跌=3 | L1 腾讯K线 |
| 筹码集中度 | 15 | CYQ90%集中度<0.10得高分, 发散扣分 | L3 proxy-patch |
| 资金流向 | 15 | 主力净流入>0.5亿=15, 净流出=5 | L3 proxy-patch |
| 板块共振 | 5 | 板块>1%+TOP10=5 | L2 脚本 |
| PE估值 | 5 | PE<15低估=5, PE>100极高估值=1 | L1 腾讯行情 |

**降级策略**: L1 模式 (缺 CYQ/资金流) 自动退回 70 分制，评分归一化后评级不变。

### 评级映射

| 总分 | 评级 | 仓位建议 |
|:----:|:----:|:--------:|
| ≥ 56 | A | 30-40% |
| ≥ 49 | B | 15-25% |
| ≥ 35 | C | 仅观察 |
| < 35 | D | 放弃 |

### 入场时机判断

按**距MA20百分比**排优先级:

| 档位 | 距MA20 | 操作 |
|:----:|:------:|:-----|
| **第一档** | < 1% | 今日可关注，回踩充分 |
| **第二档** | 1~3% | 等待1~2日候低 |
| **第三档** | 3~5% | 需更大回调 |

### CLI用法

```bash
python3 a_stocks.py score 600519 --board-top10
python3 a_stocks.py score 600519 --board-chg 2.5 --board-top10 --short  # 短线模式
```

---

## 四、大盘健康度评估 (`market_assessor.py`)

### 五维模型

| 维度 | 权重 | 指标 | 获取方式 |
|:-----|:----:|:-----|:---------|
| 趋势 | 30% | 上证MA20方向 | 腾讯直连 `sh000001` |
| 情绪 | 20% | 涨跌比 | 腾讯直连指数数据 |
| 量能 | 20% | 全市场成交额 | 腾讯直连估算 |
| 结构 | 15% | 涨幅>2%板块数 | a-share-data 脚本 |
| 资金 | 15% | 北向资金 | 需proxy-patch |

### 市场模式

| 总分 | 模式 | 仓位上限 |
|:----:|:-----|:--------:|
| ≥ 85 | 强牛市 | 80% |
| ≥ 65 | 结构性行情 | 60% |
| ≥ 45 | 弱势震荡 | 50% |
| < 45 | 偏弱/系统性下跌 | 30%/20% |

---

## 五、被困持仓量化解套 (`trapped_position.py`)

### 诊断画像

- 成本 vs 现价 + 浮亏%
- ATR(14) + 60日波动率
- 年高低点
- **凯利公式仓位建议** (f* < 0 = 数学上不该持有)

### 四种量化策略

#### 策略A: 阶梯减仓 ⭐ 推荐
四档触发价 (MA5 → 1ATR → MA20 → MA20+2%)，每档减仓25%

#### 策略B: 网格做T (中风险)
4格 × 1 ATR 间距，布林下轨~中轨区间，月化4-6轮

#### 策略C: 等额补仓 (5条件门禁)
需 ≥3 项同时满足: RSI<30 + KDJ_J<0 + 地量 + 60日新低 + 主力流入

#### 策略D: 波动率锚定换股 (高风险)
四维筛选(评分/价格/资金/板块) + 排除688/30/8板块

### 量化决策树

```
浮亏 < 5%  → 持有等待 + MA20防守
浮亏 5-8%  → 策略A + B (减仓+做T)
浮亏 8-15% → 策略A + B
浮亏 15-25% → 策略A + D (减仓+换股)
浮亏 > 25% → 策略A强制 (承认错误，放弃回本)
```

---

## 六、Cron 持仓监控 (`monitor_watchdog.py`)

### 特性

- 每5分钟自动检测 (仅A股交易时间)
- **三级预警**: 🔴止损触发 / 🟠接近止损(<3%) / 🟡关注
- 📉 单日跌>3%异动提醒
- 🔔 **散户行为矫正**: 每日首次8条警示语随机推一条
- 💰 可用资金提示
- Windows Toast + 微信推送

### 部署

```bash
cp ./.AI-Platform/skills/stocks/a-stocks/scripts/monitor_watchdog.py ~/.AI-Platform/scripts/
nano ~/.AI-Platform/scripts/monitor_watchdog.py  # 修改 HOLDINGS 和 AVAILABLE_CASH
AI-Platform cron create --name '全天持仓监控' \
  --script monitor_watchdog.py --schedule 'every 5m' \
  --no-agent --workdir ~/.AI-Platform/scripts --deliver all
```

---

## 六-A、三层漏斗选股 (`stock_screener.py`) 🆕

端到端选股流水线: 板块→技术→策略评分

```bash
a_stocks.py screen "600498,600487,002281,600406,600519,000400"
a_stocks.py screen "600498,600487" --cyq  # 含筹码分布
```

---

## 六-B、风险管理 (`risk_manager.py`) 🆕

T0/T1/T2三级止损 + MACD卖点信号 + 回撤控制 + K线形态

```bash
a_stocks.py risk 600519 --entry 185
a_stocks.py risk 600760 --cost 43 --current-value 38000 --peak 50000
```

---

## 六-E、持股策略评估 (`strategy_evaluator.py`) 🆕 (替代回测)

对历史持股时期的策略建议与实际股价走势做比对分析，评估策略准确性。
**不是传统回测** — 不模拟交易，而是后验评估策略信号与市场实际走向的吻合度。

### 四维准确率模型

| 维度 | 权重 | 评估方法 |
|:-----|:----:|:---------|
| 方向准确性 | 40% | A/B推荐后涨、C/D回避后跌的比例 |
| 评级校准度 | 30% | A>B>C>D 的收益率梯度是否成立 |
| 入场时机 | 20% | 距MA20不同距离档位的实际收益差异 |
| 样本充分性 | 10% | 评估决策点数量 (≥5个才能得出有意义的结论) |

### 两种评估模式

```bash
# 模式1: 自动扫描 (无需历史持仓记录)
# 在历史K线上以固定间隔生成假想买入点
python3 a_stocks.py evaluate 600519 --auto --interval 30
python3 a_stocks.py evaluate 600519 --auto --interval 15 --count 250 --output json

# 模式2: 基于真实历史持仓
python3 a_stocks.py evaluate 600519 --entries '[{"date":"2026-06-01","price":1250,"action":"buy"}]'
python3 a_stocks.py evaluate 600519 --entries-file /path/to/holdings.json
```

### 输出解读

- **综合评分 ≥80**: 策略在该股票上表现优秀，可以信赖
- **综合评分 60-79**: 策略有一定效果，但存在盲区
- **综合评分 40-59**: 策略表现一般，需结合其他因素
- **综合评分 <40**: 策略在该股票上不适用，需调整参数或放弃

### 与传统回测的差异

| 传统回测 | 持股策略评估 |
|:--------|:-----------|
| 模拟完整交易 (开/平仓) | 评估策略信号与市场走向的吻合度 |
| 需要资金/滑点/手续费模型 | 纯方向性判断，无需资金模拟 |
| 输出: 收益率曲线/最大回撤 | 输出: 准确率/评级梯度/时机分析 |
| 依赖回测框架 | 零依赖，使用自身评分引擎 |
| 告诉你能赚多少 | 告诉你策略在什么时候有效 |

---

## 六-C、MACD二次金叉 (`second_golden_cross`) 🆕

10项检查清单 → A(观察)/B(试错)/C(放弃) 三档判决

```bash
a_stocks.py golden-cross 600760
```

---

## 六-D、筹码分布 + 个股事件 + 积分余额 🆕

```bash
a_stocks.py cyq 600519          # 筹码分布(集中度/获利比例)
a_stocks.py events 600760       # 个股事件
a_stocks.py balance             # 代理积分余额
```

---

## 七、HTML 报告 (`report_generator.py`)

白色系亚光背景 · 涨红跌绿 · 960px居中 · 自包含单文件 · 响应式

```bash
python3 scripts/report_generator.py 600519
# 输出: /mnt/c/Users/user/coding/AAAAA/20260729/aStocks_600519_20260729.html
```

### 报告持久化约定（全局规范）

| 项目 | 约定 | 说明 |
|:-----|:-----|:-----|
| **基准目录** | `/mnt/c/Users/user/coding/AAAAA/<YYYYMMDD>/` | 以日期分目录，自动创建 |
| **报告格式** | `.html` (自包含单文件) | 使用 stock-report-html CSS 规范 |
| **命名模式** | `<prefix>_<code/symbols>_<YYYYMMDD>.html` | 英文/数字+下划线，无中文 |
| **多股报告** | `<prefix>_<codes-joined>_<YYYYMMDD>.html` | 代码用短横连接 |
| **模板路径** | `skills/a-share-data/templates/stock-report.html` | 含完整CSS变量+组件系统 |
| **模板占位符** | `{{TITLE}}` `{{DATE}}` `{{HEADER_TAG}}` `{{MAIN_TITLE}}` `{{SUB_TITLE}}` `{{HEADER_STATS}}` `{{CONTENT}}` `{{FOOTER_TEXT}}` | 快速替换模式（8个占位符） |
| **组件库** | `.card` `.tbl` `.tl` `.grid-2` `.grid-3` `.stat-row` `.info-box.(blue|green|red|ylw)` `.tag-(up|down|blue|ylw|cyan)` | 基于 stock-report-html skill |
| **涨跌色** | 涨=`#d0312d` 红 / 跌=`#219653` 绿 | A股惯例 |
| **自动弹出** | `cmd.exe /c start "" ".\\<date>\\<file>.html"` | 仅Windows |
| **cron持久化** | cron无agent脚本应同时写报告文件到基准目录，仅JSON state不够 | 避免报告只出现在通知投递中 |

### 命名示例

```
# 单股报告
aStocks_600519_20260729.html
aStocks_000400_20260729.html

# 多股报告（代码按字母序、短横连接）
midday_000400-002230-600760_20260729.html
evaluation_000400-002230-600760_20260729.html

# 特殊格式报告（HTML vs MD vs JSON）
午盘三股评估报告_20260729.html          # HTML可视化报告
20260729_午盘三股评估与持股策略.md       # 终端可读Markdown（可选补充）
```

### 使用流程

```bash
# 1. 读取模板
TEMPLATE="$HOME/.AI-Platform/skills/stocks/a-share-data/templates/stock-report.html"
HTML=$(cat "$TEMPLATE")

# 2. 替换占位符
HTML="${HTML//\{\{TITLE\}\}/三股午盘评估}"
HTML="${HTML//\{\{DATE\}\}/2026-07-29}"
# ...

# 3. 确定输出路径
DATE_DIR="/mnt/c/Users/user/coding/AAAAA/$(date +%Y%m%d)"
mkdir -p "$DATE_DIR"
OUTPUT="$DATE_DIR/午盘三股评估报告_$(date +%Y%m%d).html"
echo "$HTML" > "$OUTPUT"

# 4. 自动弹出（Windows）
cmd.exe /c start "" "${OUTPUT//\//\\}"
```

---

## 八、统一 CLI (`a_stocks.py`)

```
基础命令 (8个):
  quote <code>            实时行情 (L1腾讯直连)
  technical <code>        技术指标 + 跳空分析
  score <code>            完整100分策略评分 + 入场判断
  analyze <code>          全维度: 大盘+技术+评分+入场
  trapped <code>          解套分析: 诊断+4策略+决策树
  market                  大盘健康度五维评估
  batch <codes>           批量行情 (L1腾讯直连, ~0.1s)
  deploy-monitor          监控部署指南

P1 新增命令 (7个):
  screen <codes>          三层漏斗选股 (板块→技术→评分)
  risk <code>             风控分析 (T0/T1/T2止损+卖点+回撤)
  golden-cross <code>     MACD二次金叉/底背离检测
  evaluate <code>         持股策略评估 (历史策略vs实际走势)
  events <code>           个股事件查询
  cyq <code>              筹码分布(CYQ)分析
  balance                 代理积分余额查询

P2-P3 量化策略命令 (7个):
  backtest <code>         回测评估 (夏普/回撤/胜率/盈亏比/过拟合)
  multi-factor <code>     多因子选股评分 (动量+价值+质量+波动率)
  portfolio-risk          组合风险管理 (波动率目标/相关性/回撤/暴露)
  mean-reversion <code>   均值回归策略 (RSI+BOLL)
  grid <code>             网格交易策略 (ATR+BOLL分档)
  vol-breakout <code>    波动率突破策略 (BOLL收缩+放量)

选项:
  --output json|text      输出格式 (默认 text)
  --count N               K线数量 (默认 120)
```

---

## 九、独立运行保证

本技能设计为**零外部项目依赖**：

- ✅ `data_bridge.py`: L1 模式仅需标准库 `urllib`；L2/L3 需配置 `ASTOCKS_VENV_PY` 环境变量
- ✅ `technical_indicators.py`: 纯 `math` 标准库
- ✅ `combo_scorer.py`: 依赖 `technical_indicators` + `data_bridge` (同 package)
- ✅ `market_assessor.py`: 依赖 `data_bridge`
- ✅ `trapped_position.py`: 依赖 `technical_indicators` + `data_bridge`
- ✅ `risk_manager.py`: 依赖 `technical_indicators` + `data_bridge`
- ✅ `stock_screener.py`: 依赖 `data_bridge` + `combo_scorer`
- ✅ `monitor_watchdog.py`: 仅需 `urllib`
- ✅ `report_generator.py`: 纯标准库
- ❌ **不依赖**: TACN 项目、TradingAgents 项目、LangGraph、MongoDB、FastAPI

**路径配置优先级**: 环境变量 > `config.yaml` > 自动探测。详见 [十三、环境配置与迁移](#十三环境配置与迁移)。

L2/3/4 增强功能需要 `a-share-data` skill + venv Python (可选)，默认 L1 模式已覆盖 80% 需求。

---

## 十、与已有技能的关系

| 技能 | aStocks 替代/增强 |
|:-----|:-------------------|
| `a-share-data` | data_bridge 封装其4层降级脚本，提供统一API |
| `trading-combo` | combo_scorer 将评分逻辑独立为可编程模块 |
| `a-share-investment-expert` | 四维分析被 integrate 到 `analyze` 命令 |
| `macd-trend-resonance-stock-picker` | 技术评分+入场判断被整合 |
| `a-share-strategy-mainboard-multi-swing-defensive` | 策略候选池可通过 daily_decisions.py 集成 |
| `a-share-paper-trading` | 与模拟盘独立，通过 HTTP API 对接 |
| `a-share-dashboard` | 股池管理独立，通过 pool_manager.py 对接 |
| `tradingagents-cn` | **替代** TACN 项目——本技能独立重实现了数据层+策略层+报告层 |
| `stock-report-html` | report_generator 引用其样式标准 |

---

## 十一、常见场景速查

| 场景 | 命令 |
|:-----|:-----|
| 快速看行情 | `a_stocks.py quote 600519` |
| 技术面体检 | `a_stocks.py technical 600519` |
| 选股评分 | `a_stocks.py score 600519 --board-top10` |
| 全维度分析 | `a_stocks.py analyze 600519` |
| 持仓深度套牢 | `a_stocks.py trapped 600760 --cost 43 --shares 2200` |
| 盘前大盘评估 | `a_stocks.py market` |
| 批量扫描10只 | `a_stocks.py batch "600519,000400,..."` |
| 策略有效性评估 | `a_stocks.py evaluate 600519 --auto --interval 30` |
| 程序化集成 | `a_stocks.py score 600519 --output json --board-top10` |
| 部署监控 | `a_stocks.py deploy-monitor` (手册) + 手动部署 cron |
| **回测评估** | `a_stocks.py backtest 600519 --strategy sma_cross --split` |
| **多因子选股** | `a_stocks.py multi-factor 600519 --pe 20` |
| **组合风控** | `a_stocks.py portfolio-risk --pnl -5` |
| **均值回归** | `a_stocks.py mean-reversion 600519` |
| **网格交易** | `a_stocks.py grid 600519 --cash 500000` |
| **波动率突破** | `a_stocks.py vol-breakout 600519` |

---

## 十二、LLM 多分析师协议 🧠 (替代 LangGraph)

### 定位

**a-stocks LLM 多分析师协议**是 TACN LangGraph 多分析师协作的 AI-Platform 原生替代方案。
核心差异:

| 维度 | TACN LangGraph (旧) | a-stocks + AI-Platform (新) |
|:-----|:-------------------|:----------------------|
| 架构 | Python 代码调用多个 LLM API 节点，Graph 编排 | AI Platform 自身 LLM 执行结构化多轮推理 |
| API 调用 | 每个分析师一次 LLM 调用 (10+次) | **零额外 API 调用** — 复用当前会话的模型 |
| 上下文 | 节点间消息传递，信息丢失风险 | **单一连贯推理链**，全数据在上下文中 |
| 成本 | 高 (每次分析 ~$0.5-2) | **零** |
| 灵活性 | 固定Graph拓扑 | 动态调整分析师权重和深度 |
| 辩论质量 | 消息传递式辩论 | **同窗口多视角推理**，交叉引证更充分 |

### 工作流程

当用户执行 `analyze <code> --deep` 或要求对股票做深度分析时，AI Platform 按以下五阶段执行：

```
Phase 1: 数据采集 (脚本)
  ├─ a_stocks.py analyze <code> --output json     # 全维数据
  ├─ a_stocks.py market --output json              # 大盘环境
  └─ a_stocks.py cyq <code> --output json          # 筹码分布(可选)

Phase 2: 多视角分析 (LLM 推理 — 零 API 调用)
  ├─ 🐂 看涨研究员: 上涨催化剂、乐观目标价、突破信号
  ├─ 🐻 看跌研究员: 下跌风险、悲观目标价、危险信号
  ├─ 📈 市场/技术分析师: 多周期技术面精读
  ├─ 💰 基本面分析师: PE/估值/成长性/质量 (基于可用数据)
  └─ 🌐 情绪/宏观分析师: 板块轮动、大盘环境、资金面

Phase 3: 研究经理综合
  ├─ 加权整合各视角 (技术权重 > 基本面包容)
  ├─ 风险/收益比计算
  └─ 核心矛盾识别

Phase 4: 风险辩论
  ├─ 🔴 激进场景: 最优情况 + 最大仓位
  ├─ 🟡 中性场景: 基准情况 + 标准仓位
  ├─ 🟢 保守场景: 最差情况 + 最小/零仓位
  └─ 最终裁决: 建议 + 置信度 + 理由

Phase 5: 决策输出
  ├─ 投资建议 (买入/持有/卖出)
  ├─ 置信度 (高/中/低)
  ├─ 仓位建议 (占总资金%)
  ├─ 入场价格 / 止损位 / 目标价
  └─ 关键监控指标
```

### 各分析师职责详解

#### 🐂 看涨研究员 (Bull Case)

输出内容:
- 3-5 个上涨催化剂 (技术面+基本面+事件)
- 乐观目标价 (基于技术突破位/估值上沿)
- 当前信号: 哪些数据支撑看涨 (如 MACD金叉/均线多头/PE低于行业中位数)
- 概率估计

#### 🐻 看跌研究员 (Bear Case)

输出内容:
- 3-5 个下跌风险 (技术破位+估值压力+宏观逆风)
- 悲观目标价 (基于支撑破位/估值下沿)
- 当前信号: 哪些数据警示下跌 (如 RSI超买/量价背离/PE高于行业)
- 概率估计

#### 📈 市场/技术分析师 (Technical Deep-Read)

输出内容:
- **周线级别**: 大趋势方向、关键支撑/压力
- **日线级别**: MACD 状态(金叉/死叉/背离)、均线排列、BOLL位置
- **60分钟级别**: 短期买卖点、日内支撑压力
- **量价关系**: 放量/缩量含义、主力资金迹象
- **K线形态**: 最近3日组合含义
- **跳空分析**: 缺口补回情况、突破缺口
- 综合技术评分 (0-100)
- 关键价位: 强支撑/弱支撑/强压力/弱压力

#### 💰 基本面分析师 (Fundamentals)

输出内容 (基于可用数据，标注哪些字段来自真实数据 vs 推断):
- [真实] PE (来自腾讯L1) + 行业分位判断
- [真实] 市值 + 流通盘
- [推断] 财务健康度估计 (基于行业+市值规模推断)
- [推断] 成长性评级
- 估值结论: 低估/合理/高估 + 理由
- ⚠️ 明确标注: "以下字段为行业推断，非真实财务数据"

#### 🌐 情绪/宏观分析师

输出内容:
- 大盘环境: 当前市场模式 + 仓位上限约束
- 板块强度: 所属板块排名/趋势
- 资金面: 北向资金方向 + 量能健康度
- 散户行为观察 (来自 monitor_watchdog 心理指标)

### 使用方式

```bash
# 标准分析 (脚本数据 + 简要总结)
python3 a_stocks.py analyze 600519

# 深度分析 (脚本数据 + LLM 多分析师推理)
# 通过 AI Platform 执行 (agent 收到 analyze --deep 后自动进入协议)
AI-Platform "对 600519 做深度分析，包含多角度评估和风险辩论"

# 批量深度分析
AI-Platform "对 600519,000400,002230 做批量深度分析"
```

### 与 TACN 能力对照

| TACN LangGraph 节点 | a-stocks 对应 |
|:-------------------|:-------------|
| Bull Researcher | Phase 2: 🐂 看涨研究员 |
| Bear Researcher | Phase 2: 🐻 看跌研究员 |
| Market Analyst (技术) | Phase 2: 📈 市场/技术分析师 |
| Fundamentals Analyst | Phase 2: 💰 基本面分析师 |
| News Analyst + Social Analyst | Phase 2: 🌐 情绪/宏观分析师 |
| Research Manager | Phase 3: 研究经理综合 |
| Trader + Portfolio Manager | Phase 5: 决策输出 |
| Risk Debate (3方+委员会) | Phase 4: 风险辩论 |

**未被复现**: TACN 的 Reflection (反思迭代) — 但这在单一 LLM 推理中天然更好:
AI-Platform 单窗口连贯推理本身就支持"自我反思"，无需单独节点。

### 为什么比 LangGraph 更好

1. **上下文不丢失**: TACN 每个分析师独立 LLM 调用，只能看到上一个节点的输出文本。
   AI-Platform 全部数据 + 之前分析师的输出都在同一窗口，可以随时交叉引证。

2. **辩论更真实**: TACN 的 Risk Debate 是三个独立 LLM 调用 + 委员会裁决，本质是消息传递。
   AI-Platform 在同一个推理中构建 3 种场景，能发现更深层的矛盾 (如"激进条件在保守场景中也成立"这种跨场景推理)。

3. **自适应深度**: TACN 固定 10 节点拓扑。AI-Platform 可以动态决定:
   - 对高波动股深度分析基本面
   - 对趋势股侧重技术面
   - 对横盘股侧重筹码和资金

4. **零边际成本**: 每次分析零额外 API 费用。TACN 一次完整分析 10+ LLM 调用。

---

## 十三、环境配置与迁移

### 环境变量

a-stocks 支持三级配置优先级: **环境变量 > config.yaml > 自动探测**

```bash
# 核心环境变量
export ASTOCKS_VENV_PY="$HOME/.AI-Platform/venvs/a-stocks/bin/python3"
export ASTOCKS_SYSTEM_PY="python3"
export ASTOCKS_A_SHARE_DATA_DIR="$HOME/.AI-Platform/skills/stocks/a-share-data"
```

### 从 TACN 迁移环境

```bash
# 1. 创建独立 venv + 自动探测 (推荐)
bash skills/a-stocks/setup.sh

# 2. 或手动设置环境变量指向遗留 venv (临时)
export ASTOCKS_VENV_PY="python3"

# 3. 验证
python3 skills/a-stocks/scripts/a_stocks.py quote 600519
```

---

## 十四、Python 代码集成
import sys
sys.path.insert(0, "./.AI-Platform/skills/stocks/a-stocks/scripts")

from data_bridge import DataBridge, batch_quote
from technical_indicators import calc_all
from combo_scorer import ComboScorer
from trapped_position import TrappedPositionAnalyzer

# 获取数据
bridge = DataBridge()
klines = bridge.tencent_kline("600519", 120)
quote = list(batch_quote(["sh600519"]).values())[0]

# 技术指标
tech = calc_all(klines)

# 策略评分
scorer = ComboScorer()
scores = scorer.score_full(klines, tech["latest"], board_chg=1.5, board_top10=True)

print(f"评级: {scores['rating']} ({scores['total']}/{scores['max_total']})")
print(f"建议仓位: {scores['suggested_position']}")

# 解套分析
analyzer = TrappedPositionAnalyzer(cost=43.0, shares=2200, klines=klines)
result = analyzer.analyze()
print(f"建议策略: {result['decision_tree']['recommended']}")
```

---

## 十五、验证清单

- [ ] `setup.sh` 执行成功，config.yaml 自动生成
- [ ] `a_stocks.py quote 600519` 能返回腾讯直连实时行情
- [ ] `a_stocks.py technical 600519` 能零依赖计算所有技术指标
- [ ] `a_stocks.py score 600519 --board-top10` 能输出完整100分评分
- [ ] `a_stocks.py analyze 600519` 能完成全维度分析
- [ ] `a_stocks.py trapped 600760 --cost 43 --shares 2200` 能输出解套方案
- [ ] `a_stocks.py market` 能评估大盘健康度
- [ ] `a_stocks.py batch "600519,000400"` 能批量返回行情
- [ ] `a_stocks.py risk 600519 --entry 185` 能输出三级止损
- [ ] `a_stocks.py golden-cross 600760` 能检测MACD二次金叉
- [ ] `backtest_engine.py 600519 --strategy sma_cross --count 250` 能输出夏普/回撤/Calmar
- [ ] `backtest_engine.py 600519 --strategy mean_reversion` 能回测均值回归策略
- [ ] `backtest_engine.py 600519 --strategy grid` 能回测网格交易策略
- [ ] `backtest_engine.py 600519 --strategy volatility` 能回测波动率突破策略
- [ ] `backtest_engine.py 600519 --strategy multi_factor` 能回测多因子策略
- [ ] `backtest_engine.py 600519 --split` 能输出过拟合检测结果(样本内外对比)
- [ ] `multi_factor_scorer.py 600519 --pe 30` 能输出多因子评分+截面排名
- [ ] `mean_reversion_strategy.py 600519` 能回测+输出均值回归评分
- [ ] `grid_trading_strategy.py 600519 --cash 500000` 能构建网格+模拟+适合度评估
- [ ] `volatility_breakout_strategy.py 600519` 能检测收缩+突破评分
- [ ] `portfolio_risk_manager.py --pnl -6` 能输出组合风险报告(波动率/相关性/回撤/暴露)
- [ ] `portfolio_risk_manager.py` 在 holdings 含 entry_price 时能输出 per_stock_stops
- [ ] `--output json` 模式均能输出结构化 JSON
- [ ] monitor_watchdog.py 在交易时间能正确检测止损
- [ ] 不依赖 TACN/TradingAgents 项目文件
- [ ] 环境变量 `ASTOCKS_VENV_PY` 未设置时 L2/L3 优雅降级 (不死机)
- [ ] AI Platform 可通过本协议的 Phase 1-5 执行 LLM 深度分析


## 🆕 实战交易反应动作与意图决策中枢 (Execution Overlay - EMS 2.0)

### 1. 架构定位
作为独立分层执行中枢，上接任意阿尔法选股模型（5A旋转、多维共振、多因子、退哥短线），下发精确到分钱、股数与执行时间窗口的用户操作卡片。

### 2. 核心模块与能力
1. **自然语言意图评估 (`IntentEvaluator`)**：
   * 自动从用户口语中提取【标的代码】、【买入/建仓/做T/止盈/止损/解套诉求】与【心理状态】，自动路由至对应底层模块。
2. **五类下跌场景化诊断与应对矩阵 (`DownsideReactionMatrix`)**：
   * **类型 A (高位乖离见顶)**: $\text{Bias}_{20} > 10\%$，尾盘 14:45 抢跑卖出 25%~50% 锁定利润；
   * **类型 B (主力缩量假摔)**: 跌幅 $>2.5\%$ 但量比 $<0.65$，均线支撑完好，绝不割肉，现价低吸 30% 做 T；
   * **类型 C (反弹遇强阻力)**: 弱势碰 MA60 滞涨，早盘冲高限价坚决卖出 50%；
   * **类型 D (中期破位杀跌)**: 收盘跌破 MA20 或降为 D 级，严禁补仓，次日 09:30~09:45 市价全清；
   * **类型 E (突发极端闪崩)**: 日内触碰 $-5.0\%$，一键市价清仓保本。
3. **六大交易反应战术与订单精算**：
   * 40/60 突破尾盘市价买入、均线缩量回踩两笔限价挂单、动态移动追踪止盈 (ATR回撤保护)、1-2-1 阶梯减仓。

### 3. CLI 快速调用
```bash
# 1. 意图解析
python3 scripts/a_stocks.py intent "感觉半导体启动了，明天有什么突破能买的票？"

# 2. 生成具体个股交易执行指令
python3 scripts/a_stocks.py action 601899 --cost 32.50 --shares 2000

# 3. 下跌性质诊断与应对
python3 scripts/a_stocks.py downside 600760 --cost 42.70 --shares 500
```

### 4. 详细实战手册与量化规则库
完整操作规则、量化阈值与决策公式详见参考文档：[`references/A股实战交易反应动作与量化决策手册.md`](references/A股实战交易反应动作与量化决策手册.md)
