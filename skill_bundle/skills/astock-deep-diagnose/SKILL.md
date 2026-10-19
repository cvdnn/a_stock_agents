---
name: astock-deep-diagnose
description: A股个股全维穿透体检、7角色多空循证辩论与交互式研报交付。内建100分量化打分、解套决策树、财务排雷与多空双向证据链。用于机构投研六步闭环第④步穿透体检。
metadata:
  version: '2.0.0'
  author: A-Stock Agents
  tags: ["A股", "股票诊断", "多空辩论", "HTML研报", "解套决策", "穿透体检"]
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared runtime is not bundled per skill.
---

# astock-deep-diagnose — 个股全维穿透体检与多空循证中枢

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有调用强制追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`）。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

---

## 1. 机构投研六步闭环定位（阶段 ④：穿透体检）

本技能处于专业买方投研六步闭环的**个股深度穿透核心**：
$$① 看盘知势 \longrightarrow ② 选股立池 \longrightarrow ③ 择时定买 \longrightarrow \mathbf{④ 穿透体检} \longrightarrow ⑤ 仓位风控 \longrightarrow ⑥ 回测验证$$

**核心解决命题**：
- 经过前序选股立池与择时信号触发的标的，**其基本面与量价筹码到底能不能买？**
- 标的是否存在商誉减值、大股东高质押或 ST 退市等财务致命暗雷？
- 7 大专业分析师多空博弈结论如何？看多看空的真实实证与证伪条件是什么？
- 被套持仓该如何按解套决策树科学施救？
- 如何一键生成自包含、红涨绿跌、具备买方级质感的交互式 HTML 研报？

---

## 2. 统一 CLI 调用矩阵

所有命令返回标准化 JSON 格式，严禁大模型捏造或口算指标数据。

| 业务诉求 | 跨平台统一 CLI 命令 | 核心产出与字段 |
| :--- | :--- | :--- |
| **全维综合诊断** | `astock diagnose <代码> [--cost <成本> --shares <股数>] --json` | 100分打分、S/A/B/C/D评级、六维雷达、保本价与三级止损单 |
| **100分量化体检** | `astock evaluate <代码> --json` | 宏观/基本面/技术/量价/游资/风控六维得分、核心观点卡 |
| **7角色多空辩论** | `astock debate <代码> --json` | 基本面/量价/消息/政策/游资/筹码/风控 7 角色论证与双向证据链 |
| **解套决策树** | `astock trapped <代码> --cost <成本> --shares <股数> --json` | 浅度/中度/深度套牢诊断、FIFO成本复核、网格T+0与减仓解套方案 |
| **单文件HTML研报** | `astock report <代码> [--html] --json` | 自包含免CDN交互式研报，输出至 `output/reports/<代码>_report.html` |

---

## 3. 数据溯源与循证信封规范 (`evidence_meta`)

所有诊断响应顶层强制封装 `evidence_meta` 溯源信封：

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

## 4. 金字塔结论先行范式 (BLUF - Bottom Line Up Front)

在面向用户输出任何股票诊断结论时，**必须严格按以下三屏金字塔结构组织呈现**：

### 4.1 第一屏：【核心结论卡】
- **综合评级**：`S / A / B / C / D`
- **量化总分**：100 分制（如：`82.5 分`）
- **大盘健康度门控**：🟢 绿灯进攻 / 🟡 黄灯控仓 / 🔴 红灯防守
- **一句话投研核心观点**：明确指出催化逻辑、关键支撑位与证伪触发价。

### 4.2 第二屏：【实战交易三原则执行单】
根据项目铁律强制输出：
1. **精确最低保本卖出价**：严格计入 0.05% 印花税、万 2.5 佣金（最低 5 元）与过户费，强制向上进位至分位（`math.ceil`）；
2. **三级风控止损阶梯**：
   - T0 警戒线：$-3\%$（防守准备）
   - T1 减仓线：$-5\%$（减仓 $50\%$ 保本防守）
   - T2 绝杀线：$-8\%$（无条件止损出局）
3. **三场景即时动作单**：明确开盘冲高择机兑现、盘中窄幅震荡观望、盘中跳水急跌防御的三场景触发条件。

### 4.3 第三屏：【六维穿透与多空双向证据链】
- **六维正交得分**：宏观(15%) / 基本面(25%) / 技术(20%) / 量价筹码(20%) / 游资(10%) / 风控(10%)；
- **Top 3 看多实证**：具体指标数值、历史分位与支撑逻辑；
- **Top 3 风险证伪条件**：均线破位点、止损位与博弈失败迹象。

---

## 5. 核心量化模型与判定规范

### 5.1 100 分制全维量化评估模型
详见参考文档 [comprehensive-evaluation-model.md](references/comprehensive-evaluation-model.md)。
- 五大财务硬排雷一票否决：触碰 ST、高质押($\ge 70\%$)、高商誉($\ge 30\%$)、财报非标或严重失真时，总分强行降至 40 分以下，评级直接归入 D (高危)。

### 5.2 7 角色多空对抗辩论机制
详见参考文档 [seven-agent-debate-protocol.md](references/seven-agent-debate-protocol.md)。
- 基本面、量价、政策、游资、筹码、风控 6 位分析师展开对抗质询，由投决会首席裁判综合裁定。

### 5.3 被套持仓分级解套决策树
详见参考文档 [trapped-position-decision-tree.md](references/trapped-position-decision-tree.md)。
- 浅度被套 (0%~5%) 逢高保本，中度被套 (5%~15%) 控仓做 T，深度被套 (>15%) 严防加仓陷阱、依托 90% 筹码峰设定减亏救赎计划。

### 5.4 单文件自包含 HTML 研报规范
详见参考文档 [html-report-design-spec.md](references/html-report-design-spec.md)。
- 零外部 CDN 依赖、红涨绿跌、专业买方亚光白视觉质感、全自包含图表与三原则动作单。

---

## 6. 工业级高可靠性与 Fail-Closed 铁律

1. **零幻觉与零估算**：所有指标数值必须由底层 Python 算法确定性计算，严禁模型自行脑补财务数值或手算保本价。
2. **失败关闭 (Fail-Closed)**：标的代码不存在、已退市、停牌或日 K 线不足 30 根时，坚决返回 `status: "error", code: "DATA_UNAVAILABLE"`，拒绝生成伪造研报。
