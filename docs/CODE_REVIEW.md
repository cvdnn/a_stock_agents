# A-Stock Agents 代码审查报告

> 审查范围：`core/` 全部 6 个子系统 + CLI + 周边脚本（`bin/`、`reporting/`、`install/`）
> 审查方法：5 路并行逐文件审查 + 主线程交叉复核关键缺陷
> 审查基准：PEP 8 / 命名 / 类型注解 / docstring / 魔法数字，SOLID / DRY / 内聚与耦合，正确性（资金、费率、T+1、涨跌停）、健壮性（异常处理）、安全性（注入、密钥、路径穿越）
> 严重度分级：🔴 高（崩溃/算错钱/泄密/可被攻击）、🟡 中（结果失真/健壮性差/逻辑矛盾）、🟢 低（规范与可维护性）

---

## 一、总体结论

代码库**结构清晰、分层合理**（数据桥 4 级降级、指标/模型/策略/风控/模拟盘职责分明），但**工程化与正确性欠账明显**：跨模块存在一类同构问题——**数据契约字段名不一致**导致大量分支逻辑静默失效，以及**异常被无差别吞掉**掩盖真实错误。共识别 🔴 高危 11 项、🟡 中危约 25 项、🟢 低危约 40 项。

最高优先级是 4 处「读不存在的字段，静默用默认值」的正确性缺陷，它们不报错却会让卖出/买入决策退化为固定值。

---

## 二、🔴 高危问题（正确性 / 崩溃 / 安全）

### 1. `execution_action_engine.py` — 字段名契约不匹配，动作引擎大量分支失效

- `core/strategy/execution_action_engine.py:124-134` 及 `:312-330`
- 读取的字段在真实数据源中**全部不存在**，永远命中默认值：

| 代码读取字段 | 真实字段（数据桥/指标） | 后果 |
|---|---|---|
| `quote["vol_ratio"]` | 无此字段（腾讯行情无量比） | 恒为 `1.0` |
| `quote["outer_ratio"]` | 实际为 `o_ratio` | 恒为 `50.0` |
| `quote["turnover"]` | 实际为 `turnover_pct` | 恒为 `0.0` |
| `quote["open"]` | 腾讯快照无 `open` | 恒等于 `price` |
| `tech["rsi14"]` | 实际为 `rsi` | 恒为 `50.0` |
| `tech["atr14"]` | 实际为 `atr` | 恒为 `price*0.03` |
| `tech["macd_dif"]`/`tech["macd_dea"]` | 实际为 `dif`/`dea` | 恒为 `0.0` |

- 后果：`generate_action` 中「放量突破买入（vol_ratio>1.4 and outer_ratio>53）」「缩量回踩买入（vol_ratio<0.90 and macd_dif>macd_dea）」「高位见顶（rsi14>72）」等分支**永远不会触发**，实际只走默认观望/持股路径。`DownsideReactionMatrix` 的类型 B（缩量假摔）/类型 A（见顶）判定同样失效。
- 附：文件头 docstring 声称佣金「万0.85」，实际默认 `万2.5（0.00025）`（`calc_min_breakeven_price`），文档与实现不一致。

### 2. `data_bridge.py:492` — 调用不存在的方法，`--action index` 必崩

- `core/data/data_bridge.py:492`：`result = bridge.index_snapshot()`，但 `index_snapshot` 是**模块级函数**，`DataBridge` 类上没有此方法 → `AttributeError`。
- CLI `python data_bridge.py index` 立即崩溃。

### 3. `combo_scorer.py:381` — `sys` 未导入，K 线不足时抛 `NameError`

- `core/models/combo_scorer.py:381`：`sys.exit(1)`，但文件头仅 `import json` + `from typing import ...`（第 10-11 行），未导入 `sys`。
- 当 K 线不足 26 根时，本应优雅退出，实际抛 `NameError: name 'sys' is not defined`。

### 4. `multi_dim_model.py:670` — 未来函数：历史快照误用末日收盘价

- `core/models/multi_dim_model.py:670`：`_latest_at` 构造历史某日 `latest` 快照时，`latest["close"] = tech_all["latest"]["close"]` 取的是**全序列最后一日收盘价**，而非目标 `day` 日收盘价。
- 当前该 `close` 恰好未被 `score()` 直接使用，但属回测未来函数隐患，一旦被引用即产生前视偏误。

### 5. `unstructured_factors.py:124-129` — 舆情时间衰减被施加两次

- `core/models/unstructured_factors.py:124-129`：`decayed = apply_decay(score, ...)` 已含 `2^(-d/h)`，随后 `weighted_scores.append(decayed * w)` 又乘一次 `w = 2^(-d/h)`，得分被**平方衰减**，舆情因子整体系统性压低。

### 6. `technical_indicators.py:427-434` — CLI 入口引用未导入的 `Path`/`sys` 与错误模块

- `core/indicators/technical_indicators.py`：直接运行 `python technical_indicators.py --input ...` 时：
  - `:427` 使用 `Path(...)` 但文件未导入 `from pathlib import Path`
  - `:429` `from data_bridge import DataBridge`（应为 `core.data.data_bridge`，且当前目录无此模块）
  - `:434` `sys.exit(1)` 但未导入 `sys`
- 三条路径均会 `NameError`/`ModuleNotFoundError`。

### 7. `investment_report.py:95` — 硬编码代理鉴权令牌（泄密）

- `core/reporting/investment_report.py:95`：代理 IP + `auth` 令牌 `202606169K83S6LN` 硬编码在源码中，随仓库分发即泄露代理凭据。

### 8. `update.py:63-64` — Zip Slip 路径穿越

- `bin/update.py:63-64`：解压升级包时未校验 `zip_entry` 是否含 `..`，可将文件写入包目录之外的任意路径（目录穿越写入漏洞）。

### 9. `ta_analyze.py:605` — 引用未定义的 `SKILL_DIR`

- `core/multi_agent/ta_analyze.py:605` 附近使用 `SKILL_DIR` 变量，但该作用域未定义 → 运行时 `NameError`。

### 10. `paper_trading/engine.py:791-804` — 卖出先扣仓、校验失败不回滚

- `core/paper_trading/engine.py:791-804`：卖出流程先对持仓 `lots` 做递减，随后若校验（T+1/数量等）不通过直接 `return` 拒绝，**未回滚已扣减的仓位**，导致持仓被凭空削减。

### 11. `multi_backtest_engine.py` — 声明支持但完全缺失涨跌停 / T+1

- 多策略回测引擎对外宣称支持 A 股约束，但实现中**没有任何涨跌停价限制、也没有 T+1 当日不可卖**的逻辑，回测结果与实际可成交性不符。

---

## 三、🟡 中危问题（结果失真 / 逻辑矛盾 / 健壮性）

### 数据层 `core/data/`

| 位置 | 问题 |
|---|---|
| `data_bridge.py:151` | `tencent_quote` 以 `name`（股票名）为返回字典键，同名/重名标的互相覆盖 |
| `data_bridge.py` 多处 | 市场前缀推断逻辑（`sh`/`sz`/`bj`）重复 ≥4 处，未抽取公共函数 |
| `data_bridge.py:366-418` | `get_fundamentals`/`get_cyq` 用 `python -c "..."` f-string 拼接执行，`code` 未转义，存在命令注入面 |
| `fetch_realtime.py:869` | `parts[0]=="1"` 恒为假，沪市股票被误标为 `sz` |
| `fetch_history_fallback.py:844` | 引用未定义的 `EM_PERFORMANCE_URL` |
| 多处 | `except Exception: pass` 静默吞掉行情解析失败，上游拿到空数据继续算分 |

### 指标层 `core/indicators/technical_indicators.py`

| 位置 | 问题 |
|---|---|
| `gap_analysis` | 向下跳空 `filled = today_low < yesterday_close` 恒为 `True`，方向判定错误 |
| `:386` | `("失效位可承受", True)` 硬编码恒真，人为抬高通过数 |
| `second_leg` 检查 | `("第二脚回踩低位区", True)` 等主观项硬编码为真 |
| `:388-397` | 通过 7 条判 `B`（可试错）、5-6 条判 `A`（观察名单）——评级语义与直觉相反（A 应优于 B） |
| `ma` | `len(closes) < n` 时除零/索引越界未防护 |
| `rsi` | 存在 off-by-one 边界 |

### 模型层 `core/models/`

| 位置 | 问题 |
|---|---|
| `market_assessor.py:20-37` | `assess_trend` docstring 称「基于 MA20 方向」，实际只用单日 `change_pct>0.5` |
| `market_assessor.py:64-93` | `assess_volume`/`assess_capital` 无条件返回固定 15/10 分，五维中两维（35/100 权重）是占位常量 |
| `market_assessor.py:24` | `"000001" in code` 子串匹配误命中平安银行（000001.SZ） |
| `combo_scorer.py:180` | 资金流解析只删「亿/万」不换算量纲，「5000万」与「5000亿」同值 |
| `combo_scorer.py:259,272-277` | `total` 未归一化；缺失维度仍计入 8+8 中性分，尺度不统一 |
| `multi_factor_scorer.py:137-144` | `trend_score` 区间重叠且非单调（0.6 得 100、0.66 得 70） |
| `multi_factor_scorer.py:330-363 vs 382` | 因子计算逻辑重复两处（DRY 违反） |
| `factor_synthesizer.py:109,119` | `custom_weights` 不校验和为 1；缺失因子填 `0.0` 经 Z-score 后成为极端值 |
| `stock_screener.py:55,134` | `float(b.get("changePct",0))` 遇 None/字符串抛 `TypeError` |
| `stock_screener.py:198` | 按未归一化 `total` 排序，有无 cyq/fund 的股票不可比 |
| `stock_screener.py:176` | `board_top10` 参数用涨跌幅代替「是否进 TOP10」布尔语义 |
| `multi_dim_model.py:576,611` | 涨跌停/单日跌幅以当日开盘价为基准，而非前一交易日收盘 |
| `multi_dim_model.py:434-441` | `evaluate` 依赖调用方先手动调 `gate.assess()`，漏调用则门控恒关闭 |
| `multi_dim_model.py:483-505` | `STATE_CONFIG` 阈值从未参与决策，配置与逻辑脱节 |
| `multi_dim_model.py:931-934` | 换股轮动把当前持仓也纳入候选，且拿「他人今日分」对比「持仓入场日分」，口径错位 |
| `multi_dim_model.py:1258` | 用样本内收益 `max()` 选最优参数，样本内过拟合 |
| `strategy_evaluator.py:125` | 循环内对每条 entry 重复拉取同一支股票完整 K 线 |

### 策略层 `core/strategy/`（主线程亲自补审）

| 位置 | 问题 |
|---|---|
| `risk_manager.py:100,109` | 顶背离死代码（恒为假）；MACD 红柱缩短条件 `<=` 倒挂且未判红柱 `> 0` |
| `risk_manager.py:20-34` | 三级止损 T0 硬编码 `-5%`（docstring），与 README/配置文件「T0 警戒 -3%」口径不一致 |
| `grid_trading_strategy.py` | 网格动作分配 `"buy" if i < grid_count/2 else "sell"` 与网格价位语义无耦合，低档位未必映射到买 |
| `position_manager.py:60-83` | `_get_quote` 双层 `except Exception: pass`，行情失败静默返回 `{}` |
| `pool_schema.py:97-102` | `write_pool_csv` 用「rows 首元素是否为 str」推断参数顺序，空列表/字符串行会误判字段与数据 |

### 模拟盘 `core/paper_trading/`

| 位置 | 问题 |
|---|---|
| `engine.py` | `except Exception: pass` 多处；卖出后不校验涨跌停价、不核 T+1 的边界仍在若干路径缺失 |
| `backtest_metrics.py` | 指标口径（年化/夏普）魔法数字分散，部分分母未防零 |

### CLI 与周边

| 位置 | 问题 |
|---|---|
| `cli.py:1350-1353` | `version` 硬编码 `2.0.0`，与 `config.py VERSION="v3"`、`pyproject 3.0.0` 三者不一致 |
| `cli.py` 全篇 | 1359 行「上帝模块」，约 30 个子命令全部内联实现，重复参数解析与 `--json` 分支 |
| `investment_report.py` | 除令牌外，报告 HTML 模板字符串拼接无转义，存在注入面 |

---

## 四、🟢 低危问题（编码规范与可维护性）

**跨模块系统性通病：**

1. **`except Exception: pass` 泛滥** — `data_bridge`、`position_manager`、`stock_screener`、`multi_factor_scorer`、`paper_trading/engine` 等大量「静默吞异常」，掩盖真实故障、留下错误数据继续传播。
2. **`print` 代替 `logging`** — 全库无统一日志，仅少量 `file=sys.stderr`，生产不可观测。
3. **魔法数字密集** — 评分阈值（75/60/50）、止损比例（0.95/0.98）、乖离率（8.0/1.5）、评级分界等散落各处，未外置到 `config`。
4. **市场前缀逻辑重复** — `sh`/`sz`/`bj` 推断在 `data_bridge`、`fetch_*`、`position_manager` 等多处重写。
5. **`python -c` f-string 注入** — `data_bridge.get_fundamentals`/`get_cyq` 等用字符串拼接生成子进程代码，`code` 未做白名单校验。
6. **版本号漂移** — `2.0.0` / `v3` / `3.0.0` 三处不一致。
7. **路径与编码** — Windows/POSIX 路径拼接混用 `os.path`/`Path`/字符串，`open()` 多处未显式 `encoding="utf-8"`。

**模块级示例（摘录）：**

- `combo_scorer.py`：`score_ma_structure` 的 `klines` 参数未使用；`:343` `stop_loss_b` 计算后从未使用；`:374` 未关文件/未指定编码；docstring 权重表与实现不一致。
- `multi_dim_model.py`：`import sys, os, json, math` 一行多导入且 `sys`/`math` 未用；`_find_a_stocks_scripts` 死代码；`FiveDimScorer.score` 单函数约 250 行；`prev_equity` 死变量；`_latest_at` 附近 `vol_change` 已 `abs` 后 `elif vol_change>=-20` 分支不可达。
- `multi_dim_model_v3.py:10,12`：星导入 `from ... import *`；`DeprecationWarning` 默认被解释器隐藏。
- `factor_synthesizer.py`：`FACTOR_DIRECTIONS` 中多个因子未在权重表使用；分位数口径 `(rank+1)/n` 与 `_zscore` 的 n-1 与 `multi_factor_scorer` 的 n 不一致。
- `mean_reversion_strategy.py`：`generate_signal` 用 try/except 双导入，`backtest_signals` 又只用 `from technical_indicators import`，导入风格不统一。
- `execution_action_engine.py`：`parse_user_query` 的 `KNOWN_NAMES` 硬编码 15 支股票名，无法扩展。
- `position_manager.py`：emoji 密集输出与 `print` 混用，`cmd_*` 函数职责混杂 I/O 与业务逻辑。

---

## 五、按模块严重度汇总

| 模块 | 🔴 高 | 🟡 中 | 🟢 低 |
|---|---|---|---|
| `core/data/data_bridge.py` | 1 | 3 | 3 |
| `core/data/fetch_*` | 0 | 2 | 2 |
| `core/indicators/technical_indicators.py` | 1 | 4 | 3 |
| `core/models/combo_scorer.py` | 1 | 2 | 5 |
| `core/models/multi_dim_model.py` | 1 | 6 | 6 |
| `core/models/multi_factor_scorer.py` | 0 | 2 | 3 |
| `core/models/factor_synthesizer.py` | 0 | 2 | 3 |
| `core/models/unstructured_factors.py` | 1 | 1 | 2 |
| `core/models/market_assessor.py` | 0 | 3 | 2 |
| `core/models/stock_screener.py` | 0 | 4 | 2 |
| `core/models/strategy_evaluator.py` | 0 | 1 | 3 |
| `core/strategy/execution_action_engine.py` | 1 | 0 | 2 |
| `core/strategy/risk_manager.py` | 0 | 2 | 1 |
| `core/strategy/*`（其余） | 0 | 2 | 3 |
| `core/paper_trading/engine.py` | 1 | 2 | 2 |
| `core/paper_trading/multi_backtest_engine.py` | 1 | 0 | 1 |
| `core/cli.py` | 0 | 1 | 3 |
| `core/reporting/investment_report.py` | 1 | 1 | 0 |
| `core/multi_agent/ta_analyze.py` | 1 | 0 | 0 |
| `bin/update.py` | 1 | 0 | 0 |
| **合计（去重）** | **11** | **~25** | **~40** |

---

## 六、建议修复优先级（P0 → P3）

**P0 — 立即修复（崩溃 / 算错钱 / 泄密 / 可被攻击）** [✅ 全部 11 项已修复并通过全量验证]

1. [✅ 已修复] `execution_action_engine.py` 字段名统一：`vol_ratio` 补全、`outer_ratio→o_ratio`、`turnover→turnover_pct`、`rsi14→rsi`、`atr14→atr`、`macd_dif/macd_dea→dif/dea`（提交 `ea6f56a`）。
2. [✅ 已修复] `data_bridge.py:492` 改为模块级 `index_snapshot()`（提交 `edfa8ad`）。
3. [✅ 已修复] `combo_scorer.py` 补 `import sys`，并规范 CLI 命名空间导入与路径（提交 `af1ee27` 及优化）。
4. [✅ 已修复] `multi_dim_model.py:670` 改为取 `day` 日收盘价，消除未来函数（提交 `f575a59`）。
5. [✅ 已修复] `unstructured_factors.py` 移除重复衰减，采用单次加权归一（提交 `44c6bed`）。
6. [✅ 已修复] `investment_report.py` 移除硬编码令牌改环境变量（提交 `f07c269`）；并对参考文档示例脱敏。
7. [✅ 已修复] `bin/update.py` 校验 zip 条目路径防穿越（提交 `259ecc4`）。
8. [✅ 已修复] `paper_trading/engine.py` 卖出前置汇总校验可卖数量后扣仓（提交 `e85187a`）。
9. [✅ 已修复] `multi_backtest_engine.py` 补 10%/20%/30% 涨跌停封板拦截与 T+1 状态机约束（提交 `3015a80`）。
10. [✅ 已修复] `technical_indicators.py` CLI 入口补 `import sys` / `Path` 与绝对导入（提交 `6dd457e`）。
11. [✅ 已修复] `ta_analyze.py` 显式定义 `SKILL_DIR`，消除运行时 `NameError`（提交 `6dd457e`）。

**P1 — 数据正确性（结果失真）** [✅ 全部 9 项已修复并通过全量验证]

1. [✅ 已修复] `fetch_realtime.py` 沪市标识修复：修正 `parts[0] == "1"` 恒假逻辑，结合 `_sh` / `_bj` 标识及 600/688/900 代码规则准确分配市场前缀。
2. [✅ 已修复] `fetch_history_fallback.py` 补齐常量：定义 `EM_PERFORMANCE_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"`，消除交易日历调用抛 `NameError`。
3. [✅ 已修复] `market_assessor.py` 指数匹配与动态评估：修复 `"000001"` 误匹配平安银行（增加严格 `sh` 标识与命名强校验），`assess_trend` 增加 MA20 趋势计算；`assess_volume` 依据成交额动态分档；`assess_capital` 支持资金流向动态评分与降级基准。
4. [✅ 已修复] `technical_indicators.py` 缺口与评级修复：`gap_analysis` 向下跳空回补修正为 `today_high >= yesterday_close`；修复 7+ 条件判 B、5-6 条件判 A 的评级语义反转；增强 `ma`/`rsi` 短序列防护。
5. [✅ 已修复] `combo_scorer.py` 资金流量纲与归一化：`score_fund_flow` 准确换算“万”与“亿”，消除 5000万 误判为 5000亿 满分故障；在缺失 `cyq` 或 `fund_flow` 时动态调减有效满分并计算百分制 `normalized_score`。
6. [✅ 已修复] `stock_screener.py` 健壮性与归一化排序：`changePct` 转 float 增加 None/空串保护；选股候选列表改按百分制 `normalized_score` 排序，确保缺失筹码标的与完整标的公平可比。
7. [✅ 已修复] `multi_factor_scorer.py` 评分区间单调化：消除 `trend_score` 的区间重叠，采用清晰互斥且单调的上涨日占比区间映射。
8. [✅ 已修复] `factor_synthesizer.py` 缺失因子与权重规范：`custom_weights` 自动归一化使权重和为 1.0；缺失因子改用截面中位数（Median）填充，避免经 Z-score 产生极端伪异常值。
9. [✅ 已修复] `risk_manager.py` 顶背离死代码与红柱缩短修复：将 `dif < max(dif for _ in [0])` 恒假死代码修复为基于阶段新高与前期 DIF 峰值对比的顶背离检测；修复 MACD 红柱连续 3 日缩短条件（修正 `<=` 倒挂并限定红柱 `> 0` 且单调递减）。

**P2 — 健壮性治理**

- 全局清理 `except Exception: pass`，改为分级日志 + 可降级异常；`python -c` 注入加 `code` 白名单校验；统一字段默认值与 `None` 防护；统一版本号来源。

**P3 — 可维护性**

- 抽出公共市场前缀/费用常量到 `config`；`cli.py` 子命令拆分为模块；引入 logging；外置魔法数字；统一导入风格与类型注解。

---

## 附：审查线程分工

| 线程 | 范围 | 状态 |
|---|---|---|
| 子代理 1dc8adbb | data 与 indicators 层 | ✅ 完成 |
| 子代理 80bb70a1 | models 模型层（9 文件） | ✅ 完成 |
| 子代理 f0f3f2f8 | paper_trading 模拟盘 | ✅ 完成 |
| 子代理 a2aa9d88 | 多智能体与周边模块 | ✅ 完成 |
| 主线程 | strategy 策略层（子代理耗尽空间，亲自补审） | ✅ 完成 |
