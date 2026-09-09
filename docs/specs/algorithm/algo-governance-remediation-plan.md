# 算法准入、执行门禁与退役实施计划

> **For agentic workers:** 使用 `executing-plans` 按 G1→G2→G3 执行；单元测试通过与算法生产准入分别记录。

**Goal:** 让生命周期与质量证据真正约束生产调用，阻止未验收或已退役算法继续产生正式结果。

**Architecture:** 注册表保存元数据并检查执行上下文，质量门禁生成可持久化证据，生命周期管理器验证证据后转换状态；生产入口与盘后任务调用同一治理服务。

**Tech Stack:** Python、SQLite、pytest、现有AlgorithmQualityGate/AlgorithmLifecycleManager/AlgoRegistry。

---

依赖E1/E2。发现G1；对应SPEC-ALGO-001。禁止复制模型到新版本文件，也不重写既有IC、回测或撮合算法。

## G1：区分研究解析与生产执行

**文件：** 修改 `scripts/core/models/registry.py`、`base_algorithm.py`、`monitor_governance.py`、`scripts/core/commands/model_cmds.py`、`strategy_cmds.py`、`scripts/server/agent/tools.py`；扩展 `tests/test_algo_registry.py`、`test_algo_monitoring.py`、`test_commands_suite.py`。

- [ ] 将审查探针变成稳定测试：注册retired的函数，默认run_algo必须拒绝；旧实现会返回executed，先观察红灯。
- [ ] 注册默认stage改research；显式注册production不能只接受枚举值，必须由G2证据恢复状态。元数据解析resolve_target保留研究用途；生产调度新增 `assert_execution_allowed(name, execution_context)`。
- [ ] `run_algo`、factory get及生产命令入口明确execution_context，默认production；研究/回测入口显式research/backtest，不能由模型参数自行切换上下文。上下文规则如下：

| 状态 | research/backtest | staging | production |
|---|---|---|---|
| research/backtested | 可用于实验并标识非生产 | 仅backtested且G2合格 | 拒绝 |
| staging | 可 | 可 | 拒绝 |
| production | 可 | 可 | 证据有效且版本一致时可 |
| deprecated/retired | 仅明确的离线复现入口可加载 | 拒绝 | 拒绝 |

- [ ] 引入 `AlgorithmExecutionDenied` 异常，由CLI/API转成结构化错误。禁止get_target/别名直接作为生产旁路；逐一检查model_cmds、strategy_cmds和server工具，顶层生产算法先过门禁，内部纯数学帮助函数不反复建治理上下文。
- [ ] 维护内置算法清单，从实际注册枚举得出数量并与指南逐项对应；不批量写production来恢复旧测试。研究兼容用例改为显式研究模式，生产用例注入真实格式的测试证据。
- [ ] 在tests/test_algo_registry.py增加以下类型断言；新异常在registry.py定义并导出：

```python
def test_retired_algorithm_denied_in_production():
    import pytest
    from core.models.registry import AlgoRegistry, AlgorithmExecutionDenied
    from core.models.base_algorithm import AlgorithmLifecycleStage
    AlgoRegistry.register("test_retired", "", lambda: "executed",
                          is_class=False, stage=AlgorithmLifecycleStage.RETIRED)
    with pytest.raises(AlgorithmExecutionDenied):
        AlgoRegistry.run_algo("test_retired")
```

- [ ] 运行 `python -m pytest tests/test_algo_registry.py tests/test_algo_monitoring.py tests/test_commands_suite.py -q`；提交 `fix: enforce lifecycle restrictions at production dispatch`。

## G2：证据完整性、持久化与受控晋级

**文件：** 新增 `scripts/core/models/governance_store.py`、`config/algo_governance.yaml`；修改quality_gates.py、monitor_governance.py、registry.py；扩展test_quality_gates.py、test_algo_monitoring.py。

- [ ] 新增无输入证据测试：`audit_algorithm("name")` 不能因为没执行检查而返回100分passed；缺必要数据返回incomplete，并列出missing_checks。
- [ ] 给QualityGateStatus增加INCOMPLETE，给QualityGateReport增加 `missing_checks: List[str]` 和 `checked_profile: str` 并纳入to_dict；按算法类别声明证据profile。指标/度量要求确定性正确性及边界测试；预测/评分/策略要求样本外证据；撮合/风控要求T+1/涨跌停/费用契约。某检查不适用必须在配置profile和指南中明确原因，不能因没有数据自动跳过。
- [ ] governance_store SQLite位于统一OUTPUT_CACHE_DIR/algo_governance.db，三张表：algorithm_state（算法/版本/阶段）、gate_evidence（门禁/结果/输入数据窗口/源码版本/配置版本/指标/缺失项/创建时间）、lifecycle_events（旧状态/新状态/证据ID/原因/时间）。测试注入临时路径。
- [ ] `record_gate_evidence(report, identity)` 保存实际检查结果；identity包含algo_id、source_hash、config_hash、data_start/data_end、synthetic标记。测试/合成数据证据不能被生产晋级采纳；源码或关键配置变化使相关证据失效。
- [ ] transition_stage仅允许research→backtested→staging→production，及生产退役链；每次晋级读取本版本必要门禁通过证据。强制research→production、失败/缺失/过期证据返回错误，不改变原stage。
- [ ] 采用指南现有标准：G2年化Sharpe≥1.2、最大回撤≤18%、OOS衰减≤35%；G3至少20交易日、成交率100%、滑点偏差≤20%。所有单位在配置中固定为比例或百分数，避免18与0.18混用。未满足或没有样本就不晋级。
- [ ] 进程重启后恢复stage和有效证据；同一迁移重复请求幂等；事务失败保持状态与审计一致。测试示例目标：

```python
assert incomplete_report.status.value == "incomplete"
assert "G2.oos" in incomplete_report.missing_checks
# 缺少有效G3证据的staging算法，晋级必须失败，状态不变。
assert metadata.stage.value == "staging"
```

- [ ] 运行 `python -m pytest tests/test_quality_gates.py tests/test_algo_monitoring.py tests/test_algo_registry.py -q`；提交 `feat: persist gate evidence and validate lifecycle promotion`。

## G3：接入真实观察与熔断路径

**文件：** 修改monitor_governance.py、实际生产model/strategy命令、`scripts/server/tasks/task_manager.py`、core/cli.py；扩展test_algo_monitoring.py、test_commands_suite.py；更新算法验收台账。

- [ ] 新增统一CLI入口 `astock algo audit|promote|monitor --json`，在已有cli/commands结构注册；业务实现留在models，不复制到脚本。audit使用现有数据/回测结果文件，禁止临时网络爬虫。
- [ ] 生产入口在计算前调用G1，在结果/交易记录生成后写观察记录。盘后monitor读取连续交易日指标，调用现有IC计算和回撤逻辑；任务调度只调用这条统一入口，重复调度按algo_id+trading_date去重。
- [ ] 对齐指南：20日IC均值转负持续5日预警；连续两周负IC或近30交易日回撤>基线1.5倍触发G4。用交易日历计数，不用自然日或一次IC阈值替代持续条件；历史不足返回insufficient_history。
- [ ] G3跟踪至少20交易日；涨跌停/T+1拒单不能被记录为成交以凑100%。若指南门槛未达到，记录实际比例并延长staging，禁止调整分母掩盖失败。
- [ ] G4触发时原子更新为deprecated并审计；下一次生产调用通过G1被拒绝。只停止新的算法调度，不自动平仓用户持仓、不删除历史结果。
- [ ] 合成连续数据测试触发→状态持久化→重启→下一次调用拒绝；数据不足、重复日、缺交易日、数据修订均有断言。真实20日观察记录单独存档，不把合成序列算作已经完成观察期。
- [ ] 运行算法/commands套件及默认回归，提交 `feat: connect production monitoring to retirement enforcement`。

**完成门槛：** 代码接线、失败传播和合成状态机可在实现阶段完成；每个正式算法仍需自己的真实G1/G2/G3证据。无真实观察期的算法保持staging，SPEC-ALGO-001相关验收项保持待验证。

**回滚：** 回滚实现不能自动把deprecated改production。治理状态与证据备份后只做兼容迁移；需要恢复生产时重新满足晋级条件，不能删除治理库绕过门禁。
