# A股实战交易反应动作与风控执行手册（速查索引）

> 本文件是**纯速查索引**，不承载任何规范正文。所有分层架构契约、交易反应动作的触发条件与仓位配比、量化风控阈值、三级止损阶梯与保本价进位规则一律以 `docs/guidelines/` 为唯一真理来源 (SSOT)，本文件不复述、不定义。

---

## 一、权威定义与实施看板（SSOT 直达）

| 类型 | 文档 | 定位 |
|:---|:---|:---|
| 权威规范 (SSOT) | [`guidelines/business/trading-execution-rules.md`](../guidelines/business/trading-execution-rules.md) | 实战交易反应动作与风控执行规则的**唯一真理来源**：阿尔法与贝塔解耦架构、实战交易三原则、交易反应动作库、量化阈值库与保本价规则 |
| 实施看板 | [`specs/business/biz-trading-execution-and-risk-control.md`](../specs/business/biz-trading-execution-and-risk-control.md)（`SPEC-BIZ-003`） | 执行中枢 (EMS) 落地的任务矩阵、里程碑与验收证据 |
| 关联 SSOT | [`guidelines/business/breakeven-calculation-rules.md`](../guidelines/business/breakeven-calculation-rules.md) | 最低保本卖出价精算与向上进位规则的权威定义 |

---

## 二、速查入口（CLI / 技能）

| 我想做什么 | 调用入口 |
|:---|:---|
| 生成实战交易反应动作决策单（含保本价与止损阶梯） | `./bin/astock action --code <代码> --cost <成本> --shares <股数> --json` |
| 查阅交易反应动作与三级风控动作库 | 技能 `astock-action-execution` |
| 全流程个股诊断与综合评分 | `./bin/astock evaluate <代码> --json`（技能 `astock-platform-evaluate`） |
| 查看持仓与资金，准备执行参数 | `./bin/astock trade positions --json`（技能 `astock-trade-paper`） |
| 模拟下单与撮合验证 | `./bin/astock trade buy/sell --json`（技能 `astock-trade-paper`） |
| 输出交互式 HTML 指令单 | `./bin/astock report <代码> --json`（技能 `astock-report-html`） |
| 短线接力、游资战法与波段规则的场景化决策 | 技能 `astock-strategy-tuige` / `astock-strategy-chenxiaoqun` / `astock-strategy-mainboard` |
| 股票池清单与盘中监控 | `./bin/astock pool list --json`（技能 `astock-pool-dashboard`） |

---

## 三、使用约定

- 需要精确架构契约、动作触发条件、仓位配比、风控阈值与止损阶梯 → 一律打开上表 SSOT 链接，**不要在本文档内寻找数值**；
- 动作单与挂单必须以引擎返回值及 SSOT 定义为准，**禁止手工口算或自行复制常量**；
- 任何规则或阈值变更，只需修改 `docs/guidelines/` 下的权威规范，本索引无需同步；
- 若本索引与 SSOT 出现任何表述差异，**以 SSOT 为准**。

---

## 四、相关索引

- 保本价精算速查 → [`breakeven-rules.md`](breakeven-rules.md)
- 执行层技能参考原文 → [`../../.agents/skills/astock-platform-evaluate/references/action-execution-manual.md`](../../.agents/skills/astock-platform-evaluate/references/action-execution-manual.md)