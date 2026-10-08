from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest


def _create_isolated_user(client, menu_codes: set[str]) -> dict[str, str]:
    menus_response = client.get("/api/menus")
    assert menus_response.status_code == 200
    menu_ids = [
        item["id"] for item in menus_response.json()["menus"]
        if item["code"] in menu_codes
    ]
    assert len(menu_ids) == len(menu_codes)

    suffix = uuid4().hex[:8]
    role_response = client.post(
        "/api/roles",
        json={
            "code": f"e2e_{suffix}",
            "name": f"E2E {suffix}",
            "description": "temporary browser authorization test",
            "menu_ids": menu_ids,
        },
    )
    assert role_response.status_code == 200, role_response.text
    username = f"177{int(suffix, 16) % 100_000_000:08d}"
    password = "E2eAuthz!123"
    user_response = client.post(
        "/api/users",
        json={
            "username": username,
            "name": "E2E authorization user",
            "password": password,
            "role_id": role_response.json()["id"],
        },
    )
    assert user_response.status_code == 200, user_response.text
    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    return {"Authorization": f"Bearer {login_response.json()['token']}"}


def test_test_runtime_bind_is_loopback_only() -> None:
    from server.config import ensure_safe_test_bind

    for allowed in ("127.0.0.1", "::1", "localhost"):
        ensure_safe_test_bind(allowed, "test")

    for exposed in ("0.0.0.0", "192.168.1.8", "example.test", ""):
        with pytest.raises(ValueError, match="loopback"):
            ensure_safe_test_bind(exposed, "test")

    ensure_safe_test_bind("0.0.0.0", "production")


def test_explicit_config_path_never_falls_back_to_production(monkeypatch, tmp_path: Path) -> None:
    from core.config import PROJECT_ROOT, resolve_config_file
    from server import db

    isolated = tmp_path / "isolated" / "config.yaml"
    monkeypatch.setenv("A_STOCK_CONFIG_PATH", str(isolated))

    assert resolve_config_file() == isolated.resolve()
    assert Path(db.PROJECT_ROOT_CONFIG()) == isolated.resolve()
    assert Path(db.PROJECT_ROOT_CONFIG()) != (PROJECT_ROOT / "config" / "config.yaml").resolve()
    assert db._load_user_system_config() == {}


def test_explicit_database_path_disables_legacy_database_copy(monkeypatch, tmp_path: Path) -> None:
    import server.config as config

    explicit_db = tmp_path / "isolated" / "chats.db"
    legacy_db = tmp_path / "output" / "cache" / "chats.db"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_bytes(b"production-like-private-data")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("A_STOCK_DB_PATH", str(explicit_db))

    settings = config.load_server_settings()

    assert settings.db_path == explicit_db.resolve()
    assert not explicit_db.exists(), "explicit isolated DB must not be populated from the legacy user DB"


def test_local_runtime_directory_can_be_isolated(monkeypatch, tmp_path: Path) -> None:
    from core import config
    from core import workspace

    isolated = tmp_path / "local"
    monkeypatch.setenv("A_STOCK_LOCAL_DIR", str(isolated))

    assert config._resolve_runtime_dir("A_STOCK_LOCAL_DIR", "local") == isolated.resolve()
    assert workspace._runtime_dir("A_STOCK_LOCAL_DIR", "local") == isolated.resolve()


@pytest.mark.parametrize(
    "headers,params",
    [
        ({"X-Test-User": "1"}, None),
        ({"X-Debug-Admin": "true"}, None),
        ({}, {"bypass_auth": "1"}),
        ({"Authorization": "Bearer forged-browser-token"}, None),
    ],
)
def test_browser_test_identity_spoofing_is_rejected(anon_client, headers, params) -> None:
    response = anon_client.get("/api/auth/me", headers=headers, params=params)
    assert response.status_code == 401
    assert response.json()["detail"]["error"] in {"unauthorized", "invalid_token"}


def test_data_sync_console_requires_explicit_menu_permission(client) -> None:
    ordinary_headers = _create_isolated_user(client, {"dashboard"})
    denied_read = client.get("/api/data-sync/settings", headers=ordinary_headers)
    denied_write = client.put(
        "/api/data-sync/settings",
        headers=ordinary_headers,
        json={"enabled": False},
    )
    assert denied_read.status_code == 403
    assert denied_write.status_code == 403
    assert denied_read.json()["detail"]["error"] == "forbidden"

    datasync_headers = _create_isolated_user(client, {"dashboard", "datasync"})
    allowed = client.get("/api/data-sync/settings", headers=datasync_headers)
    assert allowed.status_code == 200, allowed.text
