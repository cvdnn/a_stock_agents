from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
_BROWSER_E2E_FAILED = False


class BrowserRuntime(dict):
    """Fixture mapping whose pytest representation never exposes credentials."""

    def __repr__(self) -> str:
        return (
            "BrowserRuntime("
            f"base_url={self.get('base_url')!r}, "
            f"artifacts_dir={str(self.get('artifacts_dir', ''))!r}"
            ")"
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Remember browser failures so only sanitized evidence is retained."""
    outcome = yield
    report = outcome.get_result()
    if "browser_e2e" in item.keywords and report.failed:
        global _BROWSER_E2E_FAILED
        _BROWSER_E2E_FAILED = True


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        return exc.code, json.loads(text) if text else {}


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _is_loopback_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https", "ws", "wss"}:
        return True
    return _is_loopback_host(parsed.hostname)


def _is_loopback_host(host: str | None) -> bool:
    value = str(host or "").strip().lower()
    if value == "localhost":
        return True
    try:
        return socket.inet_pton(socket.AF_INET, value) is not None and value.startswith("127.")
    except OSError:
        return value == "::1"


def _redact_browser_log(text: str, secrets_to_remove: tuple[str, ...]) -> str:
    for secret_value in secrets_to_remove:
        if secret_value:
            text = text.replace(secret_value, "[REDACTED]")
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)


def _remove_runtime_root(path: Path) -> None:
    """Remove credential-bearing runtime data, tolerating brief Windows handle lag."""
    for attempt in range(6):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.2 * (attempt + 1))


@pytest.fixture(scope="session")
def isolated_browser_server(tmp_path_factory):
    if os.getenv("A_STOCK_RUN_BROWSER_E2E") != "1":
        pytest.skip("browser E2E is opt-in; set A_STOCK_RUN_BROWSER_E2E=1")

    runtime_root = tmp_path_factory.mktemp("astock-browser-e2e")
    output_dir = runtime_root / "output"
    log_dir = runtime_root / "log"
    temp_dir = runtime_root / "temp"
    db_path = runtime_root / "server" / "chats.db"
    settings_path = runtime_root / "settings" / "data_sync.json"
    config_path = runtime_root / "config.yaml"
    artifacts_dir = runtime_root / "artifacts"
    for path in (output_dir, log_dir, temp_dir, db_path.parent, settings_path.parent, artifacts_dir):
        path.mkdir(parents=True, exist_ok=True)

    suffix = f"{secrets.randbelow(10**8):08d}"
    admin_phone = f"199{suffix}"
    user_phone = f"188{secrets.randbelow(10**8):08d}"
    admin_password = f"E2e!{secrets.token_hex(12)}"
    user_password = f"View!{secrets.token_hex(12)}"
    config = {
        "version": "3.0.0",
        "paths": {"output_dir": str(output_dir)},
        "user_system": {
            "super_admin_username": admin_phone,
            "super_admin_password": admin_password,
            "super_admin_role_code": "super_admin",
            "default_user_role_code": "researcher",
            "token_ttl_seconds": 900,
        },
    }
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

    port = _free_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    # Keep the isolated UI test incapable of using developer/provider secrets.
    # Empty values also prevent core.config's local .env loader from restoring
    # them merely because the keys were absent from the child environment.
    for secret_name in (
        "A_STOCK_SERVER_TOKEN",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AUTH_TOKEN",
        "PROXY_GATEWAY",
    ):
        env[secret_name] = ""
    env.update(
        {
            "A_STOCK_AGENTS_ROOT": str(ROOT),
            "A_STOCK_RUNTIME_MODE": "test",
            "A_STOCK_SERVER_HOST": "127.0.0.1",
            "A_STOCK_SERVER_PORT": str(port),
            "A_STOCK_DEFAULT_MODEL": "mock",
            "A_STOCK_CONFIG_PATH": str(config_path),
            "A_STOCK_DB_PATH": str(db_path),
            "A_STOCK_OUTPUT_DIR": str(output_dir),
            "A_STOCK_LOG_DIR": str(log_dir),
            "A_STOCK_TEMP_DIR": str(temp_dir),
            "A_STOCK_LOCAL_DIR": str(runtime_root / "local"),
            "A_STOCK_DATA_SYNC_SETTINGS_FILE": str(settings_path),
            "ASTOCK_LOG_TO_FILE": "false",
            "PYTHONPATH": os.pathsep.join((str(ROOT / "scripts"), str(ROOT))),
        }
    )
    server_log_path = log_dir / "server.log"
    server_log = server_log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("isolated_server.py")), "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                server_log.flush()
                raise RuntimeError(f"isolated server exited early; see {server_log_path}")
            try:
                status, health = _request_json(f"{base_url}/api/health")
                if status == 200 and health.get("status") == "ok":
                    break
            except OSError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError(f"isolated server did not become healthy; see {server_log_path}")

        status, login = _request_json(
            f"{base_url}/api/auth/login",
            method="POST",
            payload={"username": admin_phone, "password": admin_password},
        )
        if status != 200 or not login.get("token"):
            raise RuntimeError("ephemeral administrator could not authenticate")
        admin_token = login["token"]

        status, menus = _request_json(f"{base_url}/api/menus", token=admin_token)
        required_menu_codes = {"dashboard", "datasync", "selection", "selection.view", "selection.track"}
        menu_ids = [
            item["id"] for item in menus.get("menus", [])
            if item.get("code") in required_menu_codes
        ]
        if status != 200 or len(menu_ids) != len(required_menu_codes):
            raise RuntimeError("isolated browser role menus were not seeded")
        role_code = f"browser_e2e_{suffix}"
        status, created_role = _request_json(
            f"{base_url}/api/roles",
            method="POST",
            token=admin_token,
            payload={
                "code": role_code,
                "name": "Browser E2E 最小权限角色",
                "description": "ephemeral browser E2E role",
                "menu_ids": menu_ids,
            },
        )
        if status != 200 or not created_role.get("id"):
            raise RuntimeError("ephemeral least-privilege browser role could not be created")
        status, created = _request_json(
            f"{base_url}/api/users",
            method="POST",
            token=admin_token,
            payload={
                "username": user_phone,
                "name": "Browser E2E Researcher",
                "password": user_password,
                "role_id": created_role["id"],
                "remark": "ephemeral browser E2E identity",
            },
        )
        if status != 200 or created.get("status") != "ok":
            raise RuntimeError("ephemeral least-privilege browser user could not be created")

        yield BrowserRuntime({
            "base_url": base_url,
            "username": user_phone,
            "password": user_password,
            "db_path": db_path,
            "expected_menu_codes": sorted(required_menu_codes),
            "artifacts_dir": artifacts_dir,
            "server_log": server_log_path,
        })
    finally:
        try:
            if "admin_token" in locals():
                _request_json(f"{base_url}/api/auth/logout", method="POST", token=admin_token)
        except OSError:
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        server_log.close()
        keep_artifacts = _BROWSER_E2E_FAILED or os.getenv("A_STOCK_KEEP_BROWSER_ARTIFACTS") == "1"
        if keep_artifacts:
            evidence_base = Path(
                os.getenv("A_STOCK_BROWSER_ARTIFACT_DIR")
                or (ROOT / "temp" / "browser-e2e")
            ).resolve()
            evidence_dir = evidence_base / f"run-{suffix}-{secrets.token_hex(3)}"
            evidence_dir.mkdir(parents=True, exist_ok=False)
            if artifacts_dir.exists():
                shutil.copytree(artifacts_dir, evidence_dir / "artifacts")
            if server_log_path.exists():
                sanitized = _redact_browser_log(
                    server_log_path.read_text(encoding="utf-8", errors="replace"),
                    (admin_phone, user_phone, admin_password, user_password, locals().get("admin_token", "")),
                )
                (evidence_dir / "server.log").write_text(sanitized, encoding="utf-8")
            print(f"browser E2E sanitized evidence: {evidence_dir}")
        _remove_runtime_root(runtime_root)


@pytest.fixture(scope="session")
def edge_browser(isolated_browser_server):
    playwright = pytest.importorskip(
        "playwright.sync_api",
        reason="install the browser-test extra to run authenticated browser E2E",
    )
    with playwright.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch(
                channel="msedge",
                headless=True,
                args=[
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--no-first-run",
                ],
            )
        except Exception as exc:
            pytest.skip(f"system Microsoft Edge is unavailable to Playwright: {exc}")
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture()
def browser_page(edge_browser):
    context = edge_browser.new_context(
        viewport={"width": 1440, "height": 900},
        service_workers="block",
    )
    context.route(
        "**/*",
        lambda route: route.continue_()
        if _is_loopback_url(route.request.url)
        else route.abort("blockedbyclient"),
    )
    context.add_init_script(
        """
        (() => {
          const style = document.createElement('style');
          style.textContent = '*,*::before,*::after{animation:none!important;transition:none!important}';
          document.addEventListener('DOMContentLoaded', () => document.head.appendChild(style), {once:true});
        })();
        """
    )
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()
