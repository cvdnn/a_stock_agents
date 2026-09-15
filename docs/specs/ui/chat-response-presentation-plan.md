# Chat Response Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render safe Markdown, show a concise answer in each AI chat card, expose expandable child-task results, place task errors inside the execution timeline, and show the full response in the right workbench.

**Architecture:** Add a dependency-free `ChatPresentation` browser module for Markdown, summarization, redaction, error mapping, and reply/timeline state. Keep `app.js` as the DOM orchestration layer: it translates existing SSE callbacks into reply-state updates, renders the compact card, and creates one right-side detail pane per reply. CSS supplies the existing light visual language and accessible disclosure states.

**Tech Stack:** Browser-native HTML/CSS/JavaScript, existing SSE client in `web/js/api.js`, Node `assert`/`vm` regression tests, pytest production safety suite, in-app browser manual verification.

---

## File map

- Create `web/js/chat_presentation.js`: pure rendering, extraction, redaction, error mapping, and timeline state helpers exposed as `window.ChatPresentation`.
- Create `tests/test_chat_presentation.js`: executable unit tests for the pure module.
- Create `tests/test_chat_response_ui.js`: source/DOM-contract tests for card, timeline, details, errors, and accessibility.
- Modify `web/index.html`: load `chat_presentation.js` before `app.js`.
- Modify `web/js/app.js`: render reply cards, consume SSE events, bind disclosures, and mount/focus right-side reply panes.
- Modify `web/css/style.css`: Markdown, timeline, disclosure, details, responsive, focus, and reduced-motion styles.

### Task 1: Safe Markdown and deterministic summary module

**Files:**
- Create: `web/js/chat_presentation.js`
- Create: `tests/test_chat_presentation.js`

- [ ] **Step 1: Write failing Markdown, summary, redaction, and error mapping tests**

Create `tests/test_chat_presentation.js` with a VM sandbox that loads the new module and asserts the public contract:

```javascript
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('web/js/chat_presentation.js', 'utf8');
const sandbox = { window: {}, URL };
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const P = sandbox.window.ChatPresentation;

assert.ok(P);
const rendered = P.renderMarkdown('# 标题\n\n- **结论**\n\n|列|值|\n|-|-|\n|A|1|');
assert.match(rendered, /<h1>标题<\/h1>/);
assert.match(rendered, /<ul>[\s\S]*<strong>结论<\/strong>[\s\S]*<\/ul>/);
assert.match(rendered, /<table>[\s\S]*<td>1<\/td>[\s\S]*<\/table>/);
assert.doesNotMatch(P.renderMarkdown('<img src=x onerror=alert(1)>'), /<img/i);
assert.doesNotMatch(P.renderMarkdown('[x](javascript:alert(1))'), /javascript:/i);

assert.deepStrictEqual(
  Array.from(P.summarizeMarkdown('## 核心结论\n- 趋势偏弱\n- 严守止损\n\n## 详情\n很长的证据')),
  ['趋势偏弱', '严守止损']
);
assert.deepStrictEqual(Array.from(P.summarizeMarkdown('第一段结论。\n\n第二段证据。')), ['第一段结论。', '第二段证据。']);

assert.doesNotMatch(P.redactSensitive('Authorization: Bearer secret-token'), /secret-token/);
assert.strictEqual(P.presentError({ code: 'LLM_NOT_CONFIGURED' }).title, '模型尚未配置');
assert.strictEqual(P.presentError({ code: 'UNKNOWN', message: 'boom' }).code, 'UNKNOWN');
console.log('chat presentation helpers: PASS');
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `node tests/test_chat_presentation.js`

Expected: FAIL because `web/js/chat_presentation.js` does not exist.

- [ ] **Step 3: Implement the pure presentation module**

Create an IIFE with this complete public surface:

```javascript
(function initChatPresentation(global) {
  'use strict';

  const ERROR_MESSAGES = {
    LLM_NOT_CONFIGURED: ['模型尚未配置', '请先在系统设置中绑定并启用模型。'],
    LLM_AUTH_FAILED: ['模型认证失败', '请检查供应商密钥后重试。'],
    LLM_MODEL_UNAVAILABLE: ['模型当前不可用', '请检查模型 ID、服务地址和模型状态。'],
    LLM_CAPABILITY_UNSUPPORTED: ['模型能力不满足任务要求', '请选择支持当前能力的模型。'],
    LLM_TIMEOUT: ['模型请求超时', '请检查网络或稍后重试。'],
    SSE_HTTP_ERROR: ['无法连接 Agent 服务', '请确认服务已启动并检查服务状态。'],
    SSE_INCOMPLETE: ['响应意外中断', '请重新生成本次回复。']
  };

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function safeUrl(value) {
    try {
      const url = new URL(value, 'http://localhost');
      return ['http:', 'https:', 'mailto:'].includes(url.protocol) ? escapeHtml(value) : '#';
    } catch (_) { return '#'; }
  }

  function renderInline(value) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, label, href) =>
        `<a href="${safeUrl(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`);
  }

  function renderMarkdown(markdown) {
    return renderBlocks(String(markdown || '').replace(/\r\n?/g, '\n'));
  }

  function renderBlocks(markdown) {
    const lines = markdown.split('\n');
    const html = [];
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) { index += 1; continue; }
      if (/^```/.test(line)) {
        const language = line.slice(3).trim();
        const code = [];
        index += 1;
        while (index < lines.length && !/^```/.test(lines[index])) code.push(lines[index++]);
        if (index < lines.length) index += 1;
        html.push(`<pre><code class="language-${escapeHtml(language)}">${escapeHtml(code.join('\n'))}</code></pre>`);
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        const level = heading[1].length;
        html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        index += 1;
        continue;
      }
      if (index + 1 < lines.length && line.includes('|') && /^\s*\|?\s*:?-+/.test(lines[index + 1])) {
        const rows = [line];
        index += 2;
        while (index < lines.length && lines[index].includes('|') && lines[index].trim()) rows.push(lines[index++]);
        const cells = row => row.replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
        html.push(`<div class="markdown-table-wrap"><table><thead><tr>${cells(rows[0]).map(cell => `<th>${renderInline(cell)}</th>`).join('')}</tr></thead><tbody>${rows.slice(1).map(row => `<tr>${cells(row).map(cell => `<td>${renderInline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
        continue;
      }
      if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
        const ordered = /^\s*\d/.test(line);
        const items = [];
        const pattern = ordered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/;
        while (index < lines.length) {
          const match = lines[index].match(pattern);
          if (!match) break;
          items.push(`<li>${renderInline(match[1])}</li>`);
          index += 1;
        }
        const tag = ordered ? 'ol' : 'ul';
        html.push(`<${tag}>${items.join('')}</${tag}>`);
        continue;
      }
      if (/^>\s?/.test(line)) {
        const quote = [];
        while (index < lines.length && /^>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^>\s?/, ''));
        html.push(`<blockquote>${quote.map(renderInline).join('<br>')}</blockquote>`);
        continue;
      }
      const paragraph = [line];
      index += 1;
      while (index < lines.length && lines[index].trim() && !/^(#{1,6})\s|^```|^>|^\s*[-*+]\s+|^\s*\d+[.)]\s+/.test(lines[index])) paragraph.push(lines[index++]);
      html.push(`<p>${paragraph.map(renderInline).join('<br>')}</p>`);
    }
    return html.join('');
  }

  function stripMarkdown(value) {
    return String(value || '').replace(/^#{1,6}\s+/, '').replace(/^\s*(?:[-*+]|\d+[.)])\s+/, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/[*_`>#|]/g, '').trim();
  }

  function collectSectionItems(lines, headingPattern) {
    const result = [];
    let active = false;
    for (const line of lines) {
      const heading = line.match(/^#{1,6}\s+(.+)$/);
      if (heading) { active = headingPattern.test(heading[1]); continue; }
      if (active && line.trim()) result.push(stripMarkdown(line));
    }
    return result.filter(Boolean);
  }

  function collectMeaningfulItems(lines) {
    return lines.filter(line => line.trim() && !/^```|^\s*\|?\s*:?-+/.test(line)).map(stripMarkdown).filter(Boolean);
  }

  function uniqueClamped(items, limit, maxLength) {
    const seen = new Set();
    const result = [];
    for (const item of items) {
      const normalized = item.replace(/\s+/g, ' ').trim();
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      result.push(normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}…` : normalized);
      if (result.length >= limit) break;
    }
    return result;
  }

  function summarizeMarkdown(markdown, limit = 5) {
    const lines = String(markdown || '').split(/\r?\n/);
    const preferred = collectSectionItems(lines, /核心结论|结论|建议|风险|策略/);
    const fallback = collectMeaningfulItems(lines);
    return uniqueClamped(preferred.length ? preferred : fallback, limit, 120);
  }

  function redactSensitive(value) {
    return String(value == null ? '' : value)
      .replace(/(authorization\s*:\s*bearer\s+)[^\s,;]+/ig, '$1[REDACTED]')
      .replace(/((?:api[_-]?key|token|cookie|secret)\s*[=:]\s*)[^\s,;]+/ig, '$1[REDACTED]');
  }

  function presentError(error) {
    const code = error && error.code ? String(error.code) : 'UNKNOWN_ERROR';
    const mapped = ERROR_MESSAGES[code] || ['任务执行失败', '请展开诊断详情后重试。'];
    return { code, title: mapped[0], recovery: mapped[1], detail: redactSensitive(error && (error.message || error.error || error.detail || '')) };
  }

  global.ChatPresentation = { escapeHtml, renderMarkdown, summarizeMarkdown, redactSensitive, presentError };
})(window);
```

- [ ] **Step 4: Run the helper tests**

Run: `node tests/test_chat_presentation.js`

Expected: `chat presentation helpers: PASS`.

- [ ] **Step 5: Commit the pure module**

```bash
git add web/js/chat_presentation.js tests/test_chat_presentation.js
git commit -m "feat: add safe chat presentation helpers"
```

### Task 2: Reply state and expandable execution timeline

**Files:**
- Modify: `web/js/chat_presentation.js`
- Modify: `tests/test_chat_presentation.js`

- [ ] **Step 1: Add failing state-transition tests**

Append tests that create one reply, start two calls to the same skill, complete them independently, and record a model-level failure:

```javascript
const state = P.createResponseState('reply-1');
P.applyEvent(state, 'thought', { content: '规划分析步骤' });
P.applyEvent(state, 'tool_call_start', { call_id: 'c1', skill_id: 'astock-data-feed', action: 'quote' });
P.applyEvent(state, 'tool_call_complete', { call_id: 'c1', status: 'success', summary: '现价 1272.60', data: { price: 1272.6 } });
P.applyEvent(state, 'tool_call_start', { call_id: 'c2', skill_id: 'astock-data-feed', action: 'tech' });
P.applyEvent(state, 'tool_call_complete', { call_id: 'c2', status: 'unavailable', summary: '资金流不可用', data: { status: 'unavailable' } });
assert.strictEqual(state.timelineNodes.filter(node => node.type === 'tool').length, 2);
assert.strictEqual(state.timelineNodes.find(node => node.callId === 'c1').result.price, 1272.6);
assert.strictEqual(state.timelineNodes.find(node => node.callId === 'c2').status, 'degraded');

P.applyEvent(state, 'error', { code: 'LLM_TIMEOUT', message: 'timed out' });
assert.strictEqual(state.status, 'failed');
assert.strictEqual(state.timelineExpanded, true);
assert.strictEqual(state.timelineNodes.at(-1).type, 'error');
assert.strictEqual(state.timelineNodes.at(-1).expanded, true);
```

- [ ] **Step 2: Run and verify the missing API failure**

Run: `node tests/test_chat_presentation.js`

Expected: FAIL because `createResponseState` and `applyEvent` are undefined.

- [ ] **Step 3: Implement reply and timeline state**

Add and export:

```javascript
function createResponseState(responseId) {
  return {
    responseId, status: 'streaming', fullMarkdown: '', summaryItems: [],
    timelineNodes: [], toolResultsByCallId: Object.create(null), errors: [],
    detailTabId: `chat-response-${responseId}`, timelineExpanded: false,
    metrics: { elapsedMs: null, tokens: null, finishReason: null }
  };
}

function applyEvent(state, type, payload = {}) {
  if (type === 'content_delta') state.fullMarkdown += payload.text || payload.delta || payload.content || '';
  if (type === 'thought') appendThoughtNode(state, payload.content || payload.thought || '');
  if (type === 'tool_call_start') startToolNode(state, payload);
  if (type === 'tool_call_complete') completeToolNode(state, payload);
  if (type === 'error') failResponse(state, payload);
  if (type === 'done' && state.status !== 'failed') completeResponse(state, payload);
  return state;
}
```

Implement each private transition so `call_id` is the primary key, unmatched completions create a node, non-success terminal tool statuses map to `degraded` except explicit `error`/`timeout` which map to `failed`, and an error automatically expands the timeline and first error node.

- [ ] **Step 4: Run the state tests**

Run: `node tests/test_chat_presentation.js`

Expected: PASS.

- [ ] **Step 5: Commit timeline state**

```bash
git add web/js/chat_presentation.js tests/test_chat_presentation.js
git commit -m "feat: model chat execution timeline state"
```

### Task 3: Integrate the compact card, SSE events, and child-task results

**Files:**
- Modify: `web/index.html`
- Modify: `web/js/app.js`
- Create: `tests/test_chat_response_ui.js`

- [ ] **Step 1: Write failing UI contract tests**

Create a Node test that reads the three frontend files and checks the integration contract:

```javascript
const assert = require('assert');
const fs = require('fs');
const html = fs.readFileSync('web/index.html', 'utf8');
const app = fs.readFileSync('web/js/app.js', 'utf8');

assert.ok(html.indexOf('js/chat_presentation.js') < html.indexOf('js/app.js'));
for (const symbol of ['createAIResponseController', 'renderExecutionTimeline', 'renderResponseSummary', 'openChatResponseDetail']) {
  assert.ok(app.includes(`function ${symbol}`), `${symbol} must exist`);
}
assert.ok(app.includes("applyEvent(state, 'tool_call_start'"));
assert.ok(app.includes("applyEvent(state, 'tool_call_complete'"));
assert.ok(app.includes("applyEvent(state, 'error'"));
assert.ok(app.includes('aria-expanded'));
assert.ok(app.includes('timeline-node-result'));
assert.ok(!app.includes("contentBody.innerHTML = accumulatedText +"));
console.log('chat response UI contract: PASS');
```

- [ ] **Step 2: Run and verify failure**

Run: `node tests/test_chat_response_ui.js`

Expected: FAIL because the module is not loaded and integration functions do not exist.

- [ ] **Step 3: Load the presentation module before app.js**

Insert this script after `ui_engine.js` and before `app.js`:

```html
<script src="js/chat_presentation.js"></script>
```

- [ ] **Step 4: Replace the single status bubble with structured card regions**

Update the AI branch of `appendChatMessage` to render stable containers:

```html
<section class="execution-timeline" data-role="timeline" aria-label="任务执行情况">
  <button type="button" class="timeline-toggle" aria-expanded="false">
    <span data-role="timeline-summary">任务准备中</span>
    <span class="timeline-chevron" aria-hidden="true"></span>
  </button>
  <div class="timeline-nodes" data-role="timeline-nodes" hidden></div>
</section>
<div class="ai-content-body markdown-body" data-role="response-summary" aria-live="polite"></div>
<button type="button" class="response-detail-button" data-role="open-detail">查看完整分析</button>
```

Keep existing title, badges, copy, and regenerate actions. Escape title, summary, and operator labels through `ChatPresentation.escapeHtml` before interpolation.

- [ ] **Step 5: Add one controller per streamed response**

Implement `createAIResponseController(msgId)` to hold `ChatPresentation.createResponseState(msgId)` and DOM references. Implement `renderExecutionTimeline(controller)` with one semantic disclosure button per node. The node result must be rendered only into its own `.timeline-node-result`; text uses safe Markdown and objects use escaped JSON in `<pre><code>`.

Implement `renderResponseSummary(controller)` as:

```javascript
function renderResponseSummary(controller) {
  const items = ChatPresentation.summarizeMarkdown(controller.state.fullMarkdown);
  controller.state.summaryItems = items;
  const markdown = items.length ? items.map(item => `- ${item}`).join('\n') : '模型未返回文本内容。';
  controller.summaryElement.innerHTML = ChatPresentation.renderMarkdown(markdown);
}
```

Add delegated click handlers that toggle `hidden` and synchronize `aria-expanded` for the main timeline and every child-task result.

- [ ] **Step 6: Translate every SSE callback into a state event**

Replace overwrite-based status updates in `streamAIResponse` with:

```javascript
onThought: content => updateAIResponse(controller, 'thought', { content }),
onToolStart: data => updateAIResponse(controller, 'tool_call_start', data),
onToolComplete: data => updateAIResponse(controller, 'tool_call_complete', data),
onDelta: text => updateAIResponse(controller, 'content_delta', { text }),
onDone: data => updateAIResponse(controller, 'done', data),
onError: error => updateAIResponse(controller, 'error', normalizeStreamError(error))
```

On delta, update only the in-memory full text and an optional throttled right-side preview. On done, render the summary and final details. On error, render the timeline failure node and never render the successful completion label.

- [ ] **Step 7: Run UI and helper tests**

Run:

```bash
node tests/test_chat_presentation.js
node tests/test_chat_response_ui.js
node tests/test_frontend_production_safety.js
```

Expected: all print PASS and exit 0.

- [ ] **Step 8: Commit chat-card integration**

```bash
git add web/index.html web/js/app.js tests/test_chat_response_ui.js
git commit -m "feat: show expandable chat execution timeline"
```

### Task 4: Full Markdown and evidence in the right workbench

**Files:**
- Modify: `web/js/app.js`
- Modify: `tests/test_chat_response_ui.js`

- [ ] **Step 1: Extend the failing contract for one detail pane per reply**

Add assertions for `ensureChatResponseDetailPane`, `data-response-id`, the three detail sections, and reuse of `state.detailTabId`:

```javascript
for (const marker of ['ensureChatResponseDetailPane', 'data-response-id', '完整分析', '数据证据', '异常详情', 'state.detailTabId']) {
  assert.ok(app.includes(marker), `${marker} must be wired`);
}
```

- [ ] **Step 2: Run and verify failure**

Run: `node tests/test_chat_response_ui.js`

Expected: FAIL because the right-detail pane helpers are absent.

- [ ] **Step 3: Implement idempotent right-side detail panes**

`ensureChatResponseDetailPane(state, title)` must look up `pane-${state.detailTabId}` before creating a `.right-pane.chat-response-detail-pane`, append it to `#rightContentScroll`, and register `ViewHeaderInfo[state.detailTabId]`. Its markup contains tab buttons and panels for complete analysis, tool evidence, and conditional error details.

`renderChatResponseDetail(controller)` must:

```javascript
fullPanel.innerHTML = ChatPresentation.renderMarkdown(state.fullMarkdown || '正在生成完整分析…');
evidencePanel.innerHTML = renderToolEvidence(state.timelineNodes);
errorPanel.innerHTML = state.errors.length ? renderErrorDetails(state.errors) : '';
errorTab.hidden = state.errors.length === 0;
```

`openChatResponseDetail(responseId)` retrieves the controller, ensures/render the pane, calls `openRightTab(state.detailTabId, title, 'AI', true)`, and focuses the detail heading. Multiple clicks reuse the same pane and tab ID.

- [ ] **Step 4: Run frontend tests**

Run: `node tests/test_chat_response_ui.js && node tests/test_chat_presentation.js`

Expected: PASS.

- [ ] **Step 5: Commit right-side details**

```bash
git add web/js/app.js tests/test_chat_response_ui.js
git commit -m "feat: project full chat responses into workbench"
```

### Task 5: Unified light styling and accessibility

**Files:**
- Modify: `web/css/style.css`
- Modify: `tests/test_chat_response_ui.js`

- [ ] **Step 1: Add failing style and accessibility assertions**

Read `web/css/style.css` in the UI contract test and assert these selectors/tokens exist:

```javascript
const css = fs.readFileSync('web/css/style.css', 'utf8');
for (const selector of ['.markdown-body', '.execution-timeline', '.timeline-node-result', '.timeline-node.is-failed', '.chat-response-detail-pane', ':focus-visible', 'prefers-reduced-motion']) {
  assert.ok(css.includes(selector), `${selector} must be styled`);
}
assert.ok(css.includes('min-height: 44px'));
```

- [ ] **Step 2: Run and verify failure**

Run: `node tests/test_chat_response_ui.js`

Expected: FAIL because the new selectors do not exist.

- [ ] **Step 3: Add styles using existing semantic variables**

Add a focused section that provides:

- `.markdown-body` typography, headings, lists, blockquotes, code, and responsive table wrapper.
- `.execution-timeline` light surface and border matching existing cards.
- `.timeline-toggle` and child `.timeline-node-toggle` with 44px hit area and visible focus ring.
- `.timeline-node` status icon/label styles for running, succeeded, degraded, and failed.
- `.timeline-node-result` escaped JSON/Markdown result surface.
- `.timeline-node.is-failed` red border/background and readable text.
- `.chat-response-detail-pane` header, internal tabs, full report, evidence, and error sections.
- 150–300ms opacity/transform transitions without animating layout height.
- `@media (prefers-reduced-motion: reduce)` disabling nonessential animation.
- narrow-screen rules that keep page-level width stable and only scroll Markdown tables.

- [ ] **Step 4: Run UI tests**

Run: `node tests/test_chat_response_ui.js`

Expected: PASS.

- [ ] **Step 5: Commit styling**

```bash
git add web/css/style.css tests/test_chat_response_ui.js
git commit -m "style: unify chat timeline and markdown details"
```

### Task 6: Regression, production safety, and manual browser verification

**Files:**
- Modify only if failures reveal a defect in files already listed above.

- [ ] **Step 1: Run focused JavaScript regression tests**

Run:

```bash
node tests/test_chat_presentation.js
node tests/test_chat_response_ui.js
node tests/test_frontend_production_safety.js
node tests/test_model_role_defaults.js
node tests/test_model_settings_security.js
node tests/test_at_operator_null_safety.js
```

Expected: every process exits 0.

- [ ] **Step 2: Run Python production and live-server regressions**

Run:

```bash
uv run pytest tests/test_production_authenticity.py tests/test_llm_readiness.py tests/test_llm_stream_chunk_usage.py tests/test_live_server_e2e.py -q
```

Expected: all selected tests pass; environment-dependent live tests may report their existing explicit skips only.

- [ ] **Step 3: Run the full offline suite**

Run: `uv run pytest -q`

Expected: no failures.

- [ ] **Step 4: Restart the service on the established local port**

Stop only the known A-Stock Agents service process listening on `127.0.0.1:6300`, verify its executable/command belongs to this workspace, then start the documented development server on the same port. Do not terminate unrelated listeners.

- [ ] **Step 5: Verify the success path in the in-app browser**

Open `http://127.0.0.1:6300/`, submit a real configured-model prompt that produces headings, a list, a table, and at least one tool call, then verify:

- the chat card shows rendered Markdown summary rather than Markdown source;
- task history retains every child task;
- each child task expands to its own result;
- “查看完整分析” opens one reusable right-side pane with complete content and evidence;
- browser console has no new errors.

- [ ] **Step 6: Verify the failure path**

Use a safe, reversible invalid-model test configuration or a mocked local SSE test page, then verify the failure appears inside the same chat card timeline, auto-expands, exposes recovery guidance and redacted details, and never shows a success completion state. Restore the prior valid model configuration immediately after the check.

- [ ] **Step 7: Verify responsive and keyboard behavior**

Check desktop plus 768px and 375px viewports. Tab through main and child disclosures, open the detail pane with Enter/Space, and verify focus indicators, ARIA expansion state, no page-level horizontal scroll, and reduced-motion compatibility.

- [ ] **Step 8: Review and commit any verification fixes**

If verification required changes, rerun the failing command plus the focused JavaScript suite, then commit only the feature files:

```bash
git add web/index.html web/js/chat_presentation.js web/js/app.js web/css/style.css tests/test_chat_presentation.js tests/test_chat_response_ui.js
git commit -m "fix: harden chat response presentation"
```
