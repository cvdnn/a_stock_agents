---
name: astock-paper-backtest
description: A股高保真模拟撮合账户、多股轮动回测与滚动样本外OOS防过拟合检验中枢。严格支持T+1冻结、涨跌停拦截、冲击滑点与过拟合三重警报。用于机构投研六步闭环第⑥步回测验证。
metadata:
  version: '2.0.0'
  author: A-Stock Agents
  tags: ["A股", "模拟盘", "策略回测", "多股轮动", "样本外OOS", "防过拟合", "回测验证"]
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared runtime is not bundled per skill.
---

# astock-paper-backtest — 模拟撮合与样本外回测检验中枢

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有调用强制追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`）。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

---

## 1. 机构投研六步闭环定位（阶段 ⑥：回测验证）

本技能处于专业买方投研六步闭环的**实盘前最终质量检验收官站**：
$$① 看盘知势 \longrightarrow ② 选股立池 \longrightarrow ③ 择时定买 \longrightarrow ④ 穿透体检 \longrightarrow ⑤ 仓位风控 \longrightarrow \mathbf{⑥ 回测验证}$$

**核心解决命题**：
- 策略或选股规则在历史时序上到底能不能赚钱？历史胜率与最大回撤如何？
- 策略是否利用未来函数过度拟合了历史样本（In-Sample）？
- 在考虑真实 T+1 制度、涨跌停无法买卖、印花税佣金与冲击滑点后，净收益几何？
- 样本外（Out-of-Sample）推演时，收益与夏普比衰减率是否超过安全红线？

---

## 2. 统一 CLI 调用矩阵

所有命令返回标准化 JSON 格式，严禁大模型手算收益或生成虚构交割单。

| 业务诉求 | 跨平台统一 CLI 命令 | 核心产出与字段 |
| :--- | :--- | :--- |
| **模拟账户查询** | `astock trade balance --json` | 可用现金、冻结资金、持仓总市值、账户总资产、累计浮动盈亏 |
| **模拟持仓明细** | `astock trade positions --json` | 持仓代码、持股数、可用股数（T+1）、持仓成本、现价、盈亏率 |
| **模拟报单买入** | `astock trade buy --code <代码> --price <价格> --shares <股数> --json` | 委托状态、成交均价（计入滑点）、成交数量、实扣规费税费 |
| **模拟报单卖出** | `astock trade sell --code <代码> --price <价格> --shares <股数> --json` | 委托状态、可用股数校验、成交回款、实扣印花税与佣金 |
| **成交流水审计** | `astock trade history --json` | 历史成交清单、时间戳、买卖方向、价格、税费明细 |
| **单股/组合回测** | `astock backtest <代码或股池> [--start <日期>] [--end <日期>] --json` | 累计收益率、年化收益率、夏普比率、最大回撤、基准阿尔法对比 |
| **滚动样本外OOS** | `astock backtest <代码或股池> --oos --json` | 步进样本内(IS)与样本外(OOS)表现对比、衰减率与过拟合三重警报 |

---

## 3. 数据溯源与循证信封规范 (`evidence_meta`)

所有回测与交易响应顶层强制封装 `evidence_meta` 溯源信封：

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

## 4. 真实市场交易制度硬约束

详见参考文档 [paper-trading-simulation-engine.md](references/paper-trading-simulation-engine.md)。
1. **T+1 硬约束**：当天买入份额冻结为 `frozen_shares`，绝不允许日内卖出，严禁高频日内回转；
2. **涨跌停封板拦截**：
   - 涨停板（主板 10% / 双创 20% / ST 5%）买一封死状态严禁挂单买入；
   - 跌停板卖一封死状态严禁挂单卖出；
3. **真实交易滑点与税费**：
   - 包含 0.05% 印花税（卖出）、万 2.5 佣金（最低 5 元起收）与过户费；
   - 自动施加 0.1%~0.25% 冲击滑点，杜绝虚假零摩擦收益。

---

## 5. 多股轮动回测与防过拟合三重警报

### 5.1 多股组合轮动回测
详见参考文档 [portfolio-rotation-backtest.md](references/portfolio-rotation-backtest.md)。
- 支持基于 5A 评分或 ISS 漏斗的多股轮动，计算年化收益、Alpha/Beta、卡玛比率与最大回撤持续期。

### 5.2 滚动样本外 (Rolling OOS) 检验机制
详见参考文档 [rolling-oos-validation.md](references/rolling-oos-validation.md)。
- 划分连续且不重叠的步进 IS 窗口与 OOS 窗口，检验策略在未知时序数据上的泛化能力。

### 5.3 防过拟合三重警报标准
详见参考文档 [overfitting-three-alarms.md](references/overfitting-three-alarms.md)。
当回测结果出现以下任一异常时，系统自动触发严重警告并标记 `is_overfit_suspected: true`：
1. **夏普比率过高**：$\text{Sharpe} > 3.5$（极大概率存在未来函数或收盘价偷价）；
2. **胜率异常完美**：$\text{WinRate} > 75\%$（违背 A 股单向做多常识，疑似过度拟合）；
3. **样本外严重衰减**：$\text{Decay} > 50\%$（IS 到 OOS 收益或夏普比腰斩，实盘不可用）。

---

## 6. 工业级可靠性与 Fail-Closed 铁律

1. **账户资金隔离**：SQLite 多账户数据存放于 `output/trade/` 本地私有目录，禁止跨用户或跨会话污染。
2. **不可用即刻拒绝**：历史 K 线数据存在断点、复权异常或标的停牌时，回测引擎直接终止并返回 `DATA_GAP_ERROR`，严禁通过线性插值伪造行情数据。
