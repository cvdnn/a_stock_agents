# 项目代码结构与规范完成情况审查

审查日期：2026-09-09。代码基准：`88f1f71`，审查开始时 Git 工作区无已跟踪文件改动。依据 `docs/guidelines/` 的契约与 `docs/specs/` 的任务矩阵，检查源码、实际调用链及本地测试。本文只评估工程实现，不构成个股投资建议。

**结论：目录分层已经形成，生产交付声明明显领先于实际集成。** 总看板共 11 项规范，10 项标为“100% 基线”，Token 安全网关 1 项标为规划中。本次在上述 10 项中均发现未闭环的验收要求，暂不能确认任何一项符合其完整的“生产基线”声明。这不代表已有功能没有价值，也不是“代码完成率为零”；未建立带权重的逐条验收清单前，不给出貌似精确的总体百分比。

## 代码结构评估

| 层级 | 当前结构 | 评价 |
|---|---|---|
| 智能体资产 | `.agents/skills/` 下实际有 17 个技能目录；另有 prompts/manifests | 就地资产主体存在；旧模板与独立服务仍残留全局路径 |
| 核心业务 | `scripts/core/{data,indicators,models,strategy,paper_trading,multi_agent,governance,monitor,reporting}` | 领域分层合理，CLI 已拆至 commands；跨层治理和费率契约没有统一执行 |
| 服务端 | `scripts/server/{api,agent,llm,tasks}` 与 SQLite | API/运行时/提供商有分层；ReAct 实际执行绕过治理层，角色配置缺调用方 |
| 前端 | `web/js/{app,api,charts,ui_engine}.js` 与 `components/astock.js` | 原生 JS、组件包和引擎已分离；app.js 仍混合示例数据、报告模板、路由和交互，真实后端与演示路径并存 |
| 运维入口 | `bin/astock`、`bin/astock.cmd`、安装/打包工具 | 两个 CLI 启动器已指向 scripts；安装与打包链路迁移不完整 |
| 私有数据 | `output/`、可配置输出目录、`.gitignore` | 主路径已有隔离；独立模拟盘默认全局路径、已跟踪缓存数据库等例外仍在 |
| 测试与文档 | tests、guidelines、specs | 有领域回归；测试隔离、集成断言、代码映射和实际验收记录不足 |

根目录的 `core/`、`skills/` 在本工作区仍有实体目录残留，但 `git ls-files core skills` 未列出跟踪文件，不能据此认定存在两套受版本控制的业务实现。技能目录中的大量同名薄转发器则与 naming-conventions 的反影子模块要求冲突；verify.py 又要求至少 50 个转发器，规范本身需要明确兼容例外及退役计划。

## 逐项 specs 判定

| 规范 | 看板状态 | 本次判定 | 已有成果与未完成验收 |
|---|---|---|---|
| SPEC-ENG-001 | 100% 基线 | 部分完成 | 17 技能、scripts 分层和跨平台 CLI 已有；安装旧路径、打包入口、全局运行路径和测试隔离未通过，见 E1–E3、T1 |
| SPEC-UI-001 | 100% 基线 | 部分完成 | 双模布局、富文本与操作符交互已有；三原则紧凑卡片缺 T0/三场景，股票路径仍输出固定诊断，见 U1、B3 |
| SPEC-ARCH-001 | 100% 基线 | 部分完成，关键链路缺失 | FastAPI/SSE/SQLite/注册表存在；工具治理绕过、占位成功、多轮历史错误，见 A1–A4 |
| SPEC-ARCH-002 | 100% 基线 | 管理面已有，运行时未闭环 | Provider/Role 管理及工厂存在；chat/quant/debate 等业务未按 role 调用，见 A5 |
| SPEC-ARCH-003 | 规划中 RFC | 未实施，状态一致 | 未见 security 网关、上行脱敏、下行过滤与规定的指纹审计链；应保持 Backlog，不算虚报完成 |
| SPEC-A2UI-001 | 100% 基线 | 原型已有，生产验收未完成 | 骨架、水合和投射接口存在；真实路径靠计时器与固定数据，图表未使用传入数据，历史投射覆盖，见 U1、U3 |
| SPEC-A2UI-002 | 100% 基线 | 部分完成 | 分包与逆序缓冲可用；规范全名解析失败、短名覆盖、自省契约及组件数量不符、自动发现未接线，见 U2 |
| SPEC-BIZ-001 | 100% 基线 | 部分完成 | 配置读写、CLI 及部分动态费率已有；模拟盘过户费与前端算价仍分叉，见 B1、B2 |
| SPEC-BIZ-002 | 100% 基线 | 核心算法已有，跨端一致性未完成 | 后端有精算与进位；前端采用另一公式，10 列 HTML 表映射不存在，见 B2、D1 |
| SPEC-BIZ-003 | 100% 基线 | 部分完成 | 动作引擎、提示词、技能入口已有；CLI 缺规定止损/场景结构，紧凑卡片也不完整，见 B3 |
| SPEC-ALGO-001 | 100% 基线 | 算法/治理组件已有，强制门禁未闭环 | 注册表、质量检查与监控类已有；默认直接 production，退役仍可调用，质量检查未接业务执行，见 G1 |

## 高优先级发现

### A1 · P1：ReAct 绕过技能治理执行门禁

[react_runner.py:182](C:/Users/cvdnn/coding/a_stock_agents/scripts/server/agent/react_runner.py:182) 直接 `await execute_tool(...)`；[tools.py:513](C:/Users/cvdnn/coding/a_stock_agents/scripts/server/agent/tools.py:513) 通过 TOOL_MAP 调度。启停复核、确认、参数 Schema、超时与审计位于 [skill_registry.py:368](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/governance/skill_registry.py:368)，对话执行没有走这条路径。生成工具清单时过滤 enabled 不能替代执行端校验。需要以 API→ReAct→受控执行器的全过程证明禁用/未确认/非法参数调用被拒绝。

### A2 · P1：多项技能返回占位成功

[tools.py:410](C:/Users/cvdnn/coding/a_stock_agents/scripts/server/agent/tools.py:410) 的股池审查未读写股池就声称关键位已校准；:418 的归档无写文件动作却返回 archived；:447 的外部模型验证固定返回 passed 和 IC=0.065。辩论路径在 :363 附近失败后还会返回固定多空结论。这些结果没有 error 字段，因此被运行时当作成功发送给模型。必须连接真实执行结果，或明确返回尚未实现/失败。

### A3 · P1：工具调用轮次的 assistant 消息未落库

[react_runner.py:149](C:/Users/cvdnn/coding/a_stock_agents/scripts/server/agent/react_runner.py:149) 只把带 tool_calls 的 assistant 消息加入内存；:153 仅在没有工具调用时写 assistant；:223 却总会写 tool 结果。下一轮回放会出现缺少对应 assistant tool_calls 的 tool 消息。应持久化完整调用轮次，并通过严格协议校验的第二轮测试验收。

### A4 · P1：超过 30 条消息后上下文丢失最新请求

[react_runner.py:81](C:/Users/cvdnn/coding/a_stock_agents/scripts/server/agent/react_runner.py:81) 读取 limit=30；[db.py:358](C:/Users/cvdnn/coding/a_stock_agents/scripts/server/db.py:358) 使用 `ORDER BY id ASC LIMIT ?`，取最早 30 条。当前用户消息虽然先落库，但超限后不在提供给模型的历史中。应按最近的完整工具轮次截取，再按时间正序组织。

### A5 · P1：角色配置未控制真实提供商选择

[factory.py:36](C:/Users/cvdnn/coding/a_stock_agents/scripts/server/llm/factory.py:36) 有 role 解析能力，但 [react_runner.py:102](C:/Users/cvdnn/coding/a_stock_agents/scripts/server/agent/react_runner.py:102) 始终传非空 selected_model，scripts 范围未发现业务 `get_provider(role=...)` 调用。配置界面修改 debate/quant 角色不等于相关业务会采用该绑定。需要真实业务调用与模型选择断言。

### U1 · P1：A2UI 把固定示例展示为已完成的个股分析

[app.js:2925](C:/Users/cvdnn/coding/a_stock_agents/web/js/app.js:2925) 股票操作符直接进入 executeA2UITask 并返回；[app.js:2863](C:/Users/cvdnn/coding/a_stock_agents/web/js/app.js:2863) 用 setTimeout 注入固定指数；:2876 使用固定“多头排列、二次金叉确认、主力净流入”结论，未在这条路径调用真实后端。展开雷达和 K 线也在 [astock.js:49](C:/Users/cvdnn/coding/a_stock_agents/web/js/components/astock.js:49)、:144 写死价格或生成曲线。必须由实际数据/事件驱动，并明确标识演示模式。

### B1 · P1：模拟盘过户费与统一费率配置不一致

[engine.py:87](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/paper_trading/engine.py:87) 仅为上海标的收过户费，使用 DEFAULT_TRANSFER_FEE_RATE；:105 的实际佣金计算依赖它。指南明确沪深双向收费，且过户费属于动态配置。修改配置不会改变这里的过户费，深圳标的直接返回 0，导致模拟成交成本与后端保本价口径不同。

### B2 · P1：前端保本价另写公式，未使用统一精算与配置

[astock.js:166](C:/Users/cvdnn/coding/a_stock_agents/web/js/components/astock.js:166) 写死最低 5 元、佣金、税率及过户费，并把两侧费用都按买入金额估计；过户费使用 `0.00002 * 2`，也不同于规范的单边 0.00001。后端 [execution_action_engine.py:286](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/strategy/execution_action_engine.py:286) 则按卖出净收入反解并支持 market_cfg。前端并非后端精算结果的展示端，免五/自定义费率不会生效。

### B3 · P1：动作单没有兑现规定的三原则输出契约

[strategy_cmds.py:219](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/commands/strategy_cmds.py:219) 将 generate_action 结果原样输出；[execution_action_engine.py:339](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/strategy/execution_action_engine.py:339) 的结构没有 `stop_loss`、`action_scenarios`。这与 BIZ-003 明确要求的 T0/T1/T2 和 open_surge/narrow_range/plunge 验收不一致。前端 [astock.js:189](C:/Users/cvdnn/coding/a_stock_agents/web/js/components/astock.js:189) 计算 T0 却未渲染，紧凑卡片也没有三场景。应先统一数据契约，再逐个验证 CLI、API、卡片和 HTML。

### G1 · P1：算法生命周期是元数据，未形成强制执行约束

[registry.py:61](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/models/registry.py:61) 默认注册为 production；[registry.py:168](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/models/registry.py:168) 的 run_algo 不检查生命周期。现有 [monitor_governance.py:324](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/models/monitor_governance.py:324) 允许直接转换状态，退市熔断仅更新元数据；执行层仍可解析并执行 retired 算法。G1/G2 检查器和 G3/G4 监控类确实存在，不能说完全没有治理代码，但未见质量检查 audit_algorithm 的业务调用。应验证未验收算法不能晋级、退役算法不能进入生产调度。

### E1 · P1：安装器引用迁移前路径

[install.sh:49](C:/Users/cvdnn/coding/a_stock_agents/install.sh:49)、[install.ps1:46](C:/Users/cvdnn/coding/a_stock_agents/install.ps1:46) 执行 `core/workspace.py`，该文件不存在，实际在 scripts/core。Unix 安装器启用 set -e，会在这里停止；PowerShell 未显式检查原生命令退出码，后续成功提示也不可靠。此次未安装依赖或修改环境，结论来自明确的文件路径核验。

### E2 · P1：打包转发器无声跳过整个打包流程

[bin/pack.py:19](C:/Users/cvdnn/coding/a_stock_agents/bin/pack.py:19) 仅在被导入模块存在 main 时调用；[scripts/tools/pack.py:87](C:/Users/cvdnn/coding/a_stock_agents/scripts/tools/pack.py:87) 没有 main，参数解析和 package_project 调用仅位于自身 __main__ 块。转发导入不会执行该块，因此入口可退出成功却没有 ZIP。验收应检查实际产物而非仅检查退出码。

## 其他确定性差距

| 编号 | 优先级 | 问题与证据 |
|---|---|---|
| U2 | P2 | [ui_engine.js:108](C:/Users/cvdnn/coding/a_stock_agents/web/js/ui_engine.js:108) 解析全名仅取前两段，`@a2ui/pack-astock/MarketRadar` 不能命中；:84 覆盖同名短名而非拒绝歧义；:166 的 catalog 缺 propsSchema/defaultTarget。实际 astock.js 注册 3 个组件，spec 验收却写 6 个。loadPack 有实现，但未知组件解析没有自动调用它。 |
| U3 | P2 | [ui_engine.js:292](C:/Users/cvdnn/coding/a_stock_agents/web/js/ui_engine.js:292) 重写同一个投射内容节点；旧标签没有独立报告内容重建。未实际测量 CLS，不能认可 CLS=0 的生产验收结论。 |
| E3 | P2 | [paper_trading_runtime.py:17](C:/Users/cvdnn/coding/a_stock_agents/scripts/core/paper_trading/paper_trading_runtime.py:17) 默认使用用户全局应用数据目录；独立 service/ctl 会调用该路径。部分监控模板仍写 `.AI-Platform`。`git ls-files cache` 仍列出 3 个测试 DB，忽略规则不能解除既有跟踪。没有读取这些数据库内容，也不能认定它们包含真实持仓。 |
| T1 | P2 | 默认 pytest 收录 [test_live_server_e2e.py:6](C:/Users/cvdnn/coding/a_stock_agents/tests/test_live_server_e2e.py:6) 的固定 localhost:6300 测试；普通 server suite 也调用真实行情，且默认 DB 未被临时 fixture 全面替换。与 testing-guide 的本地 Mock、确定性、隔离要求不一致。 |
| D1 | P2 | specs 中 `scripts/core/reporting/html_reporter.py`、`scripts/core/models/five_dim_model.py`、`scripts/core/commands/cmd_backtest.py` 均不存在。ALGO 的 `quant pipeline --help` 只能证明解析帮助，不能证明算法流水线运行成功。 |
| D2 | P2 | guidelines/code-review.md 实际是带历史问题和修复记录的审查报告，与索引描述的规范清单不同；SSE 路由/事件名也存在指南与源码漂移。应分离历史审计与现行验收契约。 |

## 验证记录与边界

- Python 选定范围：**114 passed，1 failed**，运行耗时 80.40 秒。完整输出见 [pytest-results.txt](C:/Users/cvdnn/coding/a_stock_agents/output/audit-review/pytest-results.txt)。这是 115 项选定测试的结果，绝非全库通过率或规格完成率。
- 运行方式：项目 `.venv` Python，`pytest tests -q -p no:cacheprovider`，排除 test_live_server_e2e.py、test_server_suite.py、test_market_data_api.py、test_governance_suite.py，使用独立 basetemp；设置 A_STOCK_OUTPUT_DIR、A_STOCK_DB_PATH、A_SHARE_PAPER_TRADING_HOME 到审查目录。首次更宽范围执行已中断，不计为完成验证。
- 失败用例为 `TestStockCodeDecoupling.test_action_plan_missing_code_defensive_behavior`。该用例未建立空持仓 fixture，实际读到持仓后进入行情分支；因此连收窄范围也不能称为完全无网络测试。应修正测试依赖隔离，再重新验收。原始失败结果保留，不通过临时改变条件把它记成套件全绿。
- Node 的现有操作符套件通过；其中多数是源码字符串断言，另外有排序与 Mock DOM 退格断言，不能代替浏览器、真实 SSE、角色路由或风控契约集成测试。输出见 [node-results.txt](C:/Users/cvdnn/coding/a_stock_agents/output/audit-review/node-results.txt)。
- 独立复核的 Node VM 探针验证了逆序载入缓冲可用，同时复现完整组件名查询失败、短名覆盖及展开行情未采用传入数据。
- 本地合成探针记录见 [probe-results.json](C:/Users/cvdnn/coding/a_stock_agents/output/audit-review/probe-results.json)。本次未运行外部 LLM 联调、真实浏览器 CLS 测量、完整安装/升级或生产部署。

本地探针的确定结果如下（均为合成输入）：

| 检查 | 结果 |
|---|---|
| bin/pack.py 指定输出路径 | 退出码 0、stdout 为空、ZIP 不存在 |
| 成本 1000、100 股、规范默认费率 | 后端保本价 1001.03，前端 1001.04；两端不一致 |
| 后端黄金样例：成本 6.1411、5000 股 | 输出 6.15，与该样例验收一致 |
| 成交额 10000、传入过户费率 0.0001 | 上海实际 0.1、深圳实际 0；均未按配置应有的 1.0 收取 |
| 合成持仓动作单 | stop_loss、action_scenarios 均不存在 |
| 注册为 retired 的合成算法 | run_algo 仍返回 executed |
| 写入 31 条编号 0–30 的消息，再 limit=30 | 返回 0–29，最新 30 不在结果中 |
| 原失败测试注入空持仓路径 | 1 项通过；只用于确认测试前置条件缺失，不替代原始套件失败记录 |
| A2UI 逆序载入 | 缓冲清空，3 个组件注册成功 |
| A2UI 规范全名与冲突 | 规范全名查询失败，另一个包同名注册覆盖原短名 |

前端探针完整结果见 [frontend-probe-results.json](C:/Users/cvdnn/coding/a_stock_agents/output/audit-review/frontend-probe-results.json)。临时 Python 探针源文件在验证后删除，仅保留结果。

## 建议的验收顺序

1. 先处理固定分析/占位成功、治理绕过、会话历史，以及成本和风控契约。它们直接影响用户看到的结果与实际执行。
2. 修复安装与打包入口，统一默认数据路径；将上述 10 项状态按真实任务拆为已完成、部分完成、未完成、待验证。
3. 为关键调用链补集成断言：第二轮工具历史、31 条以上消息、role 修改生效、禁用/未确认技能拒绝、退役算法拒绝、相同输入跨端保本价一致、动作单三原则完整、构建后实际 ZIP 存在。
4. 隔离所有测试的持仓、会话库、配置和网络；将 live 联调显式标记并默认排除。
5. 更新 specs 的文件映射与验收证据，记录提交号、准确命令、测试计数、外部依赖及产物，再申请恢复 Production Baseline 状态。

审查未修改项目业务源码或 specs 状态；仅新增本地审查材料。历史审查中的问题没有未经复验直接列为本次缺陷。
