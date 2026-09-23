# 智能选股系统 · 选股模型通用设计规范 (Selection Model General Specification)

> 文档 ID：`SPEC-ALGO-003` · 家族定位：选股模型定义规范的**通用维度**，与[《智能选股系统 · 模型类型设计规范》](./selection-model-types-specification.md)（`SPEC-ALGO-ISS-MT-001`，类型维度）并列，共同隶属于[《智能选股系统 · 功能建设规范》](./selection-system-specification.md)（`SPEC-ALGO-ISS-001`）。
> 适用范围：把「T日盘后选股 → T+1 早盘择时触发」这一类战法抽象为**可复用的通用选股模型**，覆盖条件谓词模型、SFTC 五阶段流水线、时点契约与数据就绪矩阵、Stage 0-4 详细规格、策略 YAML Schema 与回测治理口径。
> 核心目标：不把任何一套具体条件写死成一个策略，而是抽象出「条件谓词 + 阶段流水线 + 时点契约」三件套，让用户能用一份 YAML 配出新战法；每个条件声明数据依赖并由调度器决定可运行时点，杜绝"盘中现算全市场"类性能陷阱与未来函数。

> **关联代码**：`scripts/core/models/`、`scripts/core/strategy/`、`scripts/core/data/`、`scripts/core/monitor/schedule_gate.py`

> **文档定位（规范与示例分离）**：本文是**通用规范层**，只承载可复用的抽象约束——条件谓词模型（Predicate Schema）、SFTC 阶段流水线、时点契约与数据就绪矩阵、编译期派生约束、回测方法与治理门禁口径。
> **本文不出现任何具体战法的阈值取值、时间点、评分权重与配置样例**；一切具体取值由以下两处单点承载，本文与二者不得互相复制：
> - 唯一示例（业务叙事 + 可执行漏斗口径 + 参数化评估）：[选股漏斗示例 1](./selection-funnel-example-1.md)
> - 可执行配置（阈值唯一权威）：`config/funnel_strategy.yaml`
>
> 示例中的一切阈值均由用户在可视化配置中**参数化**设定，并纳入 `definition_hash`。

---

## 1. 设计目标

1. **通用化**：不把任何一套条件写死成一个策略，而是抽象出「条件谓词 + 阶段流水线 + 时点契约」三件套，让用户以后能用一份 YAML 配出新战法。
2. **可工程化**：每个条件都声明数据依赖，由调度器决定它能在哪个时点运行，杜绝"盘中现算全市场"这类性能陷阱。
3. **可标定**：把"卖盘枯竭、买盘增加"这种盘感描述转成可计算、可回测、可调参的复合评分，而不是一句玄学。
4. **不引入未来函数**：明确每个条件的数据就绪时刻，接入现有 `quality_gates.py` 的 `LookaheadGuard`。

---

## 2. 从战法到通用抽象：抽象方法与强制参数化约束

### 2.1 抽象方法（规范）

把一段口语化战法抽象为可复用谓词，固定走三步：

1. **逐条解构**：把口述的每一个条件拆成「条件类型（`category`）→ 形式化表达（`expr`）→ 作用方式（`mode`）」三元组；
2. **归入阶段**：按该条件的数据就绪时刻，归入 SFTC 中最早可运行的阶段（见 §3、§5）；
3. **暴露参数**：把一切具体取值（窗口周期、均线、门槛、上限、区间）从表达式中摘出为 `params`，禁止硬编码。

具体战法的条件清单、取值、问财语句与业务叙事，见[选股漏斗示例 1](./selection-funnel-example-1.md)。

### 2.2 两条强制参数化约束（规范）

**约束 A：周期类窗口必须参数化且须交互确认。**
同一战法口述中，「突破周期」（如 N 日新高）常年存在语义歧义——中短期突破与中期突破的候选池规模差异极大。因此该类窗口必须暴露为参数 `new_high_window`，且**列为歧义项，须在引导式意图理解中向用户交互确认**，不得由系统默认。

**约束 B：缺口阈值必须暴露为参数对并强制上限护栏。**
缺口阈值必须暴露为 `gap_min` / `gap_max` 两个参数。**`gap_max` 上限护栏不得缺省、不得关闭**，理由（规范约束，非示例取值）：
- (a) 高开越高，距涨停空间越窄，日内可回撤幅度被严重压缩；
- (b) T+1 制度下当日无法止损，高开越多次日跳空低开亏损越大；
- (c) 极易遇"高开低走"出货形态，与本类"回调后拐点买入"战法的前提（洗盘而非出货）相冲突。

上限具体数值须回测标定；示例战法的分档预设见[选股漏斗示例 1](./selection-funnel-example-1.md)。

---

## 3. 核心抽象：SFTC 五阶段流水线

这是整套体系的骨架。任何"T日选股 + T+1择时"类战法都可以映射到这五个阶段。下图只标注**阶段角色**与**相对时点**；各阶段的**具体时钟与标的数量级属示例口径**，须由用户在配置中参数化设定（见[选股漏斗示例 1](./selection-funnel-example-1.md)）。

```
┌─────────────────────────────────────────────────────────────────┐
│ Stage 0 · Universe Gate  股票域准入                              │
│   时点：T日盘后（可日频缓存，低频变更）                            │
│   性质：静态结构性过滤，与行情信号无关                              │
│   条件：非ST / 非北交所 / 流通市值下限 / 上市天数 / 流动性下限       │
│   产物：Eligible Universe                                        │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 1 · Signal Screen  信号筛选                                │
│   时点：T日盘后（日K + 资金流数据就绪之后）                         │
│   性质：趋势/位置/量能/资金 四类共振                                │
│   条件：N日新高 + 站上 MA60 且 MA60 向上 + 放量 + 主力净流入 + 涨幅上限  │
│        （新高周期与均线周期均参数化）                                │
│   产物：Candidate Pool                                           │
├─────────────────────────────────────────────────────────────────┤
│ Stage 1.5 · Ranking  候选排序截断     ← 新增，工程必需             │
│   时点：紧随 Stage 1                                             │
│   性质：软条件打分排序，取 Top-N                                   │
│   理由：候选池 × tick级监控 超出轮询能力，必须截断到可监控规模        │
│   产物：Watchlist（Top-N，落盘 output/pools/）                    │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2 · Regime Gate  大盘环境门禁                              │
│   时点：T日盘后预判 + T+1 开盘前复核（双重校验）                    │
│   性质：一票否决（veto），不通过则整日不执行任何买入                  │
│   条件：指数收盘 > 指数 MA(N)（可选加强：MA(N) 向上，N 参数化）     │
│   产物：GO / NO-GO                                               │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓  (仅 GO)
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3 · Opening Trigger  早盘触发                              │
│   窗口：开盘后回调观察窗口（全程受理触发）                          │
│   3a 缺口过滤：open/pre_close - 1 ∈ [gap_min, gap_max]           │
│   3b 拐点识别：冲高 → 回调 → ERS 复合评分 ≥ 阈值 + 二次确认         │
│   产物：Triggered Set（触发个股集合：代码+触发价+时间戳+评分明细）    │
├─────────────────────────────────────────────────────────────────┤
│ Stage 3.5 · Confirm & Publish  确认输出                          │
│   窗口：回调观察窗口之后的确认窗口                                  │
│   性质：对 Triggered Set 做最终确认，一次性收敛输出股票代码          │
│   产物：Buy Signal List（正式交付清单，供下单与风控引用）            │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 4 · Risk Exit  风控离场（与入场完全解耦）                     │
│   约束：T+1 → 当日不可卖，止损最早 T+2 开盘执行                     │
│   阶梯：警戒 / 减仓 / 无条件出局（梯度由策略配置显式给定，见 §8）      │
└─────────────────────────────────────────────────────────────────┘
```

> **窗口口径（规范）**：回调观察窗口与确认输出窗口**互不重叠且顺序衔接**——先在观察窗口内全程受理触发，窗口关闭后进入确认输出窗口，并在确认窗口末端**一次性收敛**输出最终股票代码清单。两窗口的起止时刻为可配置参数，不含系统默认值。

### 3.1 阶段划分的三条设计原则

**原则一：阶段边界由「数据就绪时刻」决定，而非由业务直觉决定。**
「主力资金净流入」不能在盘中运行 —— 日级主力资金流是收盘后结算数据。「高开」不能在盘后运行 —— 需要 T+1 的开盘价。把每个条件按数据就绪时刻归入最早可运行阶段，就自然得到了流水线切分。

**原则二：越靠前的阶段，计算量越大、频率越低；越靠后的阶段，标的越少、频率越高。**
Stage 0/1 处理全市场，日频一次；Stage 3 只处理 Watchlist 规模，秒频轮询。这是本类战法能在数分钟窗口内跑完的**唯一可行架构**。反过来（盘中扫全市场）在时间上不可能。

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
    KLINE_D      = "kline_daily"        # 日K，T日盘后结算后就绪
    KLINE_MIN    = "kline_minute"       # 分钟K，盘中实时增量
    SNAPSHOT     = "realtime_snapshot"  # 实时快照，亚秒级延迟
    AUCTION      = "call_auction"       # 集合竞价（首期采集归档，默认开启、可配置关闭）
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
    params: dict                   # 可调参数，如 {"window": <int>}
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
本类战法有一个天然的合法"未来信息"陷阱：Stage 1 用 T日收盘数据，Stage 3 在 T+1 交易 —— 这是合法的。但若回测引擎错误地在 T日 bar 上就用 T日收盘价成交，就构成未来函数。所有 Stage 1 谓词必须打上 `execution_offset = T+1` 标记。

---

## 5. 时点契约与数据就绪矩阵

**这是本设计最关键的工程章节。** 时点契约的**规范性要求**是：每个条件必须声明数据依赖，由调度器推导其最早可运行时点，杜绝盘中现算全市场与未来函数。下表只给出**数据就绪的相对关系与硬约束**；各阶段的具体调度时钟属示例口径，须由用户在配置中参数化设定（见[选股漏斗示例 1](./selection-funnel-example-1.md)）。

### 5.1 数据就绪矩阵

| 数据 | 就绪时刻 | 延迟 | 现有状态 | 用于阶段 |
|---|---|---|---|---|
| 个股日K（OHLCV） | T日收盘后 | — | ✅ 已有 `data_bridge.py:328` | S0/S1 |
| 指数日K | T日收盘后 | — | ✅ 已有 `data_bridge.py:267` | S2 |
| 日级主力资金流 | T日盘后结算完成 | 分钟级 | ✅ 已有 `fetch_realtime.py:625` | S1 |
| 全市场快照批量 | 实时 | 亚秒级 | ✅ 已有，600只/批×8线程，全市场 3-5s | S2/S3a |
| 1分钟K线 | 开盘后每分钟 | 1~3s | ✅ 已有 `fetch_realtime.py:167` | S3b |
| tick 成交明细 | 实时 | ~3s（聚合分页） | ✅ 已有 `fetch_realtime.py:1067` | S3b |
| 集合竞价 | 竞价时段实时 | ? | 🟡 **首期采集归档**（默认开启、可配置关闭；失败不影响主链路，不参与信号） | S3a 增强；二期预筛 |
| 买卖五档 | 实时 | ~0.5s | ⚠️ 快照已含但未解析 · P2 | S3b（B2指标） |
| 流通市值/流通股本 | 日频 | — | ❌ **缺失 · P1**（仅有总市值） | S0 |
| ST 标记 | 日频 | — | ⚠️ 仅能靠名称正则 · P1 | S0 |
| 分钟级资金流 | 盘中 | 未验证 | ⚠️ **未验证 · P1** | S3b 增强 |

### 5.2 时点契约表（Timing Contract）

下表为**相对时点契约**：只约束动作之间的先后与依赖关系；每一行对应的具体时钟由配置参数给定，不含系统默认值。

| 相对时点 | 动作 | 依赖数据 | 产物 | 硬约束 |
|---|---|---|---|---|
| T日盘后（资金流结算后） | 启动 Stage 0 + 1 | 日K、资金流、静态列表 | 原始候选集 | 资金流须待盘后结算完成，**不可早于结算** |
| T日盘后 | Stage 1.5 排序截断 | 同上 | Watchlist Top-N | 落盘 `output/pools/` |
| T日盘后 | Stage 2 大盘预判 | 指数日K | GO/NO-GO 预估 | 仅预判，供用户睡前决策 |
| T+1 开盘前 | Stage 2 门禁复核 | 指数实时快照 | **GO/NO-GO 终判** | 竞价结束后、开盘前完成；NO-GO 则终止全流程 |
| T+1 开盘瞬间 | Stage 3a 缺口过滤 | 全市场快照（仅监控规模标的） | 高开票子集 | 须在开盘后极短时间（秒级）内完成 |
| T+1 观察窗口 | Stage 3b 拐点识别（回调观察窗口） | 1分钟K + tick + 五档 | ERS 评分流 → Triggered Set | 秒级轮询，标的数 ≤ 监控上限；全程受理触发 |
| 观察窗口关闭 | 停止受理新触发 | — | 停止受理新触发 | 此后触发的拐点作废 |
| 确认窗口 | Stage 3.5 确认输出 | 触发集合 + 二次确认K | 最终股票代码清单 | 确认窗口末端**一次性收敛** |
| 确认窗口后 | 下单执行 | Buy Signal List + 账户状态 | 成交回报 | 对接模拟盘/实盘下单 |
| T+1 全天 | 持仓监控 | 实时快照 | 风控状态 | 仅记录，**T+1不可卖** |
| T+2 开盘 | 止损执行 | 实时快照 | 卖出 | 最早可执行止损时点 |

### 5.3 由时点契约推导出的三条架构铁律

**铁律一：T日盘后必须落盘，T+1 盘中禁止全市场扫描。**
开盘瞬间的缺口过滤若要覆盖全市场需数秒（勉强可行但无冗余）；而观察窗口内的 tick 级监控若覆盖全市场则完全不可能。因此 Watchlist **必须**在 T日盘后落盘为 CSV，盘中只加载这 ≤ 监控上限的少数标的。这也正是现有 `pool_schema.py` 关注池的设计用途。

**铁律二：主力资金流决定了 Stage 1 不能早于盘后结算。**
用户说"下午，或下午的3点后开始执行" —— 这个直觉是对的，但要精确到**盘后资金流结算完成之后**，因为日级主力资金流是盘后结算数据，收盘瞬间拿到的可能是残缺值。调度须加入数据完整性校验（若资金流字段为空则重试而非当作 0）。

**铁律三：大盘门禁必须双时点校验。**
T日盘后用 T日收盘价预判（给用户睡前参考），T+1 开盘前用竞价后的实时指数终判（因为隔夜可能有利空导致低开跌破均线）。**只有终判有效**。仅做盘后预判会漏掉隔夜跳空风险。

---

## 6. Stage 0-2 详细规格

> **规范与示例边界**：本章各表只给出**谓词 id、条件语义、数据依赖与实现要点**；一切具体阈值取自示例战法口径，见[选股漏斗示例 1](./selection-funnel-example-1.md) 与 `config/funnel_strategy.yaml`。

### 6.1 Stage 0 · Universe Gate

| 谓词 id | 条件 | 数据依赖 | 现状 |
|---|---|---|---|
| `not_st` | 非 ST/*ST/退市整理 | STATIC_LIST | ⚠️ 需补：仅能靠名称正则 |
| `not_bse` | 非北交所 | STATIC_LIST | ✅ 已有 `config.py:128` |
| `float_cap_min` | 流通市值下限 | FUNDAMENTAL | ❌ **需补** |
| `listed_days_min` | 上市天数下限（建议新增） | STATIC_LIST | 建议加：次新股无 MA60 |
| `liquidity_min` | 日均成交额下限（建议新增） | KLINE_D | 建议加：防僵尸票 |
| `price_band` | 股价区间（建议新增） | KLINE_D | 建议加：防仙股 |

> **为什么「MA60 向上」隐含要求上市 ≥ 60 日**：次新股无 60 根日K，MA60 计算会返回 NaN。现有 `pv_factors.py` 的 `_sma` 对不足窗口的处理需确认，否则会产生静默的错误信号。建议 Stage 0 直接挡掉，比在 Stage 1 处理 NaN 更安全。

> **流通市值 vs 总市值**：现有数据层只有总市值（`data_bridge.py:255` 的 `market_cap`）。**用总市值替代会放宽条件**（总市值 ≥ 流通市值），导致纳入限售股占比高的票 —— 这类票实际流通盘小、易被操纵，与本类战法"选流动性好的强势票"意图相悖。因此列为 P1 必补项，不建议用总市值降级替代。

### 6.2 Stage 1 · Signal Screen

| 谓词 id | 条件 | 数据依赖 | 实现要点 |
|---|---|---|---|
| `close_new_high` | 收盘价创 N 日新高 | KLINE_D | `close_T >= max(close[T-window+1..T])`，用 `>=` 而非 `>`（当日自身即高点）；`window` 为参数且属歧义项（§2.2 约束 A） |
| `above_ma60` | 收盘价在均线上 | KLINE_D | `close_T > MA_N_T`；建议加 `buffer` 参数容错 |
| `ma60_rising` | 均线向上 | KLINE_D | 见下方斜率口径讨论 |
| `volume_expand` | 今日量 > 昨日量 | KLINE_D | `vol_T / vol_{T-1} > ratio_min`；建议加**量比下限**（`vol_T/MA5(vol) > vol_ratio_min`）过滤"昨日缩量导致的假放量" |
| `main_inflow` | 主力净流入为正 | FUND_FLOW_D | 建议用**净流入占成交额比例** `> 0`，避免大市值票的绝对值偏差 |
| `change_pct_cap` | 当日涨幅上限 | KLINE_D | 须**按板块差异化**参数化（见下） |

#### 关于均线向上的斜率口径（三种可配置选项）

"均线向上"有三种常见实现，语义强度递增，**统一暴露为 `ma60_rising` 谓词的可选 `method` 参数**：

| 口径 | 表达式 | 特点 |
|---|---|---|
| A. 单点比较 | `MA_T > MA_{T-lag}` | 宽松，短期抖动即通过 |
| B. 连续比较 | `MA_T > MA_{T-1} > MA_{T-2}` | 严格，要求连续多日上行 |
| C. 归一化斜率 | `(MA_T - MA_{T-lag}) / MA_{T-lag} / lag > θ` | 可跨股价比较，θ 可标定 |

**规范建议**：默认取 A（与用户"均线向上"的字面表述一致），并把 C 作为 Stage 1.5 的排序因子 —— 斜率越陡说明趋势动能越强，用于 Top-N 截断时优先保留。**具体 `lag` 取值、`min_slope` 与 θ 均为配置参数**；引擎实现必须与配置中的 `lag` 保持同一口径，其示例取值见[选股漏斗示例 1](./selection-funnel-example-1.md)。

#### 关于涨幅上限的板块差异化（规范）

用户要求"剔除当日涨幅超过某阈值的股票"，其意图是**避免追高、避免次日一字板买不进**。但 A股涨跌幅限制分板块不同（主板 ±10%、创业板/科创板 ±20%、北交所 ±30%），单一阈值会造成板块间误杀或失效。

**规范结论**：涨幅上限必须**按板块差异化**参数化为 `change_pct_cap_by_board: {main, gem, star}`，北交所在 Stage 0 剔除；具体阈值由配置给出并纳入 `definition_hash`。

### 6.3 Stage 1.5 · Ranking（新增阶段，工程必需）

**为什么必须新增**：用户预期候选池规模可达数十只。若全部进入 Stage 3 的 tick 级监控，并发请求量会触发数据源限流（现有 `fetch_realtime.py:83` 的重试策略在 429 下会退避，导致信号延迟）。因此**必须**在进入 Stage 3 前截断到可监控规模 Top-N。

**排序因子设计**（全部为 T日盘后可算，`RANK` 模式）：

| 因子 id | 计算 | 方向 | 理由 |
|---|---|---|---|
| `breakout_strength` | 突破幅度（收盘相对前 N 日高点） | + | 突破幅度越大，新高越"实"（非擦线新高） |
| `ma60_slope_norm` | 归一化均线斜率（口径C） | + | 中期趋势动能 |
| `volume_quality` | `vol_T / MA5(vol)` | + | 放量强度，非仅"比昨天多" |
| `inflow_intensity` | `main_net_inflow / amount` | + | 资金流入的相对强度，跨市值可比 |
| `change_pct_sweet` | 涨幅落入钟形成分区间 | 钟形 | 涨幅太小动能不足，太大追高风险 |
| `float_cap_score` | 流通市值落入钟形成分区间 | 钟形 | 太小易操纵，太大弹性不足 |

> **规范要求**：各因子权重为工程初值，**必须经回测标定**（见第 10 章）并纳入 `definition_hash`；禁止直接用于实盘。示例权重见[选股漏斗示例 1](./selection-funnel-example-1.md) 与 `config/funnel_strategy.yaml`。

### 6.4 Stage 2 · Regime Gate（一票否决）

**规范口径**：门禁条件为「指数收盘价 > 指数 N 日均线」；指数标的、`N` 与参与方式均为参数。

**支持可配置的多指数投票**（`mode: all_of | any_of | weighted_vote`）。字段契约如下（**不含具体取值**）：

```yaml
regime_gate:
  mode: <all_of | any_of | weighted_vote>
  indices:                  # 指数标的、权重、是否必需
    - {code: <index_code>, weight: <float>, required: <bool>}
  conditions:
    - id: index_above_maN   # 必选门禁
      expr: "close > MA(close, <N>)"
      mode: veto
    - id: index_maN_rising  # 可选加强项
      expr: "MA(close,<N>)_T > MA(close,<N>)_{T-lag}"
      mode: veto
      enabled: <bool>
  check_points:             # 双重校验：盘后预判 + 开盘前终判
    - {at: <T日盘后>, type: preview, data: index_kline_daily}
    - {at: <T+1开盘前>, type: final, data: index_snapshot_realtime}  # 唯一有效判定
```

**与现有代码的关系**：`market_assessor.py` 已有五维健康度模型（趋势/情绪/量能/结构/资金），其中趋势维度已用均线口径。
- **不要直接复用五维总分作为门禁** —— 用户的门禁是单一、明确、可解释的（"站上 N 日线"），五维加权分会稀释这个信号，且难以向用户解释"为什么今天不做"。
- **正确做法**：Stage 2 用独立的单条件 veto；五维健康度作为**附赠信息**展示给用户（如"门禁通过，但市场情绪偏弱，建议减半仓"），不参与否决。

---

## 7. Stage 3 · 早盘触发详细规格

### 7.1 Stage 3a · 缺口过滤（开盘瞬间）

```
输入：Watchlist（T日盘后落盘，规模 ≤ max_concurrent_monitor）
动作：批量快照（单次请求即可覆盖全部监控标的）
计算：gap_pct = (open_T+1 / close_T - 1) × 100
过滤：gap_min <= gap_pct <= gap_max
输出：GapPassed 子集
```

**可选增强（依赖竞价数据归档）**：在竞价结束时预筛，用竞价量/竞价金额占流通市值比判断"高开是否有资金支撑"，剔除"无量虚高开"。这能提前缩小监控范围，是显著优化，但**当前数据层不支持**，列为二期。

### 7.2 Stage 3b · 拐点识别：ERS 复合评分方法论规范

> **规范与示例边界**：本节只规定 ERS（Exhaustion-Reversal Score）的**模型结构与判定方法论**；具体指标定义、满分配额、权重、阈值与降级折算系数为**示例实例**，见[选股漏斗示例 1](./selection-funnel-example-1.md)。评分模型的**规范定义**（`scoring_rank` 类型的过滤层/评分层/排序层/输出层、权重归一化、三态求值）见 [`SPEC-ALGO-ISS-MT-001` §5](./selection-model-types-specification.md)。

**模型结构（规范）**：ERS 不是一个指标，而是**三组指标的综合评分**，且要求多组同时达标，防止单侧偏科误判：
- **A 组 · 卖盘枯竭分（Exhaustion）**：刻画抛压自然衰竭；
- **B 组 · 买盘增强分（Absorption）**：刻画承接资金入场；
- **C 组 · 形态位置分（Structure）**：刻画回调形态与位置约束（含硬条件）。

#### 7.2.1 个股日内阶段划分（规范）

```
open
   ↓      冲高段 (Rally)：价格从 open 上行至局部高点 P_peak
   ↓      识别条件：连续 k 根 tick/1分钟K 未创新高（k 为参数）
P_peak
   ↓      回调段 (Pullback)：价格从 P_peak 回落至局部低点 P_low
   ↓      识别条件：见下方 A/B/C 三组指标
拐点 →    买入触发
```

**关键约束（规范）**：
- 冲高段必须**真实存在**：`P_peak / open - 1 >= min_rally_pct`（参数），否则不构成"冲高后回调"形态，直接跳过该股。
- 回调段起点 P_peak 需经若干根 bar 确认，故最早触发时刻**晚于开盘**（延迟由 bar 粒度决定）。
- 若开盘即最高、全程单边下行（高开低走），**不触发** —— 这类形态是出货，不是洗盘。**这条规则是本类战法最重要的自我保护。**

#### 7.2.2 A 组：卖盘枯竭分（Exhaustion）

| 指标 | 计算方式 | 数据依赖 |
|---|---|---|
| A1 主动卖量衰减 | 近端窗口主动卖量 / 前端窗口主动卖量 | TICK |
| A2 缩量回调 | 回调段均量 / 冲高段均量 | KLINE_MIN |
| A3 跌幅收窄 | 回调段连续 1分钟K 实体绝对值递减 | KLINE_MIN |
| A4 卖单笔数衰减 | 近端窗口卖单笔数 / 前端窗口卖单笔数 | TICK |
| A5 无大单砸盘 | 回调段是否存在远超当日均笔量的大额卖单 | TICK |

> **A2「缩量回调」是这组指标的灵魂**：价格下跌但成交量萎缩，说明抛压在自然衰竭而非有资金出逃。这与"放量下跌"（真出货）形成鲜明对比，是区分洗盘/出货最有效的单一指标。
> 各指标的窗口长度、比值门槛与满分配额均为配置参数。

#### 7.2.3 B 组：买盘增强分（Absorption）

| 指标 | 计算方式 | 数据依赖 | 现状 |
|---|---|---|---|
| B1 主动买量回升 | 近端窗口主动买量 / 前端窗口主动买量 | TICK | ✅ |
| B2 委买卖比回升 | 五档买量/卖量自回调低点的回升幅度 | L2_BOOK | ❌ **缺失** |
| B3 下方承接 | P_low 附近小区间内的连续主动买笔数 | TICK | ✅ |
| B4 VWAP 之上 | `current_price > 当日VWAP` | KLINE_MIN | ✅ |
| B5 tick 净买比转正 | 最近若干笔 `(B-S)/(B+S)` | TICK | ✅ |

**降级规则（规范，必须实现，否则模型跑不起来）**：

```
若某组数据依赖不可用（如 L2_BOOK 缺失）：
  该组满分下调至其可用指标的满额
  ERS 总分满分随之下降
  触发阈值等比折算：threshold_effective = threshold_base × (可用满分 / 满分基数)
  同时在信号输出中标注 "degraded: <缺失项>"
```

> **五档数据其实"部分有"**：腾讯快照 `parts[9-28]` 已包含五档买卖价量，只是 `_parse_tencent_quote` 当前未解析这些字段。**补齐成本很低，建议优先做**，它直接决定 B2 指标能否启用。

#### 7.2.4 C 组：形态位置分（Structure）

| 指标 | 计算方式 | 性质 |
|---|---|---|
| C1 回调不破开盘价 | `P_low > open` | **硬条件（不满足直接否决）** |
| C2 回调深度合理 | `retrace = (P_peak-P_low)/P_peak` 落入钟形区间 | 软条件 |
| C3 缺口回补约束 | P_low 不低于"缺口回补上限"对应价 | 软条件 |
| C4 时间有效性 | 拐点时刻落在观察窗口内 | 硬条件 |

> **C2 的钟形约束很重要**：回撤过小说明根本没洗盘，回调太浅后续动能存疑；回撤过大说明抛压过重，可能已转为出货。区间需回测标定。
>
> **C3 的缺口保护**：高开缺口被完全回补 = 高开失败，是明确的弱势信号，故要求最多回补一定比例。

#### 7.2.5 触发判定逻辑（规范骨架）

```python
def check_trigger(stock, bars_min1, ticks, book) -> Signal | None:
    phase = detect_phase(bars_min1)          # RALLY / PULLBACK / NONE
    if phase != "PULLBACK":
        return None
    if not rally_valid(stock):               # 冲高段必须真实存在
        return None

    A = score_exhaustion(ticks, bars_min1)
    B = score_absorption(ticks, bars_min1, book)
    C, c_hard_ok = score_structure(stock, bars_min1)

    if not c_hard_ok:                        # C1/C4 任一不满足 → 否决
        return None

    total_max = available_max(book)          # 依数据可得性折算
    threshold = BASE_THRESHOLD * total_max / FULL_SCALE

    ers = A + B + C
    if ers < threshold:
        return None
    if A < A_MIN or B < B_MIN:               # 双侧达标，防单侧偏科
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

**三个防误判设计的必要性（规范）**：

1. **双侧达标**：若只要求总分，则可能"卖盘枯竭满分 + 买盘毫无动静"也达标 —— 那是阴跌无人接盘，不是拐点。
2. **二次确认**：ERS 达标瞬间价格可能仍在下跌途中，抓在半山腰。等待"收阳或突破前一分钟高点"再确认，牺牲一点入场价换取显著胜率提升。代价是延迟一根 bar，仍须落在观察窗口内。
3. **冲高段有效性前置校验**：直接排除高开低走的出货形态。

### 7.3 监控调度设计（规范）

```
开盘前     预加载 Watchlist，建立快照连接池
开盘        Stage 3a 批量快照 → GapPassed 子集
开盘        启动 N 个并行监控协程（每只一个）
            每只轮询：tick / 分钟K / 快照 按各自周期
观察窗口    持续 ERS 评分，命中即记录触发（Triggered Set）
观察窗口末  回调观察窗口关闭，停止受理新触发
确认窗口    对 Triggered Set 做最终确认
确认窗口末  一次性收敛，输出最终股票代码清单（Buy Signal List）
此后        下单执行（对接 astock-trade-paper 模拟盘 / 实盘）
```

**限流保护（规范）**：并发监控标的数 × 轮询频率须落在数据源可承受范围内；若 GapPassed 超过监控上限，按 Stage 1.5 排序截断，其余记录为"未监控"（**不可静默丢弃，须在日志中体现**）。

### 7.4 输出定性：候选清单 ≠ 正式信号

`funnel screen`（Stage 1 + 1.5）输出的 `selected_codes` 在一期**定性为「观察候选清单」，不等于正式交易信号**：

- 一期仅落地「筛选 → 观察候选」能力，候选仅进入观察池并落盘（`output/pools/`），**不产生可下单的正式信号**；
- 代理档（缺 tick / 五档等精细数据）下，输出必须携带 `not_eligible_for_signal` 标记，明确提示"本清单不可直接用于下单"；
- 正式信号（Stage 3 触发判定 + Stage 3.5 确认输出 → Buy Signal List）在**二期**启用，且须先通过 §10.3 治理门禁。

> `not_eligible_for_signal` 的判定门槛与「候选 → 正式信号」的晋级规则均以**参数形式**在可视化配置中暴露（全量参数化口径）。

---

## 8. Stage 4 · 风控离场

### 8.1 T+1 制度带来的根本性约束（规范）

A股 **T+1** 交易制度下，早盘触发买入的标的**当日不可卖出**，这直接决定了风控离场层的结构：

- 任何"买入当日生效"的止损阶梯在制度上**不可执行**；
- 最早可执行止损的时点为**买入次日开盘**；
- 若买入次日尾盘大幅跳水、或再次跳空低开，实际亏损可能**远超最深层止损线**（跳空缺口无法用限价止损单规避）。

因此规范强制要求：**风控离场层必须显式声明本策略受 T+1 约束**，并据此区分"当日可执行"与"次日才可执行"的两类动作，禁止把次日止损伪装成当日可生效的规则。

### 8.2 双层止损方法论（规范）

风控离场层固定拆为两层：

**第一层：当日仓位控制（唯一当日可执行的手段）**

| 机制 | 规范要求 |
| :--- | :--- |
| 单票仓位上限 | 必须显式配置；因当日不可止损，上限须保守设定，**具体取值下沉为参数** |
| 同日总建仓上限 | 必须显式配置当日最大建仓比例与最大并发持仓只数 |
| 大盘弱势降档 | 应支持"大盘健康度低于阈值时仓位自动减半"，阈值参数化 |
| 高开幅度反向调节 | 应支持"缺口越大、单票仓位越小"的反向仓位映射 |

**第二层：次日止损执行（真正的止损）**

- 必须配置**至少三级百分比止损阶梯**（警戒 / 减仓 / 绝杀），每一级的触发浮亏比例、动作、执行时点均参数化；
- **T-Gap 跳空止损**（强制新增）：若次日开盘价已越过最深层止损线，须**以开盘价无条件出局**，禁止"等反弹回本"；
- **T-Time 时间止损**（强制新增）：若次日收盘仍未盈利，视为拐点判断失效，清仓离场——本类战法逻辑基础为"回调后立即重拾升势"，不养套牢票。

> 三级阶梯的具体比例、T-Gap/T-Time 的具体换算与执行时钟，均由示例文档与 `config/funnel_strategy.yaml` 单点承载，本文不复制。

### 8.3 保本价核算（规范）

保本价核算**沿用项目现有铁律**（`docs/trading/breakeven-rules.md`）：计入印花税、佣金（含最低起收）与过户费，并**向上进位至分位**，禁止四舍五入。实现上**必须调用既有 `astock-action-execution` 能力，不得在本体系中重复实现**。

### 8.4 止损口径自持原则（规范）

在本体系引入前，项目内可能并存多套止损定义（固定百分比、均线口径、硬阈值等），彼此互不兼容。本体系的规范要求是：

1. **止损阶梯必须显式写入策略配置**（见 §9），**不得继承任何全局默认值**——即本战法自带止损定义，与全局口径解耦；
2. 本类"早盘入场 + T+1 约束"的超短线战法，**建议采用固定百分比口径而非均线口径**：均线止损依赖收盘价确认，而本类战法盘中入场，等收盘确认等于放任日内亏损扩大，与 T+1 叠加将造成不可控回撤；
3. "统一全局止损口径"作为**独立技术债**登记，须在 Stage 4 落地前由用户裁决，本文不做全局口径裁定。

### 8.5 板块差异化仓位（规范）

仓位上限**应复用项目既有的板块差异化约定**（主板与 20cm 板块采用不同上限）而非另立标准；差异化的具体数值随 §9 配置外置为参数，禁止硬编码。

---

## 9. 配置化：策略 YAML Schema

本体系把 §3–§8 的全部机制收敛为**一份声明式配置**，实现"改参数不改代码"。以下为**规范性要求**，具体取值不在此处出现。

### 9.1 配置结构（规范）

一份策略配置必须包含以下顶层区块，并满足各自的参数化要求：

| 区块 | 规范性要求 |
| :--- | :--- |
| `strategy` | 必须声明 `id`、版本、生命周期状态（研究 / 已回测 / 生产）与受 T+1 约束标记 |
| `stage0_universe` | 每个标的池谓词可参数化：ST 判定、板块排除、流通市值下限、上市天数下限、流动性下限、价格下限等，取值一律外置 |
| `stage1_screen` | 每个选股谓词可参数化（窗口周期、均线、缓冲、量能倍率、资金流口径与门槛等）；须声明 `data_readiness_check`（数据缺失时重试，**不得按 0 处理**） |
| `stage1_5_rank` | 必须声明 `top_n` 与持久化路径；各排序因子以 `{id, weight, params}` 显式列出，权重可配置 |
| `stage2_regime` | 必须声明复检时点（相对时点）、指数清单与各自 `required` 标记、`mode`（`all_of`/`any_of`）与各 veto 谓词；其结论**只做否决、不做打分** |
| `stage3_trigger` | 必须声明观察窗口、软/硬截止（相对时点）、监控上限、缺口过滤参数、冲高有效性参数、ERS 各阈值与降级策略、形态硬条件、回调区间、缺口回补比例上限 |
| `stage4_exit` | 必须声明下单窗口、`t1_constraint`、仓位控制层参数、止损阶梯（等级 / 触发比例 / 动作 / 执行时点）、跳空与时间止损条件、保本价核算引用 |

### 9.2 四条编译期派生约束（规范）

1. **全量参数化**：每个谓词的一切阈值（窗口、均线、门槛、上限、区间）必须以 `params` 形式暴露，禁止硬编码；
2. **参数纳入指纹**：全部 `params` 必须参与策略 `definition_hash` 计算——改参数即视为新策略，回测结果不可跨哈希复用；
3. **止损与仓位自持**：止损阶梯与仓位参数**必须在本配置内显式声明**，不继承全局默认值（见 §8.4）；
4. **不约定固定目录**：体系不强制策略文件的物理目录与文件名，路径由部署方自定；本文档与示例不复制同一份取值。

### 9.3 可执行配置骨架（占位符）

```yaml
# <策略配置文件路径由部署方自定>
strategy:
  id: <string>
  version: <semver>
  stage: <RESEARCH | BACKTESTED | PRODUCTION>
  t1_constraint: <bool>          # 是否受 T+1 约束（超短线须为 true）

stage0_universe:
  predicates:
    - {id: not_st,          mode: hard, params: {pattern: <regex>}}
    - {id: not_bse,         mode: hard, params: {prefixes: <list>}}
    - {id: float_cap_min,   mode: hard, params: {min: <float>}}
    - {id: listed_days_min, mode: hard, params: {min: <int>}}
    - {id: liquidity_min,   mode: hard, params: {min_amount_20d: <float>}}
    - {id: price_band,      mode: hard, params: {min: <float>}}

stage1_screen:
  data_readiness_check: true     # 资金流为空须重试，不得按 0 处理
  predicates:
    - {id: close_new_high, mode: hard, params: {window: <int>}}
    - {id: above_ma60,     mode: hard, params: {ma_window: <int>, buffer_pct: <float>}}
    - {id: ma60_rising,    mode: hard, params: {lag: <int>, method: <point_compare|continuous|slope_norm>}}
    - {id: volume_expand,  mode: hard, params: {dod_ratio_min: <float>, vol_ratio_5d_min: <float>}}
    - {id: main_inflow,    mode: hard, params: {metric: <...>, min: <float>}}
    - {id: change_pct_cap, mode: hard, params: {main: <float>, gem: <float>, star: <float>}}

stage1_5_rank:
  top_n: <int>
  persist_to: <path>
  factors:
    - {id: <factor_id>, weight: <float>, params: <object>}

stage2_regime:
  check_points: [{at: <relative_time>, type: preview}, {at: <relative_time>, type: final}]
  mode: <all_of | any_of>
  indices:
    - {code: <index_code>, required: <bool>}
  predicates:
    - {id: index_above_ma20, mode: veto, params: {ma_window: <int>}}

stage3_trigger:
  window:        {start: <relative_time>, end: <relative_time>}
  soft_cutoff:   <relative_time>
  max_concurrent_monitor: <int>
  gap_filter:    {gap_min: <float>, gap_max: <float>}
  rally_validity:{min_rally_pct: <float>, peak_confirm_bars: <int>}
  ers_model:     {base_threshold: <float>, a_min: <float>, b_min: <float>, degrade_when_no_book: <bool>, require_second_confirm: <bool>}
  structure_hard: <list>
  retrace_band:  {min_pct: <float>, max_pct: <float>}
  gap_fill_max_ratio: <float>

stage4_exit:
  order_window: {start: <relative_time>, end: <relative_time>}
  t1_constraint: true
  intraday_controls: {single_position_max_pct: <float>, daily_total_max_pct: <float>, max_concurrent_holdings: <int>, weak_market_halve_below: <float>}
  stop_ladder:
    - {level: <L>, drawdown_pct: <float>, action: <alert|reduce|clear>, exec: <relative_time>}
    - {level: T_GAP,  condition: <...>, action: clear_at_open, exec: <...>}
    - {level: T_TIME, condition: <...>, action: clear,          exec: <...>}
  breakeven: {skill: astock-action-execution, round: ceil_to_cent}
```

> 本示例配置的**唯一真实取值**见 `config/funnel_strategy.yaml`；业务叙事、问财语句与参数化评估见[选股漏斗示例 1](./selection-funnel-example-1.md)。

---

## 10. 回测、标定与过拟合防护

### 10.1 参数标定原则（规范）

本体系中一切**未经数据验证的工程初值，禁止直接实盘**。规范要求：

- 凡影响信号数量或质量的阈值（评分门槛、分组下限、回调区间、缺口上限、截断数量、因子权重等），**必须经历史数据标定**后方可进入 `BACKTESTED` 状态；
- 标定方法固定为：单参数用分组统计或网格搜索，多参数用二维及以上网格，因子权重用滚动 IC 加权（复用既有因子合成能力）；
- 具体参数的初值清单**不在本文列出**，随示例与 `config/funnel_strategy.yaml` 单点承载，并在实施看板中跟踪标定状态。

### 10.2 回测的三个特殊难点（须提前设计，否则结论不可信）

**难点一：分钟级 / tick 级历史数据缺失。**
现有数据源只能取到有限根数的短周期 K 线，**没有 1 分钟 K 与 tick 的历史归档**，意味着盘中触发模型**无法用历史数据严谨回测**。可行路径：

1. **前向采集**：自上线日起每日盘中归档监控清单的分钟级数据，积累足够交易日后再标定——**唯一严谨路径，但有等待期**；
2. **降级代理回测**：用更粗粒度（如 5 分钟 K）近似回测，仅用于**排除明显错误的参数区间**，不可用于确定最优参数，且报告必须标注"代理回测，结论不可直接实盘"。

**难点二：Stage 1 的未来函数风险。**
T日盘后选股 + T+1 成交本身合法，但回测引擎若在 T日 bar 上以 T日收盘价成交即构成未来函数。规范强制：回测须设 `execution_offset = T+1`，且成交价取 **T+1 的触发时点价**而非 T+1 收盘价，否则严重高估收益。

**难点三：滑点与手续费敏感性。**
超短线 + 集中时点下单，滑点影响极大。回测**必须计入**佣金（含最低起收）、印花税（卖出）、过户费与**冲击滑点**（早盘波动大时应更高），复用既有模拟盘的滑点模型。

### 10.3 治理门禁（上线前强制通过）

正式信号启用（见 §7.4）前，必须通过既有 `quality_gates.py` 的三道校验：

- `LookaheadGuard`：验证所有 Stage 1 谓词的 `execution_offset = T+1`；
- `AShareComplianceGuard`：验证 T+1 约束、涨跌幅限制、停牌处理；
- `OverfittingGuard`：盘中触发模型可调指标与待标定参数众多，**过拟合风险极高**；要求样本外胜率不低于样本内的既定比例，否则判定过拟合。

---

## 附录 A：术语对照

| 术语 | 含义 |
| :--- | :--- |
| SFTC | Screen–Filter–Trigger–Control，本文提出的五阶段流水线抽象 |
| Predicate（谓词） | 单个可判定的选股条件，体系的最小复用单元 |
| ERS | Exhaustion-Reversal Score，卖盘枯竭-买盘反转复合评分 |
| VETO | 一票否决模式，作用于全局而非单标的 |
| Watchlist | Stage 1.5 产出的 Top-N 监控清单，T日盘后落盘 |
| 时点契约 | 各阶段绑定执行窗口与数据就绪时刻的约束表 |
| T-Gap | 跳空止损：次日开盘已破止损线则无条件开盘价出局 |
| T-Time | 时间止损：次日收盘仍未盈利则清仓 |
| definition_hash | 策略定义指纹，参数变更即变更哈希 |

---

## 附：关联索引

- 唯一示例（业务叙事 + 可执行口径 + 参数化评估）：[选股漏斗示例 1](./selection-funnel-example-1.md)
- 可执行配置（阈值唯一权威）：`config/funnel_strategy.yaml`
- 实施进度看板：[`general-selection-and-turning-point-plan.md`](../../specs/algorithm/general-selection-and-turning-point-plan.md)
- 系统建设规范：[`selection-system-specification.md`](./selection-system-specification.md)
- 模型类型定义：[`selection-model-types-specification.md`](./selection-model-types-specification.md)
- 算法治理规范：[`algorithm-governance.md`](./algorithm-governance.md)