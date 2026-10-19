# -*- coding: utf-8 -*-
"""
tests/webapi/conftest.py
WebAPI 专属测试基座与懒加载 Fixtures（SPEC-SKILL-002 §9.2 铁律二）。

设计原则：
1. 本目录内所有测试用例自动打上 @pytest.mark.webapi 标签；
2. 懒加载 FastAPI app、auth_headers、client、anon_client，确保在跑 core 纯内存门禁时不加载 FastAPI/Uvicorn；
3. 提供股池与选股落盘临时目录隔离，杜绝测试污染。
"""
from __future__ import annotations

import csv
from importlib import import_module
from pathlib import Path

import pytest


def pytest_configure(config):
    """注册 webapi marker 避免 strict-markers 报错。"""
    config.addinivalue_line("markers", "webapi: WebAPI 独立后端测试分仓")


def pytest_collection_modifyitems(config, items):
    """自动为 tests/webapi 下的所有用例标记 webapi 标签。"""
    for item in items:
        if "tests/webapi" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.webapi)


@pytest.fixture(scope="session")
def app():
    """进程内唯一 FastAPI 实例（懒加载）。"""
    from server.app import app as fastapi_app
    return fastapi_app


@pytest.fixture(scope="session")
def auth_headers():
    """有效用户会话凭证，供 /api/* 鉴权测试复用。"""
    from server.db import create_auth_token
    token = create_auth_token(1, 24 * 3600)
    return {"Authorization": f"Bearer {token['token']}"}


@pytest.fixture()
def client(app, auth_headers):
    """带有效鉴权的 TestClient。"""
    from starlette.testclient import TestClient
    with TestClient(app, headers=auth_headers) as test_client:
        yield test_client


@pytest.fixture()
def anon_client(app):
    """匿名 TestClient，专供未登录或身份仿冒拒绝契约校验。"""
    from starlette.testclient import TestClient
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def isolated_user_pools(tmp_path, monkeypatch):
    """把用户三级股池整体重定向到临时空池，防止污染真实资产。"""
    from core.strategy.pool_schema import POSITIONS_FIELDS, SELECTED_FIELDS, WATCH_FIELDS

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
    for attr in ("OUTPUT_POOLS_DIR", "OUTPUT_POSITIONS_DIR", "USER_POOLS_DIR", "POOLS_DIR"):
        if hasattr(config_module, attr):
            monkeypatch.setattr(config_module, attr, pools_dir, raising=False)

    for module_name, attrs in {
        "core.strategy.pool_manager": ("POOLS_BASE",),
        "core.strategy.position_manager": ("POOLS_BASE", "POSITIONS_PATH"),
    }.items():
        try:
            target = import_module(module_name)
            for attr in attrs:
                if hasattr(target, attr):
                    val = positions_path if attr == "POSITIONS_PATH" else pools_dir
                    monkeypatch.setattr(target, attr, val, raising=False)
        except Exception:
            pass

    return pools_dir
