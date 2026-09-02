# Token 链路安全网关 + 本地化审计 Agent —— 架构设计文档

- 版本：v1.0
- 日期：2026-08-10
- 状态：设计评审稿
- 关联痛点：`TOKENRIVER_API_KEY` 曾被真实值送入第三方供应商上下文（已轮换）

---

## 0. 文档目的

设计一个位于 **本地 Agent（如 AI-Platform）与上游 LLM 供应商 API 之间** 的控制平面，实现四项能力：

1. **数据脱敏访问 API** —— 请求上行脱敏、响应下行过滤/还原
2. **内容审计** —— 实时捕获进出流量，形成不可篡改、只存指纹的审计日志
3. **Agent 动作风险评估** —— 对 Agent 的工具调用/命令执行做语义级风险评分与阻断
4. **系统弱耦合** —— 网关、审计 Agent、执行 Agent 三者独立部署、独立故障

设计原则：**控制平面（网关 + 审计）与执行平面（Agent）分离**。信任不放在 Agent 上，也不放在上游供应商上，而是放在本地自持的可观测、可脱敏、可阻断、可审计的中间层。

---

## 1. 总体架构

```
                    ┌──────────────────── 控制平面 ────────────────────┐
                    │                                                  │
┌──────────┐  ①   ┌─────────────┐   ②    ┌──────────────────┐          │
│ 本地Agent │────▶│ Token网关     │──────▶│ 上游LLM供应商API   │          │
│ (AI-Platform/ │      │ (反向代理)    │         │ (DeepSeek/Silicon│          │
│  Codex/  │      │  [脱敏][审计] │◀──────│   Flow/OpenCode)  │          │
│  Claude) │◀────│              │  ③    └──────────────────┘          │
└──────────┘ 响应 │              │                                     │
    │   ▲         └──────┬───────┘                                     │
    │   │                │ ④ 事件流(请求/响应元数据+指纹)               │
    │   │  ⑤   ┌─────────▼──────────┐      ┌──────────────────────┐   │
    │   └──────│  本地审计 Agent      │◀────│ 决策存储 (规则/历史)    │   │
    │          │  [风险评分][审计分析] │      └──────────────────────┘   │
    │          └─────────┬──────────┘                                  │
    │                    │ ⑥ 审计日志 (JSONL, 只存指纹)                │
    └────────────────────┴──────────────────────────────────────────────┘
```

**数据流（编号对应上图）：**

| 步骤 | 方向 | 内容 | 关键动作 |
|---|---|---|---|
| ① | Agent → 网关 | 完整 LLM 请求（含 body） | 上行脱敏、请求元数据采集 |
| ② | 网关 → 上游 | 脱敏后的请求 | 供应商调用（真实 Token 在此注入，不外泄给 Agent） |
| ③ | 上游 → 网关 | 原始响应 | 下行过滤、敏感内容剥离 |
| ④ | 网关 → 审计 Agent | 事件流（哈希/指纹/元数据，**非明文**） | 异步旁路，不阻塞主链路 |
| ⑤ | 审计 Agent → Agent | 风险评估结论（放行/阻断/需确认） | 独立控制点，Agent 无权重写 |
| ⑥ | 审计 Agent | 审计日志落盘 | 只存指纹 + 脱敏副本 |

---

## 2. 组件设计

### 2.1 Token 网关（核心控制点）

**定位**：反向代理，唯一持有真实上游 Token 的地方。Agent 侧只配网关地址，永不接触真实密钥。

**技术选型建议**：优先评估现成方案（LiteLLM Proxy / One-API / OpenRouter 自建），二次开发加脱敏与审计钩子；若需深度定制再自研（FastAPI + httpx 流式转发）。

**核心职责：**

```text
[入站]  LLM 请求
   ├─ ① Token 管理      —— 从安全存储读取上游密钥，注入 Authorization 头
   ├─ ② 上行脱敏        —— 对 request body 做 DPA（PII/密钥/域名替换）
   ├─ ③ 请求指纹        —— SHA-256(request body + 元数据)，落审计事件
   ├─ ④ 风险预检        —— 可选：命中高危规则时直接阻断（fail-closed）
   └─ 转发上游

[出站]  上游响应
   ├─ ⑤ 下行过滤        —— 剥离/脱敏响应中的敏感片段
   ├─ ⑥ 响应指纹        —— 落审计事件
   └─ 返回 Agent
```

### 2.2 本地审计 Agent（风险评分 + 审计分析）

**定位**：独立进程（非 Agent 插件），只消费网关事件流，回写阻断决策。本地自持 LLM 连接（复用本机 deepseek/siliconflow），**推理不外发到第三方**，保证"本地化"。

**核心模块：**

```text
本地审计 Agent
 ├─ 事件订阅器   —— 消费网关事件流（文件/队列/HTTP）
 ├─ 语义风险引擎 —— 本地 LLM 对工具调用参数做语义评分（超越纯正则）
 ├─ 规则引擎     —— 混合：确定性正则规则 + LLM 语义评分
 ├─ 决策器       —— 汇总评分 → LOW/MEDIUM/HIGH/CRITICAL → 放行/确认/阻断
 ├─ 审计分析器   —— 离线批扫：泄露指纹匹配、供应商归属、异常行为
 └─ 审计日志器   —— JSONL 落盘，只存指纹，自动轮转
```

### 2.3 决策存储与审计存储

| 存储 | 内容 | 安全要求 |
|---|---|---|
| 决策存储 | 规则库、历史评分、阻断记录 | 只存指纹，不存明文 |
| 审计日志 | JSONL，`audit_trail.log` | **只存指纹 + 脱敏副本**，自动轮转（10MB/5份），防篡改（append-only + 可选签名链） |

---

## 3. 接口设计

### 3.1 网关对外接口（Agent 视角，OpenAI 兼容）

Agent 配置 `model.base_url = http://127.0.0.1:8787/v1`，其余照常。网关对 Agent 表现为标准 OpenAI Chat Completions 端点，**弱耦合**（Agent 无需任何定制）。

```
POST /v1/chat/completions        # 标准 OpenAI 格式，含流式 SSE
POST /v1/responses               # （可选）Responses API
GET  /v1/models                  # 暴露可用模型列表
```

### 3.2 审计事件接口（网关 → 审计 Agent）

异步、旁路、非阻塞。建议走本地事件（避免引消息队列复杂度）：

```text
POST /audit/events                # 或：本地文件 + inotify 监听
Content-Type: application/json
{
  "ts": 1723290000,
  "session_id": "sess_abc",
  "tool_name": "read_file",
  "arg_fingerprint": "sha256:4d866edb01...",
  "arg_pii_classes": ["api_key"],
  "target_provider": "deepseek",
  "risk_hint": null
}
```

### 3.3 决策接口（审计 Agent → Agent）

```text
GET /risk/verdict?fingerprint=<sha256>     # 查询某动作的当前风险结论
POST /risk/policy                          # 注册/更新规则（仅审计 Agent 可写）
```

**关键约束**：风险评估**必须从 Agent 进程内剥离到独立控制平面**。Agent 只读 `GET /risk/verdict`，不能写 `POST /risk/policy`。这是"控制平面独立"的实质。

---

## 4. 四项能力的实现细节

### 4.1 数据脱敏访问 API（双层模型）

> **关键审查结论**：网关层脱敏**必要但不充分**。上一轮审计发现的真实泄露路径是 `cat .env` 把明文带进 tool_calls —— 这发生在 **Agent 上下文**，网关挡不住。因此必须双层：

| 层 | 位置 | 拦截对象 | 手段 |
|---|---|---|---|
| **A. Agent 工具参数层** | Agent 进程内 | tool_calls 参数、工具输出 | AI-Platform `security.redact_secrets: true`（已开启）+ 强化 `.env`/`auth.json` 读取拦截 |
| **B. 网关层** | 网关 | 发往上游的 request body | DPA 替换 + 响应下行过滤 |

**脱敏类型映射：**

| 敏感类型 | 脱敏规则（示例） | 还原性 |
|---|---|---|
| API Key / Token | `sk-abc…→sk-***` | 不可还原（下游不需要） |
| 手机号 | `138****1234` | 部分 |
| 身份证 | `110***********1234` | 部分 |
| 邮箱 | `zh***@mail.com` | 部分 |
| 域名/URL | 保留 schema+域名，脱 query | 保真 |
| 代码中的密钥字面量 | 按 `KEY=value` 模式脱值 | 保真 |

**风险控制**：脱敏会损伤语义。策略是**只对已归类的敏感字段脱敏，不脱业务字段**；对 LLM 明确需要的字段（如测试用的固定值）通过"允许列表"放行。

### 4.2 内容审计（实时 + 追溯双轨）

| 轨 | 来源 | 时机 | 能力 |
|---|---|---|---|
| 实时旁路 | 网关事件流 | 每次请求 | 指纹捕获、供应商归属、实时告警 |
| 追溯深度 | AI-Platform `state.db`（`agent-session-secret-audit` 技能） | 事后批扫 | 含 tool_calls 深扫、真实密钥逐字匹配 |

**审计日志只存指纹**（`sha256:<前10位>`），绝不存明文——否则网关自身成为新的泄露源。

### 4.3 Agent 动作风险评估（正则 → LLM 语义）

| 现有能力（`operation-audit-core`） | 目标能力 |
|---|---|
| 纯正则 `audit_rules.py` | 本地 LLM 语义评分 |
| 识别模式（`rm -rf`、`cat .env`） | 识别语义（"这条命令会外发 token"） |
| **依赖 Agent 自觉调用**（Audit 点在 Agent 手里） | **独立进程，Agent 无权重写** |

**评分模型：**

```text
risk_score = max( deterministic_rule_score,   # 正则/模式命中
                  llm_semantic_score )        # 本地LLM语义评分

verdict = CRITICAL(score>=4) → 阻断 (fail-closed)
          HIGH(score==3)     → 需用户确认
          MEDIUM(score==2)   → 建议确认
          LOW(score<=1)      → 记录放行
```

### 4.4 系统弱耦合

| 设计点 | 实现 |
|---|---|
| 网关 ↔ 审计 Agent | 通过事件流/文件解耦，无进程内调用 |
| 审计 Agent 故障 | **必须 fail-closed**（宕机即阻断高风险动作），否则是摆设 |
| 网关故障 | Agent 无法调用上游（可见性优先，宁断不放） |
| Agent 被诱导 | 审计控制点在独立进程，Agent 无法绕过/改写规则 |

**设计红线**：弱耦合 ≠ 无耦合。审计 Agent 必须能**阻塞**高风险动作；需明确 `fail-open`/`fail-closed` 策略（参照 AI-Platform Tirith 当前 `fail_open: true`，审计场景建议 `fail_closed` 用于 CRITICAL）。

---

## 5. 与现有 AI-Platform 资产的映射（不重复造轮子）

| 方案组件 | 已有资产 | 差距 / 复用 |
|---|---|---|
| Token 网关 | ❌ 无 | 需新增（LiteLLM Proxy / One-API / 自研） |
| 内容审计（追溯） | ✅ `agent-session-secret-audit` | 离线→在线，接网关事件流 |
| Agent 动作风险 | ✅ `operation-audit-core` | 纯正则→本地 LLM 语义 |
| Agent 侧脱敏 | ✅ `security.redact_secrets: true` | 已开启，强化工具参数级 |
| 审批/阻断 | ✅ `approvals.mode` + Tirith | 独立进程化改造 |

---

## 6. 落地路径（三阶段，按投入递增）

### 阶段一：轻量（0 新增组件，堵住当前泄露场景）
- 强化 `security.redact_secrets`，覆盖工具参数级
- 启用 `operation-audit-core` watchdog 做动作风险拦截（正则级）
- 定期跑 `agent-session-secret-audit` 做追溯审计
- **成本**：低，小时级。**收益**：堵住上次 `TOKENRIVER` 泄露这类场景。

### 阶段二：中型（引入 Token 网关）
- 部署 LiteLLM Proxy，Agent 改指网关地址
- 网关接入 `POST /audit/events`，实时审计接管追溯扫描
- 网关实现上行脱敏（阶段 4.1 的 B 层）
- **成本**：中，天级。**收益**：实时审计 + 请求脱敏 + Token 与 Agent 解耦。

### 阶段三：完整（独立本地审计 Agent）
- 独立进程 + 本地 LLM 语义风险引擎 + fail-closed 决策
- 风险评分脱离 Agent 进程，Agent 无权重写
- **成本**：高，周级。**收益**：完整控制平面。

---

## 7. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 脱敏损伤 LLM 语义 | 白名单字段、分类脱敏、响应还原测试 |
| 网关单点 → 全链路可用性下降 | 无状态可横向、本地高可用、失败策略明确 |
| 审计 Agent 自身被诱导 | 独立进程 + 只读 Agent 决策 + 规则只由审计 Agent 写 |
| 本地 LLM 评分不准 | 混合引擎（正则保底 + LLM 提语义），可回退 |
| 多一跳延迟 | 异步审计（④⑤ 旁路）、流式转发不缓冲 |

---

## 8. 待确认决策项

1. **网关选型**：现成（LiteLLM/One-API）vs 自研？
2. **本地 LLM 来源**：复用本机 deepseek/siliconflow 连接，还是起本地推理服务？
3. **fail 策略**：CRITICAL 阻断是否 fail-closed？（建议是）
4. **审计日志落点**：`~/.AI-Platform/logs/operation-audit/` 复用，还是独立目录？
5. **范围**：先做阶段一堵泄露，还是直接规划阶段三完整方案？
