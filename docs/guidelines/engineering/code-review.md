# A-Stock Agents 现行代码审查规则

**生效日期：** 2026-09-10

旧审查原文与当时的“完成”声明保存在 [代码审查历史归档](../../audits/code-review-history.md)。整改证据按 [审查整改验收台账](../../specs/engineering/eng-remediation-acceptance.md) 逐项记录；台账未给出已验证结论的能力不得宣称完成。

## 强制检查项

1. **生产真实性**：`apps/web-console/backend/server/` 与 `apps/web-console/frontend/js/` 不得选择 Mock、返回固定行情/账户/分析结论，或在失败后渲染成功。
2. **Skill 单一入口**：Web 工具执行必须经过受治理的 Skill 入口；在 P1 完成前，绕过项标为未实现。
3. **分层方向**：业务算法只在 `skill_bundle/runtime/core/` 实现；`apps/web-console/backend/server/` 与 `web/` 只做装配、传输和展示。
4. **凭据边界**：密钥不得进入 API、SSE、日志或浏览器存储；跨域默认只允许明确的本机来源。
5. **失败语义**：未接通能力返回 error 或 unavailable；只有明确 success 的本次结果可进入分析或成功组件。
6. **测试先行**：行为修改先增加能观察到预期失败的测试，再做最小实现并复跑相关套件。
7. **证据优先**：完成声明包含本次命令、通过/失败/跳过计数、平台和产物路径。
8. **用户数据保护**：不删除或覆盖 `output/` 中用户会话、持仓、报告或审计记录。
9. **投研全链路闭环与技能符合性评估（`SPEC-SKILL-002`）**：任何新增或改动的技能与投研算法，必须严格对齐专业机构股票投研六步闭环（**看盘知势 → 选股立池 → 择时定买 → 穿透体检 → 仓位风控 → 回测验证**），严守「`1 + 6` 物理精简架构」与反碎片化铁律，并逐项通过 [技能开发规范第 9 章](skill-suite-portability-specification.md) 的六维符合性评估（C1 闭环归属、C2 `evidence_meta` 循证溯源、C3 失败关闭与空池拦截、C4 250日历史胜率锚与成本过滤、C5 六维覆盖与金字塔结论先行、C6 实战交易三原则与极速门禁）。


## 当前关键路径

- 核心能力：`skill_bundle/runtime/core/config.py`
- Skill 治理：`skill_bundle/runtime/core/governance/skill_registry.py`
- Agent 运行时：`apps/web-console/backend/server/agent/react_runner.py`
- 模型装配：`skill_bundle/runtime/core/llm/factory.py`
- 模型管理 API：`apps/web-console/backend/server/api/models_mgmt.py`
- Web API 客户端：`apps/web-console/frontend/js/api.js`
- Web 应用入口：`apps/web-console/frontend/js/app.js`
- 服务端回归：`tests/webapi/test_webapi_auth_and_session.py`

## 未完成边界

P0 只负责真实性与安全止血。统一能力执行、确认续跑、任务 DAG、MCP、多智能体证据隔离和真实工作台投射分别属于后续 P1-P6；不得因返回 unavailable 而宣称这些能力已经交付。
