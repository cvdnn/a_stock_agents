from __future__ import annotations

import socket
import uuid

import pytest

from server.db import delete_provider, get_provider_by_id


@pytest.fixture()
def public_dns(monkeypatch):
    """把 DNS 解析桩成公网 IP，使 SSRF 校验走确定路径。

    `_validate_provider_base_url` 在发请求前调用真实 `socket.getaddrinfo`，
    因此虚构域名（api.example.com 等）必然 400、真实域名（api.deepseek.com）则依赖外网 DNS：
    两种写法都让用例随环境漂移。桩成公网 IP 后既离线可跑、结果确定，
    又仍完整走过 SSRF 校验分支（换成私网/环回 IP 即应被拒）。
    注意：桩 IP 必须用真公网段，勿用 203.0.113.0/24（TEST-NET-3）——
    Python `ipaddress` 已把它归入 is_private，会被 SSRF 守卫正常拒绝。
    """
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", port or 443))],
    )


def _provider_payload(provider_id: str, api_key: str | None = "sk-p0-secret") -> dict:
    payload = {
        "provider_id": provider_id,
        "name": "P0 Provider",
        "base_url": "https://models.example.test/v1",
        "enabled": True,
        "models": [{"id": "p0-model", "capabilities": ["chat", "tools"]}],
        "custom_headers": {
            "Authorization": "Bearer header-secret",
            "X-API-Key": "header-key-secret",
            "X-Trace": "safe",
        },
        "timeout_seconds": 20,
    }
    if api_key is not None:
        payload["api_key"] = api_key
    return payload


def test_provider_api_never_returns_secrets_and_exposes_has_key(client) -> None:
    provider_id = f"prov_{uuid.uuid4().hex}"
    try:
        created = client.post("/api/models/providers", json=_provider_payload(provider_id))
        assert created.status_code == 200
        listed = client.get("/api/models/providers")
        assert listed.status_code == 200

        for response in (created, listed):
            body = response.text
            assert "sk-p0-secret" not in body
            assert "header-secret" not in body
            assert "header-key-secret" not in body
            assert '"api_key"' not in body

        public = created.json()["provider"]
        assert public["has_api_key"] is True
        assert public["custom_headers"] == {"X-Trace": "safe"}
    finally:
        delete_provider(provider_id)


def test_omitted_or_empty_key_preserves_secret_and_explicit_clear_removes_it(client) -> None:
    provider_id = f"prov_{uuid.uuid4().hex}"
    try:
        assert client.post("/api/models/providers", json=_provider_payload(provider_id)).status_code == 200

        omitted = _provider_payload(provider_id, api_key=None)
        omitted["name"] = "Renamed"
        assert client.post("/api/models/providers", json=omitted).status_code == 200
        assert get_provider_by_id(provider_id)["api_key"] == "sk-p0-secret"

        empty = _provider_payload(provider_id, api_key="")
        assert client.post("/api/models/providers", json=empty).status_code == 200
        assert get_provider_by_id(provider_id)["api_key"] == "sk-p0-secret"

        empty["clear_api_key"] = True
        cleared = client.post("/api/models/providers", json=empty)
        assert cleared.status_code == 200
        assert cleared.json()["provider"]["has_api_key"] is False
        assert get_provider_by_id(provider_id)["api_key"] == ""
    finally:
        delete_provider(provider_id)


def test_connection_requests_accept_provider_id_not_browser_secrets() -> None:
    from server.api.models_mgmt import FetchRemoteModelsRequest, TestConnectionRequest, TestModelRequest

    assert set(TestConnectionRequest.model_fields) == {"provider_id", "timeout_seconds"}
    assert set(FetchRemoteModelsRequest.model_fields) == {"provider_id", "timeout_seconds"}
    assert "model_id" in TestModelRequest.model_fields


def test_test_model_endpoint_not_found_and_mocked_success(client, monkeypatch, public_dns) -> None:
    import httpx

    # Non-existent provider
    res = client.post("/api/models/test-model", json={"provider_id": "non_existent_prov", "model_id": "m1"})
    assert res.status_code == 404

    # SSRF blocked target
    res_ssrf = client.post("/api/models/test-model", json={
        "provider_id": "prov_temp",
        "model_id": "m1",
        "base_url": "http://169.254.169.254/v1"
    })
    assert res_ssrf.status_code == 400

    # Mocked upstream 200 response
    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    res_ok = client.post("/api/models/test-model", json={
        "provider_id": "prov_temp",
        "model_id": "mock-deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test"
    })
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert data["status"] == "ok"
    assert "latency_ms" in data
    assert data["model_id"] == "mock-deepseek"


def test_test_connection_and_fetch_remote_flow(client, monkeypatch, public_dns) -> None:
    import httpx

    provider_id = f"prov_test_{uuid.uuid4().hex[:8]}"
    try:
        # 1. Newly created provider saved to backend
        created = client.post("/api/models/providers", json={
            "provider_id": provider_id,
            "name": "New Test Provider",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-key",
            "enabled": False,  # even when disabled, test & fetch should work
            "models": [],
        })
        assert created.status_code == 200

        # Mock upstream GET responses for /models
        async def mock_get(self, url, *args, **kwargs):
            return httpx.Response(200, json={
                "data": [
                    {"id": "test-v3", "name": "Test V3 0324"},
                    {"id": "test-r1", "name": "Test R1 0528"}
                ]
            })

        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

        # 2. Test connection
        res_conn = client.post("/api/models/test-connection", json={"provider_id": provider_id})
        assert res_conn.status_code == 200
        assert res_conn.json()["status"] == "ok"

        # 3. Fetch remote models
        res_fetch = client.post("/api/models/fetch-remote", json={"provider_id": provider_id})
        assert res_fetch.status_code == 200
        fetch_data = res_fetch.json()
        assert fetch_data["status"] == "ok"
        assert fetch_data["count"] == 2
        assert fetch_data["models"][0]["id"] == "test-v3"
        assert fetch_data["models"][0]["name"] == "Test V3 0324"
        assert fetch_data["models"][1]["id"] == "test-r1"
    finally:
        delete_provider(provider_id)


