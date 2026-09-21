from __future__ import annotations

from starlette.testclient import TestClient

from server.app import app
from server.config import load_server_settings


def test_default_cors_is_explicit_and_non_credentialed(monkeypatch) -> None:
    monkeypatch.delenv("A_STOCK_CORS_ORIGINS", raising=False)
    settings = load_server_settings()
    assert "*" not in settings.cors_origins

    with TestClient(app) as client:
        allowed = client.options(
            "/api/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
        assert allowed.headers.get("access-control-allow-credentials") is None

        denied = client.options(
            "/api/health",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert denied.headers.get("access-control-allow-origin") is None

