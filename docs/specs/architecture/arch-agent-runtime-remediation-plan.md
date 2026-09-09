# Agent 运行时与技能真实性实施计划

> **For agentic workers:** 使用 `executing-plans` 按 R1、R2a、R3、R4、R2b 执行；依赖与前端交接按总计划控制。

**Goal:** 对话工具调用受治理约束，结果真实可追溯，多轮上下文完整，业务角色决定实际模型。

**Architecture:** server 层装配技能适配器并统一通过 core registry 执行；SQLite 保存工具轮次和用户确认快照；模型工厂统一处理显式 override 与 role 绑定。

**Tech Stack:** FastAPI、Pydantic、asyncio、SQLite、pytest、HTTPX MockTransport。

---

依赖：[工程计划 E1/E2](C:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-runtime-and-test-remediation-plan.md) 先完成。所有 provider/行情测试使用合成响应。

## R1：统一技能执行与确认续跑

**发现：** A1。**文件：** 修改 `scripts/core/governance/skill_registry.py`、`scripts/server/agent/tools.py`、`scripts/server/agent/react_runner.py`、`scripts/server/app.py`、`scripts/server/models.py`、`scripts/server/db.py`、`scripts/server/api/chat.py`；新增 `scripts/server/agent/tool_execution.py`；扩展 `tests/test_governance_suite.py`、`tests/test_server_suite.py`。

- [ ] 增加 scripted provider：第一轮请求被禁用/需确认的技能，第二轮读取观察。注册 spy handler；旧运行时会绕过门禁调用 spy，测试必须先失败。四种变体断言 handler调用次数=0：禁用、未确认、参数非法、tools_enabled=false。
- [ ] 明确所有 legacy/下划线别名到17项规范ID的映射。新增 `resolve_skill_call(tool_name, arguments) -> (skill_id, params)`，不得仅替换 `_` 为 `-`：astock_quote 映射 data-feed 的 action=quote，astock_technical 映射 action=tech，action_plan 映射 action-execution。映射在一个表内并逐条测试。
- [ ] 新增 `execute_governed_tool(tool_name, arguments, *, registry, confirmed=False)`。仅 adapter 调 registry.execute_skill；registry handler 由 app 启动时装配，移除 core.governance 内对 server.agent.tools 的运行时反向导入。执行状态保留 success/error/timeout/confirmation_required，不再按 error 键推断全部状态。
- [ ] 将 runner 内直调 execute_tool 替换为该 adapter；工具清单过滤与执行端校验均保留。拒绝和超时记一条审计，异常不要重复计两次。同步有副作用工具超时后不能后台继续写数据：采用受控子进程或可取消执行方式，并在本任务测试“超时后等待仍无写入”。
- [ ] 在 db.py 新增 pending_tool_calls 表，字段为 call_id、session_id、skill_id、params_json、expires_at、status。服务端保存原参数，用户续跑只提交 `confirm_call_id`；ChatMessageRequest 新字段只能由 HTTP 请求提供，模型参数不能给 confirmed=true。原子地将 pending 改 running，过期/跨会话/重复请求拒绝；结果完成后存 consumed。
- [ ] 增加 POST `/api/chat/tool-calls/{call_id}/confirm`，请求携带所属 session_id；从保存快照执行并继续同一会话。前端在 F2 接入前，后端先返回 confirmation_required，禁止为了演示默认确认。
- [ ] 套件覆盖：确认一次调用一次、重放不调用、更改请求参数不影响快照、禁用发生在确认前仍拒绝。命令：`python -m pytest tests/test_governance_suite.py tests/test_server_suite.py -q`。通过后提交 `fix: route agent tool calls through skill governance`。

**测试契约片段（scripted provider 和 spy 均在上述套件本地定义）：**

```python
assert result.status == "confirmation_required"
assert handler.call_count == 0
assert audit.status == "rejected"
# 使用保存的 call_id 确认后
assert confirmed_result.status == "success"
assert handler.call_count == 1
assert replay_result.status == "error"
assert handler.call_count == 1
```

## R2a：立即移除虚构成功

**发现：** A2。**文件：** 修改 tools.py、registry 的能力描述；新增 `docs/specs/architecture/arch-skill-capability-acceptance.md`；扩展 test_server_suite.py。

- [ ] 清点全部17项和 legacy aliases，台账逐行列出 handler、真实目标、输入schema、产物、网络/模型依赖、当前实现状态。新增参数化测试直接覆盖所有 handler 的异常路径。
- [ ] pool audit、archive、html、model validation、debate、quant、trade、mainboard 等占位/错误降级不再返回通过、active、simulated 或 fabricated metrics。统一未实现输出：

```python
{"status": "unavailable", "error": "CAPABILITY_NOT_IMPLEMENTED", "skill_id": skill_id}
```

- [ ] 数据获取失败返回 error，不能填默认价格/账户资产后继续给建议。知识提示/规则说明可以返回静态内容，但类型为 reference，不得称已完成个股检测。
- [ ] runner 把 unavailable/error 原样传给模型并呈现失败；仅 success 可触发成功风险卡/报告归档事件。测试断言不存在固定 IC=0.065 或52/48结论。
- [ ] 完成该任务只关闭“虚构成功”缺陷，对应未实现能力仍待交付。提交 `fix: report unavailable skills without fabricated success`。

## R3：持久化完整轮次并截取最新上下文

**发现：** A3、A4。**文件：** 修改 react_runner.py、db.py；新增 `scripts/server/agent/context.py`；扩展 test_server_suite.py。

- [ ] 新增31条消息测试、两轮 tool_calls 测试、截取窗口落在工具结果中间的测试。旧实现应遗漏最新消息或出现孤立 role=tool。
- [ ] assistant 的 text/thought/tool_calls 统一落库一次，再执行/落库工具结果；失败和确认暂停也保存原 assistant 调用。为每轮增加 turn_id，数据库通过兼容 ALTER TABLE 迁移，不删除历史记录。
- [ ] 新增 `get_context_messages(session_id, max_messages=30, db_path=None)`：从最新轮次向前累计，按完整轮次包含；最近单轮超过30条时保留该完整轮次，30为软上限。UI历史分页继续用 get_messages，不将其排序语义整体改变。
- [ ] 新增 `build_llm_context(rows)`：仅回放有配对调用的工具结果；旧库中无配对的 orphan tool 不构造伪调用，跳过并记结构化诊断。始终包含本轮用户消息；同一 call_id 的重复结果明确拒绝。
- [ ] 使用严格 Fake Provider 检查每个 tool_call_id 都有前置 assistant tool_calls，执行第二轮无协议错误。关键断言：

```python
assert context[-1]["content"] == "latest question"
known = set()
for message in context:
    for call in message.get("tool_calls", []):
        known.add(call["id"])
    if message["role"] == "tool":
        assert message["tool_call_id"] in known
```

- [ ] 运行 `python -m pytest tests/test_server_suite.py -q`，提交 `fix: preserve complete recent conversation turns`。

## R4：角色到实际提供商的接线

**发现：** A5。**文件：** 修改 factory.py、react_runner.py、server/models.py、server/db.py、api/models_mgmt.py、core/multi_agent/ta_analyze.py、ta_orchestrator.py；扩展 test_server_suite.py。

- [ ] 冻结优先级：用户本轮显式 model override > 会话显式模型偏好 > 对应业务 role 绑定 > 环境默认。会话存 resolved_model 仅用于显示，另存 model_override，避免创建会话时把环境默认误当用户选择。
- [ ] chat 默认通过 `get_provider(role="chat")`；量化文本解释用 quant、多空推理用 debate、摘要用 summary、图像输入用 vision。core/multi_agent只接受注入的模型客户端或回调，server装配层负责按role选择，不在core中新增对server的反向导入。纯Python数值计算不调用模型。未实现的角色消费者保持 unavailable，不以创建工厂对象冒充业务接线。
- [ ] provider禁用、角色不存在/缺模型时返回明确错误或仅按上述默认链降级；不能在显式选择 provider 失败后静默变成 Mock。旧 mock 只在显式演示/测试设置下保留。
- [ ] 使用 factory spy 验证每个已实现消费者传入role；通过 API 修改绑定后同一进程下一次调用使用新provider/model；显式override优先。将原 `isinstance(x, object)` 恒真断言替换为具体类型和 model_name 断言。
- [ ] 运行 server/governance 套件，提交 `fix: apply model role bindings in runtime consumers`。

## R2b：将已具备引擎的技能接到真实产物

**依赖：** R1、R2a、R4；费用相关再依赖 B2。**文件：** tools.py、core/commands/model_cmds.py、trade_cmds.py、reporting/report_generator.py、strategy/pool_manager.py；必要时新增 `scripts/core/strategy/pool_audit.py`，迁移并复用 `.agents/skills/astock-pool-audit/scripts/pool_audit.py` 中业务；扩展领域和server测试。

- [ ] 模拟盘适配实际 PaperTradingEngine，不调用不存在的 AccountManager；余额查询不隐式创建100万账户。买卖返回真实 order_id/状态，撤单失败保持失败，全部写操作经过 R1。
- [ ] pool audit 复用既有读取和均线计算，先返回 dry-run 差异，fix=true 经过确认后写入；对缺失行情不更新关键位。
- [ ] report html/归档复用实际 report_generator 的文件产物，成功必须有位于统一 reports目录且存在的路径、摘要和类型；未生成时不得 archived。
- [ ] quant/mainboard/debate 的桥接指向真实已存在函数，不猜测类名；从原CLI处理器提取共享纯业务函数供两端使用，CLI继续支持 --json。原cmd_debate同样包含固定新闻、行业地位和筹码结论，必须验证每个输出有对应输入证据，不能因函数在core就信任其全部文本；缺数据的角色明确标注不可判断。发现无可用后端时，台账写明缺失依赖并保留 unavailable。
- [ ] 外部模型验证只有在真实数据、模型依赖与样本外流程可用时才开放；执行过程和结果单独存档，synthetic测试不得写“已实证通过”。
- [ ] 每个能力分别验证输入到结果/文件/订单的因果关系，逐项提交 `feat: connect <skill> to canonical execution backend`，并逐行更新能力台账。

**完成门槛：** ARCH-001 只有在其要求的全部技能消费者、确认续跑、多轮会话和对应产物均通过后才能恢复全量基线；R2a完成不满足该门槛。
