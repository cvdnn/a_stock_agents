# 通用选股体系与早盘拐点触发机制实施计划

> 规范编号：`SPEC-ALGO-003`
> 权威定义 (SSOT)：[`general-selection-and-turning-point-rules.md`](../../guidelines/algorithm/general-selection-and-turning-point-rules.md)
> **实施状态**：规划中 (RFC)

## 一、规范核心定位摘要

- 本看板承载「通用选股体系与早盘拐点触发机制」（网阀选股 SFTC 五阶段流水线）的代码落地映射、待确认问题裁决、分期路线与验收口径。
- 条件谓词、阶段规则、时点契约、ERS 评分模型、策略 YAML Schema 与回测治理口径的权威定义一律以 [`general-selection-and-turning-point-rules.md`](../../guidelines/algorithm/general-selection-and-turning-point-rules.md) 为准，本看板不复述。
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

| 新增文件 | 职责 | 优先级 |
|---|---|---|
| `scripts/core/models/predicate.py` | 谓词 Schema + 编译期校验（三条约束） | P0 |
| `scripts/core/models/pipeline.py` | SFTC 五阶段流水线编排器 | P0 |
| `scripts/core/strategy/opening_reversal/` | 本战法的具体实现目录 | P0 |
| ├─ `ers_model.py` | ERS 复合评分（A/B/C 三组 14 指标） | P0 |
| ├─ `phase_detector.py` | 冲高/回调阶段划分 | P0 |
| ├─ `intraday_monitor.py` | 并发监控调度 + 限流 | P0 |
| └─ `signal_dispatcher.py` | 信号推送与下单窗口管理 | P1 |
| `config/strategies/*.yaml` | 策略配置目录 | P0 |
| `scripts/core/data/fetch_auction.py` | 集合竞价数据（★缺口） | P0-阻塞 |
| `scripts/core/data/intraday_archiver.py` | 盘中数据前向采集归档 | P0-回测前置 |

### 2.3 需改造

| 文件 | 改造内容 | 优先级 |
|---|---|---|
| `fetch_realtime.py` `_parse_tencent_quote` | 补充解析五档 bid/ask（`parts[9-28]`，数据已在响应中） | **P0-低成本高收益** |
| `data_bridge.py` `get_fundamentals()` | 补 `circulating_market_cap` / `float_shares` 字段 | P1 |
| `config.py` `infer_market_prefix()` | 提取为统一 `is_excluded_board()` 过滤函数 | P1 |
| `risk_manager.py` / `risk_position_manager.py` | 新增 T-Gap 跳空止损 + T-Time 时间止损 + T+1 不可卖约束 | **P0-安全** |
| `config.py` | 统一止损口径常量（见权威定义文档 8.3 发现的口径矛盾） | **P0-安全** |
| `registry.py` | 注册新策略与新因子 | P0 |
| `commands/strategy_cmds.py` | 新增 CLI handler | P1 |
| `config/skills_manifest.json` | 新增技能条目 | P2 |

### 2.4 CLI 设计（对齐现有约定，统一追加 `--json`）

```bash
# T日盘后：生成候选池
.\bin\astock.ps1 screen opening_reversal --date 2026-09-17 --json

# T日盘后：大盘门禁预判
.\bin\astock.ps1 regime check --strategy opening_reversal --json

# T+1早盘：启动实时监控（长驻进程）
.\bin\astock.ps1 trigger watch --strategy opening_reversal --json

# 任意时刻：ERS 模型单日复盘（用归档数据）
.\bin\astock.ps1 trigger replay --date 2026-09-18 --json

# 回测
.\bin\astock.ps1 backtest --strategy opening_reversal --from 2026-01-01 --json
```

## 三、⚠️ 待用户确认的开放问题

以下问题会显著改变系统行为，**不应由实现方擅自决定**：

| # | 问题 | 冲突/风险 | 本设计默认 | 影响面 |
|---|---|---|---|---|
| **Q1** | 新高周期是 **20日** 还是 **60日**？ | 原文两处矛盾（公式行20日 vs 解释行60日） | 20日 | 候选池规模从"几十只"变为"个位数" |
| **Q2** | 高开幅度用哪档？ | 原文"1~2%以上" vs "只要高开都行"矛盾 | 标准档 [1%, 5%] | 直接决定 Stage 3a 通过率 |
| **Q3** | `gap_max` 上限定多少？ | 原文只说下限，未说上限；无上限会纳入大量追高陷阱 | 5% | 胜率与盈亏比 |
| **Q4** | 涨幅 7% 上限是否按板块差异化？ | 7% 对 20cm 板块偏严，会误杀强势票 | 统一 7% | 候选池板块构成 |
| **Q5** | 大盘门禁用哪个指数？ | "大盘"未指明；上证 vs 创业板结论可能相反 | 上证综指（必需）+ 创业板（加权，非必需） | 交易日开仓率 |
| **Q6** | **是否接受 T+1 导致当日无法止损？** | 用户说"按止损做"，但制度上做不到 | 重构为双层风控（权威定义文档第 8 章） | 最大回撤可能显著超过 -8% |
| **Q7** | 单票/单日仓位上限定多少？ | 原文未提；因当日不可止损，须压缩敞口 | 单票20% / 单日40% / 最多3只 | 风险敞口 |
| **Q8** | 是否接受"前向采集 40-60 交易日后才能标定 ERS"？ | 无历史分钟/tick 数据，ERS 无法立即回测 | 先前向采集 + 降级代理回测并行 | 上线时间表 |
| **Q9** | 拐点未触发时，是否允许放宽到 9:40 后继续观察？ | 原文硬约束 9:35-9:40 出代码 | 不允许，9:34:30 软截止 | 信号数量 |
| **Q10** | 是否需要 9:25 竞价预筛（依赖 P0 数据缺口）？ | 能提前缩小监控范围，但需新增数据源 | 二期实现 | 监控压力与信号质量 |
| **Q11** | **既有三套止损口径以哪套为准？** | `-8%`（AGENTS.md）vs `MA20-2%`（risk_manager）vs `-6%`（risk_position_manager）互斥 | 本战法用固定百分比 -3/-5/-8，与全局解耦 | 全局风控一致性 · P0技术债 |
| **Q12** | 单票仓位沿用既有板块差异化上限（主板15%/20cm 8%）还是本文初值20%？ | `strategy_cmds.py:397` 已有更保守的既有约定 | **建议沿用既有 15%/8%** | 风险敞口 |

## 四、分期落地路线图

### 一期：可跑通的最小闭环（不依赖新数据源）

- [ ] `predicate.py` + `pipeline.py` 骨架，含三条编译期约束
- [ ] Stage 0/1/1.5/2 完整实现（数据全部已有，仅缺流通市值 → 临时用名称正则判ST + 待补市值）
- [ ] Watchlist 落盘至 `output/pools/`
- [ ] Stage 3a 缺口过滤（快照已有）
- [ ] Stage 3b ERS **降级版**（无五档，B组30分制，阈值59）
- [ ] `intraday_archiver.py` 前向采集上线（**越早启动越好，它是回测的前置条件**）
- [ ] CLI `screen opening_reversal` + `trigger watch`
- [ ] 全部信号只进**模拟盘**（`astock-trade-paper`），不接实盘

**一期交付标准**：连续 5 个交易日稳定产出 Watchlist + 早盘信号，无限流、无崩溃、无未来函数告警。

### 二期：数据补全与标定

- [ ] 补齐五档解析（`_parse_tencent_quote`，低成本）→ 启用 B2
- [ ] 补齐流通市值 / ST 标记 / 北交所统一过滤函数
- [ ] 接入集合竞价数据（P0 缺口）→ 实现 9:25 竞价预筛
- [ ] 积累 40-60 交易日归档数据后，网格搜索标定 ERS 全部参数
- [ ] 通过 `OverfittingGuard` 样本外校验

### 三期：验证与增强

- [ ] 完整回测（含滑点、手续费、T+1 约束、跳空止损）
- [ ] Stage 4 双层风控接入 `position_stop_monitor.py`
- [ ] HTML 复盘报告（`astock-report-html`）：每日信号 + 触发明细 + ERS 分解
- [ ] 参数敏感性分析，确定稳健区间
- [ ] 抽象为通用引擎，支持用户用 YAML 自定义新战法

### 贯穿项：既有止损口径统一（P0 技术债）

- [ ] 裁决 `AGENTS.md`（-8%）、`risk_manager.py`（MA20-2%）、`risk_position_manager.py`（-6.0%）三套互斥口径，统一 `config.py` 止损常量（见权威定义文档 8.3 节），须在 Stage 4 开发前闭环

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
| 2026-09-20 | 由 docs/guidelines/other/ 中文文档拆分迁入 |

### 附：原始需求留档

用户口述原文见对话记录（2026-09-17）。核心要点：
- T日盘后（15:00后）运行问财式选股公式，产出次日预备买入清单
- T+1 大盘须站上20日均线，否则当日不做
- T+1 09:30 筛选高开个股，09:30-09:35 捕捉冲高回调的买卖盘拐点
- 09:35-09:40 输出股票代码并下单
- 盈亏交由止损体系处理