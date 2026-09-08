# 独立 Web AIChatUI 与 Skill 治理系统架构设计 (Web AIChat & Skill Governance Architecture)

> **文档类别**：系统架构 (Architecture)  
> **适用范围**：脱离第三方 AI 终端宿主（Antigravity / Hermes / Codex 等），自建独立 Web 界面系统并原生兼容本地客户端（Desktop / TUI）的 A股全流程量化投研交互中枢  
> **实施进度看板**：[`docs/specs/architecture/arch-web-aichat-and-skill-governance.md`](../specs/architecture/arch-web-aichat-and-skill-governance.md) (`SPEC-ARCH-001`)

---

## 一、 架构设计目的与核心诉求

### 1. 现状与背景
早期架构中，A-Stock Agents 作为一个高内聚的 **Skill 集合与量化引擎底座**，主要依赖外部第三方宿主工具（如 Google Antigravity、Hermes Agent、OpenAI Codex 等）提供 LLM 对话上下文、ReAct 思考循环以及终端展示交互，项目自身主要提供“执行双手（CLI Tools & SDK）”。

### 2. 核心目标
本架构旨在**脱离第三方终端工具**，为项目构建完全自闭环、开箱即用的**独立 Web AIChatUI 界面系统**，实现：
1. **自带智能体大脑 (Native Agent Runtime)**：内置轻量 Agent 编排引擎与统一多模型网关，无需第三方工具即可进行多轮量化投研对话；
2. **Skill 治理体系 (Skill Governance)**：对 17 大量化技能提供运行时元数据管理、动态启停、输入输出 Schema 校验、调用审计度量与分级权限风控；
3. **沉浸式交互与研报预览 (Interactive Visualization)**：支持打字机流式输出（SSE）、Tool 调用折叠卡片、交互式 K 线图表渲染（Canvas / Lightweight-Charts）与买卖反应动作单直观呈现。

---

## 二、 总体架构全景 (System Architecture)

系统采用前后端解耦的现代反应式架构，划分为**前端展现层**、**服务网关与 Agent 运行时**、**Skill 治理层**与**量化投研内核基座**四层：

```mermaid
flowchart TB
    subgraph Client["Web 前端系统 (AIChatUI - 现代响应式应用)"]
        UI_Chat["AIChat 交互对话台\n(SSE 打字机 / Tool 调用进度折叠卡片 / 多轮会话)"]
        UI_Gov["Skill 独立治理中心 (顶部菜单栏常驻)\n(17项技能看板 / 动态启停开关 / Schema 参数调试终端 / 审计监控 / 热重载)"]
        UI_Report["交互式研报预览中心\n(K线缩放联动 / 5A雷达图 / 实时筹码 / 保本操作单)"]
        UI_Pool["股票池与交易看板\n(自选·关注·持仓拖拽管理 / 模拟盘委托)"]
    end

    subgraph ServerGateway["服务网关与运行时 (FastAPI Backend)"]
        API["FastAPI 统一网关\n(RESTful APIs + SSE / WebSocket 流式推送)"]
        SessionMgr["会话与上下文管理器\n(SQLite 存储多轮对话历史 chats.db)"]
        Orchestrator["本地轻量 Agent 运行时\n(意图识别 / ReAct 循环 / 动态工具挂载)"]
        LLM_GW["统一多模型接入网关\n(DeepSeek / Gemini / OpenAI / 本地 Ollama)"]
        TaskWorker["长耗时异步任务队列\n(asyncio 选股、回测、辩论调度)"]
    end

    subgraph GovernanceLayer["Skill 治理控制子系统 (Skill Governance)"]
        SkillRegistry["SkillRegistry 运行时中心\n(Manifest 解析 / Pydantic Schema 契约)"]
        Gatekeeper["分级风控门禁\n(只读研判放行 / 模拟下单 Human-in-the-loop 确认)"]
        Auditor["调用审计与度量器\n(调用次数 / 延迟分布 / 错误率 / Token 消耗)"]
    end

    subgraph CoreEngine["底层量化与模型内核 (完全复用已有资产)"]
        Core_Data["scripts/core/data (4级降级数据源与K线)"]
        Core_Models["scripts/core/models (5A旋转 / AlgoRegistry 2.0)"]
        Core_Strategy["scripts/core/strategy (保本进位 / 三级止损 / 动作单)"]
        Core_Trade["scripts/core/paper_trading (模拟撮合与回测)"]
        Core_Debate["scripts/core/multi_agent (7角色多空辩论)"]
    end

    Client <-->|HTTP / SSE| API
    API --> SessionMgr
    API --> Orchestrator
    Orchestrator --> LLM_GW
    Orchestrator --> GovernanceLayer
    API --> TaskWorker
    GovernanceLayer --> CoreEngine
    TaskWorker --> CoreEngine
```

---

## 三、 多端部署拓扑与双模兼容架构 (Dual-Mode Deployment Architecture)

系统不仅支持中心化 Web 服务部署，还原生兼容本地独立客户端（Desktop 桌面端与终端 TUI），支持以下三种部署与接入形态：

```mermaid
flowchart TB
    subgraph Core["Agent Runtime 与量化内核 (跨端共享底座)"]
        RT["AgentReActRunner (统一 ReAct 编排引擎)"]
        CoreLib["scripts/core (算法·风控·模拟盘·17项技能)"]
        RT --> CoreLib
    end

    subgraph Mode1["部署形态 A：独立 Web 服务"]
        Srv["FastAPI Backend (scripts/server/app.py)"]
        Browser["现代浏览器 (Chrome / Edge / Safari)"]
        Browser <-->|HTTP / SSE| Srv
        Srv --> RT
    end

    subgraph Mode2["部署形态 B：轻量桌面客户端"]
        Desktop["Tauri / Electron 本地宿主"]
        LocalWeb["内嵌 Webview (复用同一套 web/ 代码)"]
        Desktop --> LocalWeb
        Desktop -->|本地 IPC / Localhost| Srv
    end

    subgraph Mode3["部署形态 C：无图形终端 TUI"]
        Terminal["Rich / Textual 终端界面"]
        CLI["统一命令行门面 (astock cli)"]
        Terminal --> CLI
        CLI --> CoreLib
    end
```

---

## 四、 核心交互通信协议与治理机制

### 1. SSE 打字机流式广播规范 (`/api/chat/stream`)
通信协议采用标准 Server-Sent Events (SSE)，支持以下事件帧（Event Frame）：
- `event: thought`：传递智能体思维链片段（COT 推理步骤）；
- `event: tool_call`：传递工具调用通知（函数名、输入参数摘要）；
- `event: tool_result`：传递工具调用执行结果或错误信息；
- `event: text`：传递正式回复文本 Markdown 打字机切片；
- `event: a2ui_render`：传递 A2UI 渲染动作帧（包含组件名、目标槽位、结构化 props）；
- `event: done`：会话生成结束帧，返回耗时统计与 Token 消耗。

### 2. 17 项技能治理控制平面 (Skill Governance Plane)
- **Manifest 契约化**：集中解析 `config/skills_manifest.json` 与 `.agents/skills/*/SKILL.md`；
- **动态启停**：用户可在前端界面随时关闭某些高耗时或未授权的技能；
- **分级风控门禁 (Gatekeeper)**：
  - `Level 1（只读研报类）`：直接放行；
  - `Level 2（模拟盘写入类）`：强制经过 Human-in-the-loop 前端弹窗二次确认；
  - `Level 3（实盘交易通道）`：系统当前物理阻断，禁止任何自动委托。
