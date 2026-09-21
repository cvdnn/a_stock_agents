# 正式 Agent 平台建设实施看板

> 规范编号：`SPEC-ARCH-004`
> 权威定义 (SSOT)：[`production-agent-platform-architecture.md`](../../guidelines/architecture/production-agent-platform-architecture.md)
> **实施状态**：实施中

## 一、规范核心定位摘要
- 架构定义见 SSOT：七层分层架构与依赖方向、正式请求数据流（Web 模式 / 外部宿主模式）、多智能体协作与错误语义。
- 能力与门禁契约见 SSOT：统一能力注册与执行、模型配置与就绪门禁、任务 DAG、正式模式与 Mock 隔离、工作台数据投射、安全审计。
- 正式运行的达成条件见 SSOT「18. 完成标准」；本看板只承载其实施优先级、测试与验收策略与既有计划对齐。

## 二、优先级与依赖顺序

### P0：真实性与安全止血

禁用正式 Mock、移除静默回退和硬编码成功；增加模型门禁；修复供应商密钥返回、localStorage 和 CORS；校准失实的完成状态。该阶段完成后，系统可以“不好看地失败”，但不能继续伪造成功。

实施结果（2026-09-10）：已完成。正式模式拒绝 Mock；模型门禁先于工具执行；供应商凭据不再经 API/浏览器存储返回；默认 CORS 为显式本地来源且不携带凭据；未接通的 Skill/REST/UI 路径返回 unavailable/error/empty；`tests/test_production_authenticity.py` 提供持续扫描。P1 的统一 Skill 执行契约及其后阶段不在本结论内。

### P1：统一能力注册与 Skill 执行

统一规范 ID、别名、Schema、权限、状态和审计；所有 Web 工具调用经过 SkillRegistry/SkillExecutor；建立 `ExecutionResult`。复用现有整改计划 R1 与 R2a。

### P2：用户意图和任务规划

建立模型驱动的意图分析、任务 DAG Schema、本地计划校验和关键性标记。没有通过模型门禁时不进入该阶段。

### P3：任务执行系统

扩展现有 TaskManager，支持 DAG、依赖调度、并发、取消、超时、安全重试、确认暂停、失败传播、SQLite 状态和 SSE 事件。

### P4：MCP 接入与辅助数据

建立 MCPManager、连接配置、健康检查、工具发现、权限、凭据引用和 MCPExecutor；先接入能补足新闻、政策、舆情和基本面的数据能力。MCP 故障按任务节点关键性处理。

### P5：多智能体协作与角色模型

把现有 7 角色分析迁移到结构化任务和证据输入，按角色解析实际模型；隔离上下文；建立风控与综合仲裁。复用现有整改计划 R3、R4 和可用的 `core/multi_agent` 资产。

### P6：真实工作台与报告闭环

把市场、股池、持仓、监控、分析和报告页面改为真实任务结果投射；逐项接通已有 Skill 后端；未实现能力保持 unavailable。复用 R2b 与 A2UI 整改任务。

### P7：跨宿主与生产验收

验证 Windows/Linux/macOS 的统一 CLI JSON 契约；在无 Web 服务情况下完成 Codex/Hermes 技能调用；验证 Web 与外部宿主使用同一输入时得到同构执行结果；完成生产模式无 Mock/硬编码扫描和端到端故障测试。

## 三、测试与验收策略

实施必须采用测试先行。测试分为：

1. **契约测试**：Skill/MCP 输入输出、错误状态、来源和时间字段。
2. **模型门禁测试**：未配置、禁用、认证失败、超时、能力不足和成功路径。
3. **任务 DAG 测试**：环检测、主任务失败、辅助任务遗漏、取消、超时和安全重试。
4. **治理测试**：禁用技能、参数非法、确认重放、超时后无后台写入。
5. **多智能体测试**：角色只接收成功证据；遗漏板块不参与结论；角色模型绑定生效。
6. **安全测试**：API/SSE/日志无密钥；前端无凭据持久化；MCP 内容不能改变权限。
7. **前端测试**：错误、空状态、遗漏提示和 SSE 状态准确，不显示伪成功。
8. **跨宿主测试**：CLI、Web、Codex/Hermes 的 Skill 结果契约一致。
9. **生产真实性测试**：扫描正式源码和构建产物，阻止 Mock 行情、固定账户、模板分析和 `model='mock'`。

单元与集成测试使用显式合成数据和 Fake Provider，不访问付费模型或真实账户。生产联调单独运行并记录接口、时间和数据来源；合成测试通过不能替代生产真实性验收。

## 四、现有计划对齐

本设计不废弃现有 `docs/specs/architecture/arch-agent-runtime-remediation-plan.md` 和 `docs/specs/engineering/eng-remediation-plan.md`：

- R1、R2a 归入 P0/P1。
- R3、R4 归入 P3/P5。
- R2b 归入 P6。
- 现有 A2UI、费用风控、算法治理和工程验证计划继续作为领域子计划。
- 新增实施计划只补充模型门禁、能力统一契约、任务 DAG、MCPManager、多智能体证据隔离和跨宿主验收缺口。

## 五、关联看板
- [`arch-web-aichat-and-skill-governance.md`](./arch-web-aichat-and-skill-governance.md)
- [`production-agent-platform-p0-plan.md`](../engineering/production-agent-platform-p0-plan.md)

## 六、变更日志
| 日期 | 变更摘要 |
|:---|:---|
| 2026-09-20 | 由 `docs/specs/architecture/production-agent-platform-design.md` 拆分：架构定义迁至 `docs/guidelines/architecture/production-agent-platform-architecture.md`，实施优先级迁入本看板 |