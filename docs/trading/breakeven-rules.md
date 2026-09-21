# A股最低保本卖出价精算规则（速查索引）

> 本文件是**纯速查索引**，不承载任何规范正文。所有数学公式、费率数值、进位算法实现与规则阈值明细一律以 `docs/guidelines/` 为唯一真理来源 (SSOT)，本文件不复述、不定义、不镜像复制。

---

## 一、权威定义与实施看板（SSOT 直达）

| 类型 | 文档 | 定位 |
|:---|:---|:---|
| 权威规范 (SSOT) | [`guidelines/business/breakeven-calculation-rules.md`](../guidelines/business/breakeven-calculation-rules.md) | 最低保本卖出价精算与向上进位的**唯一真理来源**：费率参数表、数学模型、求解算法与强制进位铁律的全部定义 |
| 费率口径规范 (SSOT) | [`guidelines/business/broker-commission-rules.md`](../guidelines/business/broker-commission-rules.md) | 券商佣金配置化与费率口径的权威定义 |
| 实施看板 | [`specs/business/biz-breakeven-price-calculation-plan.md`](../specs/business/biz-breakeven-price-calculation-plan.md)（`SPEC-BIZ-002`） | 精算引擎落地的任务矩阵、里程碑与验收证据 |

---

## 二、速查入口（CLI / 技能）

| 我想做什么 | 调用入口 |
|:---|:---|
| 精算单只标的的最低保本卖出价与风控动作 | `./bin/astock action --code <代码> --cost <成本> --shares <股数> --json` |
| 查阅保本价、止损阶梯与场景动作库 | 技能 `astock-action-execution` |
| 个股全流程诊断（含持仓费用口径） | `./bin/astock evaluate <代码> --json`（技能 `astock-platform-evaluate`） |
| 生成含持仓最低卖出价列的交互式报告 | `./bin/astock report <代码> --json`（技能 `astock-report-html`） |
| 清点持仓成本与股数，作为精算输入 | `./bin/astock trade positions --json`（技能 `astock-trade-paper`） |
| 校验持仓池成本档案是否过期 | `./bin/astock pool audit --json`（技能 `astock-pool-audit`） |

---

## 三、使用约定

- 需要精确公式、费率参数、最低门槛与进位规则 → 一律打开上表 SSOT 链接，**不要在本文档内寻找数值**；
- 报告与挂单必须直接使用引擎返回值，**禁止手工口算或自行复制常量**；
- 任何费率数值或算法变更，只需修改 `docs/guidelines/` 下的权威规范，本索引无需同步；
- 若本索引与 SSOT 出现任何表述差异，**以 SSOT 为准**。

---

## 四、相关索引

- 交易执行动作与风控速查 → [`execution-manual.md`](execution-manual.md)