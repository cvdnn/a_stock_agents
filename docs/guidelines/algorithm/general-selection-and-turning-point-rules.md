# 通用选股体系与早盘拐点触发机制设计规格

> 适用范围：把用户口述的一套具体战法（"20日新高 + 60日线向上 + 放量 + 主力流入"盘后选股 → "大盘站上20日线 + 高开 + 9:30-9:35回调拐点"早盘买入）抽象为**可复用的通用选股体系**，覆盖条件谓词模型、SFTC 五阶段流水线、时点契约与数据就绪矩阵、Stage 0-4 详细规格、策略 YAML Schema 与回测治理口径。
> 核心目标：不把这一套条件写死成一个策略，而是抽象出「条件谓词 + 阶段流水线 + 时点契约」三件套，让用户以后能用一份 YAML 配出新战法；每个条件声明数据依赖并由调度器决定可运行时点，杜绝"盘中现算全市场"类性能陷阱与未来函数。

> **关联代码**：`scripts/core/models/`、`scripts/core/strategy/`、`scripts/core/data/`、`scripts/core/monitor/schedule_gate.py`

---

## 1. 设计目标

1. **通用化**：不把这一套条件写死成一个策略，而是抽象出「条件谓词 + 阶段流水线 + 时点契约」三件套，让用户以后能用一份 YAML 配出新战法。
2. **可工程化**：每个条件都声明数据依赖，由调度器决定它能在哪个时点运行，杜绝"盘中现算全市场"这类性能陷阱。
3. **可标定**：把"卖盘枯竭、买盘增加"这种盘感描述转成可计算、可回测、可调参的复合评分，而不是一句玄学。
4. **不引入未来函数**：明确每个条件的数据就绪时刻，接入现有 `quality_gates.py` 的 `LookaheadGuard`。

---

## 2. 原始条件解构

### 2.1 T日盘后（候选池生成）

| # | 用户原话 | 条件类型 | 形式化表达 | 作用方式 |
|---|---|---|---|---|
| 1 | 收盘价创20日新高 | 位置类 Position | `close_T == max(close[T-19..T])` | 硬过滤 |
| 2 | 股价大于60日均线 | 趋势类 Trend | `close_T > MA60_T` | 硬过滤 |
| 3 | 60日均线向上 | 趋势类 Trend | `MA60_T > MA60_{T-k}` (k 默认 3) | 硬过滤 |
| 4 | 今日成交量大于昨日成交量 | 量能类 Volume | `vol_T > vol_{T-1}` | 硬过滤 |
| 5 | 今日主力资金净流入 | 资金类 Flow | `main_net_inflow_T > 0` | 硬过滤 |
| 6 | 非ST | 结构类 Universe | `not name.matches(r'S?\*?T')` | 硬过滤 |
| 7 | 非北交所 | 结构类 Universe | `code not startswith ('4','8','bj')` | 硬过滤 |
| 8 | 流通市值 > 30亿 | 结构类 Universe | `float_market_cap > 3e9` | 硬过滤 |
| 9 | 剔除当日涨幅 > 7% | 位置类 Position | `change_pct_T <= 7.0` | 硬过滤 |

### 2.2 T+1日早盘（择时执行）

| # | 用户原话 | 阶段 | 形式化表达 | 作用方式 |
|---|---|---|---|---|
| 10 | 大盘要站在20日均线上面，否则不做 | 门禁 | `index_close > index_MA20` | **一票否决** |
| 11 | 9:30 选出高开 1~2% 以上 | 触发-缺口 | `gap_pct = open/pre_close - 1 >= 1.0%` | 硬过滤 |
| 12 | 9:30~9:35 冲高后回调，卖盘枯竭买盘增加的拐点 | 触发-微观 | `ERS_score >= threshold` | 复合评分 |
| 13 | 9:35~9:40 出股票代码 | 交付 | 信号推送 + 下单窗口 | 时点契约 |
| 14 | 盈亏不管，按止损做 | 离场 | 三级止损阶梯 | 风控解耦 |

### 2.3 ⚠️ 原文中的两处自相矛盾（必须确认）

**冲突 A：新高周期到底是 20 日还是 60 日？**
- 公式行写「收盘价创20日新高」，解释行写「创60日新高＋上行阶段」。
- 二者语义差异极大：20日新高是**中短期突破**（约1个月），候选池会有几十只，符合用户"这股票可能很多，有几十支"的描述；60日新高是**中期突破**（约1个季度），候选池通常骤减到个位数，与"几十支"不符。
- **本设计的处理**：默认 `new_high_window = 20`（与"几十支"的规模描述自洽），参数化开放为 20/60/双条件并存（`close 创20日新高 AND close > MA60` —— 注意后者已由条件2覆盖，因此"60日新高"很可能只是用户对"60日均线向上"的口语化重述）。

**冲突 B：高开幅度到底是「1~2% 以上」还是「只要高开都行」？**
- **本设计的处理**：做成两档预设，默认用标准档，并强制加上限护栏。

| 预设 | `gap_min` | `gap_max` | 说明 |
|---|---|---|---|
| 宽松档（"只要高开都行"） | 0.1% | 7.0% | 命中面大，但含大量弱高开与追高陷阱 |
| **标准档（默认）** | **1.0%** | **5.0%** | 对应"高开1~2个百分点以上"，上限防追高 |

> **为什么必须有 `gap_max` 上限护栏**：高开 > 5% 时，(a) 距主板涨停仅 5% 空间，日内可回撤幅度被严重压缩；(b) T+1 制度下当日无法止损，高开越多次日跳空低开亏损越大；(c) 极易遇"高开低走"出货形态，与本战法"回调后拐点买入"的前提（洗盘而非出货）相冲突。上限值需回测标定，5.0% 为工程初值。

---

## 3. 核心抽象：SFTC 五阶段流水线

这是整套体系的骨架。任何"T日选股 + T+1择时"类战法都可以映射到这五个阶段。

```
┌─────────────────────────────────────────────────────────────────┐
│ Stage 0 · Universe Gate  股票域准入                              │
│   时点：T日盘后（可日频缓存，低频变更）                            │
│   性质：静态结构性过滤，与行情信号无关                              │
│   条件：非ST / 非北交所 / 流通市值下限 / 上市天数 / 流动性下限       │
│   产物：Eligible Universe（约 3000-4000 只）                      │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 1 · Signal Screen  信号筛选                                │
│   时点：T日 15:30 之后（日K + 资金流数据就绪）                      │
│   性质：趋势/位置/量能/资金 四类共振                                │
│   条件：N日新高 + MA60之上且向上 + 放量 + 主力净流入 + 涨幅上限       │
│   产物：Candidate Pool（几十只）                                  │
├─────────────────────────────────────────────────────────────────┤
│ Stage 1.5 · Ranking  候选排序截断     ← 新增，工程必需             │
│   时点：紧随 Stage 1                                             │
│   性质：软条件打分排序，取 Top-N                                   │
│   理由：几十只 × tick级监控 超出轮询能力，必须截断到可监控规模        │
│   产物：Watchlist（默认 Top 20，落盘 output/pools/）               │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2 · Regime Gate  大盘环境门禁                              │
│   时点：T日 15:35 预判 + T+1 09:26 竞价后复核（双重校验）           │
│   性质：一票否决（veto），不通过则整日不执行任何买入                  │
│   条件：指数收盘 > 指数 MA20（可选加强：MA20 向上）                 │
│   产物：GO / NO-GO                                               │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓  (仅 GO)
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3 · Opening Trigger  早盘触发                              │
│   窗口：09:30:00 - 09:35:00（软截止 09:34:30）                    │
│   3a 缺口过滤：open/pre_close - 1 ∈ [gap_min, gap_max]           │
│   3b 拐点识别：冲高 → 回调 → ERS 复合评分 ≥ 阈值 + 二次确认         │
│   产物：Buy Signal（股票代码 + 触发价 + 时间戳 + 评分明细）          │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 4 · Risk Exit  风控离场（与入场完全解耦）                     │
│   执行窗口：09:35 - 09:40 下单                                    │
│   约束：T+1 → 当日不可卖，止损最早 T+1 日执行                       │
│   阶梯：-3% 警戒 / -5% 减半 / -8% 无条件出局                       │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 阶段划分的三条设计原则

**原则一：阶段边界由「数据就绪时刻」决定，而非由业务直觉决定。**
条件 5（主力资金净流入）不能在盘中运行 —— 日级主力资金流是收盘后结算数据。条件 11（高开）不能在盘后运行 —— 需要 T+1 的开盘价。把每个条件按数据就绪时刻归入最早可运行阶段，就自然得到了流水线切分。

**原则二：越靠前的阶段，计算量越大、频率越低；越靠后的阶段，标的越少、频率越高。**
Stage 0/1 处理全市场 5000 只，日频一次；Stage 3 只处理 20 只，秒频轮询。这是本战法能在 5 分钟窗口内跑完的**唯一可行架构**。反过来（盘中扫全市场）在时间上不可能。

**原则三：门禁（veto）与过滤（filter）与打分（rank）必须区分。**
- **veto**：不通过则整个策略当日停摆（Stage 2 大盘）。
- **filter**：不通过则该标的出局，其他标的不受影响（Stage 0/1/3a）。
- **rank**：不淘汰，只影响优先级与截断（Stage 1.5）。

现有 `quality_gates.py` 已有 PASSED/WARNING/BLOCKED 三态门禁概念，Stage 2 应复用其语义而非另造一套。

---

## 4. 通用条件谓词模型（Predicate Schema）

这是"通用体系"的核心复用单元。所有选股条件统一抽象为谓词对象。

### 4.1 数据结构定义

```python
# scripts/core/models/predicate.py  (新增)

class ConditionCategory(str, Enum):
    UNIVERSE = "universe"   # 结构性静态：ST/板块/市值/上市天数
    TREND    = "trend"      # 趋势：均线位置、均线方向、多头排列
    POSITION = "position"   # 位置：N日新高/新低、涨幅、回撤深度、缺口
    VOLUME   = "volume"     # 量能：量比、放量、缩量、换手率
    FLOW     = "flow"       # 资金：主力净流入、超大单、北向
    MICRO    = "micro"      # 微观结构：tick方向、委买卖比、拐点
    REGIME   = "regime"     # 大盘环境：指数均线、市场情绪、涨跌家数

class PredicateMode(str, Enum):
    VETO  = "veto"    # 一票否决，作用于全局
    HARD  = "hard"    # 硬过滤，作用于单标的
    SOFT  = "soft"    # 软条件，计入打分
    RANK  = "rank"    # 仅用于排序截断

class Stage(str, Enum):
    S0_UNIVERSE = "stage0_universe"
    S1_SCREEN   = "stage1_screen"
    S15_RANK    = "stage1_5_rank"
    S2_REGIME   = "stage2_regime"
    S3_TRIGGER  = "stage3_trigger"
    S4_EXIT     = "stage4_exit"

class DataDep(str, Enum):
    KLINE_D      = "kline_daily"        # 日K，T日15:05后就绪
    KLINE_MIN    = "kline_minute"       # 分钟K，盘中实时增量
    SNAPSHOT     = "realtime_snapshot"  # 实时快照，~0.1-1s延迟
    AUCTION      = "call_auction"       # 集合竞价 09:15-09:25  ★当前缺失
    TICK         = "tick_detail"        # 成交明细（聚合，非真L2）
    L2_BOOK      = "order_book_5"       # 买卖五档  ★当前未解析
    FUND_FLOW_D  = "fund_flow_daily"    # 日级主力资金流，T日盘后结算
    FUND_FLOW_M  = "fund_flow_minute"   # 分钟级资金流  ★未验证
    FUNDAMENTAL  = "fundamental"        # 流通市值/股本  ★部分缺失
    STATIC_LIST  = "static_stock_list"  # 全市场代码+名称（判ST）
    INDEX_KLINE  = "index_kline"        # 指数日K

@dataclass
class Predicate:
    id: str                        # 唯一标识，如 "close_new_high"
    name_cn: str                   # 中文名，如 "收盘价创N日新高"
    category: ConditionCategory
    mode: PredicateMode
    stage: Stage                   # 最早可运行阶段（由 data_deps 推导校验）
    expr: str                      # 可求值表达式或处理器名
    data_deps: list[DataDep]       # 数据依赖声明 → 驱动调度
    params: dict                   # 可调参数，如 {"window": 20}
    direction: int = 1             # +1 越大越好 / -1 越小越好
    weight: float = 0.0            # SOFT/RANK 模式下的权重
    lookahead_safe: bool = True    # 未来函数安全性标记，交 LookaheadGuard 校验
    degrade_rule: str | None = None  # 数据缺失时的降级策略
    version: str = "1.0.0"
```

### 4.2 谓词的三个派生约束（编译期校验）

**约束 1：`stage` 必须 ≥ `data_deps` 的最早就绪阶段。**
若某谓词声明依赖 `SNAPSHOT` 却被放到 `S1_SCREEN`（盘后），编译器报错。这条规则自动杜绝了"用盘中数据做盘后选股"这类时序错配。

**约束 2：`VETO` 模式谓词只允许出现在 `S2_REGIME`。**
一票否决语义专属大盘门禁，避免业务逻辑里散落各处 veto 造成不可预期的全局停摆。

**约束 3：`lookahead_safe` 必须为 True 才能进入回测通道。**
本战法有一个天然的合法"未来信息"陷阱：Stage 1 用 T日收盘数据，Stage 3 在 T+1 交易 —— 这是合法的。但若回测引擎错误地在 T日 bar 上就用 T日收盘价成交，就构成未来函数。所有 Stage 1 谓词必须打上 `execution_offset = T+1` 标记。

---

## 5. 时点契约与数据就绪矩阵

**这是本设计最关键的工程章节。** 用户描述的战法时间极其紧凑（9:35-9:40 必须出代码），任何数据延迟都会导致战法失效。

### 5.1 数据就绪矩阵

| 数据 | 就绪时刻 | 延迟 | 现有状态 | 用于阶段 |
|---|---|---|---|---|
| 个股日K（OHLCV） | T日 15:05~15:30 | — | ✅ 已有 `data_bridge.py:328` | S0/S1 |
| 指数日K | T日 15:05 | — | ✅ 已有 `data_bridge.py:267` | S2 |
| 日级主力资金流 | T日 **15:30~16:00**（盘后结算） | 分钟级 | ✅ 已有 `fetch_realtime.py:625` | S1 |
| 全市场快照批量 | 实时 | 0.1~1s | ✅ 已有，600只/批×8线程，全市场 3-5s | S2/S3a |
| 1分钟K线 | 09:31 起每分钟 | 1~3s | ✅ 已有 `fetch_realtime.py:167` | S3b |
| tick 成交明细 | 实时 | ~3s（聚合分页） | ✅ 已有 `fetch_realtime.py:1067` | S3b |
| 集合竞价（9:15-9:25） | 实时 | ? | ❌ **缺失 · P0阻塞** | S3a 增强 |
| 买卖五档 | 实时 | ~0.5s | ⚠️ 快照已含但未解析 · P2 | S3b（B2指标） |
| 流通市值/流通股本 | 日频 | — | ❌ **缺失 · P1**（仅有总市值） | S0 |
| ST 标记 | 日频 | — | ⚠️ 仅能靠名称正则 · P1 | S0 |
| 分钟级资金流 | 盘中 | 未验证 | ⚠️ **未验证 · P1** | S3b 增强 |

### 5.2 时点契约表（Timing Contract）

| 时刻 | 动作 | 依赖数据 | 产物 | 硬约束 |
|---|---|---|---|---|
| **T日 15:30** | 启动 Stage 0 + 1 | 日K、资金流、静态列表 | 原始候选集 | 资金流须待盘后结算完成，**不可早于 15:30** |
| T日 15:35 | Stage 1.5 排序截断 | 同上 | Watchlist Top-N | 落盘 `output/pools/` |
| T日 15:40 | Stage 2 大盘预判 | 指数日K | GO/NO-GO 预估 | 仅预判，供用户睡前决策 |
| **T+1 09:26** | Stage 2 门禁复核 | 指数实时快照 | **GO/NO-GO 终判** | 竞价结束后、开盘前完成，NO-GO 则终止全流程 |
| T+1 09:25 | （可选）竞价异动预筛 | 集合竞价数据 | 优先级重排 | ★ 依赖 P0 缺口补齐 |
| **T+1 09:30:00** | Stage 3a 缺口过滤 | 全市场快照（仅N只） | 高开票子集 | 须在 09:30:05 内完成 |
| T+1 09:30-09:35 | Stage 3b 拐点识别 | 1分钟K + tick + 五档 | ERS 评分流 | 秒级轮询，N≤20 只 |
| **T+1 09:34:30** | 软截止 | — | 停止接受新信号 | 此后触发的拐点作废（无下单时间） |
| T+1 09:35-09:40 | Stage 4 下单 | 信号 + 账户状态 | 成交回报 | 下单窗口 |
| T+1 全天 | 持仓监控 | 实时快照 | 风控状态 | 仅记录，**T+1不可卖** |
| T+2 09:30 | 止损执行 | 实时快照 | 卖出 | 最早可执行止损时点 |

### 5.3 由时点契约推导出的三条架构铁律

**铁律一：T日盘后必须落盘，T+1 盘中禁止全市场扫描。**
9:30:00 到 9:30:05 之间要完成缺口过滤，全市场扫描需 3-5s，勉强可行但无冗余；而 9:30-9:35 的 tick 级监控若覆盖 5000 只则完全不可能。因此 Watchlist **必须**在 T日盘后落盘为 CSV，盘中只加载这 ≤20 只。这也正是现有 `pool_schema.py` 关注池的设计用途。

**铁律二：主力资金流决定了 Stage 1 不能早于 15:30。**
用户说"下午，或下午的3点后开始执行" —— 这个直觉是对的，但要精确到 **15:30 之后**，因为日级主力资金流是盘后结算数据，15:00 收盘瞬间拿到的可能是残缺值。建议默认调度时刻 **15:35**，并加入数据完整性校验（若资金流字段为空则重试而非当作 0）。

**铁律三：大盘门禁必须双时点校验。**
T日盘后用 T日收盘价预判（给用户睡前参考），T+1 09:26 用竞价后的实时指数终判（因为隔夜可能有利空导致低开跌破 MA20）。**只有终判有效**。仅做盘后预判会漏掉隔夜跳空风险。

---

## 6. Stage 0-2 详细规格

### 6.1 Stage 0 · Universe Gate

| 谓词 id | 条件 | 默认参数 | 数据依赖 | 现状 |
|---|---|---|---|---|
| `not_st` | 非 ST/*ST/退市整理 | 名称正则 `r'^\*?S?T\b\|退$'` | STATIC_LIST | ⚠️ 需补 |
| `not_bse` | 非北交所 | 排除 `4*/8*/bj*` 前缀 | STATIC_LIST | ✅ 已有 `config.py:128` |
| `float_cap_min` | 流通市值下限 | `>= 30亿` | FUNDAMENTAL | ❌ **需补** |
| `listed_days_min` | 上市天数下限（建议新增） | `>= 60日` | STATIC_LIST | 建议加：次新股无 MA60 |
| `liquidity_min` | 日均成交额下限（建议新增） | `>= 5000万`（20日均） | KLINE_D | 建议加：防僵尸票 |
| `price_band` | 股价区间（建议新增） | `>= 2.0 元` | KLINE_D | 建议加：防仙股 |

> **为什么条件 3「MA60 向上」隐含要求上市 ≥ 60 日**：次新股无 60 根日K，MA60 计算会返回 NaN。现有 `pv_factors.py` 的 `_sma` 对不足窗口的处理需确认，否则会产生静默的错误信号。建议 Stage 0 直接挡掉，比在 Stage 1 处理 NaN 更安全。

> **流通市值 vs 总市值**：用户明确要求"流通市值 > 30亿"。现有数据层只有总市值（`data_bridge.py:255` 的 `market_cap`）。**用总市值替代会放宽条件**（总市值 ≥ 流通市值），导致纳入限售股占比高的票 —— 这类票实际流通盘小、易被操纵，与本战法"选流动性好的强势票"意图相悖。因此列为 P1 必补项，不建议用总市值降级替代。

### 6.2 Stage 1 · Signal Screen

| 谓词 id | 条件 | 默认参数 | 实现要点 |
|---|---|---|---|
| `close_new_high` | 收盘价创N日新高 | `window=20` ★待确认 | `close_T >= max(close[T-19..T])`，用 `>=` 而非 `>`（当日自身即高点） |
| `above_ma60` | 收盘价在60日线上 | `ma_window=60`, `buffer=0%` | `close_T > MA60_T`；建议加 `buffer` 参数容错 |
| `ma60_rising` | 60日线向上 | `slope_lookback=3`, `min_slope=0` | `MA60_T > MA60_{T-3}`；见下方斜率口径讨论 |
| `volume_expand` | 今日量 > 昨日量 | `ratio_min=1.0` | `vol_T / vol_{T-1} > ratio_min`；建议加**量比下限**（如 `vol_T/MA5(vol) > 1.2`）过滤"昨日缩量导致的假放量" |
| `main_inflow` | 主力净流入为正 | `> 0` | 建议改为**净流入占成交额比例** `> 0`，避免大市值票的绝对值偏差 |
| `change_pct_cap` | 当日涨幅上限 | `<= 7.0%` ★板块差异化待确认 | 见下方讨论 |

#### 关于 `ma60_rising` 的斜率口径

"60日均线向上"有三种常见实现，语义强度递增：

| 口径 | 表达式 | 特点 |
|---|---|---|
| A. 单点比较（默认） | `MA60_T > MA60_{T-3}` | 宽松，短期抖动即通过 |
| B. 连续比较 | `MA60_T > MA60_{T-1} > MA60_{T-2}` | 严格，要求连续3日上行 |
| C. 归一化斜率 | `(MA60_T - MA60_{T-5}) / MA60_{T-5} / 5 > θ` | 可跨股价比较，θ 可标定 |

**建议默认 A**（与用户"60日均线向上"的字面表述一致），但**把 C 作为 Stage 1.5 的排序因子** —— 斜率越陡说明趋势动能越强，用于 Top-N 截断时优先保留。

#### 关于 `change_pct_cap = 7%` 的板块差异化问题

用户要求"剔除当日涨幅在7%以上的股票"。其意图是**避免追高、避免次日一字板买不进**。但 A股涨跌幅限制分板块不同：

| 板块 | 涨跌幅限制 | 7% 阈值的含义 |
|---|---|---|
| 主板（60/00） | ±10% | 剩余空间 3%，合理 |
| 创业板（300）/科创板（688） | ±20% | 剩余空间 13%，**阈值偏严，会误杀大量正常强势票** |
| 北交所 | ±30% | 已在 Stage 0 剔除 |

**处理建议**：默认统一 7%（尊重用户原话），但参数化为 `change_pct_cap_by_board: {main: 7.0, gem: 7.0, star: 7.0}`，并在实施进度看板中列为待确认项 —— 是否对 20cm 板块放宽到 12%~15%。**这是一个会显著改变候选池构成的决策，不应由实现方擅自决定。**

### 6.3 Stage 1.5 · Ranking（新增阶段，工程必需）

**为什么必须新增**：用户预期候选池"几十支"。若全部进入 Stage 3 的 tick 级监控，按每只 3s 轮询一次 tick + 每分钟一次 K线，几十只的并发请求量会触发数据源限流（现有 `fetch_realtime.py:83` 的重试策略在 429 下会退避，导致信号延迟）。必须截断到 **Top 20**。

**排序因子设计**（全部为 T日盘后可算，`RANK` 模式）：

| 因子 id | 计算 | 方向 | 权重 | 理由 |
|---|---|---|---|---|
| `breakout_strength` | `(close_T - max(high[T-20..T-1])) / pre_close` | + | 20% | 突破幅度越大，新高越"实"（非擦线新高） |
| `ma60_slope_norm` | 归一化 MA60 斜率（口径C） | + | 20% | 中期趋势动能 |
| `volume_quality` | `vol_T / MA5(vol)` | + | 15% | 放量强度，非仅"比昨天多" |
| `inflow_intensity` | `main_net_inflow / amount` | + | 20% | 资金流入的相对强度，跨市值可比 |
| `change_pct_sweet` | 涨幅落在 [3%, 6%] 得满分，两端线性衰减 | 钟形 | 15% | 涨幅太小动能不足，太大追高风险 |
| `float_cap_score` | 流通市值在 [30亿, 300亿] 得满分 | 钟形 | 10% | 太小易操纵，太大弹性不足 |

> 权重为工程初值，**必须经回测标定**（见第 10 章）。禁止直接用于实盘。

### 6.4 Stage 2 · Regime Gate（一票否决）

**默认口径**：上证综指 `sh000001` 的 `close > MA20`。

**建议增强为可配置的多指数投票**：

```yaml
regime_gate:
  mode: all_of          # all_of | any_of | weighted_vote
  indices:
    - {code: sh000001, name: 上证综指, weight: 1.0, required: true}
    - {code: sz399006, name: 创业板指, weight: 0.5, required: false}
  conditions:
    - id: index_above_ma20
      expr: "close > MA(close, 20)"
      mode: veto
    - id: index_ma20_rising      # 可选加强项，默认关闭
      expr: "MA(close,20)_T > MA(close,20)_{T-3}"
      mode: veto
      enabled: false
  check_points:
    - {at: "T 15:40",  type: preview,   data: index_kline_daily}
    - {at: "T+1 09:26", type: final,    data: index_snapshot_realtime}  # 唯一有效判定
```

**与现有代码的关系**：`market_assessor.py` 已有五维健康度模型（趋势30% + 情绪20% + 量能20% + 结构15% + 资金15%），其中趋势维度已用 MA20。
- **不要直接复用五维总分作为门禁** —— 用户的门禁是单一、明确、可解释的（"站上20日线"），五维加权分会稀释这个信号，且难以向用户解释"为什么今天不做"。
- **正确做法**：Stage 2 用独立的单条件 veto；五维健康度作为**附赠信息**展示给用户（"门禁通过，但市场情绪偏弱，建议减半仓"），不参与否决。

---

## 7. Stage 3 · 早盘触发详细规格

### 7.1 Stage 3a · 缺口过滤（09:30:00 - 09:30:05）

```
输入：Watchlist（≤20只，T日盘后落盘）
动作：批量快照（单次请求即可覆盖20只，<1s）
计算：gap_pct = (open_T+1 / close_T - 1) × 100
过滤：gap_min <= gap_pct <= gap_max
输出：GapPassed 子集（预期 5-12 只）
```

**可选增强（依赖 P0 竞价数据缺口）**：在 09:25 竞价结束时预筛，用竞价量/竞价金额占流通市值比判断"高开是否有资金支撑"，剔除"无量虚高开"。这能提前 5 分钟缩小监控范围，是显著优化，但**当前数据层不支持**，列为二期。

### 7.2 Stage 3b · 拐点识别：ERS 复合评分模型

这是把用户的"细微感受 —— 卖盘枯竭、买盘增加的拐点"转为可计算信号的核心。**设计要点：不是一个指标，而是三组指标的综合评分，且要求多组同时达标，防止单侧偏科误判。**

#### 7.2.1 个股日内阶段划分

```
09:30:00  open
   ↓      冲高段 (Rally)：价格从 open 上行至局部高点 P_peak
   ↓      识别条件：连续 2 根 tick/1分钟K 未创新高
P_peak
   ↓      回调段 (Pullback)：价格从 P_peak 回落至局部低点 P_low
   ↓      识别条件：见下方 A/B/C 三组指标
拐点 →    买入触发
```

**关键约束**：
- 冲高段必须**真实存在**：`P_peak / open - 1 >= 0.5%`（默认），否则不构成"冲高后回调"形态，直接跳过该股。
- 回调段起点 P_peak 需经 2 根 bar 确认，因此最早可能触发时刻约 **09:31:30**（1分钟K口径）或 **09:30:40**（tick口径）。
- 若开盘即最高、全程单边下行（高开低走），**不触发** —— 这类形态是出货，不是洗盘。这条规则是本战法最重要的自我保护。

#### 7.2.2 A组：卖盘枯竭分（Exhaustion，满分 40）

| 指标 | 计算方式 | 满分条件 | 权重 | 数据依赖 |
|---|---|---|---|---|
| **A1** 主动卖量衰减 | `S_vol(最近30s) / S_vol(前30s)` | ≤ 0.6 | 12 | TICK |
| **A2** 缩量回调 | `avg_vol(回调段每分钟) / avg_vol(冲高段每分钟)` | ≤ 0.5 | 10 | KLINE_MIN |
| **A3** 跌幅收窄 | 回调段连续 1分钟K 实体 `\|Δ\|` 递减根数 | ≥ 2 根 | 8 | KLINE_MIN |
| **A4** 卖单笔数衰减 | `S_count(最近30s) / S_count(前30s)` | ≤ 0.7 | 6 | TICK |
| **A5** 无大单砸盘 | 回调段是否存在单笔 `S_vol > 5 × 当日均笔量` | 不存在 | 4 | TICK |

> **A2「缩量回调」是这组指标的灵魂**：价格下跌但成交量萎缩，说明抛压在自然衰竭而非有资金出逃。这与"放量下跌"（真出货）形成鲜明对比，是区分洗盘/出货最有效的单一指标。

#### 7.2.3 B组：买盘增强分（Absorption，满分 40）

| 指标 | 计算方式 | 满分条件 | 权重 | 数据依赖 | 现状 |
|---|---|---|---|---|---|
| **B1** 主动买量回升 | `B_vol(最近30s) / B_vol(前30s)` | ≥ 1.5 | 12 | TICK | ✅ |
| **B2** 委买卖比回升 | `bid_vol(1-5) / ask_vol(1-5)` 从回调低点回升幅度 | ≥ +50% | 10 | L2_BOOK | ❌ **缺失** |
| **B3** 下方承接 | P_low 附近 ±0.2% 区间内的连续 B 单笔数 | ≥ 3 笔 | 8 | TICK | ✅ |
| **B4** VWAP 之上 | `current_price > 当日VWAP` | 成立 | 6 | KLINE_MIN | ✅ |
| **B5** tick 净买比转正 | `(B-S)/(B+S)`，最近 20 笔 | > 0 | 4 | TICK | ✅ |

**B2 缺失时的降级规则**（必须实现，否则模型跑不起来）：
```
若 L2_BOOK 不可用：
  B组满分 = 30（而非 40）
  ERS 总分满分 = 90
  触发阈值等比折算：threshold_effective = threshold_base × (90/100)
  即默认 65 → 58.5，取 59
  同时在信号输出中标注 "degraded: no_order_book"
```
> **五档数据其实"部分有"**：腾讯快照 `parts[9-28]` 已包含五档买卖价量，只是 `_parse_tencent_quote` 当前未解析这些字段。**补齐成本很低，建议优先做**，它直接决定 B2 这个 10 分指标能否启用。

#### 7.2.4 C组：形态位置分（Structure，满分 20）

| 指标 | 计算方式 | 满分条件 | 权重 | 性质 |
|---|---|---|---|---|
| **C1** 回调不破开盘价 | `P_low > open` | 成立 | 8 | **硬条件（不满足直接否决）** |
| **C2** 回调深度合理 | `retrace = (P_peak-P_low)/P_peak` | ∈ [1.0%, 3.5%] | 6 | 软条件 |
| **C3** 缺口回补约束 | `P_low > close_T × (1 + gap_pct×0.5)` | 成立（回补不超一半） | 4 | 软条件 |
| **C4** 时间有效性 | 拐点时刻 | ∈ [09:31:00, 09:34:30] | 2 | 硬条件 |

> **C2 的钟形约束很重要**：回撤 < 1% 说明根本没洗盘，回调太浅后续动能存疑；回撤 > 3.5% 说明抛压过重，可能已转为出货。区间需回测标定。
>
> **C3 的缺口保护**：高开缺口被完全回补 = 高开失败，是明确的弱势信号。要求最多回补一半。

#### 7.2.5 触发判定逻辑

```python
def check_trigger(stock, bars_min1, ticks, book) -> Signal | None:
    phase = detect_phase(bars_min1)          # RALLY / PULLBACK / NONE
    if phase != "PULLBACK":
        return None
    if not rally_valid(stock):               # 冲高段必须真实存在
        return None

    A = score_exhaustion(ticks, bars_min1)   # 0-40
    B = score_absorption(ticks, bars_min1, book)  # 0-40 或降级 0-30
    C, c_hard_ok = score_structure(stock, bars_min1)  # 0-20 + 硬条件

    if not c_hard_ok:                        # C1/C4 任一不满足 → 否决
        return None

    total_max = 100 if book else 90
    threshold = BASE_THRESHOLD * total_max / 100   # 默认 65 → 降级 59

    ers = A + B + C
    if ers < threshold:
        return None
    if A < A_MIN or B < B_MIN:               # 双侧达标，防单侧偏科（默认各 20）
        return None

    # 二次确认：ERS 首次达标后，等下一根1分钟K确认
    if not pending_confirm(stock):
        mark_pending(stock, ers)
        return None
    if not confirm_bar(stock):               # 收阳 OR 高点 > 前一根高点
        return None

    return Signal(code=stock.code, price=current_price, ts=now(),
                  ers=ers, detail={A, B, C}, degraded=(book is None))
```

**三个防误判设计的必要性**：

1. **双侧达标（A≥20 且 B≥20）**：若只要求总分，则可能"卖盘枯竭满分 + 买盘毫无动静"也达标 —— 那是阴跌无人接盘，不是拐点。
2. **二次确认（等下一根1分钟K）**：ERS 达标瞬间价格可能仍在下跌途中，抓在半山腰。等待"收阳或突破前一分钟高点"再确认，牺牲一点入场价换取显著胜率提升。代价是延迟最多 60s，仍在 09:35 窗口内。
3. **冲高段有效性前置校验**：直接排除高开低走的出货形态。

### 7.3 监控调度设计

```
09:29:50  预加载 Watchlist，建立快照连接池
09:30:00  Stage 3a 批量快照 → GapPassed 子集（5-12只）
09:30:00  启动 N 个并行监控协程（每只一个）
          每只轮询：tick 每 3s / 1分钟K 每 60s / 快照每 1s
09:30-09:34:30  持续 ERS 评分，命中即推送 + 记录
09:34:30  软截止，停止接受新信号
09:35:00  硬截止，输出最终信号清单
09:35-09:40  下单窗口（对接 astock-trade-paper 模拟盘）
```

**限流保护**：20 只 × 3s tick 轮询 ≈ 6.7 req/s，在腾讯源可承受范围内。若 GapPassed > 20 只，按 Stage 1.5 排序取前 20，其余记录为"未监控"（不可静默丢弃，须在日志中体现）。

---

## 8. Stage 4 · 风控离场：⚠️ T+1 制度带来的根本性约束

**这是本设计必须向用户明确指出的最重要问题。**

用户原话：「至于后面的盈亏，这都不要管了。这个是按照止损来做的。」

**但 A股 T+1 交易制度下，09:35 买入的股票当日不可卖出。** 这意味着：
- `-3% / -5% / -8%` 三级止损阶梯在**买入当日完全无法执行**；
- 最早可执行止损的时点是 **T+2 日 09:30**；
- 若 T+1 日尾盘大幅跳水，或 T+2 日跳空低开，实际亏损可能**远超 -8% 绝杀线**（跳空缺口无法用止损单规避）。

### 8.1 因此止损体系必须重构为「双层」

**第一层：当日仓位控制（可执行）**
| 机制 | 规则 |
|---|---|
| 单票仓位上限 | **主板 ≤ 15%、创业/科创 ≤ 8%**（沿用 `strategy_cmds.py:397` 既有约定，最终取值口径见实施进度看板 Q12）；因当日不可止损，不采用更宽松的 20% |
| 同日总建仓上限 | 默认 ≤ 40% 总资金，最多同时持有 3 只本战法标的 |
| 大盘弱势降档 | Stage 2 通过但五维健康度 < 60 分时，仓位减半 |
| 高开幅度反向调节 | `gap_pct` 越大，单票仓位越小（跳空风险越高） |

**第二层：次日止损执行（真正的止损）**
| 阶梯 | 触发 | 动作 | 执行时点 |
|---|---|---|---|
| T0 警戒 | 浮亏 -3% | 标记，准备减仓 | T+1 日内监控（仅记录） |
| T1 减仓 | 浮亏 -5% | 减仓 50% | **T+2 09:30 开盘执行** |
| T2 绝杀 | 浮亏 -8% | 清仓 | **T+2 09:30 开盘执行** |
| **T-Gap 跳空止损（新增）** | T+2 开盘价已低于 -8% 线 | **无条件开盘价清仓，不等反弹** | T+2 09:30:00 |
| **T-Time 时间止损（新增）** | T+2 收盘仍未盈利 | 清仓（本战法是超短线，不养套牢票） | T+2 14:50 |

> **T-Gap 跳空止损是必须新增的规则**：现有 `position_stop_monitor.py` 的三级阶梯假设"价格触及止损线时即可成交"，但跳空低开时开盘价已远低于止损线，若不明确"以开盘价无条件出局"，会产生"等反弹回本"的危险行为。
>
> **T-Time 时间止损同样必要**：本战法的逻辑基础是"强势票回调后立即重拾升势"。若次日仍未盈利，说明拐点判断错误，逻辑已失效，不应继续持有。

### 8.2 保本价核算

沿用项目现有铁律（`docs/trading/breakeven-rules.md`）：印花税 0.05% + 佣金万2.5（最低5元）+ 过户费，`math.ceil` 向上进位至分位，禁止四舍五入。调用 `astock-action-execution` 技能，不重复实现。

### 8.3 ⚠️ 调研中发现的既有口径矛盾（须先解决再开发）

核对现有代码时发现，项目里**同时存在两套不一致的止损定义**，会导致本战法的 Stage 4 无所适从：

| 位置 | T1 减仓线定义 | T2 绝杀线定义 |
|---|---|---|
| `AGENTS.md` 实战三原则 / `model_cmds.py:421` | 浮亏 **-5%** | 浮亏 **-8%** |
| `risk_manager.py:26-27` | **MA10 下方 2%**（收盘跌破减半） | **MA20 下方 2%**（收盘跌破清仓） |
| `risk_position_manager.py:218` | — | 硬止损 **-6.0%** |

三者互不兼容：`-8%`、`MA20-2%`、`-6%` 在同一笔持仓上会给出不同的清仓时点。

**本设计的处理**：
- Stage 4 的止损阶梯**显式写入策略 YAML**（见第 9 章 `stop_ladder`），不继承任何全局默认值 —— 即本战法自带止损定义，与全局口径解耦；
- 同时把"统一全局止损口径"列为独立的 **P0 技术债**，须在 Stage 4 开发前由用户裁决以哪套为准；
- 本战法建议采用**固定百分比口径（-3/-5/-8）而非均线口径**。理由：均线止损依赖收盘价确认（`risk_manager.py` 明确写"收盘跌破"），而本战法是 09:35 入场的超短线，等收盘确认等于放任日内亏损扩大，与"当日不可止损"的 T+1 约束叠加会造成不可控回撤。

> **注意 `strategy_cmds.py:397` 已有板块差异化风控意识**：`standard_board_cap: {mainboard: 0.15, gem_star: 0.08}` —— 主板仓位上限 15%、创业/科创 8%。这比本文 8.1 的"单票 20%"**更保守**。建议直接复用该既有约定而非另立标准，并据此把 8.1 的单票上限下调至 15%（主板）/ 8%（20cm 板块）。

---

## 9. 配置化：策略 YAML Schema

把上述全部机制收敛为一份可配置描述，实现"改参数不改代码"。

```yaml
# config/strategies/opening_pullback_reversal.yaml
strategy:
  id: opening_pullback_reversal
  name_cn: 早盘高开回调拐点战法
  version: 1.0.0
  stage: RESEARCH              # RESEARCH → BACKTESTED → PRODUCTION
  author: user_defined
  description: T日盘后筛选强势突破票，T+1早盘于高开回调拐点介入的超短线战法

  stage0_universe:
    refresh: daily_postclose
    cache_ttl: 86400
    predicates:
      - {id: not_st,          mode: hard, params: {pattern: '^\*?S?T\b|退$'}}
      - {id: not_bse,         mode: hard, params: {prefixes: ['4','8','bj']}}
      - {id: float_cap_min,   mode: hard, params: {min: 3.0e9}}
      - {id: listed_days_min, mode: hard, params: {min: 60}}
      - {id: liquidity_min,   mode: hard, params: {min_amount_20d: 5.0e7}}
      - {id: price_band,      mode: hard, params: {min: 2.0}}

  stage1_screen:
    run_at: "T 15:35"
    data_readiness_check: true   # 资金流为空则重试，不当作0
    predicates:
      - id: close_new_high
        mode: hard
        params: {window: 20}          # ★ 待确认：20 还是 60
      - id: above_ma60
        mode: hard
        params: {ma_window: 60, buffer_pct: 0.0}
      - id: ma60_rising
        mode: hard
        params: {slope_lookback: 3, method: point_compare}
      - id: volume_expand
        mode: hard
        params: {dod_ratio_min: 1.0, vol_ratio_5d_min: 1.2}
      - id: main_inflow
        mode: hard
        params: {metric: inflow_over_amount, min: 0.0}
      - id: change_pct_cap
        mode: hard
        params: {main: 7.0, gem: 7.0, star: 7.0}   # ★ 待确认板块差异化

  stage1_5_rank:
    top_n: 20
    persist_to: output/pools/watch_opening_reversal.csv
    factors:
      - {id: breakout_strength, weight: 0.20}
      - {id: ma60_slope_norm,   weight: 0.20}
      - {id: volume_quality,    weight: 0.15}
      - {id: inflow_intensity,  weight: 0.20}
      - {id: change_pct_sweet,  weight: 0.15, params: {lo: 3.0, hi: 6.0}}
      - {id: float_cap_score,   weight: 0.10, params: {lo: 3.0e9, hi: 3.0e10}}

  stage2_regime:
    check_points: [{at: "T 15:40", type: preview}, {at: "T+1 09:26", type: final}]
    mode: all_of
    indices:
      - {code: sh000001, required: true}
      - {code: sz399006, required: false, weight: 0.5}
    predicates:
      - {id: index_above_ma20, mode: veto, params: {ma_window: 20}}
      - {id: index_ma20_rising, mode: veto, enabled: false}
    advisory: market_assessor_5dim   # 仅提示，不否决

  stage3_trigger:
    window: {start: "09:30:00", end: "09:35:00"}
    soft_cutoff: "09:34:30"
    max_concurrent_monitor: 20
    gap_filter:
      preset: standard               # strict | standard | loose
      presets:
        strict:   {gap_min: 2.0, gap_max: 4.0}
        standard: {gap_min: 1.0, gap_max: 5.0}   # 默认
        loose:    {gap_min: 0.1, gap_max: 7.0}   # "只要高开都行"
    rally_validity:
      min_rally_pct: 0.5             # 冲高段最小幅度
      peak_confirm_bars: 2
    ers_model:
      base_threshold: 65
      a_min: 20                      # 卖盘枯竭分下限
      b_min: 20                      # 买盘增强分下限
      degrade_when_no_book: true     # 五档缺失时满分90、阈值折算59
      require_second_confirm: true
    structure_hard:
      - {id: not_break_open,  required: true}   # C1
      - {id: time_valid,      required: true}   # C4
    retrace_band: {min_pct: 1.0, max_pct: 3.5}  # C2
    gap_fill_max_ratio: 0.5                     # C3

  stage4_exit:
    order_window: {start: "09:35:00", end: "09:40:00"}
    t1_constraint: true              # ★ 标记本策略受T+1约束
    intraday_controls:
      single_position_max_pct: 20
      daily_total_max_pct: 40
      max_concurrent_holdings: 3
      weak_market_halve_below: 60    # 五维健康度低于60则减半
      gap_inverse_sizing: true
    stop_ladder:
      - {level: T0, drawdown_pct: -3, action: alert}
      - {level: T1, drawdown_pct: -5, action: reduce_50, exec: next_open}
      - {level: T2, drawdown_pct: -8, action: clear,     exec: next_open}
      - {level: T_GAP,  condition: open_below_stop, action: clear_at_open, exec: next_open_immediate}
      - {level: T_TIME, condition: not_profitable_by_close, action: clear, exec: t2_1450}
    breakeven: {skill: astock-action-execution, round: ceil_to_cent}
```

---

## 10. 回测、标定与过拟合防护

### 10.1 哪些参数是"拍脑袋"的，必须标定

本设计中以下参数为工程初值，**未经数据验证，禁止直接实盘**：

| 参数 | 初值 | 标定方法 |
|---|---|---|
| `ers.base_threshold` | 65 | 网格搜索 [50, 80]，以胜率×盈亏比为目标 |
| `ers.a_min / b_min` | 20 / 20 | 同上，二维网格 |
| `retrace_band` | [1.0%, 3.5%] | 统计历史回调深度分布，取 P20-P80 |
| `gap_max` | 5.0% | 分组统计不同高开幅度的次日收益 |
| `top_n` | 20 | 权衡信号覆盖率与限流风险 |
| Stage 1.5 六因子权重 | 见 6.3 | 滚动 IC 加权（复用 `factor_synthesizer.py`） |
| `change_pct_sweet` | [3%, 6%] | 分组统计 |

### 10.2 回测的特殊难点（须提前设计，否则回测结果不可信）

**难点一：分钟级/tick 级历史数据缺失。**
现有 `Ashare.get_price(freq='5m', count=320)` 只能取约 320 根 5分钟K（覆盖近期），**没有 1分钟K 和 tick 的历史归档**。这意味着 Stage 3b 的 ERS 模型**无法用历史数据回测**。

**解决方案（必须二选一或并行）**：
1. **前向采集（Forward Collection）**：从上线日起，每日盘中自动归档 Watchlist 的 1分钟K + tick 到 `output/cache/intraday/`。积累 40-60 个交易日后才能开始标定。**这是唯一严谨的路径，但需要等待期。**
2. **降级代理回测**：用 5分钟K 近似 1分钟K 回测 ERS（时间粒度粗 5 倍，会显著高估信号质量）。仅用于**排除明显错误的参数区间**，不可用于确定最优参数，且必须在报告中标注"代理回测，结论不可直接实盘"。

**难点二：Stage 1 的未来函数风险。**
T日盘后选股 + T+1 成交是合法的，但回测引擎若在 T日 bar 上以 T日收盘价成交即构成未来函数。必须强制 `execution_offset = T+1`，且成交价用 **T+1 的 09:35 触发价**（而非 T+1 收盘价），否则严重高估收益。

**难点三：滑点与手续费敏感性。**
超短线 + 9:35 集中下单，滑点影响极大。回测必须计入：佣金万2.5（最低5元）+ 印花税 0.05%（卖出）+ 过户费 + **冲击滑点（建议 ≥ 0.2%，早盘波动大时应更高）**。复用现有 `paper_trading` 的滑点模型。

### 10.3 接入现有治理门禁

上线前必须通过 `quality_gates.py` 的三道校验：
- `LookaheadGuard`：验证所有 Stage 1 谓词的 `execution_offset = T+1`；
- `AShareComplianceGuard`：验证 T+1 约束、涨跌幅限制、停牌处理；
- `OverfittingGuard`：ERS 模型有 14 个可调指标 + 7 个待标定参数，**过拟合风险极高**。要求样本外（Out-of-Sample）胜率不低于样本内的 70%，否则判定过拟合。

---

## 附录 A：术语对照

| 术语 | 含义 |
|---|---|
| SFTC | Screen–Filter–Trigger–Control，本文提出的五阶段流水线抽象 |
| Predicate（谓词） | 单个可判定的选股条件，体系的最小复用单元 |
| ERS | Exhaustion-Reversal Score，卖盘枯竭-买盘反转复合评分 |
| VETO | 一票否决模式，作用于全局而非单标的 |
| Watchlist | Stage 1.5 产出的 Top-N 监控清单，T日盘后落盘 |
| 时点契约 | 各阶段绑定执行窗口与数据就绪时刻的约束表 |
| T-Gap | 跳空止损：次日开盘已破止损线则无条件开盘价出局 |
| T-Time | 时间止损：次日收盘仍未盈利则清仓 |

---
## 附：关联索引
- 实施进度看板：[`general-selection-and-turning-point-plan.md`](../specs/algorithm/general-selection-and-turning-point-plan.md)
- 系统建设规范：[`selection-system-specification.md`](./selection-system-specification.md)
- 算法治理规范：[`algorithm-governance.md`](./algorithm-governance.md)