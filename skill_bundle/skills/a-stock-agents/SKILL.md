---
name: a-stock-agents
description: A股投研智能体系统总控锚点与全局路由中枢。统领「1 + 6」专业机构股票投研全流程（看盘知势、选股立池、择时定买、穿透体检、仓位风控、回测验证），内建AI多宿主安装引导卡片与实战避坑心法。
compatibility: Requires complete a_stock_agents bundle, Python 3.9+ and dependencies. Supports Windows, macOS and Linux.
metadata:
  product: a_stock_agents
  version: 3.1.0
---

# A-Stock Agents — 总控锚点与专业投研闭环中枢

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有正式调用追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`）。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

---

## 1. 机构投研全流程「1 + 6」架构全景与意图路由

A-Stock Agents 遵循专业机构买方投研实战闭环，通过 **1 个总控锚点** 统领 **6 大生产级专业投研技能**：

$$\mathbf{🧭 a-stock-agents} \left\{
\begin{aligned}
& \mathbf{① 看盘知势} \longrightarrow \texttt{astock-market-data} \quad \text{（实时行情 · K线 · 筹码 · 大盘五维健康度）} \\
& \mathbf{② 选股立池} \longrightarrow \texttt{astock-smart-screener} \quad \text{（5A共振 · ISS四阶漏斗 · 截面因子 · 财务排雷）} \\
& \mathbf{③ 择时定买} \longrightarrow \texttt{astock-tactical-signals} \quad \text{（主板波段 · 水下双金叉 · 游资龙头 · 250日胜率锚）} \\
& \mathbf{④ 穿透体检} \longrightarrow \texttt{astock-deep-diagnose} \quad \text{（100分量化 · 7角色辩论 · 解套决策树 · HTML研报）} \\
& \mathbf{⑤ 仓位风控} \longrightarrow \texttt{astock-portfolio-action} \quad \text{（ceil保本价 · 三级止损 · 五步MA审计 · 凯利仓位）} \\
& \mathbf{⑥ 回测验证} \longrightarrow \texttt{astock-paper-backtest} \quad \text{（T+1仿真撮合 · 多股轮动回测 · 滚动OOS防过拟合）}
\end{aligned}
\right.$$

### 1.1 用户意图路由与统一 CLI 映射表

当用户提出投资投研诉求时，智能体根据下表精准路由至对应专业技能：

| 机构投研环节 | 用户意图与核心关键词 | 路由技能 ID (`skills/`) | 统一 CLI 调用入口 |
| :--- | :--- | :--- | :--- |
| **① 看盘知势** | 行情、现价、K线、筹码分布、技术指标、大盘健康度、情绪灯号 | `astock-market-data` | `astock data quote <代码> --json`<br>`astock market [代码] --json` |
| **② 选股立池** | 选股、5A选股、主线轮动、多因子挖掘、ISS条件树漏斗、Alpha计算 | `astock-smart-screener` | `astock screen --mode 5a --json`<br>`astock funnel run --assemble --json` |
| **③ 择时定买** | 战法、买点信号、MACD水下双金叉、主板波段、陈小群龙头、退哥短线接力 | `astock-tactical-signals` | `astock signal <代码> --json`<br>`astock pattern chenxiaoqun <代码> --json` |
| **④ 穿透体检** | 股票诊断、100分制打分、多空辩论、财务排雷、解套决策树、HTML研报 | `astock-deep-diagnose` | `astock diagnose <代码> --json`<br>`astock report <代码> --html --json` |
| **⑤ 仓位风控** | 保本价、止损位、开盘冲高动作单、三级股票池、股池审计、仓位测算 | `astock-portfolio-action` | `astock action --code <代码> --cost <成本> --shares <股数> --json`<br>`astock pool audit --json` |
| **⑥ 回测验证** | 模拟盘、模拟买卖、账户资产、策略回测、滚动样本外检验、防过拟合审查 | `astock-paper-backtest` | `astock trade balance --json`<br>`astock backtest <代码/组合> --oos --json` |

### 1.2 宿主内能力路由与执行规范（吸收 `astock-meta-routing`）
1. **纯分析 vs 代码执行**：
   - 严禁大模型手算指标或口算税费，所有计算必须通过调用统一 CLI 命令执行；
   - 模型聚焦于意图理解、参数提取与金字塔结构化综合解读。
2. **分级任务编排规范（四级任务模型）**：
   - **L0 根意图**：用户原始目标（如：“全维体检 600519 并分析大盘走势”）；
   - **L1 批量父任务**：并发或连续 $\ge 2$ 次同类调用时，必须建立父容器：`能力调用 <skill_id> 任务（批量 <N> 次调用）`；
   - **L2 挂接原子子任务**：每个原子调用缩进展示：`• 子任务 1: <能力> · <摘要>`；
   - **L3 抽屉明细**：父任务底部的折叠数据抽屉中聚合返回。

---

## 2. A股交易日全流程实战心法与避坑铁律（吸收 `astock-knowledge-tips`）

### 2.1 核心实战避坑铁律
1. **券商 FIFO (先进先出) 成本重算陷阱**：
   - 用户减仓后提供“最新持仓成本”时，券商往往按先进先出法将剩余底仓成本重置为历史极高成本；
   - 必须基于实际总本金、当前市值与已实现损益重新核算真实加权保本价，杜绝依据失真成本发出错误止损指令。
2. **防过拟合三重警报标准**：
   - `Sharpe > 3.5`：极度可疑，极大概率存在未来函数或收盘价偷价；
   - `WinRate > 75%`：疑似过度拟合，违背 A 股单向做多波动规律；
   - `IS-OOS 衰减 > 50%`：样本外严重失真，实盘坚决不可用。
3. **数据源 4 级容灾降级架构**：
   - `L1 腾讯实时快照` $\to$ `L2 东方财富` $\to$ `L3 新浪财经` $\to$ `L4 本地离线水位快照`。

### 2.2 交易日标准化时间序列 SOP
- `09:15 ~ 09:25` 【集合竞价】：监控异动高开/低开，确定今日市场主线与恐慌度；
- `09:30 ~ 10:00` 【开盘冲高】：择机兑现隔夜浮盈，严禁情绪化追高追涨；
- `10:00 ~ 11:30` 【盘中分化】：震荡期按兵不动，观察板块承接力与大盘健康度；
- `14:30 ~ 15:00` 【尾盘博弈】：确认全天量能与均线得失，执行尾盘买入或破位止损；
- `15:00 ~ 17:00` 【盘后复盘】：更新三级股票池，运行 `astock pool audit` 重算均线。

---

## 3. 模态一：AI 安装引导与 5 类信息卡片渲染契约 (Interactive Cards SOP)

当用户请求安装、配置、初始化 A-Stock Agents 时，AI 智能体**严禁自行编写临时脚本或执行全局 pip install**，必须严格按照以下 5 阶段状态机与结构化卡片呈现交互：

### 1. 状态机流水线 (5-Stage State Machine)
- **阶段 1 [探测环境]**：调用底层安装引导器 `install.ps1 -Inspect -Json`（Windows）或 `install.sh -Inspect -Json`（POSIX）；
- **阶段 2 [配置交互]**：输出【信息卡片 1：宿主选择】与【信息卡片 2：量化数据与私有配置】，等待用户确认；
- **阶段 3 [安全确认]**：输出【信息卡片 3：安装前摘要与安全审计】，明确展示 7 个入口（1 锚点 + 6 专业）与权限隔离；
- **阶段 4 [分级执行]**：执行 `install.ps1 -Agent <宿主> -Method link -Yes -Json` 并输出【信息卡片 4：执行流水线】；
- **阶段 5 [冒烟交付]**：调用 `doctor.py --json` 验证全部 7 个入口可用性，输出【信息卡片 5：交付与即时实战测试】。

### 2. 5 类信息卡片渲染规范

#### 【信息卡片 1：环境探测与目标宿主勾选卡片】
```markdown
┌──────────────────────────────────────────────────────────────┐
│ 🧩 A-Stock Agents 技能安装引导 · 第一步：选择目标宿主          │
├──────────────────────────────────────────────────────────────┤
│ 自动探测到以下 AI 工具环境，请确认需要注册的宿主：             │
│                                                              │
│ [x] 🌐 Universal 通用目录 (~/.agents/skills)                 │
│     已支持: Codex, Cursor, Cline, Kimi CLI, OpenCode 等      │
│                                                              │
│ [x] 🦊 Hermes Desktop (~/.hermes/skills)                     │
│     状态: 已检测到客户端配置 · 采用 external_dirs / 平级挂载   │
│                                                              │
│ [x] 💼 WorkBuddy (~/.workbuddy/skills)                       │
│     状态: 已检测到目录 · 采用逐技能 Junction/Symlink 注册     │
│                                                              │
│ 安装方式：(●) 符号链接/Junction (推荐，便于升级)   ( ) 物理复制 │
└──────────────────────────────────────────────────────────────┘
```

#### 【信息卡片 2：量化数据源与私有配置卡片】
```markdown
┌──────────────────────────────────────────────────────────────┐
│ ⚙️ A-Stock Agents 技能安装引导 · 第二步：量化数据与私有配置   │
├──────────────────────────────────────────────────────────────┤
│ 基础行情源（默认开箱即用，无需配置）：                       │
│  • 腾讯/新浪 L1 实时行情快照与日K线（内置 4 级自动降级）      │
│                                                              │
│ 可选进阶数据扩展（勾选后将自动写入 local/settings/.env）：   │
│  [x] AkShare / MyTT 完整开源量化扩展包 (推荐，自动安装)       │
│  [ ] 登记 Tushare Pro Token (用于高频财报/大单深度回测)       │
│  [ ] 登记 问财 / 同花顺 Cookie (用于特定题材轮动)             │
│                                                              │
│ 🛡️ 隐私承诺：所有私有凭据严格落盘于 local/settings/.env，     │
│             严禁纳入版本控制与日志外泄。                     │
└──────────────────────────────────────────────────────────────┘
```

#### 【信息卡片 3：安装前摘要与安全审计卡片】
```markdown
┌──────────────────────────────────────────────────────────────┐
│ 📋 A-Stock Agents 技能安装引导 · 第三步：安全评估与安装确认   │
├──────────────────────────────────────────────────────────────┤
│ 安装明细：                                                   │
│  • 技能数量: 1 个总控锚点 + 6 项生产级专业股票投研技能       │
│  • 代码安装根: %LOCALAPPDATA%\a_stock_agents\releases\<ver>  │
│  • 数据隔离根: %LOCALAPPDATA%\a_stock_agents (升级自动保留)  │
│  • 冲突检测: 无同名物理冲突 (Overwrites: 0)                   │
│                                                              │
│ 🛡️ 安全合规检测 (Security Clearance)：                       │
│  • 权限隔离: 独立 Python .venv，不污染系统全局 Python         │
│  • 代码安全: 本地纯静态执行，无远程代码执行 (RCE) 风险        │
│  • 依赖审计: 仅拉取 PyPI 官方认证数据计算库                  │
│                                                              │
│ 是否确认开始自动部署？                                       │
│ [ 🚀 立即安装 ]          [ ❌ 取消 ]                         │
└──────────────────────────────────────────────────────────────┘
```

#### 【信息卡片 4：执行流水线进度卡片】
```markdown
⏳ 能力调用 a_stock_installer 任务（批量 5 步流水线）
  ├─ • 子任务 1: 下载并解压 Release 归档 · 校验 SHA256 [完成]
  ├─ • 子任务 2: 宿主技能入口挂载 (Codex / Hermes / WorkBuddy) [完成]
  ├─ • 子任务 3: 初始化隔离 Python 虚拟环境 (.venv) [完成]
  ├─ • 子任务 4: 安装量化引擎依赖 (requirements.txt) [完成]
  └─ • 子任务 5: 运行 doctor 7 项技能契约冒烟自检 [完成]
```

#### 【信息卡片 5：交付与即时实战测试卡片】
```markdown
┌──────────────────────────────────────────────────────────────┐
│ 🎉 A-Stock Agents 技能安装完成！7 个标准入口已全部就绪        │
├──────────────────────────────────────────────────────────────┤
│ 💡 宿主调用方式提示：                                        │
│  • 在 Codex 中输入:     $a-stock-agents                      │
│  • 在 Hermes 中输入:    /a-stock-agents                      │
│  • 在 WorkBuddy 中输入: @a-stock-agents 或在技能面板中激活   │
│                                                              │
│ 🚀 您可以立即在下方回复体验实战量化能力：                     │
│  1. 📊「查询今日大盘健康度与资金主线」                       │
│  2. 🔍「对贵州茅台 600519 进行 100 分制体检诊断」             │
│  3. 🎯「运行 5A 量价多因子选股模型」                         │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 模态二：实战交易三原则与空池 Fail-Closed 铁律输出

在与用户对话交互中，智能体必须无条件遵守以下两大工作区铁律：

### 4.1 输出强制包含实战三原则
输出任何个股分析结论与实战建议时，必须包含：
1. **精确最低保本卖出价**：计入印花税 0.05%、佣金万 2.5 且最低 5 元、过户费，并强制向上进位至分位（`math.ceil`）；
2. **三级风控止损阶梯**：T0 警戒线（$-3\%$）、T1 减仓线（$-5\%$）、T2 绝杀线（$-8\%$）；
3. **三场景即时动作单**：开盘冲高择机兑现、盘中窄幅震荡观望、盘中跳水急跌防御。

### 4.2 空股池即刻终止分析 (Fail-Closed)
调用股池或持仓分析时：
1. 真实读取股池数据；
2. 若股池数据为空，**坚决终止分析，严禁臆测、虚构股票或擅自推荐替代股票**；
3. 直接提示用户登记格式：
   - 持仓股登记：`股票代码:股数@成本价`（例如：`000001:1000@12.50`）；
   - 关注/自选股登记：直接输入代码或名称（例如：`000001`、`600519`）。
