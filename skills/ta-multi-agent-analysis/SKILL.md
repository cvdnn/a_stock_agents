---
name: ta-multi-agent-analysis
version: "1.0.0"
author: ""
description: "Use when you need multi-agent A-stock research with 7 AI analysts (Market/Social/News/Fundamentals/Policy/HotMoney/Lockup), bull-bear debate, risk assessment, and integrated AI-Platform paper-trading + cron monitoring. Combines TradingAgents-astock multi-LLM debate pipeline with AI-Platform data fallback, quantitative scoring, and execution layers."
license: MIT
metadata:
  AI-Platform:
    tags: [A股, 多智能体, 辩论, 投研, 分析, 交易, 政策, 游资, 解禁]
    related_skills: [a-share-data, a-share-paper-trading, trading-combo, macd-trend-resonance-stock-picker, a-share-strategy-mainboard-multi-swing-defensive, a-share-investment-expert, user-feedback-verification, a-share-dashboard]
---

# 多Agent投研分析 — TradingAgents × AI-Platform 整合

## Overview

将 [TradingAgents-astock](https://github.com/simonlin1212/TradingAgents-astock)（1750⭐）的 7 分析师多 Agent 辩论管道，与 AI-Platform 已有的 A 股权威技能体系深度融合。AI-Platform 端提供数据降级、量化评分、模拟盘执行、自动监控；TradingAgents 端提供多视角分析师协作、结构化辩论、质量门控和综合决策。

## When to Use

使用触发条件：

- **个股全维度分析** — "分析 600519"、"给 688017 做个深度报告"
- **多Agent辩论决策** — "多角度分析 600760，让分析师们辩论一下"
- **投研报告生成** — "出一份带政策分析、游资、解禁的完整报告"
- **决策 + 执行** — "分析完如果推荐买入，直接在模拟盘下单并部署监控"
- **融合评分验证** — "用 TradingAgents 跑完再用 trading-combo 打分验证"

不使用场景：

- 仅查实时行情 → 用 `a-share-data `
- 仅做简单技术分析 → 用 `macd-trend-resonance-stock-picker`
- 仅跑量化选股 → 用 `trading-combo` 或 `a-share-strategy-mainboard-multi-swing-defensive`

## 架构总览

```
                            ┌──────────────────────────┐
                            │   ta_analyze.py (入口)    │
                            │ AI-Platform CLI 触发           │
                            └──────┬───────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
         ┌────────────────┐ ┌──────────┐ ┌──────────────┐
         │  AI-Platform 数据层  │ │ 量化评分 │ │ TradingAgents│
         │ (a-share-data) │ │ 预筛选   │ │ 多Agent管道  │
         │ 4层降级保障     │ │ (可选)   │ │ 7分析师辩论  │
         └────────┬───────┘ └──────────┘ └──────┬────────┘
                  │                              │
                  ▼                              ▼
         ┌──────────────────────────────────────────┐
         │        结果融合 & 交叉验证                │
         │  AI-Platform 数据源 × TA 分析师报告            │
         │  trading-combo 评分 × LLM 决策           │
         └─────────────────┬────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌────────────┐ ┌──────────────┐ ┌────────────────┐
   │ 模拟盘执行  │ │ 自动监控部署  │ │ 综合报告输出   │
   │ paper-     │ │ cron止损     │ │ Markdown/JSON  │
   │ trading    │ │ 入场条件检测  │ │ Web UI 集成    │
   └────────────┘ └──────────────┘ └────────────────┘
```

## 前置条件

### 1. TradingAgents-astock 安装

```bash
# 克隆到本地
git clone https://github.com/simonlin1212/TradingAgents-astock.git
cd TradingAgents-astock
pip install -e .

# 配置 LLM API Key (.env 文件)
cat > .env << 'EOF'
# 推荐 MiniMax（国内直连，性价比高）
MINIMAX_API_KEY=sk-xxx
# 或 DeepSeek
DEEPSEEK_API_KEY=sk-xxx
EOF

# 验证
python3 -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('OK')"
```

### 2. AI-Platform 前置技能就绪

| 技能 | 用途 | 安装状态 |
|------|------|---------|
| `a-share-data` | 数据层（4层降级） | ✅ 已验证 |
| `a-share-paper-trading` | 模拟盘交易服务 | ✅ 已验证 |
| `trading-combo` | 量化评分（可选验证） | ✅ 已就绪 |
| `macd-trend-resonance-stock-picker` | 技术评分（可选验证） | ✅ 已就绪 |

### 3. 路径约定

本 skill 在脚本中自动检测以下路径（优先级从高到低）：

```python
_TA_PATHS = [
    "/mnt/c/Users/user/coding/TradingAgents/_original_src",  # 完整管道（agents/graph/llm_clients）
    "/mnt/c/Users/user/coding/TradingAgents",                # 根项目（仅 dataflows/ 时不可用）
    "~/TradingAgents-astock",                                  # 用户目录
]
```

> ⚠️ `_original_src` 优先级高于 `TradingAgents` 根目录，因为它包含完整的 `agents/graph/llm_clients` 模块。根目录可能只有 `dataflows/` 子模块，无法运行 Phase 2。

## 核心工作流

### 完整 3 阶段分析

```
Phase 1 — 数据准备 & 预筛选（AI-Platform 端）
┌──────────────────────────────────────────────┐
│ ① 调用 a-share-data 获取实时行情 + K线        │
│ ② 调用 trading-combo 做 100 分评分预筛        │
│ ③ 调用 a-share-strategy 做趋势回踩检测        │
│ ④ 过滤不可交易标的（688/30/8 开头排除）       │
│ → 产出：量化评分 + 数据清单                    │
└──────────────────────────────────────────────┘

Phase 2 — 多Agent深度分析（TradingAgents 端）
┌──────────────────────────────────────────────┐
│ ⑤ 7 分析师并行产出报告                        │
│   市场 | 舆情 | 新闻 | 基本面 | 政策 | 游资 | 解禁 │
│ ⑥ Quality Gate 质量门控（硬检查 + LLM 审核）  │
│ ⑦ Bull vs Bear 多轮辩论                      │
│ ⑧ Research Manager 综合研判 → 投资计划       │
│ ⑨ Trader 生成交易方案（T+1/涨跌停/手数）     │
│ ⑩ 激进/保守/中立三方风险辩论                 │
│ ⑪ Portfolio Manager 最终决策（Buy/Hold/Sell）│
│ → 产出：结构化决策 + 报告                      │
└──────────────────────────────────────────────┘

Phase 3 — 执行 & 监控（AI-Platform 端）
┌──────────────────────────────────────────────┐
│ ⑫ 如果决策 Buy：                              │
│   ├─ 通过 a-share-paper-trading API 模拟下单  │
│   ├─ 部署 cron 止损监控（每5分钟检测）         │
│   └─ 设定入场条件监控（价格触及提醒）          │
│ ⑬ 如果决策 Sell：                             │
│   └─ 触发被套诊断流程（三档阶梯减仓方案）      │
│ → 产出：执行结果 + 监控状态                     │
└──────────────────────────────────────────────┘
```

## CLI 使用

### 完整分析（Phase 1+2+3，含股池同步）

```bash
VENV_PY="python3"
SKILL_DIR="./.AI-Platform/skills/stocks/ta-multi-agent-analysis"

# 基础分析（自动同步到自选股池）
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600519 --date 2026-07-09

# 关闭股池同步
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600519 --no-sync-pool

# 完整模式（Phase 1 + 2 + 3）
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600760 \
  --date 2026-07-09 \
  --pre-score \           # Phase 1: 开启量化预筛
  --paper-trade \         # Phase 3: 模拟盘下单
  --deploy-monitor        # Phase 3: 部署cron监控

# 输出格式
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600519 --date 2026-07-09 --json    # JSON 输出
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600519 --date 2026-07-09 --brief   # 精简版

# 指定 LLM 供应商
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 688017 \
  --provider minimax \
  --deep-model "MiniMax-M2.7" \
  --quick-model "MiniMax-M2.7-highspeed"

$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 688017 \
  --provider deepseek \
  --deep-model "deepseek-chat" \
  --quick-model "deepseek-chat"
```

### 仅跑特定阶段

```bash
# 仅 Phase 1：量化预筛（不跑 LLM）
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600519 \
  --phase 1 --pre-score

# 仅 Phase 2：多Agent分析（不执行、不监控）
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600519 --phase 2

# 仅 Phase 3：基于已有决策执行
$VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600519 --phase 3 \
  --decision '{"action":"BUY","price":185.50,"shares":100,"stop_loss":178.00}'
```

### 批量分析

```bash
# 从文件读取代码列表
cat stocks.txt
600519
600760
688017

$VENV_PY $SKILL_DIR/scripts/ta_analyze.py --batch stocks.txt \
  --date 2026-07-09 --phase 2 --json > batch_report.json
```

## 输出格式

### 完整报告结构

```text
═══════════════════════════════════════════════════
  {股票名称}({代码}) — 多Agent投研报告
  日期：{交易日期}
═══════════════════════════════════════════════════

─── Phase 1: 数据预筛 ───

量化评分（trading-combo 100分制）
  均线结构: 25/25 | MACD: 40/40 | 量价: 15/15 | 板块: 20/20
  总分: 85/100 → 评级: A ✅

策略引擎预筛
  趋势回踩: 通过 ✓（距MA20: 1.2%）
  账户限制: 通过 ✓（主板可交易）

─── Phase 2: 多Agent深度分析 ───

🏪 市场分析师
  [核心结论] 均线多头排列，MACD零轴上金叉
  [关键数据] MA5>MA10>MA20，RSI 62，布林带中轨上方
  [置信度] 高 | 数据源: 腾讯行情

💬 舆情分析师
  ...

📰 新闻分析师
  ...

📊 基本面分析师
  ...

🏛️ 政策分析师
  ...

🔥 游资追踪师
  ...

🔓 解禁监控师
  ...

─── 质量门控 ───
  技术: A | 舆情: B | 新闻: A | 基本面: A
  政策: A | 游资: B | 解禁: A
  整体评级: A | 数据可信度: 高

─── Bull vs Bear 辩论 ───
  多头观点: ...
  空头观点: ...
  辩论结论: 多头占优（3轮辩论）

─── Research Manager 综合研判 ───
  投资计划: 逢低建仓，受益于光通信行业景气度提升
  技术面 + 板块 + 产业逻辑三维验证: ✅

─── Trader 交易方案 ───
  入场价: 185.00~188.00
  止损价: 178.00 (MA20下方2%)
  目标价: 205.00 (前高)
  盈亏比: 2.8:1 ✅
  交易规则: T+1合格 / 涨跌幅限制内 / 100股整数倍

─── 风险评估 ───
  激进: 可建仓40%
  保守: 建仓15%即可
  中立: 建仓25%
  共识: 建仓20~25%

─── Portfolio Manager 最终决策 ───
  决策: BUY ✅
  仓位: 25%（约4.6w）
  置信度: 高
  时效: 本周有效

─── Phase 3: 执行 & 监控 ───

模拟盘执行
  账户: alpha | 状态: 已成交
  成交价: 186.20 | 数量: 200股 | 金额: 37,240.00
  剩余资金: 462,760.00

监控部署
  止损监控: ✅ 已部署（5分钟/次）
  入场条件: 已设定（MA20回踩检测）
  推送: WeChat + 桌面通知

─── 可信度标签 ───
  数据源: 腾讯行情/东方财富(proxy-patch)/新浪
  时效性: 实时/盘中 | 置信度: 高
```

### 输出控制

| 选项 | 效果 |
|------|------|
| 默认 | 完整文本报告 |
| `--json` | 结构化 JSON（含原始分析师报告） |
| `--brief` | 精简版（仅结论和关键数据） |
| `--no-report` | 仅返回决策摘要（最快模式） |

## 脚本参考

| 脚本 | 用途 |
|------|------|
| `scripts/ta_analyze.py` | 主入口：协调 3 阶段管道 |
| `scripts/setup.sh` | 安装脚本：拉 TA 依赖、配置 .env |

## 模板参考

| 模板 | 用途 |
|------|------|
| `templates/ta_entry_monitor.py` | 入场条件 cron 监控模板（no_agent模式） |
| `templates/2560_main.tni` | 2560战法通达信主图指标（导入后输入2560调出，含买卖信号图标） |
| `templates/2560_buy.tn6` | 2560战法条件选股-买入（回踩MA20+缩量+J值超卖） |
| `templates/2560_sell.tn6` | 2560战法条件选股-卖出（放量破MA20/5日死叉/天量收阴，死叉均线可选手动切换10/15日） |
| `templates/2560_formula_guide.txt` | 2560战法完整公式包说明（含主图/选股/预警三套代码，通达信导入用法） |

## 关联技能详解

### AI-Platform 端（数据层 + 执行层）

| 技能 | 在本 skill 中的角色 |
|------|-------------------|
| `a-share-data` | Phase 1 数据获取 + 所有数据降级保障 |
| `a-share-paper-trading` | Phase 3 模拟盘执行 |
| `trading-combo` | Phase 1 量化评分 + Phase 2 交叉验证 |
| `macd-trend-resonance-stock-picker` | Phase 1 MACD 技术评分 |
| `a-share-strategy-mainboard-multi-swing-defensive` | Phase 1 趋势回踩预筛 |
| `a-share-investment-expert` | Phase 2 四维评分补充 |
| `user-feedback-verification` | Phase 2 用户断言验证 |

### TradingAgents 端（多Agent管道）

| 模块 | 在本 skill 中的角色 |
|------|-------------------|
| `tradingagents/agents/analysts/*.py` | 7 个 Analyst prompt 定义 |
| `tradingagents/agents/quality_gate.py` | 报告质量门控 |
| `tradingagents/agents/researchers/` | Bull vs Bear 辩论 |
| `tradingagents/agents/managers/` | Research Manager + Portfolio Manager |
| `tradingagents/agents/trader/trader.py` | A 股约束交易方案 |
| `tradingagents/agents/risk_mgmt/` | 三方风险辩论 |
| `tradingagents/graph/` | LangGraph 图编排 |
| `tradingagents/dataflows/a_stock.py` | A 股数据 vendor（可选替换） |

## Integration Points（AI-Platform 注入点）

以下是将 AI-Platform 数据层注入 TradingAgents-astock 的关键代码钩子：

### 数据降级（替换 a_stock.py 部分函数）

```python
# ta_analyze.py 中数据获取的降级路由
_DATA_STRATEGIES = {
    "OHLCV": [
        ("proxy-patch东财",  lambda c,s,e: _AI-Platform_fetch_history(c, s, e)),
        ("新浪/腾讯脚本",     lambda c,s,e: _AI-Platform_fallback_history(c, s, e)),
        ("腾讯qt.gtimg.cn",  lambda c,s,e: _tencent_direct_kline(c, s, e)),
    ],
    "实时行情": [
        ("腾讯qt.gtimg.cn", lambda c: _tencent_quote(c)),
        ("新浪脚本",        lambda c: _AI-Platform_quote(c)),
    ],
    "技术指标": [
        ("MyTT计算", lambda c: _AI-Platform_technical(c)),
    ],
    "板块排行": [
        ("东财proxy-patch", lambda: _AI-Platform_board_summary()),
        ("akshare直连",    lambda: _akshare_board()),
    ],
}
```

### 量化评分注入（TradingAgents Research Manager context）

```python
# 在调用 Research Manager 前注入评分
SCORE_CONTEXT = """
=== AI-Platform 量化评分参考 ===
总分: {total}/100 (评级: {rating})
均线: {ma}/25 | MACD: {macd}/40 | 量价: {vp}/15 | 板块: {sector}/20

=== 筹码分布 ===
获利比例: {profit_ratio} | 90集中度: {concentration}
解读: {interpretation}
"""
```

### 模拟盘对接（TradingAgents Trader → AI-Platform paper-trading）

```python
# 在 Trader 输出交易方案后，实际落地
_EXECUTE_MAP = {
    "BUY":  lambda a,c,q,p: _paper_trade("buy", a, c, q, p),
    "SELL": lambda a,c,q,p: _paper_trade("sell", a, c, q, p),
}
```

## 配置参数

可通过 `ta_analyze.py` 的环境变量或命令行参数配置：

| 参数 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `TA_PROJECT_DIR` | `TA_PROJECT_DIR` | 自动检测 | TradingAgents 项目路径 |
| `--provider` | `TA_LLM_PROVIDER` | `minimax` | LLM 供应商 |
| `--deep-model` | `TA_DEEP_MODEL` | `MiniMax-M2.7` | 深度思考模型 |
| `--quick-model` | `TA_QUICK_MODEL` | `MiniMax-M2.7-highspeed` | 快速模型 |
| `--paper-base-url` | `TA_PAPER_BASE_URL` | `http://127.0.0.1:18765` | 模拟盘服务地址 |
| `--paper-account` | `TA_PAPER_ACCOUNT` | `alpha` | 模拟盘账户 |

## 已知问题与踩坑

1. **LLM API Key 缺失** — ta_analyze.py 需要 `.env` 文件在 TA 项目根目录。首次运行检查：`test -f $TA_PROJECT_DIR/.env && echo OK`
2. **TradingAgents 模块不全（常见陷阱 ⚠️）** — 项目根目录 `tradingagents/` 可能只有 `dataflows/` 子模块，缺少 `agents/graph/llm_clients`。**必须从 `_original_src/` 安装**：`cd .../_original_src && pip install -e .`。ta_analyze.py 的 `phase2_multiagent_analysis()` 已内置缺失模块检测。
3. **`DEFAULT_CONFIG` 缺失字段（子进程 KeyError）** — `phase2_multiagent_analysis()` 的 config dict 必须 merge `DEFAULT_CONFIG`，否则 `TradingAgentsGraph.__init__` 报 `KeyError: 'data_cache_dir'`。已修复：`config = dict(DEFAULT_CONFIG); config.update({...})`。如果新增类似子进程代码，一定要先加载 DEFAULT_CONFIG 再覆盖。
4. **`.env` 路径在 `_original_src` 下不存在** — 当 TA_DIR 指向 `_original_src` 时，`.env` 在父目录 (`TradingAgents/.env`)。子进程代码已添加 fallback：`Path(TA_DIR) / '.env'` -> `Path(TA_DIR).parent / '.env'`。
5. **`langgraph.graph` 首次导入极慢（~12s）** — 这是 `langgraph` 包的正常冷启动行为，非卡死。ta_analyze.py 的子进程 timeout=300s 足够覆盖。如需在交互式终端中测试，用 `timeout 60` 而非 `timeout 30`。
6. **A 股数据 vendor 不匹配** — `_original_src/tradingagents/dataflows/` 不含 `a_stock.py`（该文件仅在 GitHub fork 中存在）。本地改用 `akshare/` 子模块。运行时需要在 config 中指定 data_vendors。
7. **setup.sh 语法陷阱** — bash 脚本顶部不能有 Python 的 `"""..."""` 文档字符串，否则 bash 会报错。必须用 `#` 注释替代。
8. **模拟盘服务 Python 版本** — 不支持 Python 3.9（pandas 导入 `TypeAlias` 失败）。必须用 Python >= 3.10 的 venv 启动：`$VENV_PY paper_trading_service.py --port 18765`
9. **符号链接缺失导致监控静默回退** — `a-share-dashboard` 的 cron 脚本部署到 `~/.AI-Platform/scripts/` 后 `SKILL_DIR` 解析错误，需创建：`ln -sf .../a-share-dashboard/data ~/.AI-Platform/scripts/data`
10. **TradingAgents LLM 调用成本** — 一次完整分析 30-50 次 LLM 调用（20-50 万 token）。首次用 `--phase 2 --brief` 测试。
11. **数据源冲突** — TA 自带 `a_stock.py` 和 AI-Platform `a-share-data` 可能同时请求同一标的。ta_analyze.py 默认优先使用 AI-Platform 数据层。
12. **Phase 1 腾讯直连降级** — 当 `fetch_technical.py` 超时（WSL 下常见），自动退回到腾讯实时行情的简化评分，标注 `note="腾讯直连模式"`。
13. **CSV schema 自动迁移** — `pool_manager.py` 每次运行自动检测并补全 CSV 缺失字段，旧文件无需手动修改。

## 常见场景速查

| 场景 | 命令 |
|------|------|
| 给个股做深度研报 | `ta_analyze.py 600760 --date 2026-07-09 --json` |
| 决策+自动入自选股池 | `ta_analyze.py 600760`（默认开启 `--sync-pool`） |
| 决策+模拟盘下单 | `ta_analyze.py 002230 --date 2026-07-09 --paper-trade` |
| 决策+部署监控 | `ta_analyze.py 600519 --date 2026-07-09 --deploy-monitor` |
| 批量扫描候选 | `ta_analyze.py --batch cands.txt --date 2026-07-09 --phase 2 --brief` |
| 仅用量化评分 | `ta_analyze.py 600498 --phase 1 --pre-score` |
| 用 DeepSeek 跑 | `ta_analyze.py 600760 --provider deepseek --deep-model deepseek-chat --quick-model deepseek-chat` |
| 输出 JSON 用于程序处理 | `ta_analyze.py 688017 --date 2026-07-09 --json --no-report` |
| 已有决策，仅执行+监控 | `ta_analyze.py 600760 --phase 3 --decision '{"action":"BUY","price":72.50,"shares":200,"stop_loss":69.00}'` |
| 关闭股池同步 | `ta_analyze.py 600519 --no-sync-pool` |

## 调度器

`ta_orchestrator.py` 提供事件驱动调度能力（P4 优化）：

```bash
# 每日收盘后批量分析自选股池
python3 ta_orchestrator.py --mode daily-batch --pool selected

# 单只重新分析（关注股升级时触发）
python3 ta_orchestrator.py --mode reanalyze --ticker 600760

# 检查股池状态
python3 ta_orchestrator.py --mode check-pool

# 部署到 cron（每个交易日16点）
AI-Platform cron create --name "TA每日收盘分析" \
  --script /path/to/ta_orchestrator.py \
  --schedule "0 16 * * 1-5" --deliver all
```

## Verify Checklist

- [ ] `ta_analyze.py --help` 显示完整参数（含 `--sync-pool` / `--no-sync-pool`）
- [ ] `ta_analyze.py 600519 --phase 1 --pre-score --no-sync-pool` 能输出量化评分
- [ ] `ta_analyze.py 600519 --phase 2 --brief` 能跑通多Agent管道
- [ ] TradingAgents `_original_src/` 目录存在完整 `agents/graph/llm_clients` 模块
- [ ] TradingAgents `.env` 文件存在且配置正确
- [ ] `~/.AI-Platform/scripts/data` 符号链接指向 `a-share-dashboard/data`（`ls -la` 验证）
- [ ] a-share-paper-trading 服务在端口 18765 监听（用 `curl :18765/health` 验证）
- [ ] `--paper-trade` 能成功下单到模拟盘
- [ ] `--deploy-monitor` 能创建 cron 监控任务
- [ ] `ta_orchestrator.py --mode check-pool` 能扫描股池状态
- [ ] 批量模式 `--batch` 能正确处理多只标的
- [ ] 每日 cron 已部署：`cronjob list | grep TA每日收盘`
