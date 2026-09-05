# A-Stock Agents 测试用例架构与回归测试规范

本目录包含了 A-Stock Agents 项目的**全量功能回归测试套件**。所有用例均基于项目最新架构（v3.0.0）编写，统一遵循**无外部网络强依赖（Mock 隔离）**、**秒级运行**与**高覆盖率**的设计原则。

---

## 一、核心测试规约（必须严格遵守）

### 1. 规约一：功能修改，测试先行（Regression-First / TDD）
> **每次功能修改、新增或重构，必须先升级/修改对应的测试用例，用于项目功能回归测试。**

- **修改现有功能契约时**：先定位到对应的领域测试套件（如 `test_models_suite.py` 或 `test_strategy_suite.py`），更新或新增契约断言，验证其在未修改代码前按预期失败，再编写/修改业务代码直到全部通过。
- **新增模块或子命令时**：必须在相应测试套件中补全参数校验、边界防护与返回类型断言。
- **合并提交前**：本地必须全绿通过 `pytest`，确保 100% 通过且零回归。

### 2. 规约二：临时优化用例生命周期规约（Ephemeral Fix Tests Rule）
> **注意：针对某次特定优化的测试用例仅作为临时用例验证功能后便删除。**

- **临时用例定位**：在问题诊断、性能调优或缺陷排查过程中，开发者编写的单点验证脚本或临时测试（如 `test_tmp_*.py` 或置于 `scratch/` 目录中），其生命周期仅限于「当前单次优化的功能验证」。
- **即测即删要求**：
  1. 临时用例在当前优化验证通过后，**必须立即删除**，严禁以 `test_p0_fixes.py`、`test_p1_fixes.py` 等特定审查阶段命名的临时文件长期滞留在仓库中。
  2. 针对该次优化所总结出的**通用防线、安全边界与核心契约**，应当直接合并沉淀到对应的领域标准套件（如数据层、模型层、策略层等）中，保持标准套件持续健壮，同时避免临时补丁文件无序膨胀。

---

## 二、测试套件分层架构图

当前测试套件采用与 `core/` 架构完全对齐的六大领域分层：

| 测试套件文件 | 覆盖子系统 / 模块 | 核心回归验证范围 |
|---|---|---|
| [`test_commands_suite.py`](file:///Users/handy/workon/a_stock_agents/tests/test_commands_suite.py) | `core/commands/` & `core/cli.py` | 32 个模块化子命令注册、参数解析分发、向后兼容性与 `skills/` forwarder 委托转发 |
| [`test_data_suite.py`](file:///Users/handy/workon/a_stock_agents/tests/test_data_suite.py) | `core/data/` & `core/config.py` | `QuoteDict` 代码为主键多别名索引、防注入白名单、市场前缀推导、费率常量 SSOT |
| [`test_indicators.py`](file:///Users/handy/workon/a_stock_agents/tests/test_indicators.py) | `core/indicators/` | 技术指标计算（MA/MACD/KDJ/RSI/BOLL/ATR）、缺口回补方向判断、短序列边界保护 |
| [`test_models_suite.py`](file:///Users/handy/workon/a_stock_agents/tests/test_models_suite.py) | `core/models/` | 单调趋势评分、缺失维度百分制归一化、板块 TOP10 布尔匹配、中位数填补、指数区分 |
| [`test_strategy_suite.py`](file:///Users/handy/workon/a_stock_agents/tests/test_strategy_suite.py) | `core/strategy/` | `position_manager` 纯数据服务解耦、动作引擎真实契约、网格中轴、顶背离算法、解套分析 |
| [`test_paper_trading_suite.py`](file:///Users/handy/workon/a_stock_agents/tests/test_paper_trading_suite.py) | `core/paper_trading/` | 多标的回测引擎、主板10%/双创20%/北交30%涨跌停封板拦截、T+1 状态机、回测指标防御 |
| [`test_security_suite.py`](file:///Users/handy/workon/a_stock_agents/tests/test_security_suite.py) | `core/reporting/` & `bin/` | HTML 报告 XSS 转义防御、更新解压 Zip Slip 路径穿越防护、敏感凭据脱敏保护 |
| [`test_monitor.py`](file:///Users/handy/workon/a_stock_agents/tests/test_monitor.py) | `core/monitor/` | 交易日历网关（开盘/闭市/周末状态机）、状态去重存储、桌面通知降级 |
| [`test_pool_schema.py`](file:///Users/handy/workon/a_stock_agents/tests/test_pool_schema.py) | `core/strategy/pool_schema.py` | 股票池 CSV 字段契约、空数据行写入防护、板块准入与黑名单过滤规则 |
| [`test_custom_output.py`](file:///Users/handy/workon/a_stock_agents/tests/test_custom_output.py) | `core/config.py` | 自定义输出目录隔离、环境变量覆盖（`ASTOCK_OUTPUT_DIR`）与初始模板生成 |

---

## 三、运行回归测试

### 1. 运行全量测试（基线测试）
```bash
pytest -v
```

### 2. 运行指定领域套件
```bash
# 策略与风控回归
pytest tests/test_strategy_suite.py -v

# 模型与打分回归
pytest tests/test_models_suite.py -v

# 命令行与分发回归
pytest tests/test_commands_suite.py -v

# 模拟盘与回测回归
pytest tests/test_paper_trading_suite.py -v
```

### 3. 查看测试覆盖率报告（需 pytest-cov）
```bash
pytest --cov=core --cov=bin tests/
```
