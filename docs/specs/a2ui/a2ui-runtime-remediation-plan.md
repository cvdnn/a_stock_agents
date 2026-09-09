# A2UI真实事件、组件注册与报告投射实施计划

> **For agentic workers:** 使用 `executing-plans`。F1先交付生产错误语义，F2依赖R/B协议，F3与F4在协议稳定后实施。

**Goal:** 所有正式分析显示真实事件结果，组件寻址/发现有确定语义，历史报告投射互不覆盖。

**Architecture:** api.js作为唯一网络入口，新a2ui_client将SSE事件映射到UIEngine；UIEngine只管理任务状态和组件生命周期。已有业务数据加载器复用，演示模式显式标识。

**Tech Stack:** Vanilla JavaScript、Node VM/Mock DOM、FastAPI SSE、浏览器运行验证。

---

覆盖 U1/U2/U3及UI、A2UI两项spec；复用 [既有前端API接入计划](C:/Users/cvdnn/coding/a_stock_agents/docs/audits/frontend-api-integration-plan.md)，不重做已正确接线的四个加载器。

## F1：分离生产结果与显式演示

**依赖：** E2。**文件：** app.js、api.js、index.html、scripts/server/config.py、scripts/server/api/market_data.py；新增 tests/test_a2ui_suite.js，扩展test_market_data_api.py。

- [ ] 在Node VM测试模拟后端失败，断言生产模式不能出现“二次金叉确认”、固定资金流/IC、模板成功提示；旧executeA2UITask应使测试失败。
- [ ] 提供服务端 `data_mode=live|demo` 和每个响应 `data_status=live|cached|synthetic|unavailable`、as_of；缓存必须带来源时间，不称最新。默认生产失败不返回Mock。
- [ ] api.js取消自动MOCK兜底，显式demo允许合成数据但页面持续显示“演示数据”。把生成曲线/模板放入测试或demo路径；股票操作符不填默认cost/shares。
- [ ] R2b/F2尚未接通的能力先呈现unavailable并保留用户输入；不因本任务阻断假成功而标对应功能完成。
- [ ] 参数化成功/空/失败/demo四种情况，运行 `node tests/test_at_operator.js`、`node tests/test_a2ui_suite.js`，提交 `fix: separate demo data from production analysis results`。

## F2：真实SSE驱动A2UI五阶段与确认按钮

**依赖：** R1、R2a、R3、R4、B2。**文件：** 新增 web/js/a2ui_client.js；修改 api.js、app.js、index.html、server/agent/events.py、react_runner.py；扩展Node和server套件。

- [ ] 冻结新增事件 `A2UIRenderEvent`：task_id、component_id、target、phase、props、data_status、as_of；target仅chat/workbench，phase为skeleton/fast/heavy/interactive/error。统一由服务端基于真实任务/工具结果生成，不要求LLM输出可执行代码。
- [ ] 将该Pydantic类加入AgentEventUnion，复用sse_format。现有content_delta和risk_card保留，risk_card使用B2兼容适配。
- [ ] 所有quick action、股票操作符、右侧追问经过AStockAPI.streamChatCompletions；移除计时器生成行情和分析结论。纯骨架可以在请求发起时立即显示，数据水合必须等待对应task事件。
- [ ] 新增 `applyA2UIEvent(event)` 分发到现有UIEngine；仅消费已知component_id/phase，未知事件显示可诊断错误；乱序事件先暂存，不向另一task写入。重复phase事件更新对应task，不重复创建图表。
- [ ] 在ToolCallCompleteEvent状态confirmation_required时展示实际技能、参数和确认按钮；按钮调用R1的confirm接口，不把confirmed传给LLM。用户取消只取消pending调用，不追加成功结果。
- [ ] 以两个不同股票的合成事件流验证不同价格/结论、任务ID隔离、SSE分片跨JSON边界、UTF-8、多行data、断开/取消/错误；SSE解析失败不得触发demo。事件测试输入示例：

```json
{"task_id":"task-a","component_id":"@a2ui/pack-astock/MarketRadar","target":"chat","phase":"fast","props":{"indices":[{"name":"synthetic-index","price":9999,"change_pct":1.25}]},"data_status":"synthetic","as_of":"2026-09-09T00:00:00Z"}
```

- [ ] 运行server/market套件与两个Node套件，提交 `feat: render a2ui from backend task events`。

## F3：组件包寻址、按需发现与自省

**依赖：** E2，接入时与F2协议一致。**发现：** U2。**文件：** ui_engine.js、components/astock.js、index.html、test_a2ui_suite.js、对应guideline/spec。

- [ ] 添加逆序载入、全名寻址、同名冲突、缺失包、加载失败和catalog结构测试。旧全名解析与短名覆盖必须先红灯。
- [ ] 对外规范名固定 `@a2ui/pack-astock/MarketRadar`；存储采用 packId+componentName，legacy astock/MarketRadar与astock:MarketRadar作为显式别名。短名唯一才可解析；碰撞抛AmbiguousComponentError并列出全名，禁止后注册者覆盖先注册者。
- [ ] 增加 `resolveComponent(identifier) -> Promise<definition>`：先本地解析，未知已登记包调用loadPack一次后重试；同包并发共享inflight Promise；失败清理inflight，允许重试。包URL来自静态登记表，不把模型传来的任意URL当script加载。
- [ ] getCatalog保留包清单与totalComponents，并给每组件补canonical fullName、propsSchema、defaultTarget、supports；数量从已注册实体计算。3个组件分别声明真实输入Schema，缺少必需数据渲染空态而非假价格。
- [ ] 更新“6个组件”验收文字为实际3个，并在spec变更日志说明当前明确组件清单；不新增空壳。
- [ ] 最小解析断言如下；完整测试运行定义window的VM上下文加载真实源码：

```javascript
assert.equal(UIEngine.getCatalog().totalComponents, 3);
assert.ok(UIEngine.getComponent('@a2ui/pack-astock/MarketRadar'));
UIEngine.registerComponentToPack('other', 'MarketRadar', otherDefinition);
assert.throws(() => UIEngine.getComponent('MarketRadar'), /ambiguous/i);
assert.ok(UIEngine.getComponent('@a2ui/pack-astock/MarketRadar'));
```

- [ ] 测试加载失败不污染全局索引、未知包不可加载、重复声明幂等；运行两个Node套件，通过后提交 `fix: enforce a2ui namespace and discovery contracts`。

## F4：真实图表、完整卡片及独立投射

**依赖：** F2/F3、B3。**发现：** U1/U3、B3。**文件：** ui_engine.js、components/astock.js、app.js、charts.js、style.css、test_a2ui_suite.js。

- [ ] 展开视图/Canvas从props读取indices/klines，删除默认3426等曲线数据；输入9999必须在展开内容中体现，输入不同K线必须传入图表渲染器。空序列显示暂无数据。
- [ ] UIEngine任务Map保存task_id、数据快照、组件状态、目标容器、版本；project动作按task_id重建或复用独立节点。关闭标签执行onUnmount，回收listener/canvas/observer，不删除聊天原卡。
- [ ] report-a→report-b→report-a测试比较内容仍为A；流式更新A不能改B。重新投射A保持相同数据版本，不能仅改标题。
- [ ] 布局预留明确slot尺寸；heavy在requestAnimationFrame绘制，ResizeObserver只调整图形、不改变外层占位。长文本内部滚动，资源加载失败保持slot尺寸。B3紧凑卡保留全部三原则摘要。
- [ ] 用浏览器测试桌面1344×900和窄屏390×844，记录console错误、键盘操作、滚动区、慢速事件与两报告切换。使用PerformanceObserver记录本任务渲染段layout-shift，排除用户输入导致的偏移；按照现guideline验证CLS=0，未达到时如实记录，不能改阈值掩盖失败。
- [ ] 截图和指标放统一output/reports/验收目录；Node通过不能替代浏览器证据。通过后提交 `fix: preserve independent report views and data driven charts`。

**完成门槛：** 三项UI/A2UI spec逐项验证；演示渲染成功不算真实API/Agent接线，HTML字符串检查不算交互和CLS验收。
