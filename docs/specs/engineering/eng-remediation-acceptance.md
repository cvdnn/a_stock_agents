# 审查整改验收台账

**状态日期：** 2026-09-10  
**原则：** 只记录已观察到的证据，不预填未来通过结论。实现、测试和生产真实性证据齐备后，单项规格才能恢复正式基线。

| spec | original_claim | findings | tasks | code_paths | tests | current_status |
|---|---|---|---|---|---|---|
| `SPEC-ENG-001` | 正式基线 100% 已交付 | E1/E2/E3/T1 | E1-E4 | `scripts/core/config.py`; `scripts/server/config.py`; installers | `tests/test_workspace_suite.py` | 实施中：路径、测试隔离与打包待验收 |
| `SPEC-UI-001` | 正式基线 100% 已交付 | U1/U2/U3 | F1-F4 | `web/js/app.js`; `web/js/api.js` | 前端与浏览器套件 | 实施中：真实状态与浏览器验收待完成 |
| `SPEC-A2UI-001` | 正式基线 100% 已交付 | U1/U3 | F1/F2/F4 | `web/js/ui_engine.js`; `web/js/app.js` | A2UI/浏览器套件 | 实施中：生产假成功与资源回收待验收 |
| `SPEC-A2UI-002` | 正式基线 100% 已交付 | U2 | F3 | `web/js/ui_engine.js`; `web/js/components/astock.js` | A2UI registry 套件 | 实施中：注册表自省与命名契约待验收 |
| `SPEC-ARCH-001` | 正式基线 100% 已交付 | A1-A4 | R1-R3 | `scripts/server/agent`; `scripts/core/governance` | server/governance 套件 | 实施中：治理、真实性和会话完整性待完成 |
| `SPEC-ARCH-002` | 正式基线 100% 已交付 | A5 | R4 | `scripts/server/llm`; `scripts/server/api/models_mgmt.py` | provider/role 套件 | 实施中：模型门禁与角色接线待验收 |
| `SPEC-BIZ-001` | 正式基线 100% 已交付 | B1/B2 | B1/B3 | `scripts/core/strategy/trading_costs.py`（计划） | 费用领域套件 | 实施中：统一费用实现与跨端一致性待完成 |
| `SPEC-BIZ-002` | 正式基线 100% 已交付 | B1/B2 | B1/B3 | `scripts/core/strategy/trading_costs.py`（计划） | 费用领域套件 | 实施中：收费边界与配置热更新待验收 |
| `SPEC-BIZ-003` | 正式基线 100% 已交付 | B3 | B2/B3 | `scripts/core/strategy/execution_action_engine.py` | 动作单/跨端套件 | 实施中：完整动作契约待验收 |
| `SPEC-ALGO-001` | 正式基线 100% 已交付 | G1 | G1-G3 | `scripts/core/models`; `scripts/core/monitor_governance.py` | 算法治理套件 | 实施中：持久化证据、晋级和熔断待完成 |

SPEC-ARCH-003 保持 RFC/Backlog。原始审查文本与历史完成声明保存在 [代码审查历史归档](../../audits/code-review-history.md)。
