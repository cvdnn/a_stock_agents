---
name: astock-knowledge-tips
version: "1.0.0"
author: ""
description: 实战发现的 A股分析技巧、已知脚本缺陷、数据降级与应对方案。记录 a-stocks 技能使用中遇到的 bug 和工作流优化。
tags: [a-stock, pitfalls, workarounds, L1-mode]
---

# A股实战技巧与已知缺陷

> 量化策略差距分析、回测引擎审查、评估器实测数据见 `references/quant-strategy-gap-analysis-20260731.md`
> 回测引擎逐行审查(look-ahead偏差/成本模型/策略接口/Phase1-6方案)见 `references/backtest-engine-audit-20260731.md`
> 交易历史记录审查完整案例(24笔交易验证、双向验证分界点、FIFO/加权平均双方法、K线价格验证)见 `references/trade-history-audit-workflow.md`
> **web 工具链失效时的 curl 直连数据源**(东财快讯/新浪7x24/板块涨幅/全市场主力净流入排行/市场主线研判)见 `references/curl-data-sources-main-line.md`
> **本地K线「技术评分 + MA20趋势回测」一体工具** `scripts/local_ma20_backtest.py` —— 规避 backtest_engine 的 urllib SSL 超时、及 execute_code 沙箱无外网(Errno 101)。**主线选股+回测验证**标准做法：东财板块/主力净流入 clist 定主线 → terminal curl 落盘 `ifzq.gtimg.cn` fqkline JSON 到 /tmp/astk/kl/ → 本脚本评分+回测。回测仅作策略有效性参考(信号有限,非买卖指令)。
> **v3三方融合选股模型(PDF+v2+旋转模型)设计文档与回测验证**见 `references/multi-dim-model-v3-design-20260812.md` — 多股旋转回测引擎(+94.3%)、2仓分散(回撤-16.7%)、MA15离场、门控双层(上证>MA20+健康度)、跟踪止盈真实实现、指数K线获取方法

## 回测指标解读基准 (业界标准)

当 backtest_engine.py 输出指标后，用以下基准判读策略质量:

| 指标 | 良好 | 优秀 | 警惕过拟合 |
|------|------|------|-----------|
| 夏普比率 | >1 | >2 | >3 疑似过拟合 |
| 最大回撤 | <20% | <10% | <5% 疑似过拟合 |
| 胜率 | 40-60% | 60-70% | >75% 疑似过拟合 |
| 盈亏比(PF) | >1.5 | >2.0 | — |
| Calmar比率 | >1 | >2 | — |
| Recovery Factor | >3 | >5 | — |

过拟合三重判定: 夏普>3 AND 最大回撤<5% AND 胜率>75% 同时满足 → 疑似过拟合。
backtest_engine 的 `--split` 模式可做样本内外对比验证。

## 差距补全状态 (2026-07-31)

gap-analysis 中识别的6项差距，4项已通过子代理创建脚本文件补全，2项仅完成方案设计尚未写入文件:

| 原差距 | 补全模块 | CLI命令 | 实际状态 |
|--------|---------|---------|---------|
| 夏普/最大回撤/Calmar等标准指标 | backtest_engine.py (966行) | `python3 backtest_engine.py <code>` | ✅ 已写入+验证 |
| 多因子选股缺失 | multi_factor_scorer.py (393行) | `python3 multi_factor_scorer.py <code>` | ✅ 已写入+验证 |
| 均值回归策略缺失 | mean_reversion_strategy.py (298行) | `python3 mean_reversion_strategy.py <code>` | ✅ 已写入+验证 |
| 网格交易策略缺失 | grid_trading_strategy.py (322行) | `python3 grid_trading_strategy.py <code>` | ✅ 已写入+验证 |
| 组合层面风险管理缺失 | portfolio_risk_manager.py (611行) | `python3 portfolio_risk_manager.py --pnl -6` | ✅ 已写入+验证 |
| 波动率突破策略缺失 | volatility_breakout_strategy.py (644行) | `python3 volatility_breakout_strategy.py <code>` | ✅ 已写入+验证 |
| 过拟合检测 | backtest_engine --split | `python3 backtest_engine.py <code> --split` | ✅ 已写入+验证 |

全部6个模块已写入并验证通过(2026-07-31)。a-stocks SKILL.md 受保护(manually authored), 6个新脚本直接位于 scripts/ 目录，作为独立CLI运行(`python3 scripts/<module>.py <code>`)，尚未注册为 a_stocks.py 的子命令。详见 `references/quant-strategy-modules-impl-20260731.md`。

## 持仓审查关键：FIFO成本重算陷阱 (2026-07-31实测)

### 触发条件

当用户经历减仓操作后，在后续会话中提供"最新仓位"（股数+成本），券商端按 **FIFO(先进先出)法** 重新核算了剩余持仓的成本基数。此时agent必须识别成本变化并重新评估全部策略，否则会基于过时成本给出错误建议。

### 实战案例

```
002230 科大讯飞:
  减仓前: 1,600股 成本49.390 (加权平均)
  减仓1,100股后: 500股 成本84.8481 (FIFO! 原始高位底仓)

  成本骤升+71.9%! 原因: FIFO法下,卖出的是后补仓的低位筹码,
  剩余500股是最早期84.85高位建仓的原始仓位。

600760 中航沈飞:
  减仓前: 1,700股 成本43.379
  减仓1,200股后: 500股 成本42.714 (小幅下降,可能是加权均价)
```

### 识别信号

当用户提供的新成本与上次会话记录的成本差异超过 ±5% 时：
1. **不要假设成本不变** — 成本可能因FIFO重算而大幅变化
2. **必须重新计算所有盈亏** — 浮盈亏%、保本价、距止损位距离全部需重算
3. **必须重新评估策略** — 原本"持有"的判断可能因成本剧变而需要调整
4. **明确告知用户FIFO机制** — 解释为什么成本变了

### 应对流程

```
用户提供最新仓位(股数+成本)
  ├─ 对比上次会话成本 → 差异>5%?
  │   └─ YES: 识别FIFO重算, 重新计算全部指标
  │       ├─ 重新计算: 浮盈亏、保本价、距MA20、距止损
  │       ├─ 重新评估: 决策树按新浮亏%重新定位
  │       └─ 重新输出: T0/T1/T2止损位(基于新成本)
  └─ NO: 正常更新持仓即可
```

### FIFO成本的战略含义

- FIFO底仓是"历史包袱" — 之前所有补仓+减仓操作都未触及原始高位仓位
- 深度套牢(浮亏>50%)的FIFO底仓: 按决策树应"策略A强制减仓"
- 但如果减仓后仅剩小仓位(如500股,占比<33%),可考虑"用时间换空间"
- **保本价计算必须用新成本且精确进位到0.01元**: `min_sell = math.ceil(round(cost * (1+佣金) / (1-佣金-印花税-过户费), 4) * 100) / 100`。规则：按税费公式得出价格后均精确向上进位到 0.01 元（向上取整到分，例如 ¥6.1413 → ¥6.15，¥6.1463 → ¥6.15），确保挂单卖出时绝对能完全覆盖所有摩擦税费并实现无损保本。

## 工作流: 尾盘策略评估

当用户要求"审查并形成尾盘策略"时，需要在收盘前(14:30~15:00)采集最新数据并形成操作建议。

### 数据采集

```
Phase 1: 实时数据采集 (腾讯API直连)
  ├─ 个股行情: qt.gtimg.cn/q=sz000400,sz002230,sh600760
  │   parts[3]=现价 parts[4]=昨收 parts[5]=今开
  │   parts[33]=最高 parts[34]=最低 parts[6]=成交量
  ├─ 大盘指数: qt.gtimg.cn/q=sh000001,sz399001,sz399006
  └─ K线+技术指标: bridge.tencent_kline(code, 120) -> calc_all()

Phase 2: 策略评分
  └─ ComboScorer().score_full(klines, tech["latest"], 0, False)
     注意: L1模式70分制, 评级阈值: A≥56 B≥49 C≥35 D<35

Phase 3: 与午间/早间策略对比验证
  └─ session_search("000400 002230 600760 策略 持仓")
     获取当日早间/午间策略结论, 做验证:
     ✅ 判断准确 / ⏳ 待验证 / ❌ 判断有误

Phase 4: 输出
  ├─ 尾盘操作建议(持有/减仓/加仓/清仓)
  ├─ T0/T1/T2 止损纪律表(基于当前价格)
  ├─ 与午间策略的延续性/调整
  └─ 明日关键观察点
```

### 尾盘策略特殊考量

- 14:30~15:00数据为收盘前最新，需标注"尾盘"时间戳
- 需对比午间策略，标注"午后变化"和"验证结果"
- 若用户在午间已执行操作(如减仓)，必须更新持仓后再评估
- 量比计算: `今日量 / 过去5日均量`，>1.5为放量，<0.8为缩量

## 工作流: 交易历史记录审查与仓位验证

当用户要求"梳理历史记录中交易相关信息"、"审查缺漏记录"、"根据仓位情况推测数据"时，需要从多个来源重建完整交易时间线，并用用户告知的仓位百分比做交叉验证。详细案例见 `references/trade-history-audit-workflow.md`

### 数据来源（三路并行采集）

```
Phase 1: 多源数据采集
  ├─ session_search — 搜索历史会话中的交易记录
  │   关键词: "仓位 交易 买入 卖出 持仓" / "成本 减仓 加仓 建仓"
  │   搜索范围: 全部历史会话(不限当天), sort=oldest
  │   注意: session_search返回的bookend可能包含全部所需信息
  │
  ├─ HTML报告文件 — 从磁盘读取已生成的报告
  │   路径: /mnt/c/Users/user/coding/AAAAA/<YYYYMMDD>/*.html
  │   方法: 用execute_code批量读取, re.sub去HTML标签后搜索关键词
  │   关键词: 持仓/成本/买入/卖出/减仓/加仓/股数/市值/占比/FIFO/底仓
  │   注意: bs4可能未安装, 用re+html.unescape替代
  │
  └─ Markdown报告文件 — 部分日期有.md格式的报告
      路径同上目录, 直接read_file
```

### 仓位百分比交叉验证

用户告知的仓位百分比（如22.96%）可用于反推总账户资金：

```python
total_mkt = sum(shares × price for each position)  # 用最新收盘价
account = total_mkt / position_pct  # 反推总账户
# 验证: total_mkt / account == position_pct ✅
# 历史验证: 用同一account验证历史时点仓位
# 注意: 早报中"仓位~70%"可能是粗略估计, 实际可能76%
```

### 交易时间线重建

从三路数据源提取所有交易事件，按时间排序。每条记录包含: 日期 | 股票 | 操作(建仓/补仓/减仓/清仓) | 股数 | 价格 | 备注

缺漏识别规则:
- 有股数无价格 → 用当日收盘价推断, 标注"推断"
- 有成本变化无交易记录 → 可能是FIFO重算或加权均价调整
- 有历史持仓无建仓记录 → 标注为缺漏, 需用户补充
- 仓位百分比与市值不匹配 → 检查总账户是否变化

### FIFO成本变化的推断方法

当发现成本与上次记录差异>5%时:
- 成本骤升(如49.39→84.85, +71.9%) → FIFO法: 卖出低价筹码, 剩余原始高价底仓
- 成本小幅下降(如43.379→42.714, -1.5%) → 可能是加权均价法(非FIFO)
- 成本不变 → 未操作

### FIFO vs 移动加权平均双方法验证

用户补充交易记录后，需用两种成本核算方法同时验证告知成本:

**FIFO法**: 用 `collections.deque` 模拟批次队列，买入append、卖出从头部消费。`remaining > 0` 时说明超卖(缺更早建仓)。最终剩余批次的加权平均 = FIFO成本。

**移动加权平均法**: 买入时 `avg_cost = (avg_shares * avg_cost + new_shares * new_price) / (avg_shares + new_shares)`，卖出时仅 `avg_shares -= sell_shares`(成本不变)。

**反推缺失建仓成本**(移动加权平均法):
```
(已知买入总成本 + X * P) / (已知买入总股数 + X) = 告知成本
→ P = (告知成本 * (已知总股数+X) - 已知买入总成本) / X
```

### K线价格验证

当告知成本远高于已知买入价格时(如84.848 vs 最高买入价48.96)，用不复权K线验证该价格是否在历史上存在:

```python
# 不复权(检查真实成交价)
url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz002230,day,,,640,"
# 前复权(检查除权除息影响)
url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz002230,day,,,640,qfq"
```

### 数据可靠性分界点评估(双向验证)

**反向溯源**: 以用户告知的仓位为锚点，逐笔倒推每笔交易之前应有的持股数。出现负数 → 该笔之前缺建仓。

**正向验证**: 从最早交易正推，与告知仓位对比。正推 > 告知 → 中间有卖出遗漏；正推 < 告知 → 缺建仓。

**桥接验证**: 两个告知仓位间的交易完整性 — `告知A - 期间卖出 = 告知B ?`

**分界点判定**: 取三只股票各自自洽分界点的最晚时间作为统一分界点。分界点之前可能不完整，之后全部可靠。

### 输出格式

```
一、总账户推断 (仓位百分比反推)
二、完整交易时间线 (标注: 确定/推断/缺漏)
三、仓位变化轨迹 (各时点市值+仓位%)
四、资金流水 (减仓回收金额)
五、盈亏分析 (浮盈亏+已实现亏损)
六、缺漏记录审查 (逐条列出无法确定的记录, 需用户补充)
七、仓位百分比验证结论
八、数据可靠性分界点评估 (双向验证, 标注统一分界点)
```

## 用户工作流模式：多时段分步评估

用户经常分三步请求A股评估：
1. **盘前(09:25~09:30)**：竞价快照+K线+技术指标+策略评分
2. **开盘后(09:30~10:00)**：多时点快照+大盘对照+持股策略矩阵
3. **尾盘(14:30~15:00)**：最新行情+与午间策略对比+收盘前操作建议

每步需用 session_search 获取前一步结论做策略验证。三步形成完整的"盘前→午间→尾盘"日内评估链。

## 工作流: 超跌反弹/均值回归多股评估 + 网格配置 (2026-08-04实测)

当用户要求"评估多只科技股 + 入场策略 + 回测 + 配置网格"（典型输入：4只近期大幅回调的标的）时，用以下框架，**不要照搬趋势派分析**。

### 核心认知：combo D 评级对反弹候选是"预期"而非"回避"

- 超跌反弹股（空头排列 + MACD零轴下死叉）combo 评分**必然全部 D**（如 4 只全 37/70），这是趋势跟随评分器的正常输出，**不能当"回避/放弃"信号**。
- 此类标的应以 **均值回归 + 网格** 分析为主轴，combo 评级只用于标注"趋势未反转、勿重仓追高"。
- 报告里必须点明"今日上涨为超跌反抽而非趋势反转"，否则用户会误把反弹当反转重仓。

### 命令组合（对每只标的）

```bash
# 1) 行情 + K线 + 技术指标（含近5日K线做对比）——写 /tmp/*.py 用 terminal 跑
python3 /tmp/a_stocks_data.py    # fetch_batch_snapshot + tencent_kline + calc_all + gap_analysis

# 2) combo 评分（趋势确认 + 评级）
#    Python 直接调 ComboScorer().score_full()；或 a_stocks.py --output json score <code>（--output 放子命令前）

# 3) 均值回归回测（反弹策略有效性）
python3 backtest_engine.py <code> --strategy mean_reversion --count 250

# 4) 网格配置 + 适合度 + 网格回测（一步到位）
python3 grid_trading_strategy.py <code> --cash 500000 --json
#    grid_info: boll上下轨/间距(≈ATR)/格数/每格资金/止损价/各档价位
#    suitability: score + rating(A/B/C) + reason(波动率/BOLL带宽/MA60斜率)
#    simulation: total_return_pct / max_drawdown_pct / grid_fills
```

### 网格适合度判读 (grid_trading_strategy.py 的 suitability)

| 信号 | 判读 |
|------|------|
| MA60 斜率显著为负 (如 -1.12%) | **强下降趋势，不适合网格** → C 级，网格下移被套 |
| MA60 斜率近 0 / 弱趋势 | 适合网格 → A/B 级 |
| 波动率低 (≈6%) + BOLL带宽正常 | 网格优配（如 601138 工业富联 A/85） |
| 波动率 >10% (如 11.7%) | 网格回撤巨大（如 002384 网格最大回撤 36.6%），慎用 |

**实测规律**：多只同批回调股里，网格适合度差异大——只有**低波动 + 非强趋势**的标的正收益（唯一 A/85 股网格回测 +12%），深跌+强趋势股网格在下跌段全被套（回撤 19%~37%）。网格配置应**精选 1 只**而非全配。

## 工作流: 已持仓的网格交易适合度评估 (2026-08-07实测)

当用户持有某股、在反弹中问"评估是否合适配置网格交易、参数如何设置"时，**不要只把 grid_trading_strategy.py 的 suitability 分数丢给用户**——该分数基于 120 日 BOLL/MA60 计算，反映的是**历史震荡性**而非**当前动量**，在单边反弹中会严重误导。

### 核心认知：网格适合度 ≠ 当前时点适合配网格

网格的本质是**赚震荡箱体的钱**，前提是标的在区间内上下摆动。已持仓标的若正处于**单边暴力反弹**（如福晶三日+25%、长电三日+28%），此刻上网格有三个致命问题：

| 问题 | 后果 |
|:--|:--|
| 半山腰建网格，继续涨 → **卖飞** | 现价已贴近卖出档，反弹只吃到一小段，错过主升浪 |
| 反弹后的回调 → **接刀** | 超跌股波动率 9~10%，下行段网格全部买入被套，回撤近 9% |
| 大级别仍下跌（MA60 斜率负）→ **越补越套** | 下跌趋势里网格一路补仓深套 |

**关键判读**：suitability 给 B/60 分可能只是因为标的 5~6 月那段震荡行情贡献了回测收益，**不代表反弹中段是好的网格建仓点**。例：600584 长电 suitability B/60（历史震荡段贡献 +35.9% 回测），但当前 MA60 斜率仅 +0.43%、波动率 9.9% 接近红线，反弹中段配网格风险高。

### 决策输出（二选一）

**方案A【推荐】— 先锁利，等转震荡再配网格**
- 单边反弹中的利润用**移动止盈保护**更划算（破支撑减仓）
- 待反弹结束转入**横盘箱体震荡**（一般 2~4 周）后，再按下方参数上网格

**方案B【坚持配置】— 只对 B 级以上且非强趋势的标的配"非对称网格"**
- 网格**只承接下方回调、不参与上方追涨**：区间设在"现价下方到 MA20 上方"
- 排除 C 级（MA60 斜率负 / 下跌趋势）标的
- 网格资金池：单票 ≤ 组合的 1/3，且**必须与现有持仓独立核算**
- 间距加密：用 `ATR/2`（约 3.5 元/格）而非整 ATR，降低单格风险
- 网格数 5~6 格，每格资金 ~7000 元/100 股

### 命令行

```python
# 直接 Python 集成（读已落盘的K线，避免 urllib SSL 超时）
from grid_trading_strategy import GridTradingStrategy
grid = GridTradingStrategy()
info = grid.build_grid(klines, total_cash=30000)   # boll上下轨/间距/格数/各档/止损
sim  = grid.simulate(klines, initial_cash=30000)    # return_pct/max_drawdown/grid_fills
suit = grid.score_grid_suitability(klines)          # score/rating/suitable/reason
# 输出前必须人工复核当前动量 vs 分数来源, 见上方核心认知
```

### 均值回归回测注意

- 深跌强趋势股（如 -40%）均值回归策略在 250 日窗内可能 **0 笔信号**（趋势太弱，条件不满足）——这不是脚本错误，是反弹候选确实没触发。
- 只有已止跌企稳的标的才触发（实测各 1 笔 +40%）。
- 样本少（0~1 笔）时结论标"低置信度"。

### 报告结构（四股版）

大盘背景(健康度+指数) → 四股综合对比表(现价/距MA20/超卖/combo/网格适合度) → 每股grid-2分析卡 → 入场策略表(理想区/确认信号/止损/仓位) → 回测结论表 → 每只网格配置卡 → 操作优先级排序 → 风险提示。网格配置卡要标注该股 `适合/不适合`。

## 工作流: 锁利卖出策略 (tiered lock-in selling, 2026-08-07实测)

当用户持有浮盈仓位、要求"锁利 / 出一套卖出策略 / 评估卖出时机价格股数"时，用**分档卖出**框架——**不要一次性清仓，也不要死拿**。这是"超跌反弹→利润兑现"的标准出口。

### 分档结构（每只）

| 档位 | 性质 | 触发 | 股数 |
|:--|:--|:--|:--|
| T1·反弹遇阻 | 主动 | 冲高至缺口区/前高/压力位回落 | ~40% |
| T2·冲高减仓 | 主动 | 突破T1后惯性冲高 | ~30% |
| T3·破位止盈 | 被动 | 跌破MA20 / 昨收 / 今低 | 剩余 |

### 关键点
- **主动档挂限价单**（到价自动成交，不盯盘）；**被动档跌破即时执行，不侥幸**。
- 每档算清锁利金额 `(卖价-成本)×股数`，并对比"三档累计 vs 现价全清"——分档通常**多锁 10~25%** 且保留上涨不踏空空间（实证：福晶三档+2828 vs 全清+2655；长电+5472 vs +4405）。
- **若冲高失败**（未到T1价直接回落）：跌破昨低/今低直接按T3被动止盈，不等反弹。
- 卖出资金**暂不立即回补**，等回踩确认再找新买点。

### 实测案例 (2026-08-07 福晶002222/长电600584)
```
福晶(成本56.24):  T1卖200@62.5→+1252  T2卖150@64.5→+1239  T3卖150@58.49→+338  累计+2828>全清+2655
长电(成本68.83):  T1卖200@79.5→+2134  T2卖200@82→+2634   T3卖100@75.87→+704  累计+5472>全清+4405
```

## 工作流: 误操作补救 (mistaken sell↔buy order, 2026-08-07实测)

当用户把"卖出"误操作为"买入"（或反向错单）时，不要慌，按流程评估补救。

### 1. 重算持仓影响
方向错 → `新持仓 = 原持仓 + 误买股数`，`新加权成本 = (原成本×原股数 + 误买价×误买股数) / 新总股数`。
量化要点：本应减仓却加仓 = **风险敞口双倍反向**（如本应500→300，实际500→700，+400股）。

### 2. 评估方向性错误
核心是"操作方向与当日策略相反"。若当日是锁利减仓日，误买=逆势加仓，须强调：成本抬升、安全垫变薄、敞口扩大与计划相悖。

### 3. 补救三方案（按推荐排序）
| 方案 | 操作 | 适用 |
|:--|:--|:--|
| **A 立即回补卖出**（推荐） | 现价挂单卖回误买股数，恢复原仓位 | 最干净，消除错误敞口 |
| B 平价回补 | 挂误买价卖回，避免亏损 | 愿赌午后反抽 |
| C 将错就错当加仓（不推荐） | 保留误买筹码 | 除非有独立更强看多理由 |

- 误操作损失通常可忽略（每股几分×股数），**用 ~15 元损失换取敞口立即归正**最划算。
- 提示挂"现价-0.01"限价几乎秒成。

## 工作流: 入场价格审查 (entry-price review, 2026-08-04实测)

当用户在上一步多股评估后窄化范围、要求"审查/评估 XX 的入场价格"时，**不要再重跑全套回测/网格/评分**。聚焦单只：盘口快照 → 关键价位 → 分档入场价 → 止损 → 目标。

```
Phase 1: 五档盘口 + 实时行情 (qt.gtimg.cn 直连, 秒回, 优先于K线接口)
Phase 2: K线+技术位 (MA/MACD/KDJ/RSI/BOLL/ATR)
Phase 3: 关键价位
  ├─ 压力(上): 卖盘压单区(看卖5档堆量) → 今日高点 → MA20/BOLL中轨
  ├─ 支撑(下): MA10 → 今日低点/开盘价 → MA5 → 昨收
Phase 4: 分档入场 (三档, 按性价比排序)
  ├─ A档·回踩低吸(首选): 回踩MA10企稳不破 → 止损空间小
  ├─ B档·更佳买点: 回踩今日低点/开盘价(日内强支撑)企稳
  ├─ C档·突破追入: 放量站稳今日高点 → 目标看MA20
Phase 5: 止损(跌破今日低点 / 或MA5) + 目标(第一目标MA20, 再看前压力区)
```

**核心判断**: 现价若处于支撑/压力之间的"半山腰"(从日内高点回落、上方卖盘压单堆量) → **不建议市价追高**，给出分档挂单策略而非即时入场。用买卖盘口量判多空: 外盘>内盘=买方占优。

### 腾讯五档盘口解析 (`qt.gtimg.cn/q=sh601138`)

返回 GBK, `v_sh601138="..."`, 按 `~` split 成 p[]:
```
p[1]=名称 p[2]=代码 p[3]=现价 p[4]=昨收 p[5]=今开
p[6]=成交量(手) p[7]=外盘 p[8]=内盘
p[9]=买一价 p[10]=买一量 ... p[17]=买5价 p[18]=买5量
p[19]=卖一价 p[20]=卖一量 ... p[27]=卖5价 p[28]=卖5量
p[30]=时间 p[33]=最高 p[34]=最低 p[38]=换手 p[49]=量比
```
外盘>内盘=买方占优；卖盘在某价位堆量=上方压力/压单区（如卖5挂1464手 → 强压力）。

## 工作流: 分档限价单监控 cron (limit-order monitoring, 2026-08-04实测)

当用户在入场审查后要求"设置监控/限价单监控/重新监控 X 入场价"时，建一个 **no_agent cron 脚本** 轮询分档价位。完整可运行模板见 `templates/monitor_limit_order.py`（复制后改 CODE/NAME/MARKET + 分档价位即可）。

### 脚本骨架

```
交易时段门(09:25~11:30/13:00~15:00, 周末跳过) → qt.gtimg.cn 拉实时价
→ 状态文件去重(每信号每日只推一次) → 触发时 print 提醒 / 未触发 print 一行日志
```

关键点:
- **cron no_agent + 空stdout=静默**: 未触发时只 print 一行日志（不推送），触发才 print 提醒（投递）。别在脚本里无条件 print 汇总，否则每 5 分钟刷屏。
- **状态持久化**: `~/.AI-Platform/scripts/monitor_<code>_limit_state.json` 记录 `triggered` 键，`_<today>` 后缀当日去重，跨日清理。
- **分档价位来自入场审查**: 回踩低吸区 / 突破价 / 止损 / 第一目标。价位随行情变化需重跑入场审查更新。
- **部署**:
  ```bash
  cp templates/monitor_limit_order.py ~/.AI-Platform/scripts/monitor_601138_limit.py
  AI-Platform cron create --name "601138限价单监控" \
    --script monitor_601138_limit.py --schedule "every 5m" --no-agent --deliver all
  ```
- **先手动 `python3` 跑一次验证**逻辑正确（现价是否命中某档），再部署。

### 清理历史监控

设置新监控前先 `cronjob list` 找出旧的股票监控（名含旧代码/旧持仓组合，如 `portfolio_monitor` 全天持仓监控、`monitor_603501`、`auction_000400` 等），逐个 `cronjob remove`。**对应旧脚本文件**（~/.AI-Platform/scripts/ 下的 monitor_*/auction_*/midday_*/portfolio_monitor.py）移到备份目录 `/tmp/backup_old_stock_monitors/` 而非直接删（防误删可恢复）。保留非股票的 cron（gbrain/tA收盘/doc配额等）。

## 已知脚本缺陷

### 0. a-share-data 技能文档的腾讯字段索引错误 (2026-08-18 实测校正)

`a-share-data/SKILL.md` 方案D 示例代码把 `parts[5]`/`parts[6]` 当作最高/最低价 — **错误**（实为 今开/成交量(手)）。实测校正:

```
p[1]=名称 p[2]=代码 p[3]=现价 p[4]=昨收 p[5]=今开 p[6]=成交量(手)
p[30]=时间戳 p[32]=涨跌幅% p[33]=最高 p[34]=最低
```

取最高/最低必须用 `parts[33]`/`parts[34]`（与下方五档盘口解析一致）。该技能用户自有（created_by=None），无法 curator 修正 — 使用时以本条目为准。

## 工作流: 用户"更新持仓"指令 (2026-08-18实测)

用户以 `code:qty@cost` 批量登记持仓、分号分隔（例: `600276:2000@54.3071；6001899:2000@32.5042`）。

### 执行步骤

1. **解析校验** — 每项 `code:qty@cost`。代码可能误输（6001899→601899 紫金矿业），先用腾讯行情按名称核对再落盘
2. **追加 positions.csv** — `a-share-dashboard/data/positions.csv`（18列）。已存在代码不重复开仓；只填确定字段 (code/name/buy_date/buy_price/qty)，名称取自腾讯行情 p[1]，sector/止损等未知留空、不臆造
3. **实时盈亏表** — 腾讯 L1 批量直连 `qt.gtimg.cn/q=sh600276,sh601899` 拉现价，输出 成本 vs 现价 + 浮盈亏%（参考 a-stocks `batch` 子命令，注意 #2 缺陷可能空则用单只 quote）

### 陷阱: positions.csv 可能严重过期

实测 2026-08-18: CSV 仍为 2026-06-01 旧数据（沈飞1200/瑞芯微300/讯飞3000股），与真实持仓（7/31已减仓: 讯飞500/许继1000/沈飞500）严重不符。**只追加确定的新行，绝不清改旧行**; 主动向用户明示不一致，待其确认后再整体重写（遵循 a-share-pool-audit "不确定的信息不记录" 原则）。新仓可能已低于成本（600276 成本54.31 现价52.55），登记后主动提示是否接入盘中监控。

### 陷阱: 声称"已更新"但未落盘 (2026-08-18 同日实测)

首轮"更新持仓"只拉了行情就回复"已更新"，**从未真正写 positions.csv**——随后用户让"删除 沈飞/瑞芯微/讯飞"时，删除脚本读到的是旧 3 行，把它们移入历史后持仓池变空（`保留: 空`），才发现新增从未落地。已补齐重写 600276/601899 并验证。

**规则**:
1. 任何持仓 CSV 写操作后**必须 read_file 读回验证**新行存在——不信自己脚本的 print/echo，只信磁盘内容
2. 删除/重写脚本输出 `保留为空` / `kept: []` 是**红旗**，先查源文件再继续
3. 回复"已更新"前先确认写入真的发生；若发现未落盘，如实向用户明示并补写
4. 追加语义：只补确定的新行；用户随后要求"删除 X/Y/Z"时，将旧行以当日实时价移入 positions_history.csv（reason 标"清仓-池整理"，非真实成交），并保留历史归档

### 1. `a_stocks.py score <code>` text 模式崩溃

**现象**: 打印完各维度评分后 KeyError: 'score'，退出码 1。

**根因**: `combo_scorer.score_full()` 返回的字典中，`data_availability`（嵌套字典）、`effective_max`（整数）、`rating_text`（字符串）三个键没有 `score`/`max` 字段，`cmd_score()` 的打印循环未跳过它们。

**应对**:
```
# ✅ 方案A：JSON 输出（正常返回）
python3 a_stocks.py score 000400 --output json

# ✅ 方案B：用 analyze 替代（内嵌评分）
python3 a_stocks.py analyze 000400

# ✅ 方案C：Python 直接调用
python3 -c "
import sys; sys.path.insert(0, './.AI-Platform/skills/stocks/a-stocks/scripts')
from data_bridge import DataBridge; from technical_indicators import calc_all
from combo_scorer import ComboScorer
klines = DataBridge().tencent_kline('000400', 120)
tech = calc_all(klines)
scores = ComboScorer().score_full(klines, tech['latest'], 0, False)
print(f'总分: {scores[\"total\"]}/{scores[\"max_total\"]} 评级: {scores[\"rating\"]}')
"
```

### 2. `batch` 命令空数据

**现象**: 只输出表头，无数据行。

**应对**: 改用逐个 `quote` 命令或腾讯 API 直连批量。

```
# 逐个查询
python3 a_stocks.py quote 000400
python3 a_stocks.py quote 600760

# 腾讯 API 直连批量
python3 -c "
import urllib.request
url = 'https://qt.gtimg.cn/q=sz000400,sh600760'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=10)
print(resp.read().decode('gbk'))
"
```

### 3. L3 proxy-patch 不可用

**现象**: 旧 venv 路径 `python3` 已不存在。

**影响**: 无 CYQ 筹码分布、主力资金流、板块排行（东财链路）。评分引擎自动退回到 70 分制（CYQ/资金维度默认中性 8 分）。

**应对**: L1 腾讯直连模式覆盖行情 + K线 + 技术指标，满足约 80% 的分析需求。

### 3b. PYTHONPATH 污染破坏系统 Python 3.9 技能脚本（2026-08-07 实测）

**现象**: 直接 `python3 fetch_realtime.py --boards-summary` 或 `python3 -c "import akshare"` 抛
```
urllib3/_base_connection.py ... bytes, typing.IO[...], str
TypeError: unsupported operand type(s) for |: 'type' and 'type'
```
（还有 `fetch_technical.py` 静默失败、`requests` 解析错包等）。

**根因**: AI-Platform 会话注入 `PYTHONPATH=./.local/share/uv/tools/AI-Platform/lib/python3.11/site-packages`。系统 `python3` 是 3.9，import 误拉了 AI-Platform 的 3.11 包（其 urllib3 用了 `bytes | str` 3.10+ 语法）。**不是脚本/接口故障**。

**应对（所有技能脚本一律 `env -u PYTHONPATH`）**:
```bash
env -u PYTHONPATH python3 fetch_realtime.py --boards-summary --boards-limit 15 --json
env -u PYTHONPATH python3 <any a-stocks / a-share-data script>.py
```
- 清空后 akshare 1.18.64、data_bridge、fetch_realtime、腾讯 K线全部正常。
- ⚠️ `execute_code` 沙箱里 `subprocess.run(["env","-u","PYTHONPATH",...])` 会因沙箱无 `env` 而 TimeoutExpired/失败——**优先在 terminal 里跑**，不要写进 execute_code 的 subprocess。
- 判断链路是否通：先 `env -u PYTHONPATH python3 -c "import urllib.request; print(urllib.request.urlopen(...,timeout=10).read()[:200])"` 拉 `qt.gtimg.cn`。

### 3c. `calc_all()` 的 latest 字典键名（2026-08-07 实测）

`technical_indicators.calc_all(klines)["latest"]` 的键名与直觉不同，**`bar` 不存在、`j` 不存在**：
- MACD 红柱 = `latest["macd_bar"]`（不是 `bar`）
- KDJ J 值 = `latest["kdj_j"]`（不是 `j`）；K=`kdj_k`、D=`kdj_d`
- 其余：`ma5/ma10/ma20/ma60`、`dif/dea`、`rsi`、`atr`、`boll_upper/mid/lower/width`、`close`

直接用 `latest["macd_bar"]` 和 `latest["kdj_j"]`，否则抛 KeyError: 'bar'。

## 工作流技巧

### L1-only 模式下的全维分析流程

```
Phase 1: 数据采集
  ├─ a_stocks.py batch \"code1,code2,code3\"  # 批量行情（bug时用单只quote）
  ├─ a_stocks.py technical <code>            # 技术指标（无依赖）
  ├─ a_stocks.py market                      # 大盘健康度
  └─ Python 集成: data_bridge + combo_scorer
```

### 选股/横向筛选：优先腾讯K线直连，别用 daily_decisions.py（2026-08-07 实测）

当用户要"按主线选股、推荐建仓标的"时，**不要跑 `a-share-strategy-mainboard-multi-swing-defensive` 的 `daily_decisions.py`**——它用 akshare 逐只拉日线，`--top-n 200` 在 120s 内拉不完 58 只就超时（exit 124）。板块热度用 `fetch_realtime.py --boards-summary`（DangInvest，零积分）拿主线；个股筛选自己写腾讯K线 + `calc_all` 评分循环：

```python
# 主线板块热度 → 手工构造候选池 → 腾讯K线批量评分
from data_bridge import DataBridge
from technical_indicators import calc_all
bridge = DataBridge()
def calc(code):
    kl = bridge.tencent_kline(code, 120)   # 裸代码，无 sz/sh 前缀
    t = calc_all(kl); L = t["latest"]
    closes=[float(k[2]) for k in kl]; last=closes[-1]   # close 在索引2!
    # 简易80分制: 均线25 + MACD40 + 量价距MA20 15
    ms = 25 if (L["ma5"]>L["ma10"] and last>L["ma20"]) else (15 if last>L["ma20"] else (10 if last>L["ma60"] and last>L["ma10"] else 5))
    if L["dif"]>0 and L["dif"]>L["dea"] and L["macd_bar"]>0: mac=40
    elif L["dif"]>0: mac=20
    elif L["dif"]>L["dea"] and L["macd_bar"]>0: mac=10
    else: mac=0
    pct=(last-L["ma20"])/L["ma20"]*100
    vs = 15 if (last>L["ma20"] and abs(pct)<3) else (10 if last>L["ma20"] else (8 if abs(pct)<5 else 5))
    total=ms+mac+vs
    return dict(code=code,last=round(last,2),pct=round(pct,2),total=total,
                rating='A' if total>=80 else ('B' if total>=65 else ('C' if total>=50 else 'D')),
                rsi=round(L["rsi"],1),j=round(L["kdj_j"],1))
```

**建仓纪律**（回踩法）：距MA20 > 5% 视为超买/乖离过大，**即使评分 B 也要等回踩 MA5/MA10/MA20 分批低吸，严禁追当日涨停龙头**。横向排序后用实时 `qt.gtimg.cn` 复核现价/PE/换手再定 5 只推荐，并在报告里明确标注"现价 vs 回踩买点"。
Phase 2: LLM 多分析师推理（零额外 API 调用）
  ├─ 🐂 看涨: MACD金叉/均线多头/低PE/板块共振
  ├─ 🐻 看跌: KDJ超买/量价背离/高PE/板块弱势
  ├─ 📈 技术: 多周期MA排列/MACD状态/BOLL位置/跳空
  ├─ 💰 基本面: PE行业分位/市值规模
  └─ 🌐 宏观: 大盘健康度/板块轮动/涨跌比

Phase 3: 综合研判
  ├─ 个股评分 + 大盘仓位约束
  ├─ 风险/收益比核心矛盾识别
  └─ 三场景推演（激进/中性/保守）

Phase 4: 输出
  ├─ 操作建议 + 置信度
  ├─ 关键价位（支撑/压力/止损）
  └─ 明日关键观察点
```

### 评分解读速查（70 分制降级版）

| 实际总分 | 评级 | 仓位建议 |
|:--------:|:----:|:--------:|
| ≥ 56 | A | 30-40% |
| ≥ 49 | B | 15-25% |
| ≥ 35 | C | 仅观察 |
| < 35 | D | 放弃 |

### 入场时机判断

| 距MA20 | 操作 |
|:------:|:-----|
| < 1% | 今日可关注，回踩充分 |
| 1~3% | 等待1~2日候低 |
| 3~5% | 需更大回调 |

### 4. `a_stocks.py <cmd> <code> --output json` 静默失败 (exit code 2)

**现象**: `a_stocks.py quote 000400 --output json` 退出码2，无任何输出。

**根因**: `--output` 是主parser的全局参数，不是子命令的参数。argparse在子命令模式下不识别子命令后的`--output`，直接报错退出。正确用法是**将`--output`放在子命令之前**。

**应对**:
```bash
# ❌ 错误: --output 在子命令之后
python3 a_stocks.py quote 000400 --output json   # exit 2, 无输出

# ✅ 正确: --output 在子命令之前
python3 a_stocks.py --output json quote 000400

# ✅ 替代: 直接用Python调用（推荐，避免CLI陷阱）
python3 -c "
import sys; sys.path.insert(0, './.AI-Platform/skills/stocks/a-stocks/scripts')
from data_bridge import DataBridge
q = DataBridge().get_realtime_quote('000400')
import json; print(json.dumps(q, ensure_ascii=False, indent=2))
"
```

### 5. `DataBridge.index_snapshot()` 方法不存在

**现象**: 调用 `bridge.index_snapshot()` 抛出 `'DataBridge' object has no attribute 'index_snapshot'`。

**根因**: SKILL.md 文档中引用了此方法名，但 DataBridge 类中实际方法名是 `tencent_index()`。便捷函数 `index_snapshot()` 存在于模块级别而非类方法。

**应对**:
```python
# ❌ 错误
bridge = DataBridge()
idx = bridge.index_snapshot()

# ✅ 正确: 调用静态方法
idx = DataBridge.tencent_index()

# ✅ 正确: 调用模块级便捷函数
from data_bridge import index_snapshot
idx = index_snapshot()
```

### 6. `tencent_kline()` 返回 list-of-lists 而非 list-of-dicts

**现象**: 试图用 `klines[-1]["close"]` 访问数据时报错 `list indices must be integers or slices, not str`。

**根因**: `tencent_kline()` 返回 `[[date, open, close, high, low, volume], ...]` 格式的list-of-lists，不是list-of-dicts。索引顺序: `[0]=date, [1]=open, [2]=close, [3]=high, [4]=low, [5]=volume`。

**应对**:
```python
# ❌ 错误
klines = bridge.tencent_kline("000400", 120)
close = klines[-1]["close"]

# ✅ 正确: 使用索引
klines = bridge.tencent_kline("000400", 120)
close = float(klines[-1][2])
date = klines[-1][0]

# ✅ 最佳: 传入 calc_all() 后用 tech["latest"] 字典
from technical_indicators import calc_all
tech = calc_all(klines)
close = tech["latest"]["close"]
```

### 7. `batch_quote()` 便捷函数返回空字典

**现象**: `from data_bridge import batch_quote; batch_quote(["000400","002230"])` 返回 `{}`。

**根因**: `batch_quote()` 要求传入**不带前缀**的纯代码（如 `"000400"`），但它内部加上 `sh`/`sz` 前缀再调 `tencent_quote()`。而 `tencent_quote()` 解析返回数据时用的键名是 `parts[1]`（股票名称），不是代码。如果传入纯代码且匹配不上名称，结果为空。

**应对**: 直接调用 `DataBridge.tencent_quote()` 或用 `fetch_batch_snapshot()`:
```python
# ✅ 方案A: 直接调用静态方法，传入带前缀的代码
from data_bridge import DataBridge
q = DataBridge.tencent_quote(["sz000400", "sz002230", "sh600760"])

# ✅ 方案B: 用 fetch_batch_snapshot (返回 list)
bridge = DataBridge()
results = bridge.fetch_batch_snapshot(["000400", "002230", "600760"])
```

## 已知脚本缺陷 — a-stocks 主技能文档误称

### 13. `minute/query` 分时接口返回嵌套 dict (非 list)

**现象**: 解析 `ifzq.gtimg.cn/appstock/app/minute/query?code=sh601138` 时对 `d['data']['sh601138']` 直接做 `[-15:]` 切片，报 `TypeError: unhashable type: 'slice'`。

**根因**: 返回结构 `d['data']['sh601138']` 是 **dict**（含 `data`、`qt`、`mx_price` 三键），其内层 `['data']` 才是分时 list（每条 `"HHMM price vol"`）。外层 `['data']` 不是 list。

**应对**:
```python
d = json.loads(...)['data']['sh601138']
lines = d['data']   # 内层 dict 的 'data' 键 = 分时list
```
`qt` 键内含与 qt.gtimg.cn 同构的完整五档/买卖盘字段（索引相同），可作盘口备源。

### 14b. Python urllib SSL 握手超时，但 curl 正常 (2026-08-06实测)

**现象**: 用 `urllib.request.urlopen("https://ifzq.gtimg.cn/...fqkline...")` 批量拉 K 线时，全部抛 `_ssl.c:999 The handshake operation timed out`（~160s 才超时）；同一主机同一接口用 `curl` 却 ~0.1s 秒回。

**根因**: 本环境 Python 默认 SSL 握手（WSL+代理链）偶发慢/挂起，**不是 K线接口故障**。用 `curl` 验证后确认接口正常。

**应对（首选 curl 落盘 + Python 解析，不要死磕 urllib）**:
```bash
# 批量下载 K线JSON 到本地（curl 快且稳），再交给 Python 计算指标
mkdir -p /tmp/kl
for pair in "002222:sz" "600584:sh" "600760:sh"; do
  code="${pair%%:*}"; pfx="${pair##*:}"
  timeout 15 curl -s "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=${pfx}${code},day,,,120,qfq" \
    -H "User-Agent: Mozilla/5.0" -o "/tmp/kl/${code}.json"
done
```
```python
# 解析: d["data"][code]["qfqday"] 或 ["day"]，list-of-lists [date,open,close,high,low,vol]
import json
d=json.load(open("/tmp/kl/600760.json"))
k=list(d["data"].values())[0]
klines=k.get("qfqday") or k.get("day")
```
**判断次序**: K线接口疑似挂起时先 `curl -s ... | head -c 300` 验证接口是否通，再决定走 Python 还是 curl 落盘。**不要**把 urllib 的 SSL 超时误判为接口故障而放弃数据。

### 14. K线抓取偶发挂起 (ifzq.gtimg.cn) → 短超时+重试

**现象**: 同会话内 realtime (`qt.gtimg.cn`) 秒回，但 K线接口 (`ifzq.gtimg.cn` fqkline 或 `DataBridge.tencent_kline`) 偶发 60s+ 无响应，拖垮整个脚本（terminal 命令超时）。

**应对**:
- realtime 走 `qt.gtimg.cn`（快），**独立于** K线接口抓取，不要混在一个长超时调用里。
- K线用**短 timeout=8 + 3次重试**循环，而非单次长 timeout。
- 若 DataBridge 方法挂起，改直连 `ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,120,qfq` + 用 a-stock-reporting 里的零依赖公式自算指标。
- 时序: 多股分析时先批量拉 realtime（快，拿现价/盘口），再逐股拉 K线（慢），避免实时价过时。

### 8. a-stocks SKILL.md 文档方法名 `bridge.index_snapshot()` 不存在

**现象**: 按 SKILL.md "API方法" 章节调用 `bridge.index_snapshot()` 失败。

**根因**: a-stocks SKILL.md 是手动维护的(manually authored)，其中API示例 `index = bridge.index_snapshot()` 有误。实际方法:
- `DataBridge.tencent_index()` (静态方法)
- `index_snapshot()` (模块级便捷函数，非类方法)

**注意**: a-stocks 技能受保护(manually authored)，无法通过skill_manage自动修正。使用时参照本条而非SKILL.md中的API示例。

## 工作流: 盘前早报生成

当用户要求生成"早报"、"盘前评估"时，完整流程:

```
Phase 1: 外部环境采集
  ├─ 隔夜美股: 腾讯API获取 usDJI / usIXIC
  │   url = "https://qt.gtimg.cn/q=usDJI,usIXIC"
  │   返回GBK编码,~分隔,parts[3]=现价 parts[4]=昨收
  └─ A股大盘: DataBridge.tencent_index(["sh000001","sz399001","sz399006"])

Phase 2: 持仓股数据采集
  ├─ 行情: DataBridge.tencent_quote(["sz000400","sh600760",...])
  │       或逐个 a_stocks.py --output json quote <code> (注意--output位置)
  ├─ K线+技术指标: bridge.tencent_kline(code, 120) -> calc_all(klines)
  ├─ 策略评分: ComboScorer().score_full(klines, tech["latest"], 0, False)
  └─ 近5日K线: klines[-5:] (用于变化对比)

Phase 3: session_search 获取历史策略轨迹
  └─ session_search("000400 002230 600760 策略 持仓")
     获取前一日分析结论,做策略验证(✅判断准确/⏳待验证/❌判断有误)

Phase 4: LLM 多视角推理 (零额外API调用)
  ├─ 持仓盈亏计算 (含最低卖出价、距MA20百分比)
  ├─ 三场景推演 (乐观/中性/悲观)
  ├─ T0/T1/T2 止损纪律检查
  └─ 核心矛盾识别 (如"仓位过重+评级D=必须减仓")

Phase 5: 生成HTML报告 (stock-report.html模板)
  ├─ 读取: skills/a-share-data/templates/stock-report.html
  ├─ 替换8个占位符: {{TITLE}} {{DATE}} {{HEADER_TAG}} {{MAIN_TITLE}}
  │   {{SUB_TITLE}} {{HEADER_STATS}} {{CONTENT}} {{FOOTER_TEXT}}
  ├─ 保存: /mnt/c/Users/user/coding/AAAAA/<YYYYMMDD>/早报_*.html
  └─ 弹出: cmd.exe /c start "" "C:\...\早报_*.html"
```

### 隔夜美股API (腾讯国际指数)

```python
import urllib.request
# 腾讯美股指数代码: usDJI=道琼斯, usIXIC=纳斯达克, usSPX=标普500(可能不返回)
url = "https://qt.gtimg.cn/q=usDJI,usIXIC"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
resp = urllib.request.urlopen(req, timeout=10)
raw = resp.read().decode("gbk")
# 格式: v_usDJI="1~道琼斯~DJI~52208.06~51594.14~..."
# parts[3]=现价, parts[4]=昨收, 涨跌幅需自算
```

注意: `usSPX` (标普500) 可能不返回数据,需用 `usDJI` 和 `usIXIC` 作为外盘参考。

### 持仓盈亏与最低卖出价计算

```python
COMMISSION = 0.00012    # 万分之1.2 (双边)
STAMP = 0.0005          # 万分之5 (卖出)
TRANSFER = 0.00001      # 万分之0.1 (沪深双边)
MIN_FEE = 5             # 单笔佣金最低5元

min_sell = cost * (1 + COMMISSION) / (1 - COMMISSION - STAMP - TRANSFER)
```

## 工作流: 早盘审查评估（持股 + 昨日关注股）批量数据采集

当用户要求"审查评估 持股 和 昨日关注的股票的早盘信息，并生成今日策略"（典型每日盘前/早盘任务，2026-08-05 实测）时，用以下一次性批量采集配方。核心目标：**实时价先抓（快）、K线单独抓（慢）、避免长超时把整个脚本拖垮**。

### Phase 1 — 单次实时批量调用（快，~0.5s）
股票 + 大盘指数 + 隔夜美股 **合并到一个 `qt.gtimg.cn` 请求**，一次返回全部现价：
```python
codes='sz000400,sh600760,sz002230,sh601138,sz002281,sz002463,sh600584,sh603259,sh000001,sz399001,sz399006,sh000688,usDJI,usIXIC'
url='https://qt.gtimg.cn/q='+codes
# p[3]=现价 p[4]=昨收 p[5]=今开 p[33]=高 p[34]=低 p[49]=量比 p[38]=换手 p[30]=时间
```
- 指数(sh000001/sz399001/sz399006/sh000688)与美股(usDJI/usIXIC)同接口，涨跌幅自算 `(p3-p4)/p4*100`。
- ⚠️ **美股字段差异**：美股 p[30] 是日期串（如 `2026-08-04 16:42:17`）而非分时时间；p[49] 是巨大成交量（非量比），勿当量比/换手用。

### Phase 2 — 分股 K线+技术指标（慢，单独跑）
**不要**和实时价混在同一个长超时调用里（K线接口 `ifzq.gtimg.cn` 偶发 60s+ 挂起会把整个脚本拖到 timeout，见缺陷#14）。直连 `ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,120,qfq`，每只**短超时(8s)+3次重试**，返回 `[[date,open,close,high,low,vol],...]` list-of-lists。多股时先批量拉实时（拿现价），再逐股拉K线，避免实时价过时。

### Phase 3 — combo 评分
`ComboScorer().score_full(klines, tech['latest'], 0, False)`。
- 实测返回 **`max_total=100`**（非 a-stocks 文档所称的 L1 70分制）——**以返回的 `rating`/`max_total` 为准，勿硬编码 70/100 分制阈值**。
- 超跌反弹股（空头排列/MACD水下）评分多为 **D/37**，是"预期"而非"回避"信号，须结合均值回归、大盘主线（科创50强度）研判，勿单看评分。

### Phase 4 — 昨日策略验证
`session_search` 抓上日会话的持仓/建仓策略结论，逐条与今日实际走势对照，标 ✅判断准确 / ⏳待验证 / ❌有误。**这是本类任务的核心价值**（如"8/4 减仓锁利→今日-2.43% 验证正确"、"8/4 严禁追高→今日冲高回落验证"）。

### Phase 5 — 报告
按 a-stock-reporting 标准板块：大盘环境(含隔夜美股)→持仓全景(含P&L)→昨日策略验证→关注股评估→分场景方案→T0/T1/T2止损→操作优先级→风险提示。持仓P&L用实时价：`(现价-成本)×股数`。

## 工作流: 早盘竞价审查 + 主线动作判断 (2026-08-14实测)

当用户要求"早盘审查XX，XX主线动作，评估持仓策略"（开盘前/竞价时段的多股持仓审查）时，流程：①竞价快照（等09:25最终竞价）②隔夜外盘（美股+金铜期货）③主线板块强弱（代表股采样）④技术面（零依赖计算）⑤对比昨日策略报告并**核对其中价位数据** → 输出持仓策略矩阵（场景×触发×动作，以昨日止损/关键价位为锚）。完整配方见 `references/morning-auction-review-20260814.md`。

### 竞价时点陷阱

- **竞价价 09:15-09:25 持续变动，可能方向反转**：实测恒瑞 09:21 +0.32% → 09:25 最终 -0.15%，紫金 -1.02% → -1.27%。结论一律以 09:25 最终竞价为准，且标注数据时刻。
- 竞价未结束前（09:25前），深成/创业板等指数常显示昨收（涨跌 0.00%），勿误读为平开。

### 盘前竞价前 (09:00~09:15): 所有接口返回昨收快照 (2026-08-17实测)

用户在 09:00~09:15 发起"早盘审查"时（竞价9:15才开始），**所有行情接口返回的是上一交易日收盘快照，不是数据坏了**：

| 现象 | 判定 |
|:--|:--|
| qt.gtimg.cn 时间戳(p[30])是上一交易日日期(如 20260814161459) | 正常！直接以此昨收快照为审查基准 |
| 东财 push2 clist 板块接口 HTTP 000 / 空 body | 盘前限流/未开市；换新浪 `newSinaHy.php`(GBK) 或上一交易日缓存(astk/boards2.json) |
| 新浪 newSinaHy 板块全部 0.00% | 盘前未更新，竞价后才出数据 |

**流程要点**：
1. 第一步先 `date` 确认系统时间，再看 qt 时间戳字段判断数据归属日——**不要反复重拉接口确认"数据是否坏了"**（本会话浪费了3轮调用才意识到）。
2. 隔夜外盘（金铜）此时可用：东财 `ulist.np.get`(secids=101.GC00Y 等) 或新浪 `hf_` 均返回最新隔夜结算价，见 `references/curl-data-sources-main-line.md`。
3. 持仓背景走 8/13→8/14→8/17 同题会话链：`session_search` 找上一同名早盘审查会话 + 读 `AAAAA/<上一交易日>/` 建仓/追踪 HTML 报告，取止损/减仓纪律。
4. 输出时明确标注"数据为昨收快照"，并给出竞价后的触发预案（反弹离场/高开减仓/破位止损）。

### 昨日报告数据必须用 K 线核对

昨日"尾盘"track 报告（恒瑞54.34/紫金32.51/上证3955.33）与实际收盘（53.76/32.21/3926.96）偏差 1~2% — 报告数字可能实为盘中时点或上游缓存却标注"尾盘"。**复用昨日策略前先 curl K线验证昨收**：策略价位（止损位等决策产物）可沿用，但行情数字（昨收/涨跌%）必须用真实 K线。竞价恰好踩到昨日止损位（紫金竞价31.80=止损31.80）是重要触发警示，开盘30分钟方向定生死。

### 主线判断：板块 API 直连 + 代表股采样

- **DangInvest 板块 API 直连**（技能脚本缺 pandas/依赖失败时的零依赖替代）：
  `curl https://dang-invest.com/api/market/boards/summary` → JSON 结构是 **`d['data']['items']`** 列表（每条含 `groupLabel/groupKey/count/totalMarketCapYuan/totalTurnoverYuan/changePct/size`），不是 `data`/`boards` 列表——按错误结构解析会得 0 条。支持 `limit` 参数；limit=10 时只回 10 条，有色/医药等可能既不在 TOP 也不在 BOTTOM。
- **代表股采样法**（板块覆盖不全时）：qt.gtimg.cn 批量拉每板块 2-3 只代表股的竞价涨跌判强弱——有色：山东黄金/江西铜业；医药/CXO：药明康德/复星医药；算力：中科曙光/浪潮信息/紫光股份。一次 HTTP 秒回、零积分，板块强弱以代表股竞价方向一致性为准。
- **金属期货行情**（紫金/有色类隔夜催化）：⚠️ **qt.gtimg.cn 的 `hf_GC`/`hf_HG`/`hf_CL` 盘前实测返回空**(8/14、8/17两次)——改用东财 `ulist.np.get`(101.GC00Y 等) 或新浪 `hq.sinajs.cn/list=hf_GC,hf_SI,hf_CAD`(需 Referer, GBK)。两接口均盘前可用，字段解析见 `references/curl-data-sources-main-line.md` §6。新浪期货字段顺序与股票不同：split(',') 后 [3]=现价 [4]=昨结 [9]=时间 [13]=名称。

## 用户工作流模式：两步评估

用户经常分两步请求A股评估：
1. **盘前(09:25~09:30)**："审查并形成竞价信息，评估今日策略" → 竞价快照+K线+技术指标+策略评分
2. **开盘后(09:30~10:00)**："审查并分析开盘走势动向，形成持股策略" → 多时点快照+大盘对照+持股策略矩阵

第一步输出盘前竞价评估表+三股策略排序；第二步输出开盘走势追踪+持股策略矩阵(操作/仓位/止损/目标)。
详细流程见 `references/opening-bell-tracking-workflow.md`。

## 工作流: 开盘走势多时点快照追踪

当用户要求"审查开盘走势"、"分析开盘动向"时，需要在竞价后取多个时点快照追踪方向变化。单一快照无法判断开盘后的趋势是延续还是反转。

### 数据采集时间轴

```
09:25  集合竞价    → fetch_realtime.py --quote <code> --json  (市场状态="盘前")
09:30  开盘首笔    → fetch_realtime.py --tick <code> --json   (看首笔方向)
09:35  开盘5分钟   → fetch_realtime.py --quote <code> --json  (第一次回踩或冲高)
09:45  开盘15分钟  → fetch_realtime.py --quote <code> --json  (方向初步确认)
09:50  开盘20分钟  → fetch_realtime.py --quote <code> --json  (趋势验证)
```

### 关键观察点

| 时点 | 观察内容 | 判读 |
|:----:|:---------|:-----|
| 09:25竞价 | 竞价价 vs 昨收 | 高开/低开/平开 → 定性偏多/偏空 |
| 09:30首笔 | tick direction 买/卖 | 首笔方向预示当日资金态度 |
| 09:35 | 竞价价→现价变化 | 冲高回落=上方有抛压；低开拉回=下方有支撑 |
| 09:45 | 最高/最低区间形成 | 确认开盘后方向（延续竞价方向还是反转） |
| 09:50 | 量能对比 | 放量vs缩量、与前日全天量的百分比 |

### 实用对比表

对每只股票构建以下对比，用于开盘走势判读：

```
| 指标 | 竞价(09:25) | 09:45现价 | 09:50现价 | 走势特征 |
竞价价 → 开盘价 → 最高 → 最低 → 09:45 → 09:50
```

走势特征分类：
- **低开冲高回落**: 竞价低开 → 开盘后拉升至昨收上方 → 但未守住回落 → 正常回踩
- **高开放量冲高见顶**: 竞价高开 → 两波冲高 → 遇MA/BOLL阻力回落 → 追入风险大
- **窄幅偏弱走低**: 微低开 → 极窄幅波动 → 逐步走低 → 缩量调整
- **低开拉回**: 低开后快速拉回昨收上方 → 站稳 → 下方支撑强

### 大盘对照必须项

三只个股开盘走势必须与大盘对照，判断个股是否跑赢大盘：

```
大盘暴涨(+1%~+6%) → 个股逆势下跌 = 显著弱势信号
大盘暴跌(-2%~-5%) → 个股逆势上涨 = 显著强势信号
个股与大盘同向但幅度小 = 跟随大盘，无独立行情
```

### 注意事项

- tick数据仅覆盖开盘后约5分钟（已知限制），09:35后需用 `--quote` 快照替代
- 竞价成交量较小(15~60万手)，代表性有限，09:30后5~10分钟走势才是真正方向确认
- `a_stocks.py batch` 在盘前可能返回空数据（已知缺陷#2），改用逐个 `fetch_realtime.py --quote`

## 策略评估器 (strategy_evaluator) 已知缺陷 — 2026-07-31实测

### 9. 70分制下评级分布严重偏斜

**现象**: `a_stocks.py evaluate 600519 --auto --interval 15 --count 250` 实测10个决策点：0个A级 / 1个B级 / 1个C级 / 8个D级。000001同样：0个A级 / 1个B级 / 4个C级 / 5个D级。

**根因**: L1模式下combo_scorer退回70分制(缺CYQ/资金流)，但评级阈值仍按100分制比例套用:
- A需 ≥ 80% × 70 = 56分
- B需 ≥ 70% × 70 = 49分
- C需 ≥ 50% × 70 = 35分
- D < 35分
70分制下多数个股日常得分在35-42区间 → 大量被评为D级(回避) → 统计无意义。

**实测关键数据**(600519茅台, 10个决策点):
- 方向准确率仅50%(接近随机)
- A/B推荐胜率0%(唯一B级推荐5日跌4.48%)
- 评级梯度反向: B(-4.48%) < C(-1.31%) < D(-0.24%)
- D级"回避"时点后续20日反涨+0.52% → 策略信号无效

**应对**: 评估结论若主要来自D级样本需标注"低置信度"。评估器应增加评级分布展示，当任一评级样本<5条时输出警告。

### 10. 评估模型四维设计缺陷

**缺陷明细**:

| 维度 | 问题 | 影响 |
|------|------|------|
| 方向准确性(40%) | 仅以5日收益正负判定，无止损机制 | 买入后先跌5%再涨8%可能已止损出场，但评估仍判"正确" |
| 评级校准(30%) | "宽松匹配"宽到2个评级即得满分30/30 | 600519梯度全反(B<C<D)但校准分仍得15/30 |
| 入场时机(20%) | 仅比较first vs far两档 | second/third档未参与评分计算 |
| 样本充分性(10%) | 5条样本即满分10分 | 统计意义极低，但满分设计鼓励小样本误判 |

**改进模型v2设计**(6维度100分，待实现):
1. 超额收益方向准确率(25%): 用超额收益(vs buy_hold基准)而非绝对收益
2. 评级梯度单调性(20%): 斯皮尔曼秩相关系数替代宽松匹配，≥3个评级有样本才评
3. 入场时机区分度(15%): 4档全参与，用方差加权差异
4. 最大不利偏移MAE控制(15%): A/B推荐后20日内最大回撤，衡量持有体验
5. 多窗口一致性(15%): 1d/5d/10d/20d四窗口方向一致性
6. 样本充分性(10%): ≥20个=10分，≥10个=6分，≥5个=3分，<5个=0分

## paper_trading 回测引擎审查 — 2026-07-31

### 11. 回测成本模型过期

**现象**: `engine.py`中`calc_commission()`用万3佣金、`calc_tax()`用0.1%印花税。

**根因**: 印花税自2023.8.28起减半至0.05%(卖出方)，行业主流佣金为万2.5(0.025%)。

**影响**: 高频策略回测收益系统性偏低(成本偏高约50%)。

**应对**:
- `calc_tax`: `amount * 0.001` → `amount * 0.0005`
- `calc_commission`: `amount * 0.0003` → 可配置参数，默认`0.00025`

### 12. 回测缺失核心指标

`run_backtest()`输出仅有: 总收益率、最大回撤、win/loss count、equity_curve(后60条)。

**缺失(业界标准)**:
- 夏普比率 = (年化收益-无风险利率) / 年化波动率 × √250
- 卡尔玛比率 = 年化收益 / 最大回撤
- 索提诺比率 = 年化收益 / 下行波动率 × √250
- 年化收益率(需250交易日换算)
- 超额收益(vs buy_and_hold同标的基准)
- 换手率 / 平均持仓天数
- 盈亏比(profit_factor)

**缺失能力**:
- 只支持单股回测，不支持组合
- 策略硬编码3种(buy_hold/sma_cross/rsi_revert)，无策略接口抽象
- 无滑点建模
- equity_curve截断60条，无法看完整曲线

**推荐方案**: 基于paper_trading引擎扩展(~400行新增)，不引入Backtrader/qlib等重依赖框架。补全: 策略接口抽象+backtest_metrics.py(夏普/卡尔玛/索提诺)+滑点+基准对照+完整curve。

**✅ 已补全 (2026-07-31)**: 新增 `backtest_engine.py` (966行) 到 a-stocks scripts/, 实现了完整夏普/最大回撤/Calmar/盈亏比/胜率/Recovery Factor/过拟合检测, 支持任意策略函数接口和样本内外分割。作为独立CLI运行: `python3 scripts/backtest_engine.py <code> --strategy sma_cross|combo_score [--split]`。实测600519: SMA策略夏普-0.61/回撤16.8%, combo_score策略夏普-1.75/回撤14.78%, 过拟合检测均未触发。详见 `references/quant-strategy-modules-impl-20260731.md`。

### 13. 回测引擎信号过稀 → 统计无意义 (2026-08-04实测)

**现象**: 对主线 AI 硬件股跑 `backtest_engine.py --strategy combo_score` 每只仅 0~1 笔交易(winning_trades 0/1)、`sma_cross` 样本外仅 1~2 笔。胜率/夏普/PF 全是无意义数字，`--split` 的"未见过拟合"也只是因为样本太少。

**应对**: 回测引擎输出交易数/样本数 **≤5 笔时结论一律标"低置信度/不可靠"**，**不要用回测统计做买卖决策**。此时以实时技术面+大盘风格(见 `references/curl-data-sources-main-line.md` 的主线研判)为准。combo_score 在 L1 模式对超跌反弹股信号极稀(与 #9 评级偏斜同源)。

### 14. `MultiFactorScorer` 无 `.score()` 方法

**现象**: 调 `MultiFactorScorer().score(code, pe=30)` 报 `'MultiFactorScorer' object has no attribute 'score'`。

**应对**: `multi_factor_scorer.py` 的入口是**模块级函数**而非类方法。用 CLI `python3 multi_factor_scorer.py <code> --pe 30`，或读源码确认实际方法名/签名后再 Python 集成。同理——调用任一量化策略脚本(mean_reversion/grid/volatility/portfolio_risk)前，**先确认其是"类方法"还是"模块级函数"**，别照 a-stocks SKILL.md 的示例盲调(该文档多处方法名与实际不符,见 #5/#8)。

### 15. 东财个股主力资金接口不可靠 (2026-08-04实测)

**现象**: `push2.eastmoney.com/api/qt/stock/get?secid=...&fields=...,f62,f184` 返回的 `f62`(主力净流入)常为 0、`f184`(主力净占比)出现 -55% 等怪值，不可信。

**应对**: **个股主力资金方向不要用 stock/get 接口下结论**。改用板块/全市场 `clist` 接口(fid=f62 排序)看主线资金去向，或用量价/技术面判断。接口细节见 `references/curl-data-sources-main-line.md`。

### 16. `a_stocks.py backtest` CLI 仅支持 2 种策略 (2026-08-12实测)

**现象**: `a_stocks.py backtest <code> --strategy mean_reversion` 报 `invalid choice: 'mean_reversion' (choose from 'sma_cross', 'combo_score')`。

**根因**: `a_stocks.py` 的 `backtest` 子命令 argparse `choices` 硬编码为 `['sma_cross', 'combo_score']`，而 `backtest_engine.py` 的 `PRESET_STRATEGIES` 字典实际注册了6种策略(`sma_cross/combo_score/mean_reversion/grid/volatility/multi_factor`)。`a_stocks.py` 的 CLI 没有透传 `backtest_engine.py` 的完整策略列表。

**应对**: 直接用 `backtest_engine.py` 脚本而非 `a_stocks.py backtest` 子命令:
```bash
python3 scripts/backtest_engine.py <code> --strategy mean_reversion --count 250 --split
python3 scripts/backtest_engine.py <code> --strategy grid --count 250
python3 scripts/backtest_engine.py <code> --strategy volatility --count 250
python3 scripts/backtest_engine.py <code> --strategy multi_factor --count 250
```
或 Python 集成: `from backtest_engine import PRESET_STRATEGIES; PRESET_STRATEGIES['mean_reversion']`。

### 17. 多维模型脚本编写3类常见Bug (2026-08-12实测)

构建 `multi_dim_model_v2.py` 时发现3类反复出现的Bug:

1. **`MarketState` 未在 `__init__` 调用 `assess()`**: `StockSelectionV2.__init__` 中 `self.market = MarketState()` 但未调 `assess()`，导致 `self.market.config` 不存在(`AttributeError`)。**修复**: `__init__` 中 `self.market = MarketState(); self.market.assess()`。

2. **`klines[-1]` 是整条K线(list), 不是标量**: `float(klines[-1])` → `TypeError: must be real number, not list`。**修复**: `float(klines[-1][2])` (索引2=收盘价)。K线格式 `[date, open, close, high, low, volume]`。

3. **变量名拼写**: `clines` 应为 `klines`(`NameError: name 'clines' is not defined`)。用编辑器全局搜索变量名一致性。

### 18. `tencent_kline()` 无法获取指数K线 (2026-08-12实测)

**现象**: `bridge.tencent_kline("sh000001", 521)` 返回空列表(0根K线); `bridge.tencent_kline("000001", 521)` 返回的是**平安银行**(代码000001的股票)而非上证指数。

**根因**: `tencent_kline()` 使用 `ifzq.gtimg.cn/api/app/mkt/kline` 接口, 仅支持个股K线, 不支持指数。指数需要不同的API端点。

**应对**: 用 `web.ifzq.gtimg.cn/appstock/app/fqkline/get` 接口 + curl 获取指数K线:
```bash
curl -s "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,520,qfq" -A "Mozilla/5.0"
```
返回JSON: `{"data":{"sh000001":{"day":[[date,open,close,high,low,vol],...]}}}` 或 `qfqday` 键。用Python解析后可用于回测门控(上证>MA20判断)。

**完整获取+缓存模式**(v3验证): 首次curl获取→存为本地JSON→后续直接读文件避免重复网络请求。详见 `references/multi-dim-model-v3-design-20260812.md`。

### 19. 策略脚本docstring不得声称未实现的功能 (2026-08-12审计)

**现象**: v2脚本docstring第12行写"四重风控: 硬止损+信号止损+**跟踪止盈**+**时间止盈**"，但代码中**完全不存在**跟踪止盈(从最高价回落3%卖出)和时间止盈(5日未达目标评估CS)的逻辑。共7项"虚高声明"被审查发现。

**教训**: 策略脚本的docstring/注释中不得声称未实际编写的功能。审计方法: 对docstring中每个功能声称, 在代码中搜索对应的变量名/条件判断/执行逻辑, 找不到则标为"虚高声明"。v3中跟踪止盈真实实现并在回测中触发16次(22.5%), 时间止盈触发1次。

## 工作流: 多维选股模型策略设计与验证 (2026-08-12实测)

当用户要求"评估一种A股选股模型策略"或"审查PDF选股策略报告并形成v2版本"时，用以下框架。**核心是将PDF理论框架的优势与a-stocks实盘工具链融合**。

### v1→v2 改进路径 (10项核心改进)

| # | 改进项 | v1缺失 | v2实现 |
|---|--------|--------|--------|
| 1 | 维度共振门禁 | 无门禁, 仅加权求和 | A≥4维+CS≥75, B≥3维+CS≥60 |
| 2 | 市场状态自适应 | 固定参数 | 4状态(多头/偏多/震荡/空头)×5参数 |
| 3 | 量能子系统增强 | 仅量比5/20 | 5子指标: 量价配合+换手+3类异动(倍量/梯量/堆量)+资金真实+趋势 |
| 4 | 结构子系统增强 | 仅MA+BOLL | 4子指标: MA结构+箱体突破+道氏趋势+形态位置(250日) |
| 5 | 资金维度修复 | 默认8分 | 6子指标代理: 主力流入+连续性+换手+大单+集中度+北向 |
| 6 | 四重风控 | 仅ATR止损 | 硬止损-5%+ATR取紧+分档止盈(A+15%/B+8%/C+5%) |
| 7 | 分批建仓 | 一次性 | A级60%+40%(3日不破-3%补), B级50%+50% |
| 8 | 卖出信号 | 无 | 5类: CS<60/技术死叉/跌破均线/单日跌>5%/止盈止损 |
| 9 | 权重对齐PDF | 另一套 | 技术25%\|趋势22%\|资金20%\|量能18%\|结构15% |
| 10 | 评分校准 | 固定70分门槛 | 动态门槛(趋势50-65)+代理数据门槛降(量能55/资金45) |

### 构建流程

```
Phase 1: 加载技能
  ├─ skill_view(a-stocks) — 数据桥接+技术指标+评分+回测全部脚本
  ├─ skill_view(stock-model-routing) — flash模型直接编程
  └─ skill_view(macd-second-golden-cross) — MACD底部信号(可选集成)

Phase 2: 采集实盘数据 (a-stocks CLI)
  ├─ a_stocks.py market                    # 大盘健康度五维评估
  ├─ a_stocks.py batch "code1,code2,..."   # 批量行情 (注意#2缺陷可能空)
  ├─ a_stocks.py technical <code>          # 技术指标(零依赖)
  ├─ a_stocks.py score <code>              # combo_scorer 100分策略评分
  └─ a_stocks.py backtest <code> --strategy sma_cross|combo_score --split  # 回测
  注: --output json 须在子命令前! 见缺陷#4

Phase 3: 编写多维模型脚本 (write_file → terminal运行)
  ├─ 5维度类: TechnicalDimension / TrendSentimentDimension / VolumeDimension
  │            StructureDimension / FundDimension
  ├─ MarketState: 4态×5参数动态配置
  ├─ 共振门禁: A≥4维/B≥3维
  └─ 四重风控: 硬止损+ATR+止盈+卖出信号
  ⚠️ 3类常见Bug: 见缺陷#17

Phase 4: 交叉验证
  ├─ a_stocks.py evaluate <code> --auto --interval 20  # 策略评估器(方向准确率)
  ├─ 计算 v2分数 vs 评估器方向准确率的Pearson相关性
  └─ v2应比v1相关性更高 (实测: v2 r=0.406 vs v1 r=0.212, ↑92%)

Phase 5: 生成HTML报告
  ├─ 读取 stock-report.html 模板或自建CSS
  ├─ 保存: .\<YYYYMMDD>\<报告名>.html
  └─ 弹出: cmd.exe /c start "" "<path>"
```

### 验证关键指标

| 指标 | v1基准 | v2目标 | 实测 |
|------|--------|--------|------|
| v2分数 vs 评估器相关性 | r=0.212 | >0.3 | r=0.406 ✅ |
| v2分数 vs 方向准确率 | r=0.053 | >0.1 | r=0.175 ✅ |
| 评级分布合理性 | 全B级(4/8) | A/B/C/D分级 | 6C+2D(震荡市审慎) ✅ |
| 卖出信号覆盖 | 0 | ≥3类 | 5类自动检测 ✅ |
| 盈亏比计算 | 0(无止盈) | >0.8 | 0.93~1.32 ✅ |

### 震荡市的审慎设计

当前大盘50分(震荡市), v2输出6只C级+2只D级, 无A/B级信号。**这不是模型失效, 是审慎设计**:
- 震荡市要求3维共振+技术门槛75分, 多数股票达不到
- 300760评估器方向准确率75%(最高), 但v2因技术74<75门槛降C级 → 可能在震荡市过严
- 实战时需结合人工判断微调门槛

### 交付物路径

```
脚本: .\multi_dim_model_v2.py
结果: .\multi_dim_model_v2_results.json
报告: .\<YYYYMMDD>\A股选股模型v2评估报告_<YYYYMMDD>.html
```

### 完整v2模型设计文档

v2 五维框架设计理念、PDF优点审查对比(10项)、各维度子指标评分标准(5类25子项)、市场状态配置参数(4态×5参)、共振评级门禁规则、交叉验证数据分析(8股×3模型)、HTML报告生成细节见 `references/multi-dim-model-v2-design-20260812.md`。

## v2审计教训 — 勿在docstring中声称未实现的功能 (2026-08-12实测)

v2审计发现docstring第12行写"四重风控: 硬止损+信号止损+**跟踪止盈**+**时间止盈**"，但代码中**完全不存在**跟踪止盈(从最高价回落3%卖出)和时间止盈(5日未达目标评估CS)的逻辑。共7项"虚高声明"被审查发现。

**教训**: 策略脚本的docstring/注释中不得声称未实际编写的功能。审计方法: 对docstring中每个功能声称, 在代码中搜索对应的变量名/条件判断/执行逻辑, 找不到则标为"虚高声明"。v3中跟踪止盈真实实现并在回测中触发16次(22.5%), 时间止盈触发1次。

## v3审计→v3.1修复: 8类策略审计问题与修复 (2026-08-13实测)

> v3.1修复完整日志(8项问题+修复代码+OOS衰减率数据)见 `references/v3.1-audit-fixes-20260813.md`

对v3策略做审查发现8项问题(3 HIGH+3 MED+2 LOW), v3.1全部修复(8/8 PASS)。**这是策略审查的标准流程**——审查不仅是找问题, 更要逐项修复并验证。

### 8项审计问题与修复

| # | 严重性 | 问题 | 根因 | v3.1修复 |
|---|:------:|------|------|---------|
| 1 | HIGH | 堆量检测丢失 | v2→v3时FiveDimScorer移除了`is_stack_vol` | 恢复: 5日高位横盘+量>20日均量×1.3+价幅<5% → `anom_s=10` |
| 2 | HIGH | 多仓利用率>100% | `held_total=sum(所有仓位持仓日)/交易日`, 2仓自然>100% | 改为`market_held_days`(有持仓的天数, ≤1/day) + `min(100, ...)硬限制` |
| 3 | HIGH | 方向超额异常(+93pp) | `held_up_days`按仓位数累加, 3仓×3只涨=3而非1 | 改为按总市值涨跌: `today_value > prev_pos_value` |
| 4 | MED | 回测用简化版评分 | `tech_s=35 if MA5>MA10>MA20`一行版 | 升级6因子: MA排列(20)+RSI(15)+量价配合(25)+结构(20)+动量20d/60d(20) |
| 5 | MED | 样本外验证缺席 | 无train/test split | 60/40 split: 前312日样本内→后209日样本外盲测 |
| 6 | MED | 牛市偏差未说明 | docstring仅有通用声明 | 明确标注"2024.12-2026.08主要上升趋势(牛市bias)"+衰减率数据 |
| 7 | LOW | 无时间戳 | 结果不可追溯 | JSON加`run_timestamp`+`version`字段 |
| 8 | LOW | backtest注册虚标 | docstring写"可注册"但未实际import | 改为"设计为可注册,未实际import到backtest_engine" |

### 审计方法论 (可复用于其他策略审查)

```
Phase 1: 交付物完整性 — 6个文件存在性+大小
Phase 2: JSON字段完整性 — 26字段×8股逐项检查
Phase 3: 回测数学一致性 — 年化/利用率/方向超额的合理范围验证
Phase 4: 功能声称vs代码实现 — 对docstring中每个声称在代码中搜索实现
Phase 5: 评分数学正确性 — 重新计算CS=Σ(维度×权重), 对比报告值
Phase 6: 共振计数准确性 — 维度pass/fail vs报告共振数
Phase 7: v2缺陷修复验证 — 逐项检查3个HIGH是否已修复
Phase 8: 综合评级GPA — 10维度×A/B/C/D → GPA/4.0
```

**关键**: 审计不应自我标榜。v3首轮自审GPA=3.70, 但发现8项问题后v3.1修复——**诚实审计的价值在于找问题而非打高分**。

### 样本外验证关键发现 (v3.1新增)

| 配置 | 样本内收益 | 样本外收益 | 衰减率 | 样本外回撤 | 结论 |
|:-----|:---------:|:---------:|:------:|:---------:|:-----|
| MA15单仓 | +83.4% | +24.0% | 28.8% | -21.8% | **过拟合风险** |
| MA20宽离场 | +76.3% | +5.7% | 7.5% | -29.5% | 严重过拟合 |
| **MA15+2仓** | +41.8% | **+36.4%** | **87.1%** | **-12.0%** | **最稳健** |
| MA15+3仓 | +27.8% | +27.4% | 98.6% | -11.1% | 几乎无衰减 |

**核心结论**: MA15单仓衰减率28.8%(过拟合), 但2仓分散87.1%(稳健)。**推荐从MA15单仓改为A+MA15+2仓分散**——这是样本外验证推翻样本内结论的案例。

### 3类回测指标口径Bug (v3.1修复的HIGH-1/2/3)

回测引擎中多仓位指标计算有3类系统性Bug:

1. **利用率累加**: 多仓 `sum(仓位×持仓日)` → 用`market_held_days`(有持仓天数, 每天≤1)
2. **方向超额累加**: 多仓 `held_up_days += 各仓位涨跌` → 按总市值`today_value vs prev_pos_value`
3. **功能退化**: 代码重构时静默移除已有功能(如堆量检测), 需diff审查才能发现

**通用教训**: 多仓位回测的统计指标必须按"总仓位"口径计算, 不能按"单仓位累加"。否则利用率和方向超额在N仓模式下会变成N倍。

## `tencent_kline()` 无法获取指数K线 (2026-08-12实测)

**现象**: `bridge.tencent_kline("sh000001", 521)` 返回空列表(0根K线); `bridge.tencent_kline("000001", 521)` 返回的是**平安银行**(代码000001的股票)而非上证指数。

**根因**: `tencent_kline()` 使用 `ifzq.gtimg.cn/api/app/mkt/kline` 接口, 仅支持个股K线, 不支持指数。指数需要不同的API端点。

**应对**: 用 `web.ifzq.gtimg.cn/appstock/app/fqkline/get` 接口 + curl 获取指数K线:
```bash
curl -s "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,520,qfq" -A "Mozilla/5.0"
```
返回JSON: `{"data":{"sh000001":{"day":[[date,open,close,high,low,vol],...]}}}` 或 `qfqday` 键。用Python解析后可用于回测门控(上证>MA20判断)。

**完整获取+缓存模式**(v3验证): 首次curl获取→存为本地JSON→后续直接读文件避免重复网络请求。

## 工作流: 三方融合选股模型v3 — 多股旋转回测 (2026-08-12实测)

当用户要求"整合v2和旋转模型报告形成v3版本"时, 核心是将**PDF理论+v2截面评估+旋转模型回测**三方优势焊接到一个可运行的Python脚本中。v3设计文档和回测结果见 `references/multi-dim-model-v3-design-20260812.md`。

### v3相对v2的3项HIGH缺陷修复

| v2缺陷 | v3修复 | 验证 |
|--------|--------|------|
| 7项虚高声明(跟踪止盈/时间止盈) | 回测引擎中真实实现 | 跟踪止盈16次;时间止盈1次 ✅ |
| 无回测验证 | 多股旋转回测引擎,12股521日 | +94.3%,71笔交易 ✅ |
| 单日截面评估 | 截面+回测双模式 | 8股截面+12股回测 ✅ |

### 多股旋转回测引擎核心逻辑

旋转模型的核心是: 门控开时→对候选股池逐日评分→满仓持有Top1→破MA15/门控关/出现高出15分新主线时旋转换股。

```python
# v3旋转回测引擎关键参数(实测最优配置)
RotationBacktest(
    exit_line="MA15",         # 离场线: MA10/MA15/MA20, 实测MA15最优(+94.3%)
    rotation_threshold=15,     # 旋转阈值: 新主线高出15分则换股
    num_positions=2,            # 持仓数: 1=单仓, 2=分散(回撤-16.7%)
    initial_cash=1000000,
    commission_rate=0.00025,    # 万2.5双边
    stamp_tax=0.0005,           # 万5卖出
    slippage=0.001              # 0.1%滑点
)
```

### 实测回测结果(12股×521日, 0.2%往返成本, T+1, 复利)

| 配置 | 累计收益 | 年化 | 最大回撤 | 胜率 | 盈亏比 | 资金利用 |
|:-----|:--------:|:----:|:--------:|:----:|:------:|:--------:|
| A+MA15单仓 | +94.3% | +39.3% | -31.6% | 39.4% | 1.65 | 59.7% |
| **A+MA15+2仓** | +91.4% | +38.3% | **-16.7%** | 40.9% | **1.92** | 118.2% |
| A+MA15+3仓 | +81.4% | +34.6% | -13.1% | 41.1% | 1.86 | 174.7% |

**关键发现**: 2仓分散将**回撤减半**(31.6%→16.7%)而收益仅微降2.9pp, 验证了旋转模型建议#3"单仓改2-3只分散"的正确性。

### 离场原因分布(71笔交易)

| 原因 | 次数 | 占比 | 类型 |
|:-----|:----:|:----:|:-----|
| 门控关闭(上证<MA20) | 26 | 36.6% | 防御型 |
| 破MA15 | 22 | 31.0% | 防御型 |
| 跟踪止盈3% | 16 | 22.5% | 利润保护型 |
| 旋转:新主线+15~20分 | 5 | 7.0% | 主动优化型 |
| 时间止盈+更强主线 | 1 | 1.4% | 主动优化型 |

"防御→保护→进攻"完整离场体系。

### 三版本交叉验证方法

```python
# v1/v2/v3分数 vs 评估器方向准确率的Pearson相关性
# v1: r=0.212, v2: r=0.406(+92%), v3: r=-0.131(门控过滤改变分布)
# v3相关性下降是因为门控CLOSED时强制降级, 非评分精度下降
```

### v3交付物

```
脚本: .\multi_dim_model_v3.py (44KB, 1009行)
结果: .\v3_model_results.json (截面8股)
      .\v3_backtest_results.json (回测5配置)
报告: .\20260813\A股选股模型v3评估报告_20260813.html

## 工作流: 周期性盘中提醒部署 — no_agent cron + Windows Toast (2026-08-14实测)

用户要求"周期性提醒最新动向与持股策略"时的标准做法。可复制模板见 `templates/periodic_reminder.py`(改 CODES/LEVELS 即可)。

### 环境前提(Win 桌面,无消息渠道时)
- **AI-Platform 桌面/CLI 会话没有 cron 实时投递通道**: 创建 cron 时 deliver 自动为 `local`,输出只保存不推送;config.yaml 无 bot token(Telegram/微信)时,唯一可靠通知 = **Windows Toast 弹窗**。
- Gateway 必须先跑: `AI-Platform gateway install`(Win 下直接 spawn + 装开机自启项),再 `AI-Platform cron status` 确认 running,否则 cron 不触发。
- 脚本放 `~/AppData/Local/AI-Platform/scripts/`(Windows)或 `~/.AI-Platform/scripts/`(WSL),cron 用脚本名引用。

### 部署步骤
1. 写独立脚本: 腾讯行情直连(qt.gtimg.cn, urllib→curl 双兜底, GBK 解码) → 计算 距止损%/距MA20% → 触发检查(跌破止损/逼近<1%/反抽减仓区/加仓位)→ PowerShell NotifyIcon 弹窗 + print stdout。
2. `cronjob create`: `no_agent=true` + `script=<name>.py` + schedule `*/30 9-11,13-15 * * 1-5`(交易时段每30分钟,含9:00竞价与15:30收盘总结)。任务名标注"弹窗"以区别于旧监控。
3. 验证: 先手动 `python <script>` 确认弹窗与输出 → `cronjob run <job_id>` 触发一次 → `cronjob list` 看 `last_status: ok` 与 `next_run_at`(若 next_run 跳过了临近时点,说明创建时间已过,属正常)。
4. 弹窗函数: PowerShell NotifyIcon, BalloonTip 10s, `Start-Sleep -Seconds 12` 后 Dispose(见模板 `send_windows_toast()`)。

### 陷阱
- **不要用 LLM cron 做周期性推送**: 桌面会话投递永远是 local,白烧 token 且用户看不到。策略判断写死在脚本里(关键价位+触发区间+动作文案),确定性输出,零 token 成本。
- no_agent + 弹窗: stdout 仅存档;真正的通知是脚本自己弹的 Toast(用户不在屏幕前就收不到,需提醒可换渠道)。
- 关键位(止损/MA20/减仓区)来自当日早盘审查,行情变化后需重跑审查更新 LEVELS 常量。
- 部署前先 `cronjob list` 清理旧股票监控任务,避免同标的双提醒。

## 工作流: 持仓双时段审查 cron (09:40 / 13:10, 2026-08-18实测)

用户要求"每天 X:XX / Y:YY 审查持仓股池的综合信息 + 技术指标 + 主力动作 + 评估持仓策略"时的标准部署。比 `templates/periodic_reminder.py`(硬编码 CODES/LEVELS 简版提醒)更完整：**动态读 positions.csv、覆盖全持仓、含技术指标与主力动作推断、输出策略信号**。可复制模板见 `templates/portfolio_review.py`。

### 脚本要点 (templates/portfolio_review.py)
- **动态读持仓**: `a-share-dashboard/data/positions.csv`(code/name/buy_price/qty) → 全池自动纳入，加仓/清仓后无需改脚本
- **实时行情批量**(腾讯 qt.gtimg.cn): p[3]=现价 p[32]=涨跌幅% p[38]=换手 p[49]=量比 p[7]=外盘 p[8]=内盘；urllib→curl 双兜底
- **K线+技术指标**: curl `ifzq.gtimg.cn/.../fqkline/get` 落盘(规避 urllib SSL 挂起) → `sys.path.insert` 指向 Windows a-stocks scripts 后 `from technical_indicators import calc_all`，`tech["latest"]` 出 MA/MACD(MACD红柱=macd_bar)/KDJ(kdj_j)/RSI/BOLL/ATR
- **主力动作推断**(L1无CYQ/资金流时): 量比>1.5+涨=放量偏多 / 量比>1.5+跌=主力杀跌 / 量比<0.8=缩量观望 / 外盘占比判多空拉锯
- **策略信号**: 跌破止损🔴 / 距止损<1%🟠 / KDJ_J<0 勿恐慌割肉 / KDJ_J>95 防回调 / 零轴上方金叉🟢 / 破MA20且乖离>3%🟠 / 浮亏>5%🔴
- **止损常量**: `STOP_LEVELS` dict(来自当日早盘审查，行情后重跑审查更新)；脚本开头声明
- 输出: stdout(存档) + Windows Toast(唯一可见通知)，session 按当前小时判断早盘/午后

### 部署
1. `cp templates/portfolio_review.py ~/AppData/Local/AI-Platform/scripts/portfolio_review.py`，改 STOP_LEVELS(持仓代码/止损)
2. 手动 `python <script>` 跑一次验证输出与弹窗
3. 两个 cron(no_agent, deliver=local, workdir=脚本目录)分开建：
   ```bash
   AI-Platform cron create --name "持仓早盘审查(9:40)"  --script portfolio_review.py --schedule "40 9 * * 1-5"  --no-agent --deliver local --workdir <scripts>
   AI-Platform cron create --name "持仓午后审查(13:10)" --script portfolio_review.py --schedule "10 13 * * 1-5" --no-agent --deliver local --workdir <scripts>
   ```
4. `AI-Platform cron status` 确认 Gateway running；未运行则 `AI-Platform gateway install`(Y启动/n不自启)
5. `cronjob run <job_id>` 手动触发一次验证全链路
6. 与旧 periodic_reminder(每30分钟)重叠时先问是否停旧任务，避免同标的重复弹窗

### 实测价值案例
600276 恒瑞医药成本54.31，审查时已跌破止损53.00(现价52.31) → 脚本正确输出"🔴 跌破止损，纪律性清仓"。这正是双时段审查的核心价值——定时自动盯止损/超买超卖，无需人工盯盘。

## 已知缺陷 #20: 技能文档路径是 WSL 的,Windows 桌面环境需重映射 (2026-08-14实测)

- 文档中的 `SKILL_DIR=./.AI-Platform/...`、`venv_python=python3` 在 Windows 主机(git-bash)不存在;系统 `python`(3.11)通常**无 pandas** → `fetch_realtime.py` 报 ModuleNotFoundError(不是接口故障)。
- Windows 实际路径: `C:\Users\<user>\AppData\Local\AI-Platform\skills\stocks\a-share-data\scripts`。
- **Win 下可靠数据链路(零依赖,全流程可用)**: ① 实时/竞价/五档: `curl "https://qt.gtimg.cn/q=shXXXXXX,..."` GBK 解码直接用(股票字段 p[3]=现价 p[4]=昨收 p[30]=时间);② 日K: `curl "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=shXXXXXX,day,,,140,qfq"` 落盘 JSON,取 `qfqday`/`day` 键,list-of-lists [date,open,close,high,low,vol];③ 技术指标 MA/MACD/KDJ/RSI/BOLL 用零依赖 Python 自算(EMA/RSV 公式 ~40 行)。不依赖技能脚本即可完成完整早盘分析。

## 工作流规范: 报告生成后提问是否弹出在浏览器中显示 (2026-08-26 确立)

当在项目中生成 HTML 报告（如复盘报告、持仓深度审查、选股/换股策略报告）后：
1. **生成并落盘**：将自包含 HTML 报告写入日期目录 `<工作目录>/<YYYYMMDD>/<报告名>.html`；
2. **禁止无提示强制自动弹出**：不直接调用系统命令强行抢占桌面焦点；
3. **主动向用户提问确认**：在会话输出中提供本地文件链接（`file:///...`），并询问：“报告已生成，是否需要在浏览器中弹出查看？”；
4. **用户确认后执行弹出**：当用户回复确认（如“是”、“打开”、“弹出”）时，执行 `cmd.exe /c start "" "<html_path>"` 并在浏览器中呈现。

```
