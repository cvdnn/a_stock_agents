# Production Agent Platform P0 Implementation Plan

> **执行状态（2026-09-10）：已完成。** 原始步骤清单保留用于审计；实际证据见 `docs/specs/engineering/eng-remediation-acceptance.md` 及本轮六个提交。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make production mode fail closed: no runtime Mock selection, synthetic market/account/analysis success, leaked provider credentials, permissive default CORS, or inaccurate completion claims.

**Architecture:** Add an explicit runtime mode and typed LLM readiness failures at the server boundary, preserve Fake/Mock providers only in test mode, expose provider secrets only to backend execution, and make unfinished Skill/REST/UI paths return structured unavailable/error states. Keep business engines in `scripts/core/`; this P0 plan does not implement the P1 governed Skill adapter or DAG runtime.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLite, httpx MockTransport, pytest, browser-native JavaScript, Node `vm` tests.

---

### Task 1: Calibrate Specification Status Before Code Claims

**Files:**
- Create: `docs/specs/engineering/eng-remediation-acceptance.md`
- Create: `docs/audits/code-review-history.md`
- Modify: `docs/specs/README.md`
- Modify: the ten specs currently marked `Production Baseline | 100%`
- Modify: `docs/guidelines/code-review.md`
- Modify: `docs/guidelines/README.md`
- Test: `tests/test_docs_suite.py`

- [ ] **Step 1: Add a failing documentation-state test**

  Assert that the ten audited specs say `实施中`, `arch-token-security-gateway.md` remains RFC, the acceptance ledger contains all ten spec IDs and no future `PASS`, and every repository-local Markdown/code mapping used by the current guide exists.

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_docs_suite.py -q -p no:cacheprovider`

  Expected: FAIL because the ten specs still claim 100% production completion and the ledger/history files do not exist.

- [ ] **Step 3: Make the minimum documentation changes**

  Preserve the original completion statements in the audit history, change only the current status to `实施中`, create a ledger with columns `spec/original_claim/findings/tasks/code_paths/tests/current_status`, and turn `code-review.md` into current checkable rules linking to the archived report.

- [ ] **Step 4: Re-run the focused test and verify GREEN**

  Run the command from Step 2 and require zero failures.

- [ ] **Step 5: Commit**

  `git commit -m "docs: align specification status with audit evidence"`

### Task 2: Enforce Production Runtime Mode and LLM Readiness Errors

**Files:**
- Create: `scripts/server/llm/errors.py`
- Create: `scripts/server/llm/readiness.py`
- Modify: `scripts/server/config.py`
- Modify: `scripts/server/llm/factory.py`
- Modify: `scripts/server/agent/react_runner.py`
- Modify: `scripts/server/api/chat.py`
- Modify: `scripts/server/api/health.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_llm_readiness.py`
- Test: `tests/test_server_suite.py`

- [ ] **Step 1: Add failing runtime-mode and factory tests**

  Cover `A_STOCK_RUNTIME_MODE=production|test`; production rejects explicit `mock`, unknown models, disabled providers, missing model IDs/base URLs/required keys and never returns `MockLLMProvider`; test mode explicitly permits Mock/Fake. Assert stable codes `LLM_NOT_CONFIGURED`, `LLM_AUTH_FAILED`, `LLM_MODEL_UNAVAILABLE`, `LLM_CAPABILITY_UNSUPPORTED`, and `LLM_TIMEOUT`.

- [ ] **Step 2: Add failing chat-gate tests**

  Inject a Fake provider/readiness checker. Assert the selection order `turn override > session preference > chat role > system default`, tool-capability validation when tools are enabled, and zero tool calls when readiness fails. The SSE stream must emit one typed error and no success `done` event on gate failure.

- [ ] **Step 3: Run the focused tests and verify RED**

  Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_llm_readiness.py tests/test_server_suite.py -q -p no:cacheprovider`

  Expected: FAIL because production currently defaults/falls back to Mock and has no readiness contract.

- [ ] **Step 4: Implement the minimum fail-closed gate**

  Default runtime mode to `production`; default model remains a real configured identifier and is never inferred as Mock. Add `LLMReadinessError(code, message, provider_id, model_id)`, resolve provider configuration without silent fallback, and run the readiness check before any Skill/tool execution. Test mode is the sole path that can instantiate Mock.

- [ ] **Step 5: Re-run the focused tests and verify GREEN**

  Run the command from Step 3 and require zero failures.

- [ ] **Step 6: Commit**

  `git commit -m "fix: fail closed when production llm is not ready"`

### Task 3: Keep Provider Secrets on the Backend and Tighten CORS

**Files:**
- Modify: `scripts/server/db.py`
- Modify: `scripts/server/api/models_mgmt.py`
- Modify: `scripts/server/config.py`
- Modify: `scripts/server/app.py`
- Test: `tests/test_models_mgmt_security.py`
- Test: `tests/test_cors_security.py`

- [ ] **Step 1: Add failing secret-boundary tests**

  Store a provider containing a sentinel API key and sensitive custom headers. Assert GET/POST API bodies omit `api_key`, `Authorization`, `Cookie`, and `X-API-Key`, expose only `has_api_key`, preserve the existing key when an update omits/leaves the key empty, and clear it only through an explicit `clear_api_key` flag.

- [ ] **Step 2: Add failing connection-proxy tests**

  Require `provider_id` instead of browser-supplied `base_url/api_key`; assert the backend loads the saved secret, timeout bounds are enforced, redirects are not followed, malformed/private/metadata target URLs are rejected unless an explicit local-provider opt-in applies, and upstream bodies/secrets are not echoed in errors.

- [ ] **Step 3: Add failing CORS tests**

  Assert defaults contain no `*`, allow only explicit localhost development origins, set `allow_credentials=False`, reject `Origin: null` and `https://evil.example`, and echo an allowed origin exactly.

- [ ] **Step 4: Run the security tests and verify RED**

  Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_models_mgmt_security.py tests/test_cors_security.py -q -p no:cacheprovider`

- [ ] **Step 5: Implement public provider projection and secure proxy/CORS policy**

  Keep DB-internal provider records secret-bearing for the factory; add an API-boundary projection returning `has_api_key`; use omission/empty-string as “preserve existing”; resolve connection tests from `provider_id`; validate outbound URLs; remove wildcard origins and credentialed CORS defaults.

- [ ] **Step 6: Re-run the security tests and verify GREEN**

  Run the command from Step 4 and require zero failures.

- [ ] **Step 7: Commit**

  `git commit -m "fix: keep model provider credentials server side"`

### Task 4: Remove Fabricated Skill and REST Success (R2a/P0 Portion)

**Files:**
- Modify: `scripts/server/agent/tools.py`
- Modify: `scripts/server/agent/react_runner.py`
- Replace: `scripts/server/api/market_data.py`
- Create: `docs/specs/architecture/arch-skill-capability-acceptance.md`
- Test: `tests/test_capability_truthfulness.py`
- Test: `tests/test_market_data_api.py`
- Test: `tests/test_server_suite.py`

- [ ] **Step 1: Add failing handler truthfulness tests**

  Parameterize all 17 canonical Skills and legacy handlers. When a backend is absent or raises, require either explicit `status=error` or exact `{"status":"unavailable","error":"CAPABILITY_NOT_IMPLEMENTED","skill_id":"..."}`. Assert no fixed `active`, `simulated`, `passed`, `archived`, `ready`, IC `0.065`, 52/48 debate, default 10-yuan quote, 65/B score, or million-yuan account is emitted.

- [ ] **Step 2: Add failing runner status tests**

  Feed explicit success/error/unavailable/timeout results through a scripted provider. Assert status is preserved, only `success` can produce risk/report success events, failure summaries do not say “完成调用”, token counts are not fabricated, and a failed critical observation cannot be represented as a successful completion.

- [ ] **Step 3: Add failing REST authenticity tests**

  Replace tests that lock in fixed dashboard values. Require real empty states for empty pools/positions/monitor-not-running and structured `503` unavailable responses for endpoints without a canonical Skill backend; each success response must carry `source`, `fetched_at/as_of`, and non-synthetic evidence.

- [ ] **Step 4: Run focused tests and verify RED**

  Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_capability_truthfulness.py tests/test_market_data_api.py tests/test_server_suite.py -q -p no:cacheprovider`

- [ ] **Step 5: Implement fail-closed handlers and REST routes**

  Do not add new quantitative algorithms. Retain handlers with proven core backends, but stop before analysis when required data is missing. Mark reference-only knowledge as `type=reference`. For unfinished routes/Skills, return unavailable and document the missing backend/dependency in the 17-row acceptance ledger.

- [ ] **Step 6: Re-run focused tests and verify GREEN**

  Run the command from Step 4 and require zero failures.

- [ ] **Step 7: Commit**

  `git commit -m "fix: report unavailable capabilities without fabricated success"`

### Task 5: Remove Browser Mock Persistence and Silent Success Fallbacks

**Files:**
- Rewrite: `web/js/api.js`
- Modify: `web/js/app.js`
- Modify: `web/js/components/astock.js`
- Test: `tests/test_frontend_production_safety.js`
- Test: `tests/test_model_settings_security.js`

- [ ] **Step 1: Add failing API/SSE tests in a Node VM**

  Assert fetch rejection, HTTP failure, malformed SSE and server `error` events call `onError` exactly once and `onDone` zero times; `done` fires once only after a real success event. Assert `createSession` and chat do not default/pass `mock`.

- [ ] **Step 2: Add failing browser-secret tests**

  Seed legacy `astock_llm_providers` localStorage with sentinel secrets, initialize settings, and assert the entry is removed or sanitized immediately. Saving on both success and failure must never persist keys/sensitive headers; unchanged provider edits omit `api_key`; the password input is blank after save while `has_api_key` remains visible.

- [ ] **Step 3: Add failing UI fallback tests**

  Assert production chat, quick actions, Skill test, workbench loads and A2UI entry points cannot call template typewriters or timed synthetic success. Error/empty/unavailable/monitor-not-started states must replace stale success content. Static component defaults must not invent market values when properties are missing.

- [ ] **Step 4: Run Node tests and verify RED**

  Run: `node tests/test_frontend_production_safety.js` and `node tests/test_model_settings_security.js`.

- [ ] **Step 5: Implement strict browser transport and state rendering**

  Make `_fetchJSON` throw a structured error, remove all data-return fallbacks from `api.js`, make the real SSE path the only production chat path, handle error/done exactly once, remove localStorage provider persistence, use backend `provider_id` for test/fetch, and replace synthetic values with explicit empty/unavailable UI text.

- [ ] **Step 6: Verify JavaScript and existing operator behavior**

  Run: `node --check web/js/api.js`, `node --check web/js/app.js`, `node --check web/js/components/astock.js`, and `node tests/test_at_operator.js`.

- [ ] **Step 7: Commit**

  `git commit -m "fix: remove production browser mock fallbacks"`

### Task 6: Add a Production Authenticity Regression Gate

**Files:**
- Create: `tests/test_production_authenticity.py`
- Modify: `docs/specs/engineering/eng-remediation-acceptance.md`
- Modify: `docs/superpowers/specs/2026-09-10-production-agent-platform-design.md`

- [ ] **Step 1: Add a failing production-source scan**

  Scan production Python/JavaScript (excluding tests, explicit test fixtures and archived audit text) for forbidden runtime patterns: Mock factory fallback, production `model='mock'`, fixed dashboard/account/monitor success, template success fallback, fixed IC/debate ratios, or browser provider-secret persistence.

- [ ] **Step 2: Run the scan and verify RED before final cleanup**

  Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_production_authenticity.py -q -p no:cacheprovider`.

- [ ] **Step 3: Remove remaining production violations and record evidence**

  Fix only executable production paths; do not erase historical evidence. Mark each P0 ledger row with the exact commit, command and observed result. Keep unimplemented P1+ capabilities explicitly pending/unavailable.

- [ ] **Step 4: Run the complete P0 verification set**

  Run all new Python tests, the relevant existing server/governance/security tests, both new Node tests, `test_at_operator.js`, and `node --check` for every modified JavaScript file. Then run the full default offline pytest entry and report any pre-existing or out-of-scope failures separately.

- [ ] **Step 5: Commit**

  `git commit -m "test: enforce production authenticity gate"`

## Completion Boundary

P0 is complete only when production cannot instantiate Mock, model-not-ready requests execute no tools, provider secrets are absent from API/browser storage, default CORS is local and non-credentialed, unfinished capability/UI paths visibly fail or remain empty, the authenticity scan passes, and documentation states match evidence. This does **not** declare P1 governance, task DAG, MCP, multi-agent evidence isolation, or P6 workbench projection complete.
