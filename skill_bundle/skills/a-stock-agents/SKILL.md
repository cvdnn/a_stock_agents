---
name: a-stock-agents
description: A股技能总入口。用于行情、选股、持仓风控、模拟盘、报告及多空辩论；按需求路由到同集合的19项专业技能，以确定性程序计算。
compatibility: Requires complete a_stock_agents bundle, Python 3.9+ and dependencies.
  Supports Windows, macOS and Linux.
metadata:
  product: a_stock_agents
  version: 3.0.0
---

# A-Stock Agents 总入口

本技能只负责导航与自身编排，不保存公共引擎。读取集合的 [references/execution-contract.md](../../references/execution-contract.md) 和 assets/config/skills_manifest.json，按需读取 skills/<id>/SKILL.md。

从本文件真实路径定位带 bundle.json 的集合根。程序经 runtime/bootstrap.py 与 core.workspace 定位，Windows调用 runtime/astock.ps1，macOS/Linux调用 runtime/astock；所有正式调用追加 --json。

空股池停止分析并提示登记；数据不足或能力未实现必须如实返回原因。持仓建议包含精确保本价、三级风控及三场景动作。单项技能不能脱离完整集合独立安装；宿主安装使用完整Release；开发仓库不作为项目发现模式。

---

## 模态一：AI 安装引导与 5 类信息卡片渲染契约 (Interactive Cards SOP)

当用户请求安装、配置、初始化 A-Stock Agents，或输入「标准 AI 安装指令模板（AI Copilot Bootstrap Prompt）」时，AI 智能体**严禁自行编写临时脚本或执行盲目全局 pip install**，必须严格按照以下 5 阶段状态机与结构化信息卡片呈现交互：

### 1. 状态机流水线 (5-Stage State Machine)

- **阶段 1 [探测环境]**：调用底层安装引导器 `install.ps1 -Inspect -Json`（Windows）或 `install.sh -Inspect -Json`（POSIX），探测系统中已安装的 AI 工具环境（Universal 目录、Hermes Desktop、WorkBuddy 等）。
- **阶段 2 [配置交互]**：暂停自动化执行，在对话中输出【信息卡片 1：宿主选择】与【信息卡片 2：量化数据与私有配置】，等待用户做出勾选与偏好确认。
- **阶段 3 [安全确认]**：根据用户的选择，生成【信息卡片 3：安装前摘要与安全审计】，明确展示目标代码安装根、隔离数据根、Overwrites 冲突检测与权限隔离声明，等待用户确认授权。
- **阶段 4 [分级执行]**：用户确认后，组装参数执行 `install.ps1 -Agent <选定宿主> -Method link -Yes -Json`，并按工作区任务规范输出【信息卡片 4：执行流水线】展示批量任务进度。
- **阶段 5 [冒烟交付]**：调用 `doctor.py --json` 验证全部 20 个入口可用性，输出【信息卡片 5：交付与即时实战测试】。

---

### 2. 5 类信息卡片标准化渲染规范

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
│  • 技能数量: 1 个总入口 (锚点) + 19 项专业量化技能           │
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
  └─ • 子任务 5: 运行 doctor 20 项技能契约冒烟自检 [完成]
```

#### 【信息卡片 5：交付与即时实战测试卡片】
```markdown
┌──────────────────────────────────────────────────────────────┐
│ 🎉 A-Stock Agents 技能安装完成！20 个入口已全部就绪           │
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

