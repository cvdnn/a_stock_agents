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
    from server.api.models_mgmt import FetchRemoteModelsRequest, TestConnectionRequest

    assert set(TestConnectionRequest.model_fields) == {"provider_id", "timeout_seconds"}
    assert set(FetchRemoteModelsRequest.model_fields) == {"provider_id", "timeout_seconds"}

