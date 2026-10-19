---
name: astock-tactical-signals
description: A股实战战法识别与形态买点信号雷达。整合主板趋势波段、MACD水下二次金叉、陈小群顶级游资总龙头战法与退哥短线接力算法。所有买点内建250日历史胜率锚与45bps成本过滤。用于机构投研六步闭环第③步择时定买。
metadata:
  version: '2.0.0'
  author: A-Stock Agents
  tags: ["A股", "战法识别", "择时买点", "水下双金叉", "游资龙头", "退哥短线", "历史胜率锚", "择时定买"]
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared runtime is not bundled per skill.
---

# astock-tactical-signals — 实战战法与形态买点信号雷达

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有调用强制追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`）。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

---

## 1. 机构投研六步闭环定位（阶段 ③：择时定买）

本技能处于专业买方投研六步闭环的**第三顺位执行触点**：
$$① 看盘知势 \longrightarrow ② 选股立池 \longrightarrow \mathbf{③ 择时定买} \longrightarrow ④ 穿透体检 \longrightarrow ⑤ 仓位风控 \longrightarrow ⑥ 回测验证$$

**核心解决命题**：
- 候选股票池中的标的，当前是否出现了高胜率、高盈亏比的确定性买点形态？
- 形态触发时，该股在过去 250 个交易日内发生同类信号的真实胜率、盈亏比与扣费净期望如何？
- 结合大盘当前五维健康度门控，是否应当右侧追进、低吸试错或果断放弃？

---

## 2. 统一 CLI 调用矩阵

所有命令返回标准化 JSON 数据，支持单股或批量扫描。

| 业务诉求 | 跨平台统一 CLI 命令 | 核心产出与字段 |
| :--- | :--- | :--- |
| **综合战法雷达** | `astock signal <代码> [--tactic all\|mainboard\|macd\|chenxiaoqun\|tuige] --json` | 命中战法列表、信号类型、买点置信度、250 日胜率锚与扣费期望 |
| **MACD 水下双金叉** | `astock pattern macd <代码> --json` | 双波谷极值对比、DIF 低点抬高判定、间距过滤、三档决策建议 |
| **陈小群游资总龙头** | `astock pattern chenxiaoqun <代码> --json` | 竞价弱转强、深水低吸、中军做 T 缩仓、首阴二波反包四大模式判定 |
| **退哥短线场景检查** | `astock shortline check --code <代码> [--scenario <场景>] --json` | 涨停基因、缩量回踩 MA5/10 支撑、龙头首阴反包、连板接力检验 |
| **主板趋势防御反击** | `astock strategy swing --code <代码> --json` | 大市值品种趋势回踩 MA20/60、均值回归通道与防御性建仓点 |

---

## 3. 数据溯源与历史胜率锚定信封 (`evidence_meta` & `win_rate_anchor`)

本技能任何买点信号输出时，强制内嵌**近 250 日同类信号历史胜率回溯锚定（C4 标准）**：

```json
{
  "evidence_meta": {
    "as_of_trading_day": "2026-10-19",
    "quote_source": "L1:tencent_realtime",
    "kline_bars_count": 250,
    "watermark_ready": true,
    "fee_rule_ssot": "stamp_0.0005_comm_0.00025_min5_ceil"
  },
  "signal": {
    "tactic": "chenxiaoqun_weak_to_strong",
    "triggered": true,
    "trigger_price": 18.52,
    "confidence_score": 88.5
  },
  "win_rate_anchor": {
    "lookback_trading_days": 250,
    "historical_triggers_count": 6,
    "t_plus_5_win_rate": 0.667,
    "avg_profit_loss_ratio": 2.35,
    "fee_friction_bps": 45,
    "net_expected_return": 0.042,
    "market_gate_status": "GREEN_LIGHT"
  }
}
```

---

## 4. 四大实战战法量化模型

### 4.1 MACD 水下二次金叉 (Underwater Second Golden Cross)
详见参考文档 [macd-underwater-golden-cross.md](references/macd-underwater-golden-cross.md)。
- 拒绝单日 dif/dea 简单三元判断，执行真实双波谷极值对比；
- 第一波谷：跌出反抽，DIF 形成第一次低位谷值 $V_1$；
- 第二波谷：回踩验底，价格持平或跌破前期低点，但 DIF 第二次波谷 $V_2 > V_1$（动能衰竭）；
- 触发器：零轴下方 DIF 再次上穿 DEA 形成二次金叉，且两金叉间距在 8~30 个交易日内。

### 4.2 陈小群游资总龙头四大战法
详见参考文档 [chenxiaoqun-dragon-patterns.md](references/chenxiaoqun-dragon-patterns.md)。
- **模式一：竞价弱转强**（昨日烂板或尾盘炸板，今日集合竞价大幅高开超预期且成交额放大）；
- **模式二：深水大单承接低吸**（盘中下挫至 -5%~-8% 深水区，出现连续大单主动吃盘止跌）；
- **模式三：中军大票做 T 锁仓**（百亿以上核心中军品种，缩量回踩分时均线低吸做 T）；
- **模式四：总龙头首阴二波反包**（连续 4 板以上大龙头断板首阴，次日早盘分时快速拉升反包翻红）。

### 4.3 退哥短线规则与接力算法
详见参考文档 [tuige-shortline-rules.md](references/tuige-shortline-rules.md)。
- 由纯 Python 算法 `tuige.py` 驱动：
  - 涨停基因识别（近 20 日至少有 1 次涨停）；
  - 缩量回踩 MA5/MA10 企稳（回调日成交量为涨停日的 50% 以下）；
  - 首阴次日弱转强分时拉升；
  - 严格执行纪律与失效止损。

### 4.4 主板趋势波段防守反击
详见参考文档 [tactical-strategies-handbook.md](references/tactical-strategies-handbook.md)。
- 聚焦沪深主板流动性充裕品种，沿上升通道均线（MA20/MA60）低吸布局。

---

## 5. 实战风控铁律与门控约束

1. **大盘红灯自动抑制**：若大盘健康度处于红灯冰点期，系统自动对追涨型买点降权并输出 `MARKET_RED_LIGHT_SUPPRESSED` 预警；
2. **45bps 摩擦成本门槛**：历史胜率锚扣除双边 45bps 税费冲击成本后，若期望收益为负，判定为无效噪点；
3. **输出三原则联动**：买点触发后，必须无缝交付下游 `astock-portfolio-action` 精算向上进位的保本卖出价与三级止损阶梯。
