# -*- coding: utf-8 -*-
"""
Global pytest fixtures, sys.path initialization and case tiering.

设计要点（用例分层与执行效率基座）：
1. 分层归属集中在本文件的 `_TIER_BY_PATH` / `_TAGS_BY_PATH` 两张表里，按"文件 → 优先级/能力标签"
   声明，避免在 ~400 个用例上散落装饰器；改哪一档只改这一处，可整体审阅。
2. `core` 档构成 P0 门禁：改动量化底座/数据装配/撮合/税费/真实性契约时先跑 `-m core`，
   秒级给出结论；`p1`/`p2` 作为全量回归分批执行。
3. `slow` / `network` / `subprocess` 标签把真实耗时与外网依赖显式化：离线或快速反馈时
   用 `-m "not slow and not network"` 直接剔除，而不是让整套门禁"必须等 90 秒"。
4. 鉴权与 TestClient 在此统一供给：`/api/*` 中间件默认要求有效会话 Token，历史上各文件
   自建 TestClient 而不带凭证，导致大批 HTTP 用例恒 401。共享 `auth_headers` / `client`
   既修正该缺陷，也消除 6+ 文件的重复 fixture。
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_TEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="astock-pytest-"))
os.environ.setdefault("A_STOCK_RUNTIME_MODE", "test")
os.environ.setdefault("A_STOCK_DEFAULT_MODEL", "mock")
os.environ.setdefault("A_STOCK_DB_PATH", str(_TEST_RUNTIME_ROOT / "chats.db"))
# 数据同步设置持久化文件默认落在测试临时根目录，避免回归测试污染真实 local/settings
os.environ.setdefault("A_STOCK_DATA_SYNC_SETTINGS_FILE", str(_TEST_RUNTIME_ROOT / "settings" / "data_sync.json"))
atexit.register(shutil.rmtree, _TEST_RUNTIME_ROOT, ignore_errors=True)

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

for p in [ROOT, SCRIPTS, SCRIPTS / "core", ROOT / "core"]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ------------------------------------------------------------------ 分层归属表
# 优先级：core(P0 契约门禁) > p1(重要回归) > p2(补充边界)。未登记文件默认 p2。
_TIER_BY_PATH = {
    # --- P0：量化底座与数据可信性契约（错了会直接产出假结论）---
    "tests/core/test_data_assembler.py": "core",       # 快照装配 + 水位门禁 + 字段状态
    "tests/core/test_stock_funnel.py": "core",         # 漏斗规则与分钟时间戳归一
    "tests/core/test_selection_models.py": "core",     # ISS 引擎：Schema/哈希/AST/版本仓库/编排
    "tests/core/test_selection_data_and_scheduling.py": "core",  # ISS 批次二：调度/锁/幂等/Latch/覆盖率/W-09/W-10
    "tests/core/test_selection_stage_e.py": "core",    # ISS 批次四：结果研究/跟踪/评价/调优（门禁 12/14/15/16/17/19）
    "tests/core/test_selection_screen_model_cmds.py": "core",  # ISS 阶段 E CLI：assess/track/evaluate/tune 失败关闭
    "tests/core/test_indicators.py": "core",           # MA/MACD/KDJ/RSI/BOLL/ATR
    "tests/core/test_data_suite.py": "core",           # 行情字段契约、防注入、费率 SSOT
    "tests/core/test_data_sync.py": "core",            # 落盘、零假数据、交易日历真值
    "tests/core/test_paper_trading_suite.py": "core",  # 撮合、T+1、涨跌停（资金安全）
    "tests/core/test_strategy_suite.py": "core",       # 保本价、三级止损、解套决策树
    "tests/governance/test_capability_truthfulness.py": "core",  # 真实性红线（禁假成功）
    "tests/governance/test_security_suite.py": "core",           # XSS / Zip Slip 防护
    "tests/server/test_llm_readiness.py": "core",               # 生产禁回落 mock
    # --- P1：服务端 API、设置持久化、技能与治理契约 ---
    "tests/core/test_models_suite.py": "p1",
    "tests/core/test_pool_schema.py": "p1",
    "tests/core/test_commands_suite.py": "p1",
    "tests/core/test_monitor.py": "p1",
    "tests/core/test_algo_registry.py": "p1",
    "tests/core/test_algo_monitoring.py": "p1",
    "tests/core/test_dynamic_universe.py": "p1",
    "tests/core/test_robust_kline_and_report_html.py": "p1",
    "tests/governance/test_skill_contracts.py": "p1",
    "tests/governance/test_quality_gates.py": "p1",
    "tests/governance/test_production_authenticity.py": "p1",
    "tests/governance/test_fail_fast_and_code_validation.py": "p1",
    "tests/governance/test_decoupling_suite.py": "p1",
    "tests/governance/test_governance_suite.py": "p1",
    "tests/governance/test_security_audit.py": "p1",
    "tests/server/test_data_sync_settings.py": "p1",
    "tests/server/test_dataset_sync.py": "p1",
    "tests/server/test_selection_models_api.py": "p1",  # ISS 批次三：选股 API/权限/SSE/运行隔离
    "tests/server/test_selection_stage_e_api.py": "p1",  # ISS 批次四：结果研究/跟踪/评价/调优 API
    "tests/server/test_dataset_sync_funnel.py": "p1",
    "tests/server/test_data_sync_import.py": "p1",
    "tests/server/test_market_data_api.py": "p1",
    "tests/server/test_market_data_sync_api.py": "p1",
    "tests/server/test_models_mgmt_security.py": "p1",
    "tests/server/test_server_suite.py": "p1",
    "tests/server/test_session_memory.py": "p1",
    "tests/server/test_cors_security.py": "p1",
    "tests/server/test_agent_capability_execution.py": "p1",
    "tests/server/test_debate_and_quant_tools.py": "p1",
    "tests/server/test_access_and_thought_fix.py": "p1",
    # --- P2：辅助路径与文档型回归 ---
    "tests/core/test_algorithm_optimizations.py": "p2",
    "tests/core/test_custom_output.py": "p2",
    "tests/server/test_agent_tool_technical_summary.py": "p2",
    "tests/server/test_llm_stream_chunk_usage.py": "p2",
    "tests/governance/test_docs_suite.py": "p2",
}

# 能力标签：标注真实耗时来源与外部依赖，供 `-m "not slow and not network"` 精准剔除。
_TAGS_BY_PATH = {
    # 子进程 CLI 冷启动（Python + pandas 导入），并行化后仍是秒级起步
    "tests/core/test_custom_output.py": {"subprocess", "slow"},
    "tests/core/test_commands_suite.py": {"subprocess"},
    # 真实全市场扫描 / 完整辩论流水线
    "tests/server/test_agent_capability_execution.py": {"slow"},
    "tests/server/test_debate_and_quant_tools.py": {"slow"},
    "tests/core/test_models_suite.py": {"slow"},
    "tests/core/test_data_suite.py": {"slow"},
    # 触达真实外网：行情重试与连通性探测
    "tests/governance/test_fail_fast_and_code_validation.py": {"network"},
    "tests/core/test_robust_kline_and_report_html.py": {"network"},
    "tests/server/test_access_and_thought_fix.py": {"network"},
    # 端到端链路（装配 → 规则 → 快照落盘）
    "tests/core/test_data_assembler.py": {"e2e"},
    "tests/server/test_dataset_sync_funnel.py": {"slow"},
    "tests/governance/test_governance_suite.py": {"slow"},
    # 需预先启动真实服务并显式开启，默认整文件 skipif 跳过
    "tests/server/test_live_server_e2e.py": {"live", "network", "slow"},
}

# 单用例能力标签覆写：键为 pytest `nodeid`（`文件::类::用例`）。用于整文件归档粒度不够细的场合——
# 某些文件绝大多数用例离线可跑，只有个别分支真的走外网，若不点名就无法被
# `-m "not network"` 精准摘除，只能整文件一起丢，反而扩大了盲区。
_OVERRIDE_TAGS = {
    # K 线端点直连腾讯实时行情
    "tests/server/test_market_data_api.py::test_market_kline_is_implemented_and_never_synthesizes": {"network"},
    # /api/watchlist 内部调用 DataBridge.tencent_quote 批量取现价
    "tests/server/test_server_suite.py::TestFastAPIRoutes::test_watchlist_no_duplicate_stocks": {"network"},
}


def _relative_path(item) -> str:
    """取相对 ROOT 的文件路径，作为整文件档位/标签的匹配键。"""
    path = Path(str(item.location[0]))
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def pytest_collection_modifyitems(session, config, items):
    """把分层表落到用例上：未显式装饰的用例自动补齐优先级与能力标签。"""
    for item in items:
        rel = _relative_path(item)
        item.add_marker(getattr(pytest.mark, _TIER_BY_PATH.get(rel, "p2")))

        tags = set(_TAGS_BY_PATH.get(rel, ()))
        # 覆写键必须是 nodeid：`item.name` 只到方法名，不含所属测试类，
        # 用 `文件::用例` 拼键永远匹配不到类内用例。
        nodeid = item.nodeid.split("[", 1)[0]
        for key, extra in _OVERRIDE_TAGS.items():
            if nodeid == key or item.nodeid == key:
                tags |= extra
        for tag in tags:
            item.add_marker(getattr(pytest.mark, tag))


# ------------------------------------------------------------------ 共享测试基座
@pytest.fixture(scope="session")
def auth_headers():
    """一份有效的用户会话凭证，供所有 `/api/*` 用例复用。

    `/api/*` 中间件默认拒绝任何匿名请求；各文件历史上自建 TestClient 而不带凭证，
    导致 HTTP 用例整批 401。会话 Token 写入测试库（`A_STOCK_DB_PATH` 指向临时目录），
    与真实用户数据完全隔离。
    """
    from server.db import create_auth_token

    token = create_auth_token(1, 24 * 3600)
    return {"Authorization": f"Bearer {token['token']}"}


@pytest.fixture(scope="session")
def app():
    """进程内唯一 FastAPI 实例。

    `create_app()` 会重建全部路由与中间件，而 `server.app.app` 已是同一实例，
    因此直接复用模块级单例，避免每个用例重复装配。
    """
    from server.app import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app, auth_headers):
    """带鉴权的 TestClient（进入 lifespan，与浏览器已登录会话等价）。"""
    from starlette.testclient import TestClient

    with TestClient(app, headers=auth_headers) as test_client:
        yield test_client


@pytest.fixture()
def anon_client(app):
    """匿名 TestClient，专供"未登录必须 401"这类鉴权契约用例。"""
    from starlette.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


# 各模块在 import 期就把股池目录绑定成模块级常量（`POOLS_BASE = OUTPUT_POOLS_DIR`、
# `POSITIONS_PATH = os.path.join(...)`），因此只改 core.config 不足以隔离，必须逐个改绑。
_MODULE_POOL_ATTRS = {
    "core.strategy.pool_manager": ("POOLS_BASE",),
    "core.strategy.position_manager": ("POOLS_BASE", "POSITIONS_PATH"),
    "core.strategy.position_stop_monitor": ("POSITIONS_PATH",),
    "core.reporting.investment_report": ("POOLS_BASE",),
    "core.multi_agent.ta_orchestrator": ("POOLS_BASE",),
}


@pytest.fixture()
def isolated_user_pools(tmp_path, monkeypatch):
    """把用户三级股池（持仓/自选/关注）整体重定向到临时**空池**。

    多个用例通过 HTTP 或 CLI 往股池写数据，历史上直接落在真实 `output/pools/`：
    既污染用户自选/持仓，又让断言随开发者本机数据漂移（同一用例在 A 机器 PASS、
    B 机器 FAIL）。需要写股池、或断言"池为空"的用例必须显式声明本 fixture。

    注意这里刻意只写表头、不写数据行：`init_output_templates` 会把 `.example` 的
    示例行（600519 贵州茅台）一并复制进 positions.csv，使"空池"分支根本无法触发——
    历史上 action-plan 用例正是被这一行示例持仓带进了"自动选取唯一持仓"分支。
    """
    import csv
    from importlib import import_module

    from core.strategy.pool_schema import (
        POSITIONS_FIELDS,
        SELECTED_FIELDS,
        WATCH_FIELDS,
    )

    pools_dir = tmp_path / "pools"
    pools_dir.mkdir(parents=True, exist_ok=True)
    for filename, fields in (
        ("positions.csv", POSITIONS_FIELDS),
        ("selected_pool.csv", SELECTED_FIELDS),
        ("watch_pool.csv", WATCH_FIELDS),
    ):
        with open(pools_dir / filename, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(fields)

    positions_path = pools_dir / "positions.csv"
    config_module = import_module("core.config")
    replacements: list[tuple[object, str, object]] = [
        (config_module, attr, pools_dir)
        for attr in ("OUTPUT_POOLS_DIR", "OUTPUT_POSITIONS_DIR", "USER_POOLS_DIR", "POOLS_DIR")
        if hasattr(config_module, attr)
    ]
    for module_name, attrs in _MODULE_POOL_ATTRS.items():
        target = import_module(module_name)
        for attr in attrs:
            if not hasattr(target, attr):
                continue
            original = getattr(target, attr)
            # 保持原类型：部分模块用 os.path.join 生成 str 路径，部分是 Path
            source = positions_path if attr == "POSITIONS_PATH" else pools_dir
            replacements.append((target, attr, str(source) if isinstance(original, str) else source))

    for target, attr, value in replacements:
        monkeypatch.setattr(target, attr, value, raising=False)

    return pools_dir


