# -*- coding: utf-8 -*-
"""
Global pytest fixtures, sys.path initialization and case tiering.

设计要点（SPEC-SKILL-002 极速测试体系与解耦分仓基座）：
1. 明确三大核心分档：
   - `core`：P0 纯内存极速核心门禁（Engine A ~ F 纯内存单测 + 1+6 技能符合性与执行测试，8个模块，耗时 < 8s）；
   - `webapi`：WebUI 后端独立分仓（tests/webapi/ 4 个高内聚模块，FastAPI 路由、鉴权与智能体分发）；
   - `release_pack`：发布交付与打包安装集成门禁（tests/release/test_release_packaging_smoke.py）。
2. 解耦与懒加载：
   - 彻底移除顶层 FastAPI、Browser E2E 与会话数据库硬依赖；
   - `client` / `auth_headers` / `app` 仅在需要 HTTP 鉴权请求时按需懒加载，运行 `pytest -m core` 时 0 导入。
3. 隔离测试环境：统一在临时目录运行，杜绝测试污染用户私有 output 与设置。
"""
import atexit
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_TEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="astock-pytest-"))
_TEST_CONFIG_PATH = _TEST_RUNTIME_ROOT / "config.yaml"
_TEST_ADMIN_USERNAME = "199" + "".join(str(secrets.randbelow(10)) for _ in range(8))
_TEST_ADMIN_PASSWORD = secrets.token_urlsafe(24)
_TEST_CONFIG_PATH.write_text(
    "version: '3.0.0'\n"
    "paths:\n"
    f"  output_dir: '{(_TEST_RUNTIME_ROOT / 'output').as_posix()}'\n"
    "user_system:\n"
    f"  super_admin_username: '{_TEST_ADMIN_USERNAME}'\n"
    f"  super_admin_password: '{_TEST_ADMIN_PASSWORD}'\n"
    "  super_admin_role_code: 'super_admin'\n",
    encoding="utf-8",
)
os.environ["A_STOCK_RUNTIME_MODE"] = "test"
os.environ["A_STOCK_DEFAULT_MODEL"] = "mock"
os.environ["A_STOCK_DB_PATH"] = str(_TEST_RUNTIME_ROOT / "chats.db")
os.environ["A_STOCK_CONFIG_PATH"] = str(_TEST_CONFIG_PATH)
os.environ["A_STOCK_OUTPUT_DIR"] = str(_TEST_RUNTIME_ROOT / "output")
os.environ["A_STOCK_LOG_DIR"] = str(_TEST_RUNTIME_ROOT / "log")
os.environ["A_STOCK_TEMP_DIR"] = str(_TEST_RUNTIME_ROOT / "temp")
os.environ["A_STOCK_LOCAL_DIR"] = str(_TEST_RUNTIME_ROOT / "local")
atexit.register(shutil.rmtree, _TEST_RUNTIME_ROOT, ignore_errors=True)

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill_bundle" / "runtime"

for p in [ROOT, SCRIPTS, ROOT / "apps/web-console/backend", SCRIPTS / "core"]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ------------------------------------------------------------------ 分层归属表
# 优先级：core(P0 纯内存核心门禁) > webapi(WebAPI后端) > release_pack(发布打包) > p1(治理回归) > p2(补充边界)
_TIER_BY_PATH = {
    # --- P0 核心门禁：6 大纯内存底层支撑技术引擎 (SPEC-SKILL-002 Engine A ~ F) ---
    "tests/core/test_engine_a_data_sync.py": "core",
    "tests/core/test_engine_b_factors_tech.py": "core",
    "tests/core/test_engine_c_funnel_iss.py": "core",
    "tests/core/test_engine_d_tactics_risk.py": "core",
    "tests/core/test_engine_e_paper_backtest.py": "core",
    "tests/core/test_engine_f_infra_safety.py": "core",
    # --- P0 核心门禁：1 + 6 生产级投研技能符合性契约与工具执行 ---
    "tests/skills/test_skill_suite_1plus6_contract.py": "core",
    "tests/skills/test_skill_tools_execution.py": "core",
    # --- Release 交付与打包冒烟门禁 (独立 release_pack 档位) ---
    "tests/release/test_release_packaging_smoke.py": "release_pack",
    # --- WebAPI 独立后端分仓与契约（SPEC-SKILL-002 §9.2）---
    "tests/webapi/test_webapi_auth_and_session.py": "webapi",
    "tests/webapi/test_webapi_market_and_sync.py": "webapi",
    "tests/webapi/test_webapi_selection_api.py": "webapi",
    "tests/webapi/test_webapi_agent_dispatch.py": "webapi",
    # --- P1：治理契约与真实性防护 ---
    "tests/governance/test_capability_truthfulness.py": "p1",
    "tests/governance/test_security_suite.py": "p1",
    "tests/governance/test_quality_gates.py": "p1",
    "tests/governance/test_production_authenticity.py": "p1",
    "tests/governance/test_fail_fast_and_code_validation.py": "p1",
    "tests/governance/test_decoupling_suite.py": "p1",
    "tests/governance/test_governance_suite.py": "p1",
    "tests/governance/test_security_audit.py": "p1",
    # --- P2：文档型回归 ---
    "tests/governance/test_docs_suite.py": "p2",
}

# 能力标签：标注真实耗时来源与外部依赖，供 `-m "not slow and not network"` 精准剔除。
_TAGS_BY_PATH = {
    "tests/release/test_release_packaging_smoke.py": {"release_pack", "subprocess", "slow"},
    "tests/webapi/test_webapi_auth_and_session.py": {"webapi"},
    "tests/webapi/test_webapi_market_and_sync.py": {"webapi"},
    "tests/webapi/test_webapi_selection_api.py": {"webapi"},
    "tests/webapi/test_webapi_agent_dispatch.py": {"webapi"},
    "tests/governance/test_fail_fast_and_code_validation.py": {"network"},
    "tests/governance/test_governance_suite.py": {"slow"},
}

# 单用例能力标签覆写：键为 pytest `nodeid`（`文件::类::用例`）。
_OVERRIDE_TAGS = {}


def _relative_path(item) -> str:
    """取相对 ROOT 的文件路径，作为整文件档位/标签的匹配键。"""
    path = Path(str(item.location[0]))
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def pytest_collection_modifyitems(session, config, items):
    """补齐分层与能力标签（core / webapi / release_pack / p1 / p2）。"""
    for item in items:
        rel = _relative_path(item)
        tier = _TIER_BY_PATH.get(rel, "p2")
        item.add_marker(getattr(pytest.mark, tier))

        tags = set(_TAGS_BY_PATH.get(rel, ()))
        nodeid = item.nodeid.split("[", 1)[0]
        for key, extra in _OVERRIDE_TAGS.items():
            if nodeid == key or item.nodeid == key:
                tags |= extra
        for tag in tags:
            item.add_marker(getattr(pytest.mark, tag))


# ------------------------------------------------------------------ 共享测试基座（按需懒加载）
@pytest.fixture(scope="session")
def auth_headers():
    """按需懒加载一份有效的用户会话凭证，仅供需 HTTP 鉴权的用例使用。"""
    if "A_STOCK_DB_PATH" not in os.environ:
        os.environ["A_STOCK_DB_PATH"] = str(_TEST_RUNTIME_ROOT / "chats.db")
    from server.db import create_auth_token

    token = create_auth_token(1, 24 * 3600)
    return {"Authorization": f"Bearer {token['token']}"}


@pytest.fixture(scope="session")
def app():
    """按需懒加载 FastAPI 实例。运行纯内存 core 门禁时绝不触发。"""
    from server.app import app as fastapi_app

    return fastapi_app


@pytest.fixture()
def client(app, auth_headers):
    """带鉴权的 TestClient（按需懒加载）。"""
    from starlette.testclient import TestClient

    with TestClient(app, headers=auth_headers) as test_client:
        yield test_client


@pytest.fixture()
def anon_client(app):
    """匿名 TestClient（按需懒加载）。"""
    from starlette.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


_MODULE_POOL_ATTRS = {
    "core.strategy.pool_manager": ("POOLS_BASE",),
    "core.strategy.position_manager": ("POOLS_BASE", "POSITIONS_PATH"),
    "core.strategy.position_stop_monitor": ("POSITIONS_PATH",),
    "core.reporting.investment_report": ("POOLS_BASE",),
    "core.multi_agent.ta_orchestrator": ("POOLS_BASE",),
}


@pytest.fixture()
def isolated_user_pools(tmp_path, monkeypatch):
    """把用户三级股池（持仓/自选/关注）整体重定向到临时空池。"""
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
            source = positions_path if attr == "POSITIONS_PATH" else pools_dir
            replacements.append((target, attr, str(source) if isinstance(original, str) else source))

    for target, attr, value in replacements:
        monkeypatch.setattr(target, attr, value, raising=False)

    return pools_dir
