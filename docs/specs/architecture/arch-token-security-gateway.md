# Token 链路安全网关与本地化审计 Agent 架构设计规范 (Token Gateway & Security Audit Specification)

- **规范分类**：系统架构设计
- **规范编号**：SPEC-ARCH-003
- **文档版本**：v1.1
- **当前状态**：正式规范 (Production Baseline)
- **创建日期**：2026-08-10（修订日期：2026-09-07）
- **适用场景**：本地智能体（AI-Platform / Antigravity / Hermes）与上游 LLM 服务商之间的流量代理、安全脱敏与调用审计控制平面
- **关联设计**：[`arch-web-aichat-and-skill-governance.md`](arch-web-aichat-and-skill-governance.md)、[`arch-llm-provider-and-role-allocation.md`](arch-llm-provider-and-role-allocation.md)

---

## 0. 设计目的与核心诉求

设计一个位于 **本地 Agent 与上游 LLM 供应商 API 之间** 的控制平面，实现四项能力：

1. **数据脱敏访问 API** —— 请求上行脱敏、响应下行过滤/还原；
2. **内容审计** —— 实时捕获进出流量，形成不可篡改、只存指纹的审计日志；
3. **Agent 动作风险评估** —— 对 Agent 的工具调用/命令执行做语义级风险评分与阻断；
4. **系统弱耦合** —— 网关、审计 Agent、执行 Agent 三者独立部署、独立故障。

设计原则：**控制平面（网关 + 审计）与执行平面（Agent）分离**。信任不放在 Agent 上，也不放在上游供应商上，而是放在本地自持的可观测、可脱敏、可阻断、可审计的中间层。

---

## 1. 总体架构拓扑

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

## 2. 组件设计与职责

### 2.1 Token 网关（核心控制点）

**定位**：反向代理，唯一持有真实上游 Token 的地方。Agent 侧只配网关地址，永不接触真实密钥。

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
| 审计日志 | JSONL，`audit_trail.log` | **只存指纹 + 脱敏副本**，自动轮转（10MB/5份），防篡改 |

---

## 3. 接口契约设计

### 3.1 网关对外接口（Agent 视角，OpenAI 兼容）
Agent 配置 `model.base_url = http://127.0.0.1:8787/v1`，其余照常。网关对 Agent 表现为标准 OpenAI Chat Completions 端点，**弱耦合**（Agent 无需任何定制）：
```text
POST /v1/chat/completions        # 标准 OpenAI 格式，含流式 SSE
POST /v1/responses               # （可选）Responses API
GET  /v1/models                  # 暴露可用模型列表
```

### 3.2 审计事件接口（网关 → 审计 Agent）
异步、旁路、非阻塞：
```json
POST /audit/events
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

---

## 4. 四项能力的实现细节

### 4.1 数据脱敏访问 API（双层模型）
网关层脱敏必要但不充分。必须采用双层防护：
| 层 | 位置 | 拦截对象 | 手段 |
|---|---|---|---|
| **A. Agent 工具参数层** | Agent 进程内 | tool_calls 参数、工具输出 | `security.redact_secrets: true` + 强化 `.env`/`auth.json` 读取拦截 |
| **B. 网关层** | 网关 | 发往上游的 request body | DPA 替换 + 响应下行过滤 |

**脱敏类型映射：**
- **API Key / Token**：`sk-abc… → sk-***`（不可还原）
- **手机号**：`138****1234`（部分掩码）
- **身份证**：`110***********1234`（部分掩码）
- **邮箱**：`zh***@mail.com`（部分掩码）
- **代码密钥字面量**：按 `KEY=value` 模式脱值

### 4.2 内容审计
- 实时旁路：网关事件流，每次请求指纹捕获与实时告警；
- 追溯深度：事后批扫，含 tool_calls 深扫与真实密钥比对；
- 审计日志只存指纹（`sha256:<前10位>`），绝不存明文。

### 4.3 Agent 动作风险评估
```text
risk_score = max( deterministic_rule_score, llm_semantic_score )

verdict = CRITICAL(score>=4) → 阻断 (fail-closed)
          HIGH(score==3)     → 需用户确认
          MEDIUM(score==2)   → 建议确认
          LOW(score<=1)      → 记录放行
```

---

## 5. 落地路径与阶段规划

- **阶段一：轻量级防线**：强化工具参数级脱敏，开启正则 watchdog 动作拦截与追溯审计；
- **阶段二：网关层介入**：引入反向代理，接管 `POST /audit/events` 并实现上行 request body 脱敏；
- **阶段三：完整控制平面**：独立本地审计 Agent，结合本地 LLM 语义风险评分与 fail-closed 决策。
