# A-Stock Agents 回归测试与质量保证指南

> 版本：v3.0.0  
> 适用：工程核心开发、代码贡献者、测试与持续集成（CI）

---

## 一、测试核心哲学

A-Stock Agents 作为涉及实盘模拟交易、选股量化与策略执行的高确定性系统，测试套件是保障系统正确性、安全性和稳定性的第一道防线。项目确立了两条不可动摇的测试铁律：

### 1. 规约一：功能修改，测试先行（Regression-First / TDD）
**每次功能修改、功能重构或新增特性前，必须先升级修改测试用例，用于项目功能回归测试。**

- **测试先行**：修改已有接口或增加业务逻辑时，必须先在对应模块的领域回归测试套件（如 `tests/test_*_suite.py`）中更新预期输入输出断言与异常分支防护。
- **红灯到绿灯**：先观察用例在旧逻辑下失败（Red），再实现新逻辑使测试全部通过（Green）。
- **零回归交付**：任何 Git 提交（Commit）前，必须运行全量回归测试 `pytest`，确保 100% 通过且无警告。

### 2. 规约二：临时优化用例生命周期规约（Ephemeral Fix Tests Rule）
**针对某次优化的测试用例仅作为临时用例验证功能后便删除。**

- **临时用例定位**：在代码审查（Code Review）、线上排障、性能分析或单次微调时，临时编写的排查用例属于「探索性临时验证代码」。
- **即测即删要求**：
  1. 临时排查用例应当编写在 `scratch/` 目录下或以临时脚本执行，在验证当前优化生效后，**必须立即删除**。
  2. 严禁以临时缺陷编号或任务名（例如 `test_p0_fixes.py`、`test_p1_fixes.py` 等）作为文件名永久堆积在 `tests/` 根目录。
  3. 若该次优化沉淀出了通用的边界测试、契约防线或核心回归用例，必须将断言提炼整合至对应的**标准领域测试套件**（如 `test_data_suite.py`、`test_models_suite.py` 等）中，保持项目测试结构清晰有序。

---

## 二、测试套件分层体系

项目测试套件严格映射系统架构层级，所有用例均采用本地 Mock 或合成数据集，杜绝外部网络环境或接口限频对回归测试造成的干扰。

```
tests/
├── test_commands_suite.py      # 命令行调度层（32子命令注册、参数解析、forwarder委托）
├── test_data_suite.py          # 数据与配置基础设施（QuoteDict、注入防御、SSOT规范化）
├── test_indicators.py          # 技术指标引擎（MA/MACD/KDJ/RSI/BOLL/ATR、缺口与短序列）
├── test_models_suite.py        # 选股与多因子模型（多因子单调评分、归一化、中位数填补）
├── test_strategy_suite.py      # 实战策略与风控（动作单契约、仓位数据解耦、网格中轴、顶背离）
├── test_paper_trading_suite.py # 模拟盘与回测（多标的回测、涨跌停封板过滤、T+1状态机）
├── test_security_suite.py      # 安全与运维防护（HTML报告防XSS、更新解压防Zip Slip、凭据脱敏）
├── test_monitor.py             # 监控守护（交易日历状态机、状态去重持久化、通知降级）
├── test_pool_schema.py         # 股票池Schema（CSV写入参数倒置保护、板块黑名单）
├── test_custom_output.py       # 运行环境隔离（ASTOCK_OUTPUT_DIR 自定义目录与模板初始化）
└── README.md                   # 测试目录规约说明文档
```

---

## 三、常用测试命令

### 1. 全量回归测试
```bash
# 执行全量单元测试与回归测试（输出详细结果）
pytest -v

# 遇到首个失败立即中断（快速调试）
pytest -x
```

### 2. 按领域模块运行
```bash
# 验证数据桥与配置
pytest tests/test_data_suite.py -v

# 验证选股模型与多因子
pytest tests/test_models_suite.py -v

# 验证策略动作与风控
pytest tests/test_strategy_suite.py -v

# 验证模拟盘与回测引擎
pytest tests/test_paper_trading_suite.py -v

# 验证系统安全防护
pytest tests/test_security_suite.py -v
```

---

## 四、贡献代码检查清单（Checklist）

在发起 PR 或推送提交前，请完成以下自检：
- [ ] 是否在修改业务代码前，先行在对应的 `tests/test_*_suite.py` 中更新了测试用例？
- [ ] 是否未在 `tests/` 根目录残留任何针对单次优化的临时测试文件？
- [ ] 本地运行 `pytest` 是否全绿通过（100% Passed）？
- [ ] 新增的测试用例是否使用了本地 Mock 或合成数据，避免产生外部网络强依赖？
- [ ] 针对异常处理、边界条件（0值、空数据、越界、注入字符）是否具备测试覆盖？
