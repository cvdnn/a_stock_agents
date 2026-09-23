# 通用选股体系与早盘拐点触发机制实施计划

> 规范编号：`SPEC-ALGO-003`
> 权威定义 (SSOT)：[`selection-model-general-specification.md`](../../guidelines/algorithm/selection-model-general-specification.md)
> **实施状态**：规划中 (RFC) | 第 4 批审查裁定已回写（2026-09-21，B-01/B-02/B-04/A-02/A-03）

## 一、规范核心定位摘要

- 本看板承载「通用选股体系与早盘拐点触发机制」（网阀选股 SFTC 五阶段流水线）的代码落地映射、待确认问题裁决、分期路线与验收口径。
- 条件谓词、阶段规则、时点契约、ERS 评分模型、策略 YAML Schema 与回测治理口径的权威定义一律以 [`selection-model-general-specification.md`](../../guidelines/algorithm/selection-model-general-specification.md) 为准，本看板不复述。
- 系统建设总纲见 [`selection-system-specification.md`](../../guidelines/algorithm/selection-system-specification.md)，算法治理门禁见 [`algorithm-governance.md`](../../guidelines/algorithm/algorithm-governance.md)。

## 二、与现有代码的映射与改造点

### 2.1 复用（不改）

| 现有模块 | 在本体系中的角色 |
|---|---|
| `data_bridge.py` / `fetch_realtime.py` | 全部数据获取，含 4级降级 |
| `technical_indicators.py` `ma()` | MA20/MA60 计算 |
| `pv_factors.py` `vol_surge_5_20` | Stage 1.5 的 `volume_quality` 因子 |
| `schedule_gate.py` `get_market_phase()` | 时点契约的阶段判定（已有 CALL_AUCTION / CONTINUOUS_MORNING 等） |
| `pool_schema.py` / `pool_manager.py` | Watchlist 落盘（关注池 schema 已够用） |
| `AlgoRegistry` + `BaseAlgorithm` | 策略与因子注册 |
| `quality_gates.py` | 上线治理门禁 |
| `paper_trading` | Stage 4 模拟盘对接 |
| `risk_manager.py:24-27` | 三级止损阶梯 T0/T1/T2（**需扩展**，见权威定义文档 8.3 节） |
| `risk_position_manager.py:218` | 仓位与硬止损执行 |
| `config.py:77` | `DEFAULT_WARN_LOSS_PCT = 0.03`（T0 阈值来源） |

### 2.2 需新增

> **路径口径（E-01 / B-02 回写）**：以现有 `funnel` 系列为**唯一实现底座**，本节路径已回写映射到该底座，**不新建平行目录**（原 `scripts/core/models/predicate.py`、`scripts/core/models/pipeline.py`、`scripts/core/strategy/opening_reversal/` 的规划路径作废，能力就地并入下述文件）。

| 新增/落点文件 | 职责 | 优先级 |
|---|---|---|
| `scripts/core/strategy/funnel_engine.py`（**就地升级**） | 谓词 Schema + 编译期校验（三条约束）+ 规则注册表（`RuleRegistry`） | P0 |
| `scripts/core/strategy/stock_funnel.py`（**就地升级**） | SFTC 五阶段流水线编排器（`StockFunnelPipeline`） | P0 |
| `scripts/core/strategy/funnel_rules/opening_reversal/` | 本战法规则与因子实现（挂 `RuleRegistry`） | P0 |
| ├─ `ers_model.py` | ERS 复合评分（A/B/C 三组 14 指标） | P0 |
| ├─ `phase_detector.py` | 冲高/回调阶段划分 | P0 |
| ├─ `intraday_monitor.py` | 并发监控调度 + 限流 | P0 |
| └─ `signal_dispatcher.py` | 信号推送与下单窗口管理 | P1 |
| `config/funnel_strategy.yaml`（**扩展**） | 策略配置（**全量参数化**，一切规则与判定参数入 Schema 并纳入 `definition_hash`，见 X-03） | P0 |
| `scripts/core/data/auction_archive.py` | 集合竞价数据**首期采集归档**（默认开启、可配置关闭；失败不影响主链路，不参与信号） | P1 |
| `scripts/core/data/intraday_archiver.py` | 盘中数据前向采集归档 | P0-回测前置 |

### 2.3 需改造

> **路径口径（E-01 / B-02 回写）**：CLI handler 落点为既有 `scripts/core/commands/funnel_cmds.py`，不另建 `commands/strategy_cmds.py` 平行入口。

| 文件 | 改造内容 | 优先级 |
|---|---|---|
| `scripts/core/data/fetch_realtime.py` `_parse_tencent_quote` | 收敛至权威解析器 `tencent_fields`，补齐五档 bid/ask 输出（数据已在响应中） | **P0-低成本高收益** |
| `scripts/core/data/data_bridge.py` `get_fundamentals()` | 补 `circulating_market_cap` / `float_shares` 字段 | P1 |
| `scripts/core/config.py` `infer_market_prefix()` | 提取为统一 `is_excluded_board()` 过滤函数 | P1 |
| `scripts/core/strategy/risk_manager.py` / `risk_position_manager.py` | 新增 T-Gap 跳空止损 + T-Time 时间止损 + T+1 不可卖约束 | **P0-安全** |
| `scripts/core/config.py` | **止损口径不统一数值**（D-23/C-07）：仅登记口径集合与来源；**系统提供默认止损数值**，用户可自行设置、默认取系统值（A-02），纳入 `definition_hash` | **P0-安全** |
| `scripts/core/models/registry.py` | 注册新策略与新因子 | P0 |
| `scripts/core/commands/funnel_cmds.py` | 扩展 CLI handler（`funnel screen` / `funnel regime` / `funnel trigger`） | P1 |
| `config/skills_manifest.json` | 新增技能条目 | P2 |

### 2.4 CLI 设计（对齐现有约定，统一追加 `--json`）

> **口径（A-03 / T-08 回写）**：统一挂 `funnel` 子命令族，避免与顶层 `screen` / `regime` / `trigger` 命名冲突。既有 `funnel validate` 与 `funnel run --stage` 保留。

```bash
# T日盘后：生成候选池
.\bin\astock.ps1 funnel screen --mode opening_reversal --date 2026-09-17 --json

# T日盘后：大盘门禁预判
.\bin\astock.ps1 funnel regime --mode opening_reversal --json

# T+1早盘：启动实时监控（长驻进程）
.\bin\astock.ps1 funnel trigger --mode opening_reversal --watch --json

# 任意时刻：ERS 模型单日复盘（用归档数据）
.\bin\astock.ps1 funnel trigger --mode opening_reversal --replay --date 2026-09-18 --json

# 回测（沿用既有顶层 backtest）
.\bin\astock.ps1 backtest --strategy opening_reversal --from 2026-01-01 --json
```

## 三、开放问题裁定结论（已裁定，2026-09-21）

以下问题会显著改变系统行为，已于主计划第 1 批与第 4 批裁定中逐项决策。**原「本设计默认」数值已全部删除**，统一以主计划 [`selection-system-plan.md`](selection-system-plan.md) §六 裁定结论为准（B-01 回写）。

> **示例来源注记**：下表 Q1～Q5、Q7、Q9 等条目中的定值（20 日新高周期、高开 1%～2%、主板 7% / 20cm 12%、上证 MA20、09:40 收敛等）即[选股漏斗示例 1](../../guidelines/algorithm/selection-funnel-example-1.md)（见本文[附：原始需求留档](#附原始需求留档)）所采用的示例口径。它们**均为可配置参数**（X-03 全量参数化），标注「示例来源」仅表示默认取值参考，**不代表系统唯一或不可变更的规范数值**。

| # | 问题 | 裁定结论（对应编号） |
|---|---|---|
| **Q1** | 新高周期是 **20日** 还是 **60日**？ | 可配置；快捷预设 10/20/30/60 日 + 自定义 N 日，**默认冻结 20 日**（D-01 / C-01；**示例来源**） |
| **Q2** | 高开幅度用哪档？ | 可配置，**默认 `gap_min=1%` / `gap_max=2%`**，不设不可配置的硬上限（D-02；**示例来源**） |
| **Q3** | `gap_max` 上限定多少？ | 可配置，**默认 2%**（D-02；原「本设计默认 5%」作废；**示例来源**） |
| **Q4** | 涨幅 7% 上限是否按板块差异化？ | 可配置；**默认主板 7% / 20cm 12%**（D-03；**示例来源**） |
| **Q5** | 大盘门禁用哪个指数？ | **仅上证综指 MA20**，首期不提供多指数可选（D-04；**示例来源**） |
| **Q6** | **是否接受 T+1 导致当日无法止损？** | **接受硬约束**；双层风控 T-Gap / T-Time / T+1，三层阈值入配置（D-19） |
| **Q7** | 单票/单日仓位上限定多少？ | 主板单票 **15%**、20cm 单票 **8%**；单日 ≤40%；最多 3 只（D-20） |
| **Q8** | 是否接受"前向采集 40-60 交易日后才能标定 ERS"？ | **接受** 40～60 交易日前向采集期，并行代理口径回测（D-21） |
| **Q9** | 拐点未触发时，是否允许放宽到 9:40 后继续观察？ | 窗口端点可配置；**默认不加软截止，09:40 一次性收敛**（D-06） |
| **Q10** | 是否需要 9:25 竞价预筛？ | 纳入**二期**；一期仅做竞价数据**采集归档**（默认开启、可配置关闭）（D-22 / C-09） |
| **Q11** | **既有三套止损口径以哪套为准？** | **不统一数值**：仅登记口径集合与来源（D-23 / C-07）；**系统提供默认止损数值**，用户可自行设置、默认取系统值（A-02） |
| **Q12** | 单票仓位沿用既有板块差异化上限（主板15%/20cm 8%）还是本文初值20%？ | **沿用既有 15%/8%**（同 D-20） |

## 四、分期落地路线图

### 一期：可跑通的最小闭环（不依赖新数据源）

- [ ] `funnel_engine.py` + `stock_funnel.py` 就地升级骨架，含三条编译期约束（E-01/B-02）
- [ ] Stage 0/1/1.5/2 完整实现（数据全部已有，仅缺流通市值 → 临时用名称正则判ST + 待补市值）
- [ ] Watchlist 落盘至 `output/pools/`
- [ ] Stage 3a 缺口过滤（快照已有）
- [ ] Stage 3b ERS **降级版**（无五档，B组30分制，阈值59）
- [ ] `intraday_archiver.py` 前向采集上线（**越早启动越好，它是回测的前置条件**）
- [ ] `auction_archive.py` 集合竞价**首期采集归档**上线（默认开启、可配置关闭；失败不影响主链路，B-04/B-04）
- [ ] CLI `funnel screen --mode opening_reversal` + `funnel trigger --watch`
- [ ] 全部信号只进**模拟盘**（`astock-trade-paper`），不接实盘；一期代理档输出仅标 `not_eligible_for_signal`（A-04）

**一期交付标准**：连续 5 个交易日稳定产出 Watchlist + 早盘信号，无限流、无崩溃、无未来函数告警。

### 二期：数据补全与标定

- [ ] 补齐五档解析（收敛至 `tencent_fields` 权威解析器）→ 启用 B2
- [ ] 补齐流通市值 / ST 标记 / 北交所统一过滤函数
- [ ] 基于一期已归档的竞价数据，实现 9:25 竞价预筛（B-04）
- [ ] 积累 40-60 交易日归档数据后，网格搜索标定 ERS 全部参数
- [ ] 通过 `OverfittingGuard` 样本外校验

### 三期：验证与增强

- [ ] 完整回测（含滑点、手续费、T+1 约束、跳空止损）
- [ ] Stage 4 双层风控接入 `position_stop_monitor.py`
- [ ] HTML 复盘报告（`astock-report-html`）：每日信号 + 触发明细 + ERS 分解
- [ ] 参数敏感性分析，确定稳健区间
- [ ] 抽象为通用引擎，支持用户用 YAML 自定义新战法

### 贯穿项：止损口径登记与可配置（P0 技术债）

> **裁定（D-23 / C-07 / A-02）**：**不统一数值**。D-23 管口径集合（登记 `AGENTS.md` -8%、`risk_manager.py` MA20-2%、`risk_position_manager.py` -6.0% 等的适用边界与来源），D-19 管选口径与动作；**系统提供默认止损数值**，用户可自行设置、默认取系统值，全部纳入 `definition_hash`。

- [ ] 登记三套互斥口径的来源与适用边界（文件/常量名/数值/依据技能），新增模块须显式声明所引用口径
- [ ] 落 `config.py` 止损默认值 + 用户可覆盖配置；发布门禁增加「止损口径可追溯」检查（T-05），须在 Stage 4 开发前闭环

## 五、关键风险提示（诚实披露）

1. **ERS 模型的 14 个指标权重全部是工程初值，无历史数据支撑。** 在标定完成前，本战法的信号质量**不可知**，只能进模拟盘。
2. **"卖盘枯竭、买盘增加的拐点"本质是盘感，量化代理必然有损。** A/B/C 三组指标是对该盘感的**近似**，不是等价物。用户提到的"这个点很重要，要慢慢的优化"是正确判断 —— 它需要长期迭代，不存在一次到位的参数。
3. **tick 数据是聚合成交明细，非真 L2 逐笔。** A1/A4/B3/B5 依赖的"主动买卖方向"由数据源推断（`direction` 字段 B/S/M），准确性受限于源质量，无法验证。
4. **T+1 + 超短线是最不利的组合。** 当日无法止损，隔夜跳空风险完全敞口。权威定义文档第 8 章的双层风控是缓解而非消除。**本战法的最大单日亏损可能显著超过 -8% 绝杀线。**
5. **9:30-9:35 是全天数据源最拥堵、延迟最高的时段。** 现有降级链在极端情况下可能返回延迟 3-5s 的数据，而本战法的时间预算只有 300s。信号延迟会直接导致成交价劣化。需在实盘前做**延迟压测**。
6. **候选池规模对参数极其敏感。** 新高周期 20→60、涨幅上限 7%→12% 等单个参数变动都可能让候选池从几十只变为几只或几百只，进而使 Stage 1.5 的 Top-20 截断失去意义或过度激进。
7. **本设计不构成投资建议。** 所有参数须经用户确认、所有信号须先经模拟盘验证。

## 六、验收与验证证据

| 断言 | 验证方式 | 结果 |
|:---|:---|:---:|
| 一期连续 5 个交易日稳定产出 Watchlist + 早盘信号，无限流、无崩溃、无未来函数告警 | 连续 5 个交易日实盘跟踪日志与落盘产物核对 | 待验证 |
| 谓词编译期三条约束生效（stage/data_deps 时序错配报错、VETO 仅限 S2、lookahead_safe 门禁回测） | 单元测试与编译校验用例 | 待验证 |
| 上线前通过 `quality_gates.py` 三道校验（`LookaheadGuard` / `AShareComplianceGuard` / `OverfittingGuard`），样本外胜率不低于样本内 70% | 治理门禁执行报告 | 待验证 |
| ERS 全部待标定参数完成网格搜索标定并出具标定报告（禁止未标定直接实盘） | 标定报告与样本外回测结果 | 待验证 |
| Stage 4 双层风控（T-Gap 跳空止损 / T-Time 时间止损 / T+1 不可卖约束）接入并通过回放验证 | `position_stop_monitor.py` 回放用例 | 待验证 |

## 七、变更日志

| 日期 | 变更摘要 |
|:---|:---|
| 2026-09-21 | **第 4 批回写**：§2.2/§2.3 平行目录按 E-01 回写为 funnel 实际路径（`funnel_engine.py`/`stock_funnel.py`/`funnel_cmds.py`/`config/funnel_strategy.yaml`），不新建平行目录（B-02）；§2.4 CLI 回写为 `funnel screen --mode` / `funnel regime` / `funnel trigger`（A-03/T-08）；§三 Q1～Q12 逐条回写裁定结论、删除全部「本设计默认」冲突数值（B-01）；集合竞价解除 `P0-阻塞`/`★缺口` 标记，改为首期采集归档（B-04/C-09）；止损口径改为「不统一数值 + 系统默认值 + 用户可配置」（A-02/D-23/C-07） |
| 2026-09-20 | 由 docs/guidelines/other/ 中文文档拆分迁入 |

### 附：原始需求留档

> **示例来源**：以下用户口述需求即[选股漏斗示例 1](../../guidelines/algorithm/selection-funnel-example-1.md) 的原始出处。其中的具体阈值与时间点属**示例口径**，仅作案例说明与默认取值参考，**不作为系统硬编码或规范数值**（参数化见 X-03）。

用户口述原文见对话记录（2026-09-17）。核心要点：
- T日盘后（15:00后）运行问财式选股公式，产出次日预备买入清单
- T+1 大盘须站上20日均线，否则当日不做
- T+1 09:30 筛选高开个股，09:30-09:35 捕捉冲高回调的买卖盘拐点
- 09:35-09:40 输出股票代码并下单
- 盈亏交由止损体系处理