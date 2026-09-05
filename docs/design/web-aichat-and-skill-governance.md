# 独立 Web AIChatUI 与 Skill 治理系统 —— 架构设计与实施路线图

- **文档版本**：v1.0
- **创建日期**：2026-09-05
- **当前状态**：技术方案锁定 / 实施蓝图就绪
- **适用场景**：脱离第三方 AI 终端宿主（Antigravity / Hermes / Codex 等），自建独立 Web 版本 A股量化投研交互系统

---

## 0. 架构设计目的与核心诉求

### 0.1 现状与背景
在当前架构中，A-Stock Agents 作为一个高内聚的 **Skill 集合与量化引擎底座**，主要依赖外部第三方宿主工具（如 Google Antigravity、Hermes Agent、OpenAI Codex 等）提供 LLM 对话上下文、ReAct 思考循环以及终端展示交互，项目自身主要提供“执行双手（CLI Tools & SDK）”。

### 0.2 核心目标
下一阶段的目标是**脱离第三方终端工具**，为项目构建完全自闭环、开箱即用的**独立 Web AIChatUI 界面系统**，实现：
1. **自带智能体大脑 (Native Agent Runtime)**：内置轻量 Agent 编排引擎与统一多模型网关，无需第三方工具即可进行多轮量化投研对话；
2. **Skill 治理体系 (Skill Governance)**：对 17 大量化技能提供运行时元数据管理、动态启停、输入输出 Schema 校验、调用审计度量与分级权限风控；
3. **沉浸式交互与研报预览 (Interactive Visualization)**：支持打字机流式输出（SSE）、Tool 调用折叠卡片、交互式 K 线图表渲染（Lightweight-Charts / ECharts）与买卖反应动作单直观呈现。

---

## 1. 总体架构全景 (System Architecture)

系统采用前后端解耦的现代反应式架构，分为**前端展现层**、**服务网关与 Agent 运行时**、**Skill 治理层**与**量化投研内核基座**四层：

```mermaid
flowchart TB
    subgraph Client["Web 前端系统 (AIChatUI - 现代响应式应用)"]
        UI_Chat["AIChat 交互对话台\n(SSE 打字机 / Tool 调用进度折叠卡片 / 多轮会话)"]
        UI_Gov["Skill 治理控制台\n(17项技能看板 / 动态启停开关 / 契约参数调试 / 审计监控)"]
        UI_Report["交互式研报预览中心\n(K线缩放联动 / 5A雷达图 / 实时筹码 / 保本操作单)"]
        UI_Pool["股票池与交易看板\n(自选·关注·持仓拖拽管理 / 模拟盘委托)"]
    end

    subgraph ServerGateway["服务网关与运行时 (FastAPI Backend)"]
        API["FastAPI 统一网关\n(RESTful APIs + SSE / WebSocket 流式推送)"]
        SessionMgr["会话与上下文管理器\n(SQLite / DuckDB 存储多轮对话历史)"]
        Orchestrator["本地轻量 Agent 运行时\n(意图识别 / ReAct 循环 / 动态工具挂载)"]
        LLM_GW["统一多模型接入网关\n(DeepSeek / Gemini / OpenAI / 本地 Ollama)"]
        TaskWorker["长耗时异步任务队列\n(asyncio / Redis Queue: 选股、回测、辩论调度)"]
    end

    subgraph GovernanceLayer["Skill 治理控制子系统 (Skill Governance)"]
        SkillRegistry["SkillRegistry 运行时中心\n(Manifest 解析 / Pydantic Schema 契约)"]
        Gatekeeper["分级风控门禁\n(只读研判放行 / 模拟下单 Human-in-the-loop 确认)"]
        Auditor["调用审计与度量器\n(调用次数 / 延迟分布 / 错误率 / Token 消耗)"]
    end

    subgraph CoreEngine["底层量化与模型内核 (完全复用已有资产)"]
        Core_Data["core/data (4级降级数据源与K线)"]
        Core_Models["core/models (5A旋转 / AlgoRegistry 2.0)"]
        Core_Strategy["core/strategy (保本进位 / 三级止损 / 动作单)"]
        Core_Trade["core/paper_trading (模拟撮合与回测)"]
        Core_Debate["core/commands/model_cmds.py (7角色多空辩论)"]
    end

    Client <-->|HTTP / SSE / WebSocket| API
    API --> SessionMgr
    API --> Orchestrator
    Orchestrator --> LLM_GW
    Orchestrator --> GovernanceLayer
    API --> TaskWorker
    GovernanceLayer --> CoreEngine
    TaskWorker --> CoreEngine
```

---

## 2. 服务与网关层设计 (Server & API Gateway)

### 2.1 技术选型
* **API 框架**：FastAPI（高性能异步异步框架，原生支持 OpenAPI 规范与 Pydantic 契约）。
* **流式通信**：Server-Sent Events (SSE)，用于大模型打字机流式吐字及 Tool Call 进度事件推送。
* **任务调度**：轻量模式采用 Python 原生 `asyncio.create_task` + 内存状态机；生产可无缝切换至 Celery / Redis。
* **会话持久化**：SQLite（WAL 模式）存储 `sessions` 与 `messages`，数据统一落盘在 `output/cache/chats.db`，确保用户数据隔离原则。

### 2.2 核心通信协议契约 (SSE Event Stream)
在 AIChat 对话过程中，网关向前端推送结构化事件流：
```
event: conversation_start
data: {"session_id": "sess_20260905_001", "model": "deepseek-v3"}

event: thought
data: {"content": "正在理解用户意图：查询贵州茅台的行情与技术形态..."}

event: tool_call_start
data: {"skill_id": "astock-data-feed", "action": "quote", "args": {"code": "600519"}}

event: tool_call_complete
data: {"skill_id": "astock-data-feed", "status": "success", "summary": "现价 1330.00 (+2.40%)"}

event: content_delta
data: {"text": "【贵州茅台 (600519) 诊断】当前现价为 1330.00 元..."}

event: risk_card
data: {"breakeven_price": 1331.36, "stop_t0": 1290.1, "stop_t1": 1263.5, "stop_t2": 1223.6}

event: done
data: {"total_tokens": 1280, "elapsed_ms": 1420}
```

---

## 3. 本地轻量 Agent 运行时与 LLM 适配

脱离第三方工具后，项目需要自主持有智能体调度循环：

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户 (Web UI)
    participant GW as FastAPI 网关
    participant Orch as Agent 调度引擎
    participant Gov as Skill 治理层
    participant Engine as 量化内核 (core/)
    participant LLM as 上游大模型

    User->>GW: 发送投研诉求 ("帮我评估茅台并出动作单")
    GW->>Orch: 组装 Session 历史与 System Prompt
    Orch->>LLM: 首轮请求 (携带已启用的 Skill Tool Schemas)
    LLM-->>Orch: 返回 Tool Call ("astock-action-execution", {"code":"600519"})
    Orch->>GW: 推送 SSE 状态 (正在调用动作单引擎...)
    GW-->>User: 前端高亮展示 Tool 运行卡片
    Orch->>Gov: 权限校验与参数 Schema 审计
    Gov->>Engine: 就地执行量化与保本价进位算法
    Engine-->>Gov: 返回结构化量化结果 (保本价1331.36等)
    Gov->>Gov: 记录审计指标 (调用耗时、成功状态)
    Gov-->>Orch: 返回执行输出
    Orch->>LLM: 注入 Observation 观察数据，生成终审建议
    LLM-->>Orch: 流式生成深度投研决议
    Orch->>GW: 转发 SSE 打字机流
    GW-->>User: 渲染最终回复与风控动作面板
```

---

## 4. Skill 治理系统详细设计 (Skill Governance Subsystem)

### 4.1 核心数据结构 (`SkillDefinition`)
每个技能不仅是一个目录，而且在治理层拥有显式的 Python 契约定义：

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

class SkillRiskLevel(str, Enum):
    READONLY = "readonly"       # 只读研判 (行情/选股/评分)
    SIMULATION = "simulation"   # 模拟交易 (模拟盘下单/调仓)
    DESTRUCTIVE = "destructive" # 高危变更 (清空数据/策略参数重置)

class SkillMeta(BaseModel):
    id: str = Field(..., description="技能唯一标识")
    name: str
    title: str
    category: str
    description: str
    risk_level: SkillRiskLevel = SkillRiskLevel.READONLY
    enabled: bool = True
    triggers: List[str] = []
    parameters_schema: Dict[str, Any] = {}
    timeout_seconds: int = 30
    require_confirmation: bool = False  # 是否需要用户在UI点击二次确认
```

### 4.2 治理四大核心能力
1. **动态热插拔与开关控制**：
   - 允许用户在 Web 页面上一键关闭某些技能（例如临时禁用长耗时辩论或模拟下单），动态调整注入给当前会话的 Tool 列表。
2. **运行时调用审计与指标监控**：
   - 自动统计并展示：各 Skill 调用总频次、今日调用量、P95 延迟、失败异常率及 Token 消耗曲线。
3. **分级安全门禁 (Human-in-the-Loop)**：
   - 当大模型尝试调用 `risk_level == "simulation"` 或需要二次确认的技能时，网关暂停流式推理，在 Web UI 弹出确认对话框（如“确认以 1330.00 元模拟买入 100 股茅台？”），用户点击允许后继续。
4. **参数 Schema 强校验**：
   - 杜绝因大模型幻觉传入非法股票代码或畸形参数，进入内核前先通过 Pydantic 自动拦截。

---

## 5. 交互式研报预览与可视化设计

### 5.1 数据呈现双轨制
* **在线交互模式**：
  - 后端直接提供 `/api/reports/{id}/data` 吐出结构化 JSON；
  - 前端使用 **TradingView Lightweight Charts** 渲染交互式 K 线（支持分时、日K、周K缩放滑动）；
  - 使用 **ECharts** 渲染 5A 多维共振雷达图、换手率筹码分布直方图与大盘模式水球图。
* **离线归档模式**：
  - 保留单文件自包含 HTML 导出能力，支持一键下载或在本地浏览器独立查看。

---

## 6. 实施路线图与阶段里程碑 (Roadmap)

本项目采用循序渐进的交付策略，分为三个明确阶段：

### 📌 第一阶段：服务底座与 Agent 编排核心 (Backend & Runtime Foundation)
- [ ] 在项目根目录下建立 `server/` 独立工程模块；
- [ ] 集成 FastAPI 基础服务架构，提供健康检查与配置读取；
- [ ] 实现轻量级 LLM Provider 统一适配层（支持 OpenAI 规范接口、DeepSeek、Gemini、Claude、本地 Ollama）；
- [ ] 实现支持 SSE 流式打字机与 Tool Calling 调度的 Agent ReAct 运行时；
- [ ] 实现基于 SQLite 的本地会话历史与多轮对话状态存储。

### 📌 第二阶段：Skill 治理控制子系统 (Skill Governance Implementation)
- [ ] 基于 `config/skills_manifest.json` 建立 `core/governance/skill_registry.py`；
- [ ] 将 17 项技能抽象为统一注册实例，生成标准的 JSON Schema / Function Calling 规范；
- [ ] 实现 REST API：技能列表检索、启用/停用切换、参数测试与调用审计日志；
- [ ] 集成安全门禁：实现长耗时任务异步 Worker（选股与回测队列）与超时熔断控制。

### 📌 第三阶段：现代 Web 前端 AIChatUI 构建 (Frontend UI & Visualization)
- [ ] 初始化现代 Web 前端（推荐 Vite + React + TailwindCSS + Lucide Icons + ECharts / Lightweight-Charts）；
- [ ] 构建 **AIChat 投研对话台**：支持流式打字机、Thought 思考气泡折叠、Tool Call 进度卡片、快捷意图气泡；
- [ ] 构建 **Skill 治理仪表盘**：17 项技能可视化卡片、开关状态切换、调用监控与参数调试器；
- [ ] 构建 **交互式研报与股票池看板**：自选/关注/持仓池拖拽管理与多周期 K 线图表交互。

---

## 7. 附录：核心 REST API 契约草案

| 模块 | 请求方法 | 路由路径 | 说明 |
| :--- | :--- | :--- | :--- |
| **会话** | `POST` | `/api/chat/sessions` | 创建新对话会话 |
| **会话** | `GET` | `/api/chat/sessions` | 获取会话历史列表 |
| **对话** | `POST` | `/api/chat/completions/stream` | 发送问题并建立 SSE 流式对话 |
| **治理** | `GET` | `/api/skills` | 获取 17 项技能清单与状态 |
| **治理** | `PATCH` | `/api/skills/{skill_id}` | 动态启用/停用技能或修改配置 |
| **治理** | `GET` | `/api/skills/audit/stats` | 获取技能调用频次、耗时与审计度量 |
| **研报** | `GET` | `/api/reports` | 获取历史已生成的研报列表 |
| **研报** | `GET` | `/api/reports/{id}/data` | 获取研报结构化图表渲染数据 |
| **研报** | `GET` | `/api/reports/{id}/html` | 导出/预览单文件自包含 HTML |
| **任务** | `GET` | `/api/tasks/{task_id}` | 查询长耗时回测/选股异步任务进度 |
