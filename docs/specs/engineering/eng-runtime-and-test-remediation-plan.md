# 运行隔离、测试与交付底座实施计划

> **For agentic workers:** 使用 `executing-plans` 按 E1→E2→E3→E4 顺序执行；D1 与 E2 同批，D2 在所有子计划后执行。步骤使用复选框跟踪。

**Goal:** 默认运行与测试不依赖用户全局目录、正式数据库或网络，安装和打包生成可验证交付物。

**Architecture:** 以 core.config 为路径与配置入口；测试在模块导入前建立隔离环境；安装器只装配，pack.py 只调用统一 main。验收记录与历史审计分离。

**Tech Stack:** Python、pytest、SQLite、PowerShell、Bash、zipfile。

---

总计划：[整改总计划](C:/Users/cvdnn/coding/a_stock_agents/docs/specs/engineering/eng-remediation-plan.md)。所有路径以仓库根为基准；Windows 命令使用项目虚拟环境，不安装全局依赖。

## E1：统一配置及私有数据路径

**依赖：** 无。**发现：** E3、T1。

**文件：** 修改 `scripts/core/config.py`、`scripts/server/config.py`、`scripts/core/paper_trading/paper_trading_runtime.py`；新增 `tests/test_workspace_suite.py`，扩展 `tests/test_custom_output.py`。

- [ ] 在 test_workspace_suite.py 增加子进程测试，设置临时 `A_STOCK_OUTPUT_DIR` 后导入 core、server、paper runtime，断言三者的默认数据路径全部在该目录内；显式 A_STOCK_DB_PATH/A_SHARE_PAPER_TRADING_HOME 仍优先。
- [ ] 执行 `& .\.venv\Scripts\python.exe -m pytest tests/test_workspace_suite.py -q`，确认 server/paper 默认路径断言在旧代码失败。本阶段新测试必须自己在子进程启动前设置临时配置/输出，尚不执行现有完整套件。
- [ ] 增加 `A_STOCK_CONFIG_PATH` 作为完整配置文件覆盖；load_config/save_market_config 都使用同一 CONFIG_FILE。默认配置路径保持 `PROJECT_ROOT/config/config.yaml`。非法 YAML/写入失败返回错误，不覆盖整个文件为默认配置。核心规则如下：

```python
CONFIG_FILE = Path(os.environ.get("A_STOCK_CONFIG_PATH", str(CONFIG_DIR / "config.yaml"))).resolve()
# server/config.py，显式 A_STOCK_DB_PATH 仍由 load_server_settings 优先处理
from core.config import OUTPUT_CACHE_DIR
DEFAULT_DB_PATH = OUTPUT_CACHE_DIR / "chats.db"
# paper_trading_runtime.py 的无显式覆盖分支
from core.config import OUTPUT_CACHE_DIR
def get_app_data_dir() -> Path:
    custom = os.environ.get("A_SHARE_PAPER_TRADING_HOME")
    return Path(custom).expanduser().resolve() if custom else OUTPUT_CACHE_DIR / "paper_trading"
```

- [ ] 初始化只生成空表头；示例 CSV 保持 `.example`，不自动作为真实持仓。测试用配置由测试构造，不从用户 output 模板复制内容。
- [ ] 为自定义路径测试添加配置更新、失败不覆盖、空初始化、显式覆盖四类断言；目标：无任何用户全局目录 mkdir，原配置和持仓文件字节不变。
- [ ] 先运行上述受控新增测试；E1/E2作为同一个初始交付批次，在E2完成全量隔离后才执行全量回归并提交，避免提前运行会访问真实服务的旧测试。

## E2：建立默认离线且确定的回归入口

**依赖：** E1。**发现：** T1。**文件：** 修改 `tests/conftest.py`、`pyproject.toml`、`tests/test_decoupling_suite.py`、`tests/test_server_suite.py`、`tests/test_market_data_api.py`、`tests/test_governance_suite.py`、`tests/test_live_server_e2e.py`；扩展 test_workspace_suite.py。

- [ ] 将 115 项审查范围及其 114/1 结果作为历史记录。先新增测试证明“无代码、无持仓”用例在显式空 fixture 下通过，而“唯一持仓”单列测试采用 stub DataBridge，不能访问网络。
- [ ] 在 pytest_configure 阶段、任何业务模块导入前创建本轮临时根目录，设置 E1 的四个环境变量和 `A_STOCK_DEFAULT_MODEL=mock`。在该目录写合成 config.yaml 和空持仓表头；会话退出只清理本轮创建的目录。子进程继承同一隔离环境。
- [ ] 每个测试建立/重置 registry、auditor、provider、数据库状态。修复 auditor 的写/读均使用同一个注入的 db_path；不只替换一个查询方法。
- [ ] 默认网络防线在测试启动早期封锁 socket 连接及真实 subprocess 网络执行；HTTPX 使用 MockTransport、FastAPI 使用 TestClient。遇到被阻断调用要改相应 fixture，不把它转成忽略异常。核心断言示例：

```python
def test_missing_code_never_requests_market(monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace
    from core.config import OUTPUT_POOLS_DIR
    from core.data.data_bridge import DataBridge
    from core.commands.strategy_cmds import cmd_action_plan
    monkeypatch.setattr("core.config.OUTPUT_POOLS_DIR", tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected market request")
    monkeypatch.setattr(DataBridge, "get_realtime_quote", forbidden)
    cmd_action_plan(SimpleNamespace(code=None, opt_code=None, cost=None, shares=None, count=120))
    assert "请指定股票代码" in capsys.readouterr().out
```

- [ ] 增加 pytest `live` marker 和 `--run-live` 参数：默认 collection 时 skip live；仅显式参数允许联调。live 测试启动独立服务/临时 DB，使用参数化端口，不默认连接用户 6300 服务。外部模型和行情另标 external，且不随 --run-live 自动启用。
- [ ] 清点 `.agents/skills/**/test*.py` 并将通用断言迁入 tests 的对应领域套件，移除重复用例后将 testpaths 固定为 tests；保留清点表，不能因改 testpaths 丢覆盖。
- [ ] 运行两遍默认测试：一次正常顺序，一次使用反向文件顺序生成的明确参数列表；确认结果一致、没有外部连接、没有 output 正式文件变更。E1/E2合并提交 `fix: isolate runtime paths and default regression tests`，这是总计划单任务提交规则的首批依赖例外。

**验收命令：** `& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`。预期零失败，live/external 的跳过数及理由明确；不承诺固定测试数量，记录实际收集数。

## E3：修复安装与打包入口

**依赖：** E2。**发现：** E1、E2。

**文件：** 修改 `install.ps1`、`install.sh`、`bin/pack.py`、`scripts/tools/pack.py`、`verify.py`；测试落在 `tests/test_commands_suite.py`、`tests/test_security_suite.py`、`tests/test_workspace_suite.py`。

- [ ] 在临时最小仓库中通过 subprocess 调用 `bin/pack.py --output <临时路径>`，先断言旧代码退出 0 却无 ZIP，形成红灯。
- [ ] 为 scripts/tools/pack.py 抽出 `main(argv=None) -> int`，原参数解析全部移入 main；两个 __main__ 均 `raise SystemExit(main())`。bin/pack.py 只转发，不再按 hasattr 静默跳过。验收断言：

```python
assert completed.returncode == 0
assert archive.is_file()
with zipfile.ZipFile(archive) as zf:
    names = zf.namelist()
    assert "a_stock_agents/scripts/core/cli.py" in names
    assert not any("/output/" in n or "/.venv/" in n for n in names)
```

- [ ] 排除 `.env`、`.env.*`、SQLite及其 WAL/SHM、缓存、备份和自定义输出根；用假凭据文件/假数据库验证，禁止打包真实用户仓库来试泄露防线。输出 ZIP 必须在遍历排除范围外或明确排除自身。
- [ ] 两个安装器改为 scripts/core/workspace.py，Windows 每次外部命令后检查 LASTEXITCODE。统一可测试的失败传播片段：

```powershell
& $VenvPy (Join-Path $ProjectRoot 'scripts\core\workspace.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPy (Join-Path $ProjectRoot 'verify.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

- [ ] verify.py 默认执行离线自检；网络探针仅显式 --live。移除“文件含 SSOT 标记/至少50转发器即通过”等伪验收，改为真实入口调用和清单映射检查。
- [ ] 使用 stub Python/pip 在安装脚本测试中模拟每个步骤失败，确认不打印成功。Windows 实际新检出验收与 Linux/macOS 验收分别记录，当前平台未测不能代签。
- [ ] 测试通过后提交 `fix: restore portable install and packaging entry points`。

## E4：清理路径和兼容层欠账

**依赖：** E1、E3。**发现：** E3。

**文件：** 修改 `scripts/core/data/data_layer.py`、`scripts/core/data/fetch_realtime.py`、`scripts/core/multi_agent/ta_analyze.py`、`scripts/core/multi_agent/ta_orchestrator.py`、`scripts/core/reporting/investment_report.py`、`.agents/skills/` 中实际匹配的 setup/monitor 模板、`.gitignore`；测试 test_workspace_suite.py。

- [ ] 用 `rg -n 'Path.home|expanduser|\.AI-Platform|/mnt/c/Users' scripts .agents/skills -g '*.py' -g '*.sh'` 清点，分类为默认写入、默认隐式读取、显式用户路径、历史文档。测试只对前三类运行路径施加正确规则，避免字符串一刀切。
- [ ] 默认写入全部使用 core.config，模板接受注入 state_path；取消从全局环境文件自动取凭据。显式自定义路径仍支持，旧布局通过明确 legacy 选项读取，不自动复制或删除用户文件。
- [ ] 核对 `git ls-files cache` 三个 DB。仅解除这三条确认过的索引跟踪，工作区文件保留，记录文件存在性和字节哈希不变；不做递归删除和历史清洗。
- [ ] 将受维护同名薄转发器登记为有 Sunset 条件的兼容入口，验证它们转发到唯一实现；不新增影子算法。naming-conventions 记录兼容例外而非要求永久50个文件。
- [ ] 运行路径/打包/命令回归后提交 `refactor: confine legacy runtime paths to workspace`。

## D1：实施前校准真实状态

**依赖：** 阅读总计划。**文件：** `docs/specs/README.md`、10 项已标基线的 spec、`docs/specs/engineering/eng-remediation-acceptance.md`（新增）、`docs/guidelines/code-review.md`、`docs/guidelines/README.md`、`docs/audits/code-review-history.md`（新增）。

- [ ] 新建验收台账，逐项记录 spec、原声明、发现编号、执行任务、代码路径、测试、状态；填入原审查实测结果，不填写未来 PASS。
- [ ] 将有缺口的 10 项当前状态改为实施中，保留历史日期和此前声明；ARCH-003 保持 RFC。
- [ ] 保存 code-review 历史内容至 audits，现行指南提炼为可检查规则并链接历史；失效文件映射改为真实路径，尚无实现的条目明确未实现。
- [ ] 校验文档链接和所有代码映射，提交 `docs: align specification status with audit evidence`。

## D2：最终验收与单项恢复基线

**依赖：** 所有 R/B/F/G 任务和 E4。**文件：** 验收台账、全部关联 guidelines/specs、tests/README.md、docs/audits/frontend-api-integration-plan.md。

- [ ] 每条任务记录真实提交号、测试命令、收集/通过/失败/跳过计数、产物和执行平台；UI记录实际视口、浏览器、布局偏移；算法记录数据窗口和门禁证据路径。
- [ ] 执行 `python -m pytest -q`（使用项目 Python）、`node tests/test_at_operator.js`、`node tests/test_a2ui_suite.js`，另对每个 JS 文件逐个 `node --check`；执行 ZIP 解压后离线 CLI 冒烟。
- [ ] 对每项 spec 独立核对必验清单。unavailable、synthetic、未实测平台、未完成观察期均不算该要求完成；已完成项可单独恢复基线。
- [ ] 对外输出仍待验证的能力清单，保留 ARCH-003 Backlog；提交 `docs: record verified remediation acceptance evidence`。

**回滚：** 代码按任务提交回退；数据格式采用兼容追加，不删除用户 DB/持仓。路径变更回滚只恢复解析逻辑，禁止把测试目录或旧用户目录整体移动覆盖。
