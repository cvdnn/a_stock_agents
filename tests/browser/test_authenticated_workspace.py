from __future__ import annotations

import json
import sqlite3
import struct
import urllib.parse
from contextlib import closing
from pathlib import Path

import pytest


pytestmark = [pytest.mark.browser_e2e, pytest.mark.slow, pytest.mark.subprocess]

VIEWPORTS = (
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
)
EXPECTED_OFFLINE_RESPONSES = {
    ("/api/portfolio/analysis", 503),
    ("/api/market/sentiment", 503),
    ("/api/market/ranks", 503),
}
EXPECTED_SANDBOX_ERROR = (
    "Service worker is disabled because the context is sandboxed "
    "and lacks the 'allow-same-origin' flag"
)


def _login(page, runtime) -> None:
    page.goto(f"{runtime['base_url']}/ui/login.html", wait_until="domcontentloaded")
    page.wait_for_function("window.AstockAuth && window.__ASTOCK_ME_RAW__ === null", timeout=10_000)
    page.locator("#loginPhone").fill(runtime["username"])
    page.locator("#loginPassword").fill(runtime["password"])
    page.locator("#loginSubmit").click()
    page.wait_for_url(f"{runtime['base_url']}/ui/", timeout=15_000)
    page.wait_for_function("!document.body.classList.contains('astock-auth-pending')", timeout=15_000)


def _track_page_failures(page) -> dict[str, list]:
    observed = {
        "consoleErrors": [],
        "failedRequests": [],
        "httpErrors": [],
        "pageErrors": [],
        "expectedOfflineResponses": [],
        "expectedSecurityErrors": [],
    }

    def record_console(message) -> None:
        if message.type != "error":
            return
        location_url = str((message.location or {}).get("url") or "")
        location_path = urllib.parse.urlsplit(location_url).path
        if (
            any(
                path == location_path and str(status) in message.text
                for path, status in EXPECTED_OFFLINE_RESPONSES
            )
            and "Failed to load resource" in message.text
        ):
            return
        observed["consoleErrors"].append(
            {"text": message.text, "url": location_url or None}
        )

    page.on("console", record_console)
    page.on(
        "requestfailed",
        lambda request: observed["failedRequests"].append(
            {"url": request.url, "failure": request.failure}
        ),
    )

    def record_http_error(response) -> None:
        # login.html probes /api/auth/me before credentials exist; that one 401
        # is the expected fail-closed state, not a workspace failure.
        if response.status == 401 and response.url.endswith("/api/auth/me"):
            return
        response_path = urllib.parse.urlsplit(response.url).path
        if (response_path, response.status) in EXPECTED_OFFLINE_RESPONSES:
            observed["expectedOfflineResponses"].append(
                {"url": response.url, "status": response.status}
            )
            return
        if response.status >= 400:
            observed["httpErrors"].append({"url": response.url, "status": response.status})

    page.on("response", record_http_error)

    def record_page_error(error) -> None:
        message = str(error)
        if EXPECTED_SANDBOX_ERROR in message:
            observed["expectedSecurityErrors"].append(message)
            return
        observed["pageErrors"].append(message)

    page.on("pageerror", record_page_error)
    return observed


def _assert_no_page_failures(observed: dict[str, list]) -> None:
    assert observed["failedRequests"] == []
    assert observed["httpErrors"] == []
    assert observed["consoleErrors"] == []
    assert observed["pageErrors"] == []
    assert all(
        (urllib.parse.urlsplit(item["url"]).path, item["status"])
        in EXPECTED_OFFLINE_RESPONSES
        for item in observed["expectedOfflineResponses"]
    )
    assert all(EXPECTED_SANDBOX_ERROR in item for item in observed["expectedSecurityErrors"])


def _layout_audit(page) -> dict:
    return page.evaluate(
        """() => {
          const app = document.getElementById('appContainer');
          return {
            path: location.pathname,
            authPending: document.body.classList.contains('astock-auth-pending'),
            viewport: {width: innerWidth, height: innerHeight},
            selectionPanels: ['.selection-funnel-card', '.selection-result-card', '.sel-property-drawer-card']
              .map(selector => document.querySelector(selector))
              .filter(el => el && el.offsetParent !== null)
              .map(el => {
                const rect = el.getBoundingClientRect();
                return {className: el.className, left: rect.left, right: rect.right, width: rect.width};
              }),
            appChildren: [...app.children].map(el => {
              const rect = el.getBoundingClientRect();
              const style = getComputedStyle(el);
              return {
                tag: el.tagName,
                id: el.id || null,
                className: el.className,
                left: rect.left,
                right: rect.right,
                width: rect.width,
                scrollWidth: el.scrollWidth,
                clientWidth: el.clientWidth,
                minWidth: style.minWidth,
                overflowX: style.overflowX,
                borderLeft: style.borderLeftWidth,
                borderRight: style.borderRightWidth
              };
            }),
            rightEdgeOverflow: [...document.querySelectorAll('body *')]
              .filter(el => el.offsetParent !== null && el.getBoundingClientRect().right > innerWidth + 1)
              .slice(0, 20)
              .map(el => {
                const rect = el.getBoundingClientRect();
                return {tag: el.tagName, id: el.id || null, className: el.className, right: rect.right, width: rect.width};
              }),
            overflow: [...document.querySelectorAll(
              'html,body,.app-header,.app-container,.right-pane.active,.datasync-console,' +
              '.datasync-tab-panel:not([hidden]),.selection-workbench-shell'
            )]
            .filter(el => el.offsetParent !== null && el.scrollWidth > el.clientWidth + 1)
            .map(el => ({
              tag: el.tagName,
              id: el.id || null,
              className: el.className,
              scrollWidth: el.scrollWidth,
              clientWidth: el.clientWidth
            }))
          };
        }"""
    )


def _assert_png_dimensions(path: Path, viewport: dict[str, int]) -> None:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (viewport["width"], viewport["height"])
    assert len(data) > 10_000


def _capture_scene(page, runtime, viewport, scene, observed) -> None:
    suffix = f"{viewport['width']}x{viewport['height']}"
    screenshot = runtime["artifacts_dir"] / f"{scene}-{suffix}.png"
    dom_snapshot = runtime["artifacts_dir"] / f"{scene}-{suffix}.html"
    audit_path = runtime["artifacts_dir"] / f"{scene}-{suffix}.json"
    audit = _layout_audit(page)
    audit.update(observed)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    assert audit["path"] == "/ui/"
    assert audit["authPending"] is False
    assert audit["overflow"] == []
    if scene == "authenticated-selection":
        assert len(audit["selectionPanels"]) == 3
        assert all(panel["width"] >= 240 for panel in audit["selectionPanels"])
        funnel, results, drawer = audit["selectionPanels"]
        assert abs(funnel["left"] - drawer["left"]) <= 1
        assert abs(results["right"] - drawer["right"]) <= 1

    page.screenshot(path=str(screenshot), full_page=False)
    dom_text = page.content()
    session_token = page.evaluate("() => localStorage.getItem('astock_access_token')")
    assert session_token
    assert session_token not in dom_text
    assert runtime["password"] not in dom_text
    dom_snapshot.write_text(dom_text, encoding="utf-8")
    _assert_png_dimensions(screenshot, viewport)


def test_invalid_password_stays_on_login(browser_page, isolated_browser_server) -> None:
    page = browser_page
    runtime = isolated_browser_server
    page.goto(f"{runtime['base_url']}/ui/login.html", wait_until="domcontentloaded")
    page.wait_for_function("window.AstockAuth && window.__ASTOCK_ME_RAW__ === null", timeout=10_000)
    page.locator("#loginPhone").fill(runtime["username"])
    page.locator("#loginPassword").fill("definitely-wrong-password")
    page.locator("#loginSubmit").click()
    page.locator("#loginError.show").wait_for(timeout=10_000)
    assert page.url.endswith("/ui/login.html")


def test_browser_context_blocks_non_loopback_requests(browser_page, isolated_browser_server) -> None:
    page = browser_page
    runtime = isolated_browser_server
    page.goto(f"{runtime['base_url']}/ui/login.html", wait_until="domcontentloaded")
    result = page.evaluate(
        """async () => {
          try {
            await fetch('https://example.com/browser-e2e-must-not-connect');
            return 'connected';
          } catch (error) {
            return 'blocked';
          }
        }"""
    )
    assert result == "blocked"


@pytest.mark.parametrize(
    "viewport",
    VIEWPORTS,
    ids=lambda value: f"{value['width']}x{value['height']}",
)
def test_authenticated_workspace_scenes(
    browser_page,
    isolated_browser_server,
    viewport,
) -> None:
    page = browser_page
    runtime = isolated_browser_server
    page.set_viewport_size(viewport)
    _login(page, runtime)
    observed = _track_page_failures(page)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("!document.body.classList.contains('astock-auth-pending')", timeout=15_000)
    me = page.evaluate("() => window.AstockAuth.fetchMe()")
    assert me["status"] == "ok"
    assert me["user"]["username"] == runtime["username"]
    assert me["user"]["is_super_admin"] is False
    assert {item["code"] for item in me["menus"]} == set(runtime["expected_menu_codes"])
    assert set(page.evaluate("() => window.AstockAuth.currentUser().menus")) == set(
        runtime["expected_menu_codes"]
    )
    assert page.locator('[data-tab="datasync"]').is_visible()
    assert not page.locator('[data-tab="market"]').is_visible()

    page.locator("#pane-dashboard").wait_for(state="visible", timeout=10_000)
    _capture_scene(page, runtime, viewport, "authenticated-dashboard", observed)

    page.locator('[data-tab="datasync"]').click()
    page.locator("#pane-datasync").wait_for(state="visible", timeout=10_000)
    page.locator('[data-datasync-tab="settings"]').click()
    page.locator("#datasync-panel-settings").wait_for(state="visible", timeout=10_000)
    _capture_scene(page, runtime, viewport, "authenticated-datasync-settings", observed)

    page.locator('[data-tab="selection"]').click()
    page.locator("#pane-selection").wait_for(state="visible", timeout=10_000)
    _capture_scene(page, runtime, viewport, "authenticated-selection", observed)
    _assert_no_page_failures(observed)


def test_refresh_logout_and_token_revocation(browser_page, isolated_browser_server) -> None:
    page = browser_page
    runtime = isolated_browser_server
    _login(page, runtime)
    observed = _track_page_failures(page)
    token = page.evaluate("() => localStorage.getItem('astock_access_token')")
    assert token

    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("!document.body.classList.contains('astock-auth-pending')", timeout=15_000)
    assert page.evaluate("() => window.AstockAuth.currentUser().username") == runtime["username"]
    page.wait_for_load_state("networkidle")
    _assert_no_page_failures(observed)

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#userGearBtn").click()
    with page.expect_response(
        lambda response: response.url.endswith("/api/auth/logout"),
        timeout=10_000,
    ) as logout_info:
        page.get_by_role("button", name="退出登录").click()
    assert logout_info.value.status == 200
    page.wait_for_url(f"{runtime['base_url']}/ui/login.html", timeout=10_000)
    assert page.evaluate("() => localStorage.getItem('astock_access_token')") is None
    revoked_response = page.request.get(
        f"{runtime['base_url']}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoked_response.status == 401
    assert page.url.endswith("/ui/login.html")
    screenshot = runtime["artifacts_dir"] / "logout-login-gate-1440x900.png"
    page.screenshot(path=str(screenshot), full_page=False)
    dom_text = page.content()
    assert runtime["password"] not in dom_text
    assert token not in dom_text
    _assert_png_dimensions(screenshot, {"width": 1440, "height": 900})


def test_expired_session_restores_login_gate(browser_page, isolated_browser_server) -> None:
    page = browser_page
    runtime = isolated_browser_server
    _login(page, runtime)
    token = page.evaluate("() => localStorage.getItem('astock_access_token')")
    assert token

    with closing(sqlite3.connect(runtime["db_path"])) as conn:
        conn.execute(
            "UPDATE auth_tokens SET expires_at = ? WHERE token = ?",
            ("2000-01-01T00:00:00+00:00", token),
        )
        conn.commit()

    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("document.body.classList.contains('astock-auth-pending')", timeout=15_000)
    page.locator("#astockLoginGate").wait_for(state="visible", timeout=10_000)
    assert page.evaluate("() => localStorage.getItem('astock_access_token')") is None
