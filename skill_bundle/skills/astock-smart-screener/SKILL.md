---
name: astock-smart-screener
description: A股智能多因子选股与Alpha挖掘中心。整合5A五维共振选股、五大财务排雷、ISS四阶条件树智能漏斗、截面因子清洗(MAD/Z-Score/IC)与T+N跟踪评估。用于机构投研六步闭环第②步选股立池。
metadata:
  version: '2.0.0'
  author: A-Stock Agents
  tags: ["A股", "智能选股", "5A共振", "财务排雷", "条件树漏斗", "截面因子", "选股立池"]
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared runtime is not bundled per skill.
---

# astock-smart-screener — 智能漏斗选股与多因子Alpha中心

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有调用强制追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`）。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

---

## 1. 机构投研六步闭环定位（阶段 ②：选股立池）

本技能处于专业买方投研六步闭环的**第二顺位枢纽**：
$$① 看盘知势 \longrightarrow \mathbf{② 选股立池} \longrightarrow ③ 择时定买 \longrightarrow ④ 穿透体检 \longrightarrow ⑤ 仓位风控 \longrightarrow ⑥ 回测验证$$

**核心解决命题**：
- 全市场 5000+ 标的中，哪些标的符合当前主线轮动、估值合理且具备稳健超额 Alpha？
- 候选标的是否存在商誉暴雷、大股东高比例质押、业绩滑坡或长期阴跌等黑天鹅隐患？
- 如何对选出的股票池进行自动化 T+1/3/5/10 胜率跟踪与模型迭代调优？

---

## 2. 统一 CLI 调用矩阵

所有命令返回结构化 JSON 数据，支持管道处理。

| 业务诉求 | 跨平台统一 CLI 命令 | 核心产出与字段 |
| :--- | :--- | :--- |
| **5A 主线轮动选股** | `astock screen --dynamic hot_sectors --min-score 70 --json` | 5A 多因子共振候选池、五维分值、五大财务排雷结果 |
| **ISS 漏斗模型校验** | `astock funnel validate --config <模型YAML> --json` | AST 语法树合法性校验、条件节点统计、版本 SHA256 指纹 |
| **四阶智能漏斗执行** | `astock funnel run --stage <1\|2\|3\|4\|all> --assemble --json` | 各阶淘汰明细、入池标的集合、最终入选名单及特征评分 |
| **选股结果胜率跟踪** | `astock screen-model track --date <YYYY-MM-DD> --json` | 历史选股 T+1/3/5/10 真实超额收益、胜率统计与最大回撤 |
| **截面因子流水线** | `astock quant pipeline --json` | MAD 去极值、Z-Score 标准化、换手沉淀因子与滚动 IC 矩阵 |

---

## 3. 数据溯源信封规范 (`evidence_meta`)

所有选股结果必须包含规范溯源元数据：

```json
{
  "evidence_meta": {
    "as_of_trading_day": "2026-10-19",
    "quote_source": "L1:tencent_realtime",
    "kline_bars_count": 250,
    "watermark_ready": true,
    "fee_rule_ssot": "stamp_0.0005_comm_0.00025_min5_ceil"
  },
  "model_version_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "screened_stocks": [ ... ]
}
```

---

## 4. 核心选股引擎与质控规范

### 4.1 五大财务排雷一票否决机制 (Financial Minefield Rules)
详见参考文档 [financial-minefield-rules.md](references/financial-minefield-rules.md)。
在进入评分前，必须前置通过五大财务硬拦截：
1. **高股价流动性折损**：过滤股价 $> 350$ 元标的（降低散户与中小机构单手资金占用摩擦）；
2. **超高 PE / 亏损泡沫**：绝对剔除 $\text{PE} \le 0$（亏损）与 $\text{PE} > 100$ 倍泡沫股；
3. **长期亏损准 ST 风险**：净利润与扣非净利润连续为负的标的直接排除；
4. **业绩滑坡风险**：近两期营业收入与净利润同比双双大幅下滑超过 30% 且非周期股豁免者拦截；
5. **长期阴跌飞刀**：近 60 日跌幅 $>20\%$、120 日跌幅 $>30\%$ 或处于年内新低附近的标的绝对排除，禁止逆势接飞刀。

### 4.2 5A 五维多因子共振模型
详见参考文档 [5a-resonance-model.md](references/5a-resonance-model.md)。
- **技术面 (25%)** + **趋势动能 (22%)** + **量能结构 (18%)** + **筹码均线 (15%)** + **主力资金 (20%)**。
- **共振级别评定**：
  - A 级共振：总分 $\ge 75$ 且至少 4 个单维达标；
  - B 级共振：总分 $\ge 60$ 且至少 3 个单维达标。

### 4.3 SPEC-ALGO-ISS-001 四阶漏斗架构
详见参考文档 [iss-funnel-specification.md](references/iss-funnel-specification.md)。
- **Stage 1 (Universe 基础流动性池)**：剔除 ST、退市、停牌及日均成交额 $< 3000$ 万标的；
- **Stage 2 (财务排雷与基本面质地)**：执行财务排雷一票否决与 ROE 门槛；
- **Stage 3 (技术共振与趋势破位过滤)**：多头均线排列与 MACD 过滤；
- **Stage 4 (主线轮动与多因子 Alpha 排序)**：行业景气度匹配与综合打分输出。

### 4.4 截面因子工程 (Cross-Sectional Factors)
详见参考文档 [cross-sectional-factors.md](references/cross-sectional-factors.md)。
- 3倍中位数绝对偏差（MAD）去极值；
- 截面 Z-Score 标准化：$z = (x - \mu) / \sigma$；
- 滚动 Rank IC 计算与信息比率（IR）跟踪。
