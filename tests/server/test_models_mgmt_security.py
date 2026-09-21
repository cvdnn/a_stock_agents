from __future__ import annotations

import uuid

from starlette.testclient import TestClient

from server.app import app
from server.db import delete_provider, get_provider_by_id


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


def test_provider_api_never_returns_secrets_and_exposes_has_key() -> None:
    provider_id = f"prov_{uuid.uuid4().hex}"
    try:
        with TestClient(app) as client:
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


def test_omitted_or_empty_key_preserves_secret_and_explicit_clear_removes_it() -> None:
    provider_id = f"prov_{uuid.uuid4().hex}"
    try:
        with TestClient(app) as client:
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


def test_test_model_endpoint_not_found_and_mocked_success(monkeypatch) -> None:
    import httpx

    with TestClient(app) as client:
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


def test_test_connection_and_fetch_remote_flow(monkeypatch) -> None:
    import httpx

    provider_id = f"prov_test_{uuid.uuid4().hex[:8]}"
    try:
        with TestClient(app) as client:
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


