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
            selectionPanels: ['.selection-model-list-card', '.selection-funnel-card', '.sel-property-drawer-card']
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
        models, funnel, drawer = audit["selectionPanels"]
        assert models["right"] <= funnel["right"]
        assert abs(funnel["left"] - drawer["left"]) <= 1
        assert abs(funnel["right"] - drawer["right"]) <= 1

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
    page.wait_for_function(
        "window.SelModels && !SelModels.store.get().loading && SelModels.store.get().selectionMode === 'runs'",
        timeout=15_000,
    )
    assert page.locator("#selRunWorkspace").is_visible()
    assert page.locator("#selEditWorkspace").is_hidden()
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


def test_selection_r0_v04_error_and_request_order_evidence(
    browser_page,
    isolated_browser_server,
) -> None:
    """R0 V-04：区分鉴权、业务拒绝和浏览器网络失败，并记录加载顺序。"""
    page = browser_page
    runtime = isolated_browser_server
    selection_responses = []

    def record_selection_response(response) -> None:
        path = urllib.parse.urlsplit(response.url).path
        if path.startswith("/api/selection-models"):
            selection_responses.append(
                {
                    "method": response.request.method,
                    "path": path,
                    "status": response.status,
                }
            )

    page.on("response", record_selection_response)
    page.goto(f"{runtime['base_url']}/ui/login.html", wait_until="domcontentloaded")
    anonymous = page.evaluate(
        """async () => {
          const response = await fetch('/api/selection-models', {credentials: 'same-origin'});
          const body = await response.json();
          return {status: response.status, message: body.detail || body.message || ''};
        }"""
    )
    assert anonymous["status"] == 401
    assert anonymous["message"]

    _login(page, runtime)
    page.locator('[data-tab="selection"]').click()
    page.locator("#pane-selection").wait_for(state="visible", timeout=10_000)
    page.locator("#selPurposeModels").click()
    page.wait_for_function(
        "ids => ids.every(id => document.querySelector(`[data-model-id=\"${id}\"]`))",
        arg=runtime["model_ids"],
        timeout=10_000,
    )

    selection_responses.clear()
    target_model_id = runtime["model_ids"][1]
    page.locator(f'[data-model-id="{target_model_id}"]').click()
    page.wait_for_function(
        "id => window.SelModels.store.get().activeModelId === id && "
        "window.SelModels.store.get().detail !== null",
        arg=target_model_id,
        timeout=10_000,
    )
    page.wait_for_load_state("networkidle")
    switched_paths = [item["path"] for item in selection_responses]
    detail_path = f"/api/selection-models/{target_model_id}"
    assert detail_path in switched_paths
    detail_index = switched_paths.index(detail_path)
    for suffix in ("/versions", "/runs", "/schedule"):
        assert switched_paths.index(detail_path + suffix) > detail_index

    forbidden = page.evaluate(
        """async () => {
          try {
            await window.SelModels.api.createModel({
              model_type: 'condition_tree', name: 'must-not-create', template: 'blank'
            });
            return {unexpected: true};
          } catch (error) {
            window.showToast(error.message);
            return {status: error.status, message: error.message, detail: error.detail};
          }
        }"""
    )
    assert forbidden["status"] == 403
    assert forbidden["message"]
    forbidden_page_text = page.locator("#toastContainer .toast").last.inner_text()
    assert forbidden_page_text.endswith(forbidden["message"])

    business_error = page.evaluate(
        """async () => {
          const response = await window.SelModels.api.getRun('r0-v04-missing-run');
          const node = document.createElement('div');
          window.SelModels.stateViews.error(node, response);
          return {
            httpSemantic: 'HTTP 200 business response',
            status: response.status,
            errorCode: response.error_code,
            message: response.message,
            renderedText: node.textContent
          };
        }"""
    )
    assert business_error["status"] == "error"
    assert business_error["errorCode"] == "MODEL_RUN_NOT_FOUND"
    assert business_error["message"] == business_error["renderedText"]

    failed_requests = []
    console_errors = []
    page.on(
        "requestfailed",
        lambda request: failed_requests.append(
            {"url": request.url, "failure": request.failure}
        ),
    )
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    network_url = f"{runtime['base_url']}/api/selection-models?evidence=r0-v04-network"
    page.route(network_url, lambda route: route.abort("failed"))
    network_error = page.evaluate(
        """async () => {
          try {
            await window.AStockAPI._fetchJSON('/api/selection-models?evidence=r0-v04-network');
            return {unexpected: true};
          } catch (error) {
            window.showToast(error.message);
            return {name: error.name, message: error.message};
          }
        }"""
    )
    page.wait_for_timeout(250)
    page.unroute(network_url)
    assert network_error["message"] == "Failed to fetch"
    assert any("evidence=r0-v04-network" in item["url"] for item in failed_requests)
    assert page.locator("#toastContainer .toast").last.inner_text().endswith("Failed to fetch")

    evidence = {
        "anonymous401": anonymous,
        "researcher403": {
            "status": forbidden["status"],
            "message": forbidden["message"],
            "pageText": forbidden_page_text,
        },
        "businessError": business_error,
        "networkFailure": {
            "error": network_error,
            "failedRequests": failed_requests,
            "consoleErrors": console_errors,
        },
        "modelSwitch": {
            "modelId": target_model_id,
            "responses": selection_responses,
        },
    }
    evidence_path = runtime["artifacts_dir"] / "selection-r0-v04-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_selection_r1_single_entry_and_visible_errors(browser_page, isolated_browser_server) -> None:
    """R1: SelModels owns refresh/search and keeps HTTP and business errors visible."""
    page = browser_page
    runtime = isolated_browser_server
    _login(page, runtime)
    page.locator('[data-tab="selection"]').click()
    page.locator("#selPurposeModels").click()
    page.wait_for_function(
        "ids => ids.every(id => document.querySelector(`[data-model-id=\"${id}\"]`))",
        arg=runtime["model_ids"],
        timeout=10_000,
    )


    assert page.locator("#selResultSearch").get_attribute("oninput") == \
        "SelModels.runWorkspace.search(this.value)"

    forbidden = page.evaluate(
        """async () => {
          try {
            await SelModels.api.createModel({model_type: 'funnel', name: 'denied'});
          } catch (error) {
            return {status: error.status, message: error.message};
          }
          return {status: 0};
        }"""
    )
    assert forbidden["status"] == 403
    assert forbidden["message"] in page.locator("#selSelectionError").inner_text()
    assert "[object Object]" not in page.locator("#selSelectionError").inner_text()

    business = page.evaluate("() => SelModels.api.getRun('r1-missing-run')")
    assert business["status"] == "error"
    assert business["error_code"] == "MODEL_RUN_NOT_FOUND"
    assert business["message"] in page.locator("#selSelectionError").inner_text()

    refresh = page.locator('button[onclick="SelModels.main.refresh()"]')
    refresh.click()
    page.wait_for_function("document.querySelector('#selSelectionError').hidden")
    page.wait_for_function(
        "ids => ids.every(id => document.querySelector(`[data-model-id=\"${id}\"]`))",
        arg=runtime["model_ids"],
        timeout=10_000,
    )
    page.wait_for_load_state("networkidle")

    list_url = f"{runtime['base_url']}/api/selection-models"
    page.route(
        list_url,
        lambda route: route.fulfill(
            status=401,
            content_type="application/json",
            body=json.dumps({"detail": {"error": "unauthorized", "message": "测试会话失效"}}),
        ),
    )
    refresh.click()
    page.get_by_text("HTTP 401：测试会话失效").wait_for(timeout=10_000)
    assert "测试会话失效" in page.locator("#selectionModelList").inner_text()
    page.wait_for_load_state("networkidle")
    page.unroute(list_url)

    page.route(list_url, lambda route: route.abort("failed"))
    refresh.click()
    page.get_by_text("Failed to fetch").first.wait_for(timeout=10_000)
    assert "Failed to fetch" in page.locator("#selectionModelList").inner_text()
    page.wait_for_load_state("networkidle")
    page.unroute(list_url)
    refresh.click()
    page.wait_for_function(
        "ids => ids.every(id => document.querySelector(`[data-model-id=\"${id}\"]`))",
        arg=runtime["model_ids"],
        timeout=10_000,
    )


def test_selection_r2_blank_builders_save_publish_and_conflict(browser_page, edge_browser, isolated_browser_server) -> None:
    """Two isolated blank models complete the editor path; a second context forces a stale save."""
    page = browser_page
    runtime = isolated_browser_server
    admin = {**runtime, "username": runtime["admin_username"], "password": runtime["admin_password"]}
    _login(page, admin)
    page.locator('[data-tab="selection"]').click()
    page.locator("#selPurposeModels").click()
    page.wait_for_function("SelModels.store.get().models.length >= 2 && !SelModels.store.get().detailLoading")

    created_ids = []
    for model_type, param_name in (("condition_tree", "period"), ("funnel", "lookback")):
        previous_id = page.evaluate("SelModels.store.get().activeModelId")
        page.locator('#pane-selection .selection-new-btn[onclick="SelModels.main.openWizard()"]',).click()
        page.locator("#selWizardType").select_option(model_type)
        page.locator("#selWizardName").fill(f"R2 浏览器空白 {model_type}")
        page.locator('button[onclick="SelModels.wizard.submit()"]',).click()
        page.wait_for_function(
            "({type, previous}) => !document.getElementById('selectionWizardModal') && SelModels.store.get().activeModelId !== previous && SelModels.store.get().workingDefinition?.model?.model_type === type && !SelModels.store.get().detailLoading",
            arg={"type": model_type, "previous": previous_id},
        )
        model_id = page.evaluate("SelModels.store.get().activeModelId")
        created_ids.append(model_id)
        assert page.locator("#selRuleLibrary .sel-rule-item").count() > 0
        page.locator(".sel-builder-item .sel-rule-chip").first.click()
        param = page.locator(f'#selPropertyDrawer [data-param="{param_name}"]')
        param.fill("30")
        page.locator('button[onclick="SelModels.propertyDrawer.apply()"]',).click()
        assert page.evaluate("SelModels.store.get().workingDefinition.groups?.[0].rules.length || SelModels.store.get().workingDefinition.stages?.[0].rules.length") == 1

        if model_type == "condition_tree":
            page.locator('button[onclick="SelModels.conditionEditor.addGroup()"]',).click()
            new_type, new_param, owner_key, expr_key = "rolling_high", "lookback", "groups", "condition"
        else:
            page.locator('button[onclick="SelModels.funnelEditor.addStage()"]',).click()
            new_type, new_param, owner_key, expr_key = "above_sma", "period", "stages", "funnel"
        assert page.locator(".sel-builder-item").count() == 2
        page.locator(f'#selRuleLibrary button[data-rule-type="{new_type}"]',).click()
        page.locator('button[onclick="SelModels.propertyDrawer.apply()"]',).click()
        new_id = page.evaluate("key => SelModels.store.get().workingDefinition[key][1].rules[0].id", owner_key)
        original_id = page.evaluate("key => SelModels.store.get().workingDefinition[key][0].rules[0].id", owner_key)
        page.locator(".sel-builder-item").nth(1).locator(".sel-rule-chip").click()
        page.locator('#selPropertyDrawer [data-param="id"]').fill(original_id)
        page.locator('button[onclick="SelModels.propertyDrawer.apply()"]',).click()
        page.get_by_text(f"规则 ID {original_id} 已存在", exact=False).first.wait_for(timeout=5_000)
        page.locator('#selPropertyDrawer [data-param="id"]').fill(new_id)
        page.locator(f'#selPropertyDrawer [data-param="{new_param}"]').fill("1")
        page.locator('button[onclick="SelModels.propertyDrawer.apply()"]',).click()
        assert page.locator(f'#selPropertyDrawer [data-param="{new_param}"]:invalid').count() == 1
        page.locator(f'#selPropertyDrawer [data-param="{new_param}"]').fill("30")
        page.locator('button[onclick="SelModels.propertyDrawer.apply()"]',).click()
        assert page.evaluate("key => SelModels.store.get().workingDefinition[key][1].rules.length", owner_key) == 1
        page.locator(f'[data-{expr_key}-expression="1"]').fill(json.dumps({"ref": new_id}))
        page.locator(f'button[onclick="SelModels.{"conditionEditor" if model_type == "condition_tree" else "funnelEditor"}.applyExpression(1)"]',).click()
        if model_type == "funnel":
            trigger = page.locator(".sel-builder-item").nth(1).locator('input[placeholder="HH:MM-HH:MM"]')
            trigger.fill("09:30-09:35")
            trigger.press("Tab")
        editor = "conditionEditor" if model_type == "condition_tree" else "funnelEditor"
        page.locator(f'button[onclick="SelModels.{editor}.move(1,-1)"]',).click()
        page.locator(f'button[onclick="SelModels.{editor}.move(0,1)"]',).click()
        enabled = page.locator(".sel-builder-item").nth(1).locator('input[type="checkbox"]').first
        enabled.uncheck()
        enabled = page.locator(".sel-builder-item").nth(1).locator('input[type="checkbox"]').first
        enabled.check()

        name = page.locator(".sel-builder-item .sel-inline-input").first
        name.fill("第一次编辑")
        name.press("Tab")
        page.locator('button[onclick="SelModels.main.saveDraft()"]',).click()
        page.wait_for_function("SelModels.store.get().draftRevision === 2 && !SelModels.store.get().dirty")
        name = page.locator(".sel-builder-item .sel-inline-input").first
        name.fill("第二次编辑")
        name.press("Tab")
        page.locator('button[onclick="SelModels.main.saveDraft()"]',).click()
        page.wait_for_function("SelModels.store.get().draftRevision === 3 && !SelModels.store.get().dirty")

        page.reload(wait_until="domcontentloaded")
        page.locator('[data-tab="selection"]').click()
        page.locator("#selPurposeModels").click()
        page.locator(f'[data-model-id="{model_id}"]').click()
        page.wait_for_function(
            "id => SelModels.store.get().activeModelId === id && !SelModels.store.get().detailLoading",
            arg=model_id,
        )
        assert page.locator(".sel-builder-item .sel-inline-input").first.input_value() == "第二次编辑"
        assert page.locator(".sel-builder-item").count() == 2
        page.locator('button[onclick="SelModels.main.validate()"]',).click()
        valid = page.evaluate("id => SelModels.api.validate(id)", model_id)
        assert valid["status"] == "ok", valid
        page.locator('button[onclick="SelModels.main.publish()"]',).click()
        page.wait_for_function(
            "async id => (await SelModels.api.listVersions(id)).data.versions.length === 1", arg=model_id,
        )
        page.locator('button[onclick="SelModels.main.openVersions()"]',).click()
        page.locator("#selectionVersionModal .sel-version-table .sel-mini-btn").first.click()
        page.wait_for_function(
            "async id => (await SelModels.api.listVersions(id)).data.active_version === 1", arg=model_id,
        )
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#selectionVersionModal .sel-version-table .sel-mini-btn").nth(1).click()
        page.wait_for_function("SelModels.store.get().draftBaseVersion === 1 && SelModels.store.get().draftRevision === 1")
        page.locator('button[onclick="SelModels.versionManager.close()"]',).first.click()
        editor = "conditionEditor" if model_type == "condition_tree" else "funnelEditor"
        remove = "removeGroup" if model_type == "condition_tree" else "removeStage"
        page.locator(f'button[onclick="SelModels.{editor}.{remove}(1)"]',).click()
        assert page.locator(".sel-builder-item").count() == 1
        page.locator('button[onclick="SelModels.main.saveDraft()"]',).click()
        page.wait_for_function("SelModels.store.get().draftRevision === 2 && !SelModels.store.get().dirty")

    model_id = created_ids[-1]
    other_context = edge_browser.new_context(service_workers="block")
    other_context.route("**/*", lambda route: route.continue_()
                        if urllib.parse.urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost"}
                        else route.abort("blockedbyclient"))
    try:
        other = other_context.new_page()
        _login(other, admin)
        other.locator('[data-tab="selection"]').click()
        other.locator("#selPurposeModels").click()
        other.locator(f'[data-model-id="{model_id}"]').click()
        other.wait_for_function("id => SelModels.store.get().activeModelId === id && !SelModels.store.get().detailLoading", arg=model_id)
        peer = other.evaluate("id => SelModels.api.getModel(id)", model_id)["data"]["draft"]
        peer["definition"]["stages"][0]["name"] = "并发窗口已保存"
        peer_saved = other.evaluate(
            "({id, draft}) => SelModels.api.saveDraft(id, draft.definition, draft.base_version, draft.draft_revision)",
            {"id": model_id, "draft": peer},
        )
        assert peer_saved["status"] == "ok", peer_saved
        name = page.locator(".sel-builder-item .sel-inline-input").first
        name.fill("过期窗口修改")
        name.press("Tab")
        page.locator('button[onclick="SelModels.main.saveDraft()"]',).click()
        page.get_by_text("草稿修订号冲突", exact=False).first.wait_for(timeout=10_000)
        assert page.evaluate("SelModels.store.get().dirty") is True
        current = page.evaluate("id => SelModels.api.getModel(id)", model_id)
        assert current["data"]["draft"]["definition"]["stages"][0]["name"] == "并发窗口已保存"
    finally:
        other_context.close()


def test_selection_new_run_uses_published_version_without_activation(browser_page, isolated_browser_server) -> None:
    """The simple selection flow sends the chosen published version without moving the active pointer."""
    page = browser_page
    runtime = isolated_browser_server
    admin = {**runtime, "username": runtime["admin_username"], "password": runtime["admin_password"]}
    _login(page, admin)
    page.locator('[data-tab="selection"]').click()
    page.wait_for_function("window.SelModels && !SelModels.store.get().loading")
    created = page.evaluate("""async () => {
      const model = await SelModels.api.createModel({model_type: 'condition_tree', name: '直接运行已发布模型', template: 'blank'});
      if (model.status !== 'ok') throw Error(JSON.stringify(model));
      const published = await SelModels.api.publish(model.data.model_id);
      if (published.status !== 'ok') throw Error(JSON.stringify(published));
      await SelModels.bootstrap();
      return model.data.model_id;
    }""")
    assert page.locator("#selPurposeRuns").get_attribute("aria-selected") == "true"
    assert page.locator("#selNewSelectionButton").is_enabled()
    page.locator('button[onclick="SelModels.main.openNewSelection()"]',).click()
    page.locator("#selNewSelectionModel").select_option(created)
    assert page.locator("#selNewSelectionVersion").input_value() == "1"
    with page.expect_response(lambda response: response.url.endswith(f"/api/selection-models/{created}/runs")) as response_info:
        page.locator("#selNewSelectionRun").click()
    body = response_info.value.json()
    assert body["error_code"] == "MODEL_DATA_MISSING"
    assert page.evaluate("id => SelModels.api.getModel(id)", created)["data"]["active_version"] is None
    assert "本地数据水位未就绪" in page.locator("#selNewSelectionStatus").inner_text()


def test_selection_r4_permissions_schedule_and_no_false_stop(browser_page, edge_browser, isolated_browser_server) -> None:
    page = browser_page
    runtime = isolated_browser_server
    admin = {**runtime, "username": runtime["admin_username"], "password": runtime["admin_password"]}
    _login(page, admin)
    page.locator('[data-tab="selection"]').click()
    page.locator("#selPurposeModels").click()
    model_id = runtime["model_ids"][0]
    page.locator(f'[data-model-id="{model_id}"]').click()
    page.wait_for_function("id => SelModels.store.get().activeModelId === id && !SelModels.store.get().detailLoading", arg=model_id)
    assert page.get_by_role("button", name="停止运行").count() == 0
    assert page.locator("#selDaemonState").inner_text() == "离线或未启动"
    page.locator('button[onclick="SelModels.main.openSchedule()"]',).click()
    page.locator("#selScheduleBody").get_by_text("守护进程：离线或未启动").wait_for()
    assert page.locator("#selSchedulePause").is_disabled()
    page.locator('button[onclick="SelModels.scheduler.close()"]',).click()
    assert page.evaluate("id => SelModels.api.publish(id, null, 1)", model_id)["status"] == "ok"
    assert page.evaluate("id => SelModels.api.activate(id, 1)", model_id)["status"] == "ok"
    page.evaluate("id => SelModels.detailLoader.load(id)", model_id)
    page.wait_for_function("SelModels.store.get().detail?.active_version === 1 && !SelModels.store.get().detailLoading")
    page.locator('button[onclick="SelModels.main.openSchedule()"]',).click()
    assert page.locator("#selSchedulePause").is_enabled()
    page.locator("#selSchedulePause").click()
    page.wait_for_function("SelModels.store.get().schedule?.paused === true")
    assert page.locator("#selPlanState").inner_text() == "已暂停"
    assert page.locator("#selDaemonState").inner_text() == "离线或未启动"
    page.locator('button[onclick="SelModels.scheduler.close()"]',).click()

    other_context = edge_browser.new_context(service_workers="block")
    other_context.route("**/*", lambda route: route.continue_()
                        if urllib.parse.urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost"}
                        else route.abort("blockedbyclient"))
    try:
        viewer = other_context.new_page()
        _login(viewer, runtime)
        viewer.locator('[data-tab="selection"]').click()
        viewer.locator("#selNewSelectionButton").wait_for(state="visible")
        assert viewer.locator("#selNewSelectionButton").is_disabled()
        viewer.locator("#selPurposeModels").click()
        viewer.locator(f'[data-model-id="{model_id}"]').click()
        viewer.wait_for_function("id => SelModels.store.get().activeModelId === id && !SelModels.store.get().detailLoading", arg=model_id)
        assert viewer.locator('[data-sel-action="publish"]').is_disabled()
        assert viewer.locator('[data-sel-action="rerun"]').is_disabled()
        viewer.locator('button[onclick="SelModels.main.openSchedule()"]',).click()
        viewer.locator("#selScheduleBody").get_by_text("守护进程：离线或未启动").wait_for()
        assert viewer.locator("#selSchedulePause").is_disabled()
        assert "仅管理员" in viewer.locator("#selSchedulePause").get_attribute("title")
        viewer.locator('button[onclick="SelModels.scheduler.close()"]',).click()
        viewer.locator('button[onclick="SelModels.main.openVersions()"]',).click()
        assert viewer.locator("#selectionVersionModal .sel-version-table .sel-mini-btn").first.is_disabled()
    finally:
        other_context.close()


def test_selection_r3_run_stage_filter_page_and_export(browser_page, isolated_browser_server) -> None:
    """An isolated admin reviews two runs and exports only the selected stage/filter."""
    page = browser_page
    runtime = isolated_browser_server
    admin = {**runtime, "username": runtime["admin_username"], "password": runtime["admin_password"]}
    _login(page, admin)
    page.locator('[data-tab="selection"]').click()
    page.wait_for_function("SelModels.store.get().models.length >= 2 && !SelModels.store.get().detailLoading")
    result = page.evaluate("""async () => {
      const created = await SelModels.api.createModel({model_type: 'condition_tree', name: 'R3 隔离运行', template: 'blank'});
      const id = created.data.model_id;
      const validated = await SelModels.api.validate(id);
      if (validated.status !== 'ok') throw Error(JSON.stringify(validated));
      const published = await SelModels.api.publish(id);
      if (published.status !== 'ok') throw Error(JSON.stringify(published));
      const activated = await SelModels.api.activate(id, 1);
      if (activated.status !== 'ok') throw Error(JSON.stringify(activated));
      const records = Array.from({length: 51}, (_, i) => ({
        code: String(600100 + i), name: i === 50 ? '末页候选' : undefined,
        closes: Array.from({length: 70}, (_, j) => j + 1),
      }));
      const first = await SelModels.api.createRun(id, {records});
      const second = await SelModels.api.createRun(id, {records: [
        {code: '600999', closes: Array.from({length: 70}, (_, j) => j + 1)}]});
      if (first.status !== 'ok' || second.status !== 'ok') throw Error('运行失败');
      await SelModels.detailLoader.load(id);
      return {id, first: first.data.run_id, second: second.data.run_id};
    }""")
    page.locator('button[onclick="SelModels.main.openRunTimeline()"]',).click()
    page.locator("#selRunList .sel-run-item").first.wait_for()
    assert result["first"] != result["second"]
    page.evaluate("id => SelModels.runTimeline.select(id)", result["second"])
    page.wait_for_function("document.querySelector('#selRunCandidateSummary')?.textContent.includes('共 1 条')")
    assert "600999" in page.locator("#selRunCandidateTrace").inner_text()
    page.evaluate("id => SelModels.runTimeline.select(id)", result["first"])
    page.wait_for_function("document.querySelector('#selRunCandidateSummary')?.textContent.includes('共 51 条')")
    assert "未提供（运行输入未附快照）" in page.locator("#selRunCandidateSummary").inner_text()
    assert page.locator("#selRunCandidateTrace tbody tr").count() == 50
    page.locator("#selRunNext").click()
    page.wait_for_function("document.querySelector('#selRunPage')?.textContent.includes('51–51 / 51')")
    assert "600150" in page.locator("#selRunCandidateTrace").inner_text()
    assert "未提供" in page.locator("#selRunCandidateTrace").inner_text()
    page.locator("#selRunKeyword").fill("末页候选")
    page.locator("#selRunSearch").click()
    page.wait_for_function("document.querySelector('#selRunPage')?.textContent.includes('1–1 / 1')")
    with page.expect_download() as download_info:
        page.locator("#selRunExport").click()
    download = download_info.value
    assert result["first"] in download.suggested_filename
    content = download.path().read_text(encoding="utf-8-sig")
    assert content.count("\n") == 2
    assert "600150" in content
    assert "600999" not in content


def test_selection_r5_inline_run_workspace_isolated_and_responsive(browser_page, isolated_browser_server) -> None:
    """R5: the visible funnel and candidate table stay bound to one persisted run."""
    page = browser_page
    runtime = isolated_browser_server
    admin = {**runtime, "username": runtime["admin_username"], "password": runtime["admin_password"]}
    _login(page, admin)
    page.locator('[data-tab="selection"]').click()
    page.wait_for_function("SelModels.store.get().models.length >= 2 && !SelModels.store.get().detailLoading")
    runs = page.evaluate("""async () => {
      const created = await SelModels.api.createModel({model_type: 'condition_tree', name: 'R5 隔离工作区', template: 'blank'});
      const id = created.data.model_id;
      const validated = await SelModels.api.validate(id);
      if (validated.status !== 'ok') throw Error(JSON.stringify(validated));
      const published = await SelModels.api.publish(id);
      if (published.status !== 'ok') throw Error(JSON.stringify(published));
      const activated = await SelModels.api.activate(id, 1);
      if (activated.status !== 'ok') throw Error(JSON.stringify(activated));
      const records = Array.from({length: 51}, (_, i) => ({
        code: String(600100 + i), name: i === 50 ? '末页候选' : undefined,
        closes: Array.from({length: 70}, (_, j) => j + 1),
      }));
      const first = await SelModels.api.createRun(id, {records});
      const second = await SelModels.api.createRun(id, {records: [
        {code: '600999', closes: Array.from({length: 70}, (_, j) => j + 1)}]});
      if (first.status !== 'ok' || second.status !== 'ok') throw Error('运行失败');
      await SelModels.detailLoader.load(id);
      return {id, first: first.data.run_id, second: second.data.run_id};
    }""")
    page.wait_for_function("document.querySelector('#selRunWorkspace') && !document.querySelector('#selRunWorkspace').hidden")
    page.locator("#selRunSelect").select_option(runs["second"])
    page.wait_for_function("document.querySelector('#selResultTotal')?.textContent === '1'")
    assert page.locator("#selRunSelect").input_value() == runs["second"]
    assert page.locator("#selRunFunnel .sel-run-stage").count() > 0
    assert "600999" in page.locator("#selResultBody").inner_text()
    page.locator("#selRunSelect").select_option(runs["first"])
    page.wait_for_function("document.querySelector('#selResultTotal')?.textContent === '51'")
    assert "600999" not in page.locator("#selResultBody").inner_text()
    assert page.locator("#selResultBody tr").count() == 50
    page.locator("#selResultNext").click()
    page.wait_for_function("document.querySelector('#selResultPage')?.textContent.includes('51–51 / 51')")
    assert "600150" in page.locator("#selResultBody").inner_text()
    page.locator("#selResultSearch").fill("末页候选")
    page.wait_for_function("document.querySelector('#selResultTotal')?.textContent === '1'")
    with page.expect_download() as download_info:
        page.locator("#selRunWorkspace button[onclick='SelModels.main.exportResults()']").click()
    download = download_info.value
    assert runs["first"] in download.suggested_filename
    assert download.path().read_text(encoding="utf-8-sig").count("\n") == 2
    page.locator("#selPurposeModels").focus()
    page.keyboard.press("Enter")
    assert page.locator("#selEditWorkspace").is_visible()
    assert page.locator("#selRunWorkspace").is_hidden()
    assert page.locator("#selRuleLibrary .sel-rule-item").count() > 0
    page.locator("#selPurposeRuns").click()
    page.set_viewport_size({"width": 680, "height": 900})
    page.wait_for_timeout(150)
    dimensions = page.evaluate("""() => {
      const element = document.querySelector('#selStagePanelWorkbench');
      return {scroll: element.scrollWidth, width: element.clientWidth};
    }""")
    assert dimensions["scroll"] <= dimensions["width"] + 1
    assert page.locator("#selRunSelect").input_value() == runs["first"]
