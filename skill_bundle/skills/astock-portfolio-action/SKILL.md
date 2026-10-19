---
name: astock-portfolio-action
description: A股三级股票池全生命周期治理、精确保本价精算与盘中即时风控动作单中枢。内建ceil分位进位保本价、三级止损阶梯、五步MA重算审计与受限凯利仓位。用于机构投研六步闭环第⑤步仓位风控。
metadata:
  version: '2.0.0'
  author: A-Stock Agents
  tags: ["A股", "保本价", "止损阶梯", "股票池", "五步MA审计", "仓位风控"]
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared runtime is not bundled per skill.
---

# astock-portfolio-action — 股池风控与保本反应动作中枢

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有调用强制追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`）。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

---

## 1. 机构投研六步闭环定位（阶段 ⑤：仓位风控）

本技能处于专业买方投研六步闭环的**盘中实战执行与风控铁闸**：
$$① 看盘知势 \longrightarrow ② 选股立池 \longrightarrow ③ 择时定买 \longrightarrow ④ 穿透体检 \longrightarrow \mathbf{⑤ 仓位风控} \longrightarrow ⑥ 回测验证$$

**核心解决命题**：
- 买入某只股票后，**计入全部法定税费后的精确最低保本卖出价是多少？**
- 遭遇盘中逆势杀跌时，如何在 -3%/-5%/-8% 阶梯下果断执行防御与止损？
- 开盘冲高、震荡分化、跳水急跌三场景下的明确交易动作单是什么？
- 关注池、自选池、持仓池三级生命周期如何维护？过期失效与破位标的如何自动清洗？
- 如何通过受限凯利与 ATR 波动率模型科学计算每笔交易的建仓股数？

---

## 2. 统一 CLI 调用矩阵

所有命令返回标准化 JSON 格式，严禁大模型手算规费或凭感觉推荐仓位。

| 业务诉求 | 跨平台统一 CLI 命令 | 核心产出与字段 |
| :--- | :--- | :--- |
| **保本价与风控单** | `astock action [--code <代码>] --cost <成本> --shares <股数> --json` | `math.ceil` 向上进位保本价、T0/T1/T2三级止损、三场景即时动作单 |
| **三级股票池查询** | `astock pool list [--type watchlist\|focus\|positions] --json` | 关注/自选/持仓池标的清单、现价、盈亏比与更新时间戳 |
| **股池标的增删** | `astock pool add/remove --type <池类型> --code <代码> [--cost <成本>] [--shares <股数>] --json` | 增删记录、更新持久化 CSV 并返回最新股池状态 |
| **五步真实MA审计** | `astock pool audit [--data <路径>] --json` | 真实 MA(5/10/20/60) 重算、破位止损标记、失效均线偏离清洗建议 |
| **通达信股池导出** | `astock pool tdx [--output-dir <目录>] --json` | 导出通达信兼容格式自定义板块文件 (`.blk` / `.txt`) |
| **受限凯利仓位精算** | `astock position-risk --capital <本金> --win-rate <胜率> --odds <盈亏比> --atr <波幅> --json` | 受限半凯利最优建议仓位、建议买入股数（向下整百进位） |

---

## 3. 数据溯源与循证信封规范 (`evidence_meta`)

所有风控响应顶层强制封装 `evidence_meta` 溯源信封：

```json
{
  "evidence_meta": {
    "as_of_trading_day": "2026-10-19",
    "quote_source": "L1:tencent_realtime",
    "kline_bars_count": 250,
    "watermark_ready": true,
    "fee_rule_ssot": "stamp_0.0005_comm_0.00025_min5_ceil"
  },
  "data": { ... }
}
```

---

## 4. 实战交易三原则（智能体输出铁律）

在给用户输出任何持仓分析与风控建议时，**必须强制包含以下三项要素**：

1. **精确最低保本卖出价**：
   - 印花税 0.05%、佣金万 2.5 且最低 5 元起收、过户费 0.001%；
   - 必须调用 `execution_action_engine.py` 进行精算，并强制向上进位至分位（`math.ceil`），拒绝任何四舍五入。
2. **三级风控止损阶梯**：
   - **T0 警戒线：$-3\%$**（防守准备，停止左侧补仓）
   - **T1 减仓线：$-5\%$**（坚决减仓 $50\%$ 保本防守）
   - **T2 绝杀线：$-8\%$**（无条件清仓止损出局）
3. **三场景即时动作单**：
   - **开盘冲高**：早盘快速拉升超 $+3\%$，择机减仓锁定利润；
   - **盘中震荡**：振幅处于 $[-1.5\%, +1.5\%]$，耐心持股等待；
   - **跳水急跌**：放量击穿分时均线且破 T0/T1 线，果断执行减仓或止损。

详见参考文档 [breakeven-and-stoploss-rules.md](references/breakeven-and-stoploss-rules.md)。

---

## 5. 三级股池治理与五步真实 MA 审计

### 5.1 三级股票池生命周期管理
详见参考文档 [three-tier-pool-governance.md](references/three-tier-pool-governance.md)。
- 关注池 (`watchlist`) $\to$ 自选池 (`focus`) $\to$ 持仓池 (`positions`) 严格隔离；
- 持久化统一落盘至 `output/pools/`，与工程代码隔离。

### 5.2 五步真实 MA 重算与失效标的清洗算法
详见参考文档 [five-step-ma-audit.md](references/five-step-ma-audit.md)。
- 拒绝静态均线数据：拉取非空标的近 60 日真实日 K 向量化重算 `MA5/10/20/60`；
- 自动检测并输出 `breached_stops`（跌破止损位）与 `stale_records`（停牌或均线极端偏离标的）。

### 5.3 受限凯利与 ATR 动态头寸管理
详见参考文档 [kelly-position-sizing.md](references/kelly-position-sizing.md)。
- 受限半凯利控制单票上限 $\le 30\%$，结合 ATR 波动率折算最稳健整百买入股数。

---

## 6. 工业级可靠性与 Fail-Closed 铁律

1. **空股池即刻终止分析**：
   - 调用 `astock pool list --json` 时，若股池数据为空，**严禁猜测、捏造股票或擅自推荐替代标的**；
   - 必须直接向用户提示股池为空，并给出标准登记指引：
     - **持仓股登记**：`股票代码:持股数@成本价`（例如：`000001:1000@12.50`）；
     - **关注/自选股登记**：直接输入股票代码或名称（例如：`000001`、`600519`）。
2. **算力真实性**：
   - 所有费率计算必须基于统一契约，禁止大模型口算四舍五入。
