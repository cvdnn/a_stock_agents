---
name: astock-market-data
description: A股全景行情、复权K线、技术筹码与大盘五维情绪中枢。支持4级容灾实时行情、全套经典技术指标、筹码分布获利盘分析与大盘五维健康度门控。用于机构投研六步闭环第①步看盘知势。
metadata:
  version: '2.0.0'
  author: A-Stock Agents
  tags: ["A股", "行情", "K线", "技术指标", "筹码分布", "大盘情绪", "看盘知势"]
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared runtime is not bundled per skill.
---

# astock-market-data — 全景行情与大盘五维情绪中枢

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有调用强制追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`）。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

---

## 1. 机构投研六步闭环定位（阶段 ①：看盘知势）

本技能处于专业买方投研六步闭环的**第一顺位起点**：
$$\mathbf{① 看盘知势} \longrightarrow ② 选股立池 \longrightarrow ③ 择时定买 \longrightarrow ④ 穿透体检 \longrightarrow ⑤ 仓位风控 \longrightarrow ⑥ 回测验证$$

**核心解决命题**：
- 当前市场处于什么情绪周期？是适合进攻还是必须控仓防守？
- 资金主线在哪？盘面承接与量能结构如何？
- 关注标的的真实量价形态、关键均线支撑与筹码获利盘分布如何？

---

## 2. 统一 CLI 调用矩阵

所有命令返回标准化 JSON 格式，严禁大模型捏造或口算指标数据。

| 业务诉求 | 跨平台统一 CLI 命令 | 核心产出与字段 |
| :--- | :--- | :--- |
| **实时全景报价** | `astock data quote <代码> --json` | 现价、涨跌幅、内外盘、五档买卖盘、换手率、振幅、成交量/额 |
| **历史复权K线** | `astock data kline <代码> [--period D\|W\|M\|60\|30] [--limit 250] --json` | 前复权 OHLCV 序列、均线序列、分时/日线量价切片 |
| **经典技术指标** | `astock data tech <代码> --json` | MA(5/10/20/60)、MACD(DIF/DEA/柱)、KDJ、RSI(6/12/24)、BOLL、ATR、BIAS |
| **筹码分布分析** | `astock data cyq <代码> --json` | 获利盘比例、平均持仓成本、70%/90% 筹码集中度与价格区间 |
| **个股事件资金** | `astock data events <代码> --json` | 近期除权除息、业绩预告、大宗交易与主力资金流向 |
| **大盘五维健康度** | `astock market [代码] --json` | 趋势/情绪/量能/结构/资金五维 100 分制打分、操作建议灯号（红/黄/绿） |

---

## 3. 数据溯源与循证信封规范 (`evidence_meta`)

本技能产出的所有 JSON 响应顶层强制封装 `evidence_meta` 溯源信封，确保所有数据可复核、可归档：

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

## 4. 核心量化模型与判定规范

### 4.1 大盘五维健康度模型（Market Health Dimensions）
详见参考文档 [market-health-dimensions.md](references/market-health-dimensions.md)。
- **趋势动能 (25%)**：上证/深成/创业板三大指数均线多头排列及站上 MA20 情况；
- **短线情绪 (25%)**：全市场真实连板高度、涨停家数、跌停家数、炸板率与赚钱效应；
- **市场量能 (20%)**：沪深两市总成交额变化率及对比 20 日均量水准；
- **结构赚钱效应 (15%)**：上涨/下跌家数比（中位数涨跌幅）与百股涨停活跃度；
- **主力资金流向 (15%)**：北向资金净流入、两融余额变动与主力大单流向。
- **三色信号灯门控**：
  - 🟢 **绿灯进攻 (总分 $\ge 70$)**：市场健康，允许右侧追涨、连板接力与主线建仓；
  - 🟡 **黄灯控仓 (50 $\le$ 总分 $< 70$)**：分化震荡，仅允许低吸与防守波段，总仓位控制在 50% 以下；
  - 🔴 **红灯防守 (总分 $< 50$)**：退潮破位，严禁追涨追高，买点信号全面抑制。

### 4.2 筹码分布获利盘量化模型（CYQ）
详见参考文档 [cyq-chip-distribution.md](references/cyq-chip-distribution.md)。
- 获利比例 $> 80\%$：多头绝对控盘，警惕高位兑现；
- 获利比例 $< 10\%$：超跌深水区，关注水下低吸与双金叉抗跌机会；
- 筹码集中度 $< 10\%$：筹码高度集中，主力锁仓明确。

### 4.3 技术指标确定性规范
详见参考文档 [technical-indicators-handbook.md](references/technical-indicators-handbook.md)。
- 全部指标 100% 由 `skill_bundle/runtime/core/data/technical_indicators.py` 计算得出，严禁大模型手算或估算。

---

## 5. 工业级高可靠性与 Fail-Closed 铁律

1. **4 级数据源自动容灾**：
   - 优先一级通道：腾讯实时接口（毫秒级行情与高并发支持）；
   - 二级备用通道：东方财富行情接口；
   - 三级备用通道：新浪财经公共接口；
   - 四级离线保底：本地日级数据水位快照（需声明水位延迟）。
   详见 [data-source-fallbacks.md](references/data-source-fallbacks.md)。
2. **失败关闭 (Fail-Closed)**：
   - 标的代码不存在、停牌或 K 线数据不足 30 根时，坚决返回标准错误码 `DATA_UNAVAILABLE`，严禁捏造价格或生成虚构均线。
