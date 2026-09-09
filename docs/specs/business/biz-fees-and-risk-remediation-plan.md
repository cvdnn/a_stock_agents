# 费用精算与三原则动作单实施计划

> **For agentic workers:** 使用 `executing-plans` 按 B1→B2→B3 执行；先写领域断言，后接入 API/HTML/UI。

**Goal:** 相同成本、数量和配置在 CLI、模拟盘、API、HTML、前端得到相同费用及最低保本价，并输出完整三原则。

**Architecture:** 核心新增纯计算模块作为费率与保本计算唯一实现；ExecutionActionEngine 保留原入口并委托；统一动作单结构通过边界适配兼容旧字段。

**Tech Stack:** Python Decimal/dataclass、pytest、FastAPI/Pydantic、原生 JavaScript、Node。

---

依赖 E1/E2。关联 SPEC-BIZ-001/002/003、SPEC-UI-001。使用仓库规则做软件契约，不在本任务更新外部市场法规或改变策略目标。

## B1：统一费用和最低保本价

**发现：** B1、B2。**文件：** 新增 `scripts/core/strategy/trading_costs.py`；修改 `scripts/core/config.py`、`scripts/core/strategy/execution_action_engine.py`、`scripts/core/paper_trading/engine.py`、`scripts/core/strategy/risk_position_manager.py`、实际回测成本调用处；扩展 tests/test_strategy_suite.py、test_paper_trading_suite.py、test_data_suite.py。

- [ ] 新增配置覆盖及沪深计费红灯测试：成交额10000、transfer_fee_rate=0.0001时上海/深圳均应1.00，不能仍是0.10/0；测试使用内存cfg，不修改正式config。
- [ ] 冻结新接口：`calculate_trade_fees(amount, side, market_cfg) -> dict` 返回 commission/stamp_tax/transfer_fee/total；`calculate_breakeven(cost, shares, market_cfg) -> float` 返回可交易分位价格。按 Decimal(str(value)) 处理金额，默认率取共享配置；买入无印花税，卖出有，沪深同口径。调用方不再自行计费或重复 round。
- [ ] 将手续费结算精度统一写入该模块：金额字段以分结算，使用 Decimal ROUND_HALF_UP；最低佣金先比较后结算。该精度选择在 broker-commission-rules 中明确，避免 Python round 与 JS Math.round 产生分歧。保本价格只允许 ROUND_CEILING，不提供关闭进位的生产开关。
- [ ] 先求理论上界，再调用同一个手续费函数验证卖出净收入，逐分检查直到覆盖实际买入总成本；同时向下检查一分不能保本，保证返回“最低”而不仅“足够”。校验正数有限成本、正整数shares、非负费率/最低佣金，费率总和不能使净收入非递增；无效输入抛 ValueError，由CLI/API适配成结构化错误。
- [ ] 保留 `ExecutionActionEngine.calc_min_breakeven_price` 作为委托入口。示例委托与核心测试：

```python
@classmethod
def calc_min_breakeven_price(cls, cost, shares=1000, market_cfg=None):
    from core.strategy.trading_costs import calculate_breakeven
    return calculate_breakeven(cost, shares, market_cfg or get_market_config())

def test_breakeven_golden_and_minimum():
    from core.strategy.trading_costs import calculate_breakeven
    cfg = dict(commission_rate=0.00025, min_commission=5.0,
               tax_rate_sell=0.0005, transfer_fee_rate=0.00001)
    assert calculate_breakeven(1000, 100, cfg) == 1001.03
    assert calculate_breakeven(6.1411, 5000, cfg) == 6.15
```

- [ ] 模拟撮合、回测、做T统一调用共享费用函数；交易记录保存当笔配置快照/版本，变更配置只影响下一笔，不追溯改写历史成交。补佣金门槛前后、免五、低价/大额/非整百持仓、零/负/NaN/Infinity测试。
- [ ] `save_market_config` 成功后同进程下一次读取立即更新；常驻服务需检测配置文件版本/mtime重新载入，CLI跨进程修改不得等重启。读取失败不以旧配置冒充新配置，输出明确状态。
- [ ] 运行 `python -m pytest tests/test_strategy_suite.py tests/test_paper_trading_suite.py tests/test_data_suite.py -q`。通过后提交 `fix: unify trading fees and minimum breakeven calculation`。

## B2：统一动作单结构

**发现：** B3。**文件：** 新增 `scripts/core/strategy/action_contract.py`；修改 execution_action_engine.py、commands/strategy_cmds.py、server/agent/tools.py、server/agent/events.py、server/models.py；扩展 test_strategy_suite.py、test_commands_suite.py、test_server_suite.py。

- [ ] 增加 `action plan` JSON契约红灯测试，DataBridge 使用stub，强制检查 stop_loss 与 action_scenarios 的具体键，不只检查 breakeven>=cost。
- [ ] 定义 `build_risk_contract(cost, shares, market_cfg, *, quote=None, available_shares=None) -> dict`。保本价复用B1，止损按成本0.97/0.95/0.92，并标明挂单分位。ATR/MA止损作为 technical_stop 独立输出，不覆盖三条成本阶梯。
- [ ] 固定输出结构（字段和值均来自输入/计算，不以标的默认值补空）：

```json
{
  "cost": 10.0,
  "shares": 1000,
  "breakeven_price": 10.02,
  "stop_loss": {"T0": 9.70, "T1": 9.50, "T2": 9.20},
  "action_scenarios": {
    "open_surge": {"trigger": "开盘高于昨收且价格达到保本价", "action": "按可卖数量执行计划减仓", "status": "pending_data"},
    "narrow_range": {"trigger": "价格高于T0且日内振幅不超过ATR", "action": "观察边界，不追加未确认仓位", "status": "pending_data"},
    "plunge": {"trigger": "依次跌破T0/T1/T2", "action": "警戒/减仓50%/退出", "status": "pending_data"}
  }
}
```

- [ ] status 由 quote/ATR 等必需数据决定；数据缺失可输出条件式动作，但不得宣称触发。未知持仓成本时 breakeven/stop_loss 为 null，状态为 requires_position，不猜320元/1000股；API专用试算要求有效成本数量，否则422。
- [ ] 卖出建议受 available_shares/T+1/可成交限制约束：触及阈值仍显示风险等级，但不可执行时标 execution_blocked 和原因，不能虚报已经减仓/退出。T1计划数量为持仓50%，按可交易数量处理，不能为满足50%生成负数或超过可卖量。
- [ ] CLI保留action_items，追加上述结构；API/SSE在适配层兼容 stop_t0/stop_t1/stop_t2/actions，值必须来自统一结构。`--json` 的提示写stderr，stdout必须可被json.loads完整解析。
- [ ] 参数化测试正常/触发/缺行情/缺成本/T+1/不可成交，执行三套件并提交 `feat: expose a complete shared trading action contract`。

## B3：API、前端和HTML消费同一结果

**发现：** B2、B3、D1。**依赖：** B1/B2、R1。**文件：** 新增 `scripts/server/api/trading_costs.py`；修改 server/app.py、server/models.py、web/js/api.js、components/astock.js、core/reporting/report_generator.py；扩展 test_server_suite.py、test_security_suite.py、新增test_a2ui_suite.js中的费用部分。

- [ ] 新增 POST `/api/trading/breakeven`，输入 cost/shares，使用服务端当前配置；返回 breakeven_price、stop_loss、market_config_version。该接口是纯计算，不拉行情、不写持仓。core纯模块不得导入FastAPI。
- [ ] api.js 新增 `calculateBreakeven({cost,shares,signal})`，滑块请求防抖并取消旧请求；只接受最新请求序号响应。前端卸载时取消请求，不使用硬编码费率/Math.ceil公式兜底。失败显示无法计算，显式demo可用已标识合成响应。
- [ ] astock.js 紧凑卡同时展示最低保本、T0/T1/T2和三场景摘要；展开视图展示同一对象的详细触发/动作/限制。后端风险结果发生变更后旧卡显示快照版本，不悄悄改写已归档报告。
- [ ] 在真实 report_generator.py 中补 `render_positions_table(positions)`，10列固定为：代码、名称、数量、最低保本卖出价、成本、现价、盈亏率、T0、T1、T2；场景在每行关联折叠区域。所有单元格转义；持仓未知项显示未提供。
- [ ] 同一输入向CLI/API/HTML/UI送入并核对1001.03；费率变更到免五后各端一致。测试表格列数、保本价第4列、三阶梯/场景存在、错误响应无旧成功值、恶意股票名称已转义。
- [ ] 运行 Python业务/server/security套件和 `node tests/test_a2ui_suite.js`；交接F2/F4真实浏览器验证，提交 `feat: consume shared risk results across api reports and ui`。

**完成门槛：** 不只单个黄金样例通过；所有收费调用、配置热更新、边界数据、CLI/API/HTML/UI一致性都通过后，BIZ-001/002/003分别恢复基线。
