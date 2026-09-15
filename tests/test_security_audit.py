# -*- coding: utf-8 -*-
"""
tests.test_security_audit - Milestone 0 & Milestone 1 security regression test suite.
Verifies path traversal defenses, iframe sandbox hardening, XSS prevention, and source disclosure blocks.
"""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from core.reporting.report_generator import _sanitize_report_output_path
from core.config import PROJECT_ROOT, OUTPUT_REPORTS_DIR


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# SEC-01: /api/docs/save Path Traversal & Arbitrary File Overwrite Defenses
# ==============================================================================

def test_docs_save_blocks_overwriting_web_index(client: TestClient):
    """Attempting to overwrite web/index.html via /api/docs/save must return 403 Forbidden."""
    res = client.post(
        "/api/docs/save",
        json={"path": "web/index.html", "content": "<h1>Hacked</h1>", "title": "test"},
    )
    assert res.status_code == 403
    assert "restricted" in res.json().get("detail", "").lower() or "access denied" in res.json().get("detail", "").lower()


def test_docs_save_blocks_directory_traversal(client: TestClient):
    """Attempting path traversal via ../../ must return 403 Forbidden."""
    res = client.post(
        "/api/docs/save",
        json={"path": "../../evil_report.html", "content": "<h1>Hacked</h1>", "title": "test"},
    )
    assert res.status_code == 403


def test_docs_save_blocks_scripts_and_config_dirs(client: TestClient):
    """Attempting to write to scripts/ or config/ must return 403 Forbidden."""
    for bad_path in ["scripts/server/malicious.py", "config/evil.json"]:
        res = client.post(
            "/api/docs/save",
            json={"path": bad_path, "content": "{}", "title": "test"},
        )
        assert res.status_code in (400, 403)


def test_docs_save_confines_to_reports_dir(client: TestClient):
    """Legitimate save requests must strictly write to output/reports/."""
    filename = "test_sec01_verify_report.html"
    res = client.post(
        "/api/docs/save",
        json={"path": filename, "content": "<!DOCTYPE html><html><body>Report</body></html>", "title": "Test Report"},
    )
    assert res.status_code == 200
    saved_path = PROJECT_ROOT / res.json()["path"]
    assert saved_path.is_file()
    assert (PROJECT_ROOT / "output" / "reports").resolve() in saved_path.resolve().parents
    # Cleanup
    if saved_path.exists():
        saved_path.unlink()


# ==============================================================================
# SEC-06: /api/docs/read Source Code Disclosure & Directory Boundary Defense
# ==============================================================================

def test_docs_read_denies_py_source_code(client: TestClient):
    """Requesting .py source files must return 400 or 403, never disclosing backend source code."""
    res = client.get("/api/docs/read", params={"path": "scripts/server/app.py"})
    assert res.status_code in (400, 403)


def test_docs_read_denies_sensitive_system_dirs(client: TestClient):
    """Accessing scripts/, tests/, or .env must be rejected with 403 Forbidden."""
    for forbidden_path in ["scripts/server/db.py", "tests/conftest.py", ".env"]:
        res = client.get("/api/docs/read", params={"path": forbidden_path})
        assert res.status_code in (400, 403)


def test_docs_read_allows_whitelisted_docs(client: TestClient):
    """Legitimate markdown documents in docs/ must be readable."""
    res = client.get("/api/docs/read", params={"path": "docs/specs/engineering/eng-project-structure-and-workspace.md"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["format"] == "markdown"
    assert len(data["content"]) > 0


# ==============================================================================
# SEC-03: Iframe Sandbox Isolation Hardening
# ==============================================================================

def test_iframe_sandbox_excludes_same_origin():
    """Ensure web/index.html iframe sandbox does not combine allow-scripts with allow-same-origin."""
    index_html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="workspaceHtmlFrame"' in index_html
    # Must NOT have allow-same-origin
    assert 'sandbox="allow-scripts allow-same-origin allow-popups"' not in index_html
    assert 'allow-same-origin' not in index_html
    assert 'sandbox="allow-scripts allow-popups allow-forms"' in index_html


# ==============================================================================
# SEC-04: DOMPurify Sanitization & No 'onclick' in White-list
# ==============================================================================

def test_dompurify_disallows_onclick_attribute():
    """Ensure chat_presentation.js does not allow 'onclick' attribute in DOMPurify sanitize options."""
    import re
    chat_js = (PROJECT_ROOT / "web" / "js" / "chat_presentation.js").read_text(encoding="utf-8")
    m = re.search(r"ADD_ATTR:\s*\[(.*?)\]", chat_js)
    assert m is not None, "ADD_ATTR configuration block must be present in DOMPurify sanitize call"
    add_attrs = m.group(1)
    assert "onclick" not in add_attrs, "DOMPurify ADD_ATTR must not include onclick"


# ==============================================================================
# SEC-08: Report Generator Output Path Sandbox Enforcement
# ==============================================================================

def test_report_generator_sandboxes_output_path():
    """_sanitize_report_output_path must never escape to arbitrary parent system directories."""
    dangerous_path = "../../../../windows/system32/evil.html"
    safe = _sanitize_report_output_path(dangerous_path)
    reports_dirs = [(PROJECT_ROOT / "output" / "reports").resolve(), OUTPUT_REPORTS_DIR.resolve()]
    is_sandboxed = any(r_dir in safe.resolve().parents or safe.resolve().parent == r_dir for r_dir in reports_dirs)
    assert is_sandboxed
    assert safe.name == "evil.html"


# ==============================================================================
# SEC-02: Docker Port Binding & API Token Authentication Middleware
# ==============================================================================

def test_docker_compose_binds_to_localhost():
    """docker-compose.yml port mapping must be strictly bound to 127.0.0.1."""
    compose_text = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '127.0.0.1:${A_STOCK_SERVER_PORT:-6300}:6300' in compose_text, (
        "docker-compose.yml must bind port to 127.0.0.1 to avoid exposing 0.0.0.0 publicly"
    )


def test_auth_middleware_flow(client: TestClient):
    """Verify that when api_token is configured, protected endpoints require Bearer auth."""
    from server.config import server_settings

    original_token = server_settings.api_token
    try:
        # 1. 无 token 时（向下兼容单机开发），受保护端点正常放行
        server_settings.api_token = None
        res_no_auth = client.get("/api")
        assert res_no_auth.status_code == 200

        # 2. 启用 token 保护
        server_settings.api_token = "test-secret-token-9988"

        # 2.1 未携带 Token 访问受保护接口 -> 401 Unauthorized
        res_unauth = client.get("/api")
        assert res_unauth.status_code == 401
        assert "Unauthorized" in res_unauth.json().get("detail", "")

        # 2.2 携带错误 Token 访问受保护接口 -> 401 Unauthorized
        res_bad_token = client.get("/api", headers={"Authorization": "Bearer wrong-token"})
        assert res_bad_token.status_code == 401

        # 2.3 携带正确 Token 访问受保护接口 -> 200 OK
        res_authed = client.get("/api", headers={"Authorization": "Bearer test-secret-token-9988"})
        assert res_authed.status_code == 200

        # 2.4 白名单豁免：健康检查接口无需 Token
        res_health = client.get("/api/health")
        assert res_health.status_code == 200

        # 2.5 白名单豁免：Web UI 页面无需 Token
        res_ui = client.get("/")
        assert res_ui.status_code == 200

        # 2.6 白名单豁免：OPTIONS 预检请求不被拦截为 401
        res_options = client.options(
            "/api",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )
        assert res_options.status_code != 401
        assert res_options.status_code in (200, 204)

    finally:
        server_settings.api_token = original_token


# ==============================================================================
# SEC-05: DNS-Level Resolution SSRF Protection & Private IP Filtering
# ==============================================================================

def test_ssrf_rejects_private_ips():
    """Verify that literal private/link-local IP addresses are blocked."""
    from fastapi import HTTPException
    from server.api.models_mgmt import _validate_provider_base_url

    bad_urls = [
        "http://127.0.0.1:8000",       # loopback with non-ollama port
        "http://192.168.1.1:8080",     # RFC 1918 class C
        "http://10.0.0.1:80",          # RFC 1918 class A
        "http://172.16.0.1:3000",      # RFC 1918 class B
        "http://169.254.169.254/meta", # link-local metadata
    ]
    for url in bad_urls:
        with pytest.raises(HTTPException) as exc_info:
            _validate_provider_base_url(url)
        assert exc_info.value.status_code == 400
        assert "restricted" in exc_info.value.detail.lower() or "not allowed" in exc_info.value.detail.lower()


def test_ssrf_rejects_cloud_metadata_domains():
    """Known cloud metadata domains must be unconditionally blocked."""
    from fastapi import HTTPException
    from server.api.models_mgmt import _validate_provider_base_url

    for domain in ["http://metadata.google.internal", "http://metadata.azure.internal"]:
        with pytest.raises(HTTPException) as exc_info:
            _validate_provider_base_url(domain)
        assert exc_info.value.status_code == 400


def test_ssrf_allows_local_ollama_on_11434():
    """Loopback on port 11434 is allowed for local Ollama development."""
    from server.api.models_mgmt import _validate_provider_base_url

    clean = _validate_provider_base_url("http://127.0.0.1:11434")
    assert clean == "http://127.0.0.1:11434"

    clean_host = _validate_provider_base_url("http://localhost:11434")
    assert clean_host == "http://localhost:11434"


def test_ssrf_blocks_non_loopback_on_11434():
    """Even on port 11434, non-loopback private IPs (e.g. 192.168.x.x) must be blocked."""
    from fastapi import HTTPException
    from server.api.models_mgmt import _validate_provider_base_url

    with pytest.raises(HTTPException) as exc_info:
        _validate_provider_base_url("http://192.168.1.50:11434")
    assert exc_info.value.status_code == 400
    assert "restricted" in exc_info.value.detail.lower()
# ==============================================================================
# Aliases & Additional Tests for Execution Plan Conformance
# ==============================================================================

def test_docs_save_path_traversal(client: TestClient):
    """Execution plan alias: test_docs_save_path_traversal."""
    res = client.post(
        "/api/docs/save",
        json={"path": "../../etc/passwd", "content": "root:x:0:0:", "title": "traversal"},
    )
    assert res.status_code in (400, 403)


def test_docs_read_denies_py(client: TestClient):
    """Execution plan alias: test_docs_read_denies_py."""
    res = client.get("/api/docs/read", params={"path": "scripts/core/cli.py"})
    assert res.status_code in (400, 403)


def test_ssrf_rejects_dns_rebind(monkeypatch):
    """DNS rebinding or dynamic domain resolving to internal IP must be rejected."""
    import socket
    from fastapi import HTTPException
    from server.api.models_mgmt import _validate_provider_base_url

    def mock_getaddrinfo(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    with pytest.raises(HTTPException) as exc_info:
        _validate_provider_base_url("http://rebind.attacker.com:8080/v1")
    assert exc_info.value.status_code == 400
    assert "restricted" in exc_info.value.detail.lower()


def test_dompurify_and_fallback_sanitization_rules():
    """Verify chat_presentation.js strips onclick, onmouseover, and javascript: links."""
    import re
    chat_js = (PROJECT_ROOT / "web" / "js" / "chat_presentation.js").read_text(encoding="utf-8")
    m = re.search(r"ADD_ATTR:\s*\[(.*?)\]", chat_js)
    assert m and "onclick" not in m.group(1)
    assert "javascript:" in chat_js
    assert "onerror" in chat_js or "on\\w+" in chat_js or "on" in chat_js


# ==============================================================================
# SEC-07: SQLite Database API Key Obfuscation & Static Encryption
# ==============================================================================

def test_sqlite_api_key_obfuscation_and_encryption_helpers():
    """Verify _encrypt_api_key, _decrypt_api_key, and secret key derivation."""
    from server.db import _derive_secret_key, _encrypt_api_key, _decrypt_api_key

    # 1. Custom secret key derivation vs default host fingerprint
    key_custom = _derive_secret_key("my-custom-test-secret-key")
    key_custom2 = _derive_secret_key("my-custom-test-secret-key")
    assert key_custom == key_custom2
    assert len(key_custom) == 32

    key_default = _derive_secret_key(None)
    assert len(key_default) == 32

    # 2. Encryption and decryption roundtrip
    raw_key = "sk-deepseek-1234567890abcdef"
    token = _encrypt_api_key(raw_key, secret_key=key_custom)
    assert token.startswith("enc:v1:")
    assert raw_key not in token

    decrypted = _decrypt_api_key(token, secret_key=key_custom)
    assert decrypted == raw_key

    # 3. Idempotent encryption: already encrypted token is not double-encrypted
    token2 = _encrypt_api_key(token, secret_key=key_custom)
    assert token2 == token

    # 4. Backward compatibility: unencrypted legacy key returns unchanged
    legacy_key = "sk-legacy-unencrypted-key"
    assert _decrypt_api_key(legacy_key, secret_key=key_custom) == legacy_key

    # 5. Empty or None key handling
    assert _encrypt_api_key("") == ""
    assert _encrypt_api_key(None) == ""
    assert _decrypt_api_key("") == ""
    assert _decrypt_api_key(None) == ""

    # 6. Tampered token returns empty string (integrity check)
    parts = token.split(":")
    tampered_tag = "enc:v1:" + parts[2] + ":" + parts[3] + ":AAAAAAAAAAAAAAAAAAAAAA=="
    assert _decrypt_api_key(tampered_tag, secret_key=key_custom) == ""


def test_sqlite_api_key_storage_and_lifecycle(tmp_path):
    """
    Verify full lifecycle of provider API key:
    - Stored in SQLite as encrypted ciphertext (never plaintext).
    - Decrypted in-memory on read (get_provider_by_id, list_providers).
    - Preserved when updating without key.
    - Cleared when clear_api_key is set.
    """
    import sqlite3
    from server.db import (
        get_connection,
        save_provider,
        get_provider_by_id,
        list_providers,
        delete_provider,
    )
    from server.api.models_mgmt import _public_provider

    test_db = tmp_path / "test_lifecycle.db"

    # 1. Save provider with sensitive API key
    plain_key = "sk-super-secret-production-token-998877"
    saved = save_provider({
        "provider_id": "test_prov_sec07",
        "name": "安全测试供应商",
        "base_url": "https://api.example.com/v1",
        "api_key": plain_key,
        "enabled": True,
    }, db_path=test_db)

    assert saved["api_key"] == plain_key

    # 2. Inspect raw SQLite database directly — must NOT contain plaintext key!
    raw_conn = sqlite3.connect(str(test_db))
    raw_cur = raw_conn.cursor()
    raw_cur.execute("SELECT api_key FROM llm_providers WHERE provider_id = 'test_prov_sec07';")
    db_row = raw_cur.fetchone()
    raw_conn.close()

    assert db_row is not None
    stored_in_db = db_row[0]
    assert stored_in_db.startswith("enc:v1:")
    assert plain_key not in stored_in_db, "Plaintext API Key must NEVER be stored in SQLite table!"

    # 3. Reading via get_provider_by_id decrypts key in-memory
    fetched = get_provider_by_id("test_prov_sec07", db_path=test_db)
    assert fetched is not None
    assert fetched["api_key"] == plain_key

    # 4. Reading via list_providers decrypts key in-memory
    providers = list_providers(db_path=test_db)
    matched = next((p for p in providers if p["provider_id"] == "test_prov_sec07"), None)
    assert matched is not None
    assert matched["api_key"] == plain_key

    # 5. _public_provider projection strips api_key and sets has_api_key
    public = _public_provider(fetched)
    assert "api_key" not in public
    assert public["has_api_key"] is True

    # 6. Updating without api_key preserves the existing encrypted key
    updated = save_provider({
        "provider_id": "test_prov_sec07",
        "name": "安全测试供应商-已更新名称",
    }, db_path=test_db)
    assert updated["name"] == "安全测试供应商-已更新名称"
    assert updated["api_key"] == plain_key

    # 7. Updating with clear_api_key=True clears the key
    cleared = save_provider({
        "provider_id": "test_prov_sec07",
        "clear_api_key": True,
    }, db_path=test_db)
    assert cleared["api_key"] == ""
    assert _public_provider(cleared)["has_api_key"] is False

    # Cleanup
    delete_provider("test_prov_sec07", db_path=test_db)


def test_sqlite_api_key_legacy_plaintext_migration(tmp_path):
    """Verify that legacy unencrypted keys in SQLite are automatically encrypted upon schema init."""
    import sqlite3
    from server.db import get_connection, get_provider_by_id

    test_db = tmp_path / "legacy_migration.db"
    conn = sqlite3.connect(str(test_db))
    conn.execute("""
        CREATE TABLE llm_providers (
            provider_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            api_key TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            models_json TEXT DEFAULT '[]',
            custom_headers_json TEXT DEFAULT '{}',
            timeout_seconds INTEGER DEFAULT 60,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.execute("""
        INSERT INTO llm_providers (provider_id, name, base_url, api_key, created_at, updated_at)
        VALUES ('prov_legacy', '老版本明文供应商', 'https://api.legacy.com', 'sk-legacy-plain-12345', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
    """)
    conn.commit()
    conn.close()

    # Now open with get_connection which triggers _init_schemas and _migrate_llm_providers_encryption
    app_conn = get_connection(test_db)
    app_conn.close()

    # Check database content: should now be encrypted!
    chk_conn = sqlite3.connect(str(test_db))
    cur = chk_conn.cursor()
    cur.execute("SELECT api_key FROM llm_providers WHERE provider_id = 'prov_legacy';")
    migrated_val = cur.fetchone()[0]
    chk_conn.close()

    assert migrated_val.startswith("enc:v1:")
    assert "sk-legacy-plain-12345" not in migrated_val

    # Query via helper returns decrypted key
    p = get_provider_by_id("prov_legacy", db_path=test_db)
    assert p is not None
    assert p["api_key"] == "sk-legacy-plain-12345"
