const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(require('path').join(__dirname, '..', 'web', 'js', 'chat_presentation.js'), 'utf8');
const context = { window: {}, console };
vm.runInNewContext(source, context, { filename: 'chat_presentation.js' });
const api = context.window.ChatPresentation;
assert(api, 'ChatPresentation must be exported');

const html = api.renderMarkdown('# Title\n\n- **Strong** text\n- second\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```js\nconst x = 1;\n```\n\n> quoted\n\n1. first\n2. second\n\n`code` *em* [link](https://example.com)');
assert(/<h1>Title<\/h1>/.test(html));
assert(/<ul>[\s\S]*<strong>Strong<\/strong> text/.test(html));
assert(/<table>[\s\S]*<th>A<\/th>[\s\S]*<td>1<\/td>/.test(html));
assert(/<pre><code class="language-js">const x = 1;<\/code><\/pre>/.test(html));
assert(/<blockquote>quoted<\/blockquote>/.test(html));
assert(/<ol>[\s\S]*<li>first<\/li>/.test(html));
assert(/<code>code<\/code>[\s\S]*<em>em<\/em>[\s\S]*target="_blank"/.test(html));
const entities = api.renderMarkdown('`a < b` [q](https://example.com/?a=1&b=2)');
assert(entities.includes('<code>a &lt; b</code>'));
assert(entities.includes('href="https://example.com/?a=1&amp;b=2"'));
const nested = api.renderMarkdown('[`API`](https://example.com) [*em* label](https://example.com "title")');
assert(nested.includes('<a href="https://example.com" target="_blank" rel="noopener noreferrer"><code>API</code></a>'));
assert(nested.includes('<a href="https://example.com" title="title" target="_blank" rel="noopener noreferrer"><em>em</em> label</a>'));
const escapedLabel = api.renderMarkdown('[a & b](https://example.com) [`API`](https://example.com) [*API*](https://example.com) [<"x">](https://example.com)');
assert(escapedLabel.includes('>a &amp; b</a>'));
assert(!escapedLabel.includes('&amp;amp;'));
assert(escapedLabel.includes('><code>API</code></a>'));
assert(escapedLabel.includes('><em>API</em></a>'));
assert(escapedLabel.includes('>&lt;&quot;x&quot;&gt;</a>'));
const titledLink = api.renderMarkdown('[API](https://example.com "A & \\"quoted\\"")');
assert(titledLink.includes('title="A &amp; &quot;quoted&quot;"'));
assert(!nested.includes('\u0000'));
assert(!api.renderMarkdown('literal \u0000 text').includes('\u0000'));
assert.strictEqual(api.renderMarkdown('`\uE0000\uE001`'), '<p><code>\uE0000\uE001</code></p>');
assert.strictEqual(api.renderMarkdown('private \uE00017\uE001 and \uF8FF; nul \u0000 end'), '<p>private \uE00017\uE001 and \uF8FF; nul  end</p>');
const ordinaryBackslashes = String.raw`Path C:\Users\cvdnn and \alpha`;
assert.strictEqual(api.renderMarkdown(ordinaryBackslashes), '<p>Path C:\\Users\\cvdnn and \\alpha</p>');
assert.strictEqual(api.renderMarkdown(String.raw`\*literal\*`), '<p>*literal*</p>');
assert.strictEqual(api.renderMarkdown('`C:\\Users\\cvdnn`'), '<p><code>C:\\Users\\cvdnn</code></p>');
const adjacentTable = api.renderMarkdown('Introduction\n| A | B |\n|---|---|\n| 1 | 2 |');
assert(adjacentTable.includes('<p>Introduction</p>') && adjacentTable.includes('<table>'));
assert.strictEqual(api.renderMarkdown('ordinary\na | b\nlast'), '<p>ordinary<br>a | b<br>last</p>');
const paragraphThenTable = api.renderMarkdown('ordinary\nlast\na | b\n---|---\n1 | 2');
assert(paragraphThenTable.includes('<p>ordinary<br>last</p>\n<table>'));
assert(paragraphThenTable.includes('<th>a</th><th>b</th>'));
const compactTable = api.renderMarkdown('| A | B |\n|-|-|\n| x | y |');
assert(/<table>[\s\S]*<th>A<\/th>[\s\S]*<td>x<\/td>/.test(compactTable));

const unsafe = api.renderMarkdown('<img src=x onerror=alert(1)> [bad](javascript:alert(1)) [data](data:text/html,x)');
assert(!/<img|href="javascript:|href="data:/.test(unsafe));
assert(/&lt;img src=x onerror=alert\(1\)&gt;/.test(unsafe));

const summary = api.summarizeMarkdown('# 核心结论\n\n- First useful point\n- First useful point\n\n## 风险\n\nRisk item\n\n普通段落');
assert.strictEqual(JSON.stringify(summary), JSON.stringify(['First useful point', 'Risk item', '普通段落']));
assert.strictEqual(JSON.stringify(api.summarizeMarkdown('前置证据\n\n## 核心结论\n- 趋势偏弱\n- 严守止损\n\n## 详情\n补充说明')), JSON.stringify(['趋势偏弱', '严守止损']));
assert.strictEqual(JSON.stringify(api.summarizeMarkdown('普通证据\n## 核心结论\n谨慎买入')), JSON.stringify(['谨慎买入']));
assert.strictEqual(JSON.stringify(api.summarizeMarkdown('## 核心结论\n谨慎买入\n- 控制仓位')), JSON.stringify(['谨慎买入', '控制仓位']));
assert.strictEqual(JSON.stringify(api.summarizeMarkdown('> 风险较高')), JSON.stringify(['风险较高']));
assert.strictEqual(JSON.stringify(api.summarizeMarkdown('有意义的普通内容\n## 核心结论\n---')), JSON.stringify(['有意义的普通内容']));
assert.strictEqual(JSON.stringify(api.summarizeMarkdown('constructor\ntoString')), JSON.stringify(['constructor', 'toString']));
assert(!api.summarizeMarkdown('---\n|---|---|\n> 装饰').some((x) => /^-+$/.test(x) || /^\|/.test(x)));
assert(api.summarizeMarkdown('普通段落\n\n- list item\n\n```x\nnoise\n```').length >= 2);
assert(api.summarizeMarkdown('x'.repeat(500), 5)[0].length <= 120);

const redacted = api.redactSensitive('Authorization: Bearer abc123 api_key=secret token: xyz cookie=foo secret=bar Cookie: sid=one; theme=dark');
assert(!/abc123|=secret|: xyz|=foo|=bar|sid=one|theme=dark/.test(redacted));
assert(!/SECRET123|TOKEN123/.test(api.redactSensitive('{"api_key":"SECRET123","token":"TOKEN123"}')));
assert(!/SECRET123/.test(api.redactSensitive('{"Authorization":"Bearer SECRET123"}')));
assert(!/SECRET123/.test(api.redactSensitive("{'api_key': 'SECRET123'}")));
assert(!/SECRET123/.test(api.presentError({ code: 'OTHER', detail: '{"Authorization":"Bearer SECRET123"}' }).detail));
for (const credential of ['Authorization: Basic dXNlcjpwYXNz', '{"api_key":"prefix\\"SECRET_SUFFIX"}', 'api_key="two word secret"']) {
  assert(!/dXNlcjpwYXNz|SECRET_SUFFIX|two word secret/.test(api.redactSensitive(credential)));
  assert(!/dXNlcjpwYXNz|SECRET_SUFFIX|two word secret/.test(api.presentError({ code: 'OTHER', detail: credential }).detail));
}
for (const credential of [
  'Authorization: SECRET_SUFFIX\nnext: visible',
  'Authorization: Basic dXNlcjpwYXNz\nnext: visible',
  'Authorization: Bearer SECRET_SUFFIX trailing material\nnext: visible',
  'Authorization: Digest username="Mufasa", realm="test", nonce="SECRET_SUFFIX", opaque="more-secret"\nnext: visible',
  '{"api_key":"it\'s SECRET_SUFFIX"}',
  'api_key="prefix\\"SECRET_SUFFIX"',
  "{'api_key':'it\\'s SECRET_SUFFIX'}",
  "api_key='prefix\\'SECRET_SUFFIX'"
]) {
  const clean = api.redactSensitive(credential);
  assert(!/SECRET_SUFFIX|dXNlcjpwYXNz|Mufasa|more-secret/.test(clean), clean);
  assert(!/SECRET_SUFFIX|dXNlcjpwYXNz|Mufasa|more-secret/.test(api.presentError({ code: 'OTHER', detail: credential }).detail));
}
for (const authorization of [
  'Authorization: SECRET_SUFFIX',
  'Authorization: Basic dXNlcjpwYXNz',
  'Authorization: Bearer SECRET_SUFFIX trailing material',
  'Authorization: Digest username="Mufasa", realm="test", nonce="SECRET_SUFFIX", opaque="more-secret"'
]) {
  const expected = 'Authorization: [REDACTED]\nnext: visible';
  assert.strictEqual(api.redactSensitive(authorization + '\nnext: visible'), expected);
  assert.strictEqual(api.presentError({ code: 'OTHER', detail: authorization + '\nnext: visible' }).detail, expected);
}
for (const credential of [
  'x-api-key: sk-SECRET123',
  'x-api-key=SECRET123',
  '{"x-api-key":"SECRET123"}',
  'access_token: SECRET123',
  'access_token=SECRET123',
  '{"access_token":"SECRET123"}'
]) {
  assert(!api.redactSensitive(credential).includes('SECRET123'), credential);
  assert(!api.presentError({ code: 'OTHER', detail: credential }).detail.includes('SECRET123'), credential);
}

for (const code of ['LLM_NOT_CONFIGURED','LLM_AUTH_FAILED','LLM_MODEL_UNAVAILABLE','LLM_CAPABILITY_UNSUPPORTED','LLM_TIMEOUT','SSE_HTTP_ERROR','SSE_INCOMPLETE']) {
  const result = api.presentError({ code, detail: 'Authorization: Bearer leaked token=bad' });
  assert(result.title && result.recovery && result.code === code && !/leaked|bad/.test(JSON.stringify(result)));
}
assert.strictEqual(api.presentError({ code: 'LLM_NOT_CONFIGURED' }).title, '模型尚未配置');
assert.strictEqual(api.presentError({ code: 'toString' }).code, 'toString');
assert(/暂时|重试|联系|配置/.test(api.presentError({ code: 'OTHER', detail: '<script>x</script>' }).recovery));
assert.strictEqual(api.escapeHtml('&<>"\''), '&amp;&lt;&gt;&quot;&#39;');

// Verify that object detail does not render as [object Object]
const objErr1 = api.presentError({ code: 'LLM_MODEL_UNAVAILABLE', detail: { error: '模型请求失败', code: 'LLM_MODEL_UNAVAILABLE' } });
assert(!objErr1.detail.includes('[object Object]'), 'detail should not be [object Object]');
assert.strictEqual(objErr1.detail, '模型请求失败');

const objErr2 = api.presentError({ code: 'LLM_TIMEOUT', detail: { message: 'gateway timeout' } });
assert(!objErr2.detail.includes('[object Object]'), 'detail should not be [object Object]');
assert.strictEqual(objErr2.detail, 'gateway timeout');

// Reply state and execution timeline (Task 2)
const state = api.createResponseState('r1');
assert.strictEqual(state.status, 'streaming');
assert.strictEqual(state.detailTabId, 'chat-response-r1');
assert.strictEqual(Object.getPrototypeOf(state.toolResultsByCallId), null);
state.toolResultsByCallId.constructor = 'safe';
assert.strictEqual(state.toolResultsByCallId.constructor, 'safe');
api.applyEvent(state, 'thought', { content: '分析中' });
api.applyEvent(state, 'tool_call_start', { call_id: 'c1', skill_id: 'quote', action: 'get', args: { code: '600519' } });
api.applyEvent(state, 'tool_call_complete', { call_id: 'c1', status: 'success', data: { price: 100 } });
api.applyEvent(state, 'tool_call_start', { call_id: 'c2', skill_id: 'quote', action: 'get', args: { code: '600276' } });
api.applyEvent(state, 'tool_call_complete', { call_id: 'c2', status: 'unavailable', data: { reason: 'down' } });
assert.strictEqual(state.timelineNodes.filter((n) => n.type === 'tool').length, 2);
assert.strictEqual(state.timelineNodes.find((n) => n.callId === 'c1').status, 'succeeded');
assert.strictEqual(state.timelineNodes.find((n) => n.callId === 'c2').status, 'degraded');
assert.strictEqual(state.toolResultsByCallId.c1.price, 100);
assert.strictEqual(state.toolResultsByCallId.c2.reason, 'down');
assert.strictEqual(state.timelineNodes.filter((n) => n.type === 'thought')[0].summary, '分析中');

const repeated = api.createResponseState('repeat');
api.applyEvent(repeated, 'tool_call_start', { call_id: 'a', skill_id: 'same', action: 'x' });
api.applyEvent(repeated, 'tool_call_start', { call_id: 'b', skill_id: 'same', action: 'x' });
assert.notStrictEqual(repeated.timelineNodes[0].nodeId, repeated.timelineNodes[1].nodeId);
const missing = api.createResponseState('missing');
api.applyEvent(missing, 'tool_call_complete', { call_id: 'unknown', status: 'timeout', error: { code: 'LLM_TIMEOUT' } });
assert.strictEqual(missing.timelineNodes[0].status, 'failed');
assert.strictEqual(missing.timelineNodes[0].error.code, 'LLM_TIMEOUT');
const failed = api.createResponseState('failed');
api.applyEvent(failed, 'error', { code: 'LLM_TIMEOUT', detail: 'secret=bad' });
api.applyEvent(failed, 'done', { total_tokens: 3 });
assert.strictEqual(failed.status, 'failed');
assert.strictEqual(failed.timelineExpanded, true);
assert.strictEqual(failed.timelineNodes.find((n) => n.type === 'error').expanded, true);
const stream = api.createResponseState('stream');
api.applyEvent(stream, 'content_delta', { delta: 'hello ' });
api.applyEvent(stream, 'content_delta', { text: 'world' });
assert.strictEqual(stream.fullMarkdown, 'hello world');
api.applyEvent(stream, 'done', { total_tokens: 9, elapsed_ms: 42, finish_reason: 'stop' });
assert.strictEqual(stream.status, 'succeeded');
assert.strictEqual(stream.metrics.elapsedMs, 42);
assert.strictEqual(stream.metrics.tokens, 9);
assert.strictEqual(stream.metrics.finishReason, 'stop');
assert.strictEqual(stream.summaryItems.length, 1);
assert.strictEqual(stream.summaryItems[0], 'hello world');

const edge = api.createResponseState('edge');
api.applyEvent(edge, 'thought', { content: '   ' });
assert.strictEqual(edge.timelineNodes.length, 0);
api.applyEvent(edge, 'tool_call_start', { call_id: 'tool-1', skill_id: 'x' });
api.applyEvent(edge, 'thought', { content: 'thought-1' });
api.applyEvent(edge, 'tool_call_complete', { call_id: 'tool-1', status: 'confirmation_required' });
api.applyEvent(edge, 'tool_call_start', { skill_id: 'x' });
api.applyEvent(edge, 'tool_call_complete', { status: 'other_terminal', data: null });
api.applyEvent(edge, 'tool_call_complete', { call_id: 'bad', status: 'error', detail: 'failure' });
assert.strictEqual(edge.timelineNodes.filter((n) => n.type === 'tool')[0].status, 'degraded');
assert.strictEqual(edge.timelineNodes.filter((n) => n.type === 'tool')[1].status, 'degraded');
assert.strictEqual(edge.timelineNodes.filter((n) => n.type === 'tool')[2].status, 'failed');
assert.strictEqual(edge.timelineNodes.filter((n) => n.type === 'tool')[1].result, null);
assert(!edge.timelineNodes.some((n) => n.nodeId === 'tool-1' || n.nodeId === 'thought-1'));
const doneAgain = api.createResponseState('done-again');
api.applyEvent(doneAgain, 'content_delta', { content: 'first', unrelated: 'ignore' });
api.applyEvent(doneAgain, 'done', { total_tokens: 1 });
api.applyEvent(doneAgain, 'done', { total_tokens: 2 });
assert.strictEqual(doneAgain.fullMarkdown, 'first');
assert.strictEqual(doneAgain.timelineNodes.filter((n) => n.type === 'done').length, 1);
assert.strictEqual(doneAgain.metrics.tokens, 2);
const deterministicA = api.createResponseState('det');
const deterministicB = api.createResponseState('det');
api.applyEvent(deterministicA, 'thought', { content: 'x' });
api.applyEvent(deterministicB, 'thought', { content: 'x' });
assert.strictEqual(deterministicA.timelineNodes[0].nodeId, deterministicB.timelineNodes[0].nodeId);

const ordering = api.createResponseState('ordering');
api.applyEvent(ordering, 'tool_call_complete', { call_id: 'late', status: 'success', data: { x: 1 }, summary: 'late result' });
api.applyEvent(ordering, 'tool_call_start', { call_id: 'late', skill_id: 'skill', args: { mutable: true } });
assert.strictEqual(ordering.timelineNodes.filter((n) => n.type === 'tool').length, 1);
assert.strictEqual(ordering.timelineNodes[0].status, 'succeeded');
assert.strictEqual(ordering.timelineNodes[0].summary, 'late result');
api.applyEvent(ordering, 'tool_call_complete', { call_id: 'late', status: 'success', data: { x: 2 }, summary: 'updated' });
assert.strictEqual(ordering.timelineNodes.filter((n) => n.type === 'tool').length, 1);
assert.strictEqual(ordering.timelineNodes[0].result.x, 2);
const fallback = api.createResponseState('fallback');
api.applyEvent(fallback, 'tool_call_start', { skill_id: 'a', args: { nested: { ok: true } } });
api.applyEvent(fallback, 'tool_call_start', { skill_id: 'a', args: { nested: { ok: false } } });
assert.notStrictEqual(fallback.timelineNodes[0].nodeId, fallback.timelineNodes[1].nodeId);
const mutable = { deep: { value: 1 } };
api.applyEvent(fallback, 'tool_call_start', { call_id: 'snap', args: mutable });
mutable.deep.value = 9;
assert.strictEqual(fallback.timelineNodes[2].args.deep.value, 1);
const timed = api.createResponseState('timed');
api.applyEvent(timed, 'tool_call_start', { call_id: 'iso', started_at: '2026-09-11T00:00:00.000Z' });
api.applyEvent(timed, 'tool_call_complete', { call_id: 'iso', status: 'success', completed_at: '2026-09-11T00:00:01.250Z', summary: 'ok' });
assert.strictEqual(timed.timelineNodes[0].elapsedMs, 1250);
api.applyEvent(timed, 'tool_call_start', { call_id: 'badtime', started_at: 20 });
api.applyEvent(timed, 'tool_call_complete', { call_id: 'badtime', status: 'success', completed_at: 10 });
assert.strictEqual(timed.timelineNodes[1].elapsedMs, null);
const toolFailure = api.createResponseState('tool-failure');
api.applyEvent(toolFailure, 'tool_call_start', { call_id: 'timeout' });
api.applyEvent(toolFailure, 'tool_call_complete', { call_id: 'timeout', status: 'timeout', error: { code: 'LLM_TIMEOUT' } });
assert.strictEqual(toolFailure.status, 'streaming');
assert.strictEqual(toolFailure.timelineExpanded, true);
assert.strictEqual(toolFailure.timelineNodes[0].expanded, true);
const canonical = api.presentError({ error: 'provider timed out', code: 'LLM_TIMEOUT' });
assert.strictEqual(canonical.code, 'LLM_TIMEOUT');
assert(canonical.detail.includes('provider timed out'));
const lateTiming = api.createResponseState('late-timing');
api.applyEvent(lateTiming, 'tool_call_complete', { call_id: 'late-time', status: 'success', completed_at: '2026-09-11T00:00:01.250Z' });
api.applyEvent(lateTiming, 'tool_call_start', { call_id: 'late-time', skill_id: 'late-skill', started_at: '2026-09-11T00:00:00.000Z' });
assert.strictEqual(lateTiming.timelineNodes[0].elapsedMs, 1250);
const unmatchedMeta = api.createResponseState('unmatched-meta');
api.applyEvent(unmatchedMeta, 'tool_call_complete', { call_id: 'u1', skill_id: 'skill-u', action: 'act-u', title: 'Explicit', status: 'error', error: { code: 'OTHER' } });
assert.strictEqual(unmatchedMeta.timelineNodes[0].title, 'Explicit');
assert.strictEqual(unmatchedMeta.timelineNodes[0].skill_id, 'skill-u');
api.applyEvent(unmatchedMeta, 'tool_call_start', { call_id: 'u1', skill_id: 'better-skill', action: 'better-action', title: 'Better' });
assert.strictEqual(unmatchedMeta.timelineNodes[0].title, 'Better');
assert.strictEqual(unmatchedMeta.timelineNodes[0].skill_id, 'better-skill');
const collapse = api.createResponseState('collapse');
api.applyEvent(collapse, 'tool_call_start', { call_id: 'f1' });
api.applyEvent(collapse, 'tool_call_complete', { call_id: 'f1', status: 'error', error: { code: 'OTHER' } });
collapse.timelineNodes[0].expanded = false;
api.applyEvent(collapse, 'tool_call_complete', { call_id: 'f1', status: 'error', error: { code: 'OTHER' } });
assert.strictEqual(collapse.timelineNodes[0].expanded, false);
api.applyEvent(collapse, 'tool_call_start', { call_id: 'f2' });
api.applyEvent(collapse, 'tool_call_complete', { call_id: 'f2', status: 'failed', error: { code: 'OTHER' } });
assert.strictEqual(collapse.timelineNodes[1].expanded, false);
assert.strictEqual(collapse.timelineExpanded, true);
assert.strictEqual(api.applyEvent(api.createResponseState('empty-duration'), 'done', { elapsed_ms: '' }).metrics.elapsedMs, null);
const replay = api.createResponseState('replay');
api.applyEvent(replay, 'tool_call_complete', { call_id: 'elapsed', status: 'success', completed_at: 2000, elapsed_ms: 300 });
api.applyEvent(replay, 'tool_call_start', { call_id: 'elapsed', started_at: 1000 });
assert.strictEqual(replay.timelineNodes[0].elapsedMs, 300);
api.applyEvent(replay, 'tool_call_complete', { call_id: 'elapsed', status: 'error', error: { code: 'OTHER' }, data: { bad: true } });
assert.strictEqual(replay.timelineNodes[0].status, 'failed');
assert.strictEqual(replay.timelineNodes[0].result.bad, true);
assert.strictEqual(replay.toolResultsByCallId.elapsed.bad, true);
api.applyEvent(replay, 'tool_call_complete', { call_id: 'elapsed', status: 'success', data: { good: true }, summary: 'recovered' });
assert.strictEqual(replay.timelineNodes[0].status, 'succeeded');
assert.strictEqual(replay.timelineNodes[0].error, null);
assert.strictEqual(replay.timelineNodes[0].result.good, true);
assert.strictEqual(replay.timelineNodes[0].summary, 'recovered');
const errorReplay = api.createResponseState('error-replay');
api.applyEvent(errorReplay, 'tool_call_start', { call_id: 'e' });
api.applyEvent(errorReplay, 'tool_call_complete', { call_id: 'e', status: 'error', data: { code: 'OTHER', error: 'bad provider' } });
assert.strictEqual(errorReplay.timelineNodes[0].error.code, 'OTHER');
assert(errorReplay.timelineNodes[0].error.detail.includes('bad provider'));
api.applyEvent(errorReplay, 'tool_call_complete', { call_id: 'e', status: 'unavailable' });
assert.strictEqual(errorReplay.timelineNodes[0].error, null);
const sparseComplete = api.createResponseState('sparse-complete');
api.applyEvent(sparseComplete, 'tool_call_start', { call_id: 'sc', started_at: 1000 });
api.applyEvent(sparseComplete, 'tool_call_complete', { call_id: 'sc', status: 'success', completed_at: 2000, elapsed_ms: 300 });
api.applyEvent(sparseComplete, 'tool_call_complete', { call_id: 'sc', status: 'success' });
assert.strictEqual(sparseComplete.timelineNodes[0].completedAt, 2000);
assert.strictEqual(sparseComplete.timelineNodes[0].elapsedMs, 300);
const invalidElapsed = api.createResponseState('invalid-elapsed');
api.applyEvent(invalidElapsed, 'tool_call_start', { call_id: 'ie', started_at: 1000 });
api.applyEvent(invalidElapsed, 'tool_call_complete', { call_id: 'ie', status: 'success', completed_at: 2000, elapsed_ms: -5 });
assert.strictEqual(invalidElapsed.timelineNodes[0].elapsedMs, 1000);
const sparse = api.createResponseState('sparse');
api.applyEvent(sparse, 'tool_call_start', { call_id: 's', skill_id: 'skill', action: 'act', args: { x: 1 } });
api.applyEvent(sparse, 'tool_call_start', { call_id: 's' });
assert.strictEqual(sparse.timelineNodes[0].skill_id, 'skill');
assert.strictEqual(sparse.timelineNodes[0].action, 'act');
assert.strictEqual(sparse.timelineNodes[0].args.x, 1);
const terminalClear = api.createResponseState('terminal-clear');
api.applyEvent(terminalClear, 'tool_call_complete', { call_id: 'tc', status: 'failed', data: { diagnostic: true }, error: { code: 'OTHER' } });
api.applyEvent(terminalClear, 'tool_call_complete', { call_id: 'tc', status: 'success' });
assert.strictEqual(terminalClear.timelineNodes[0].result, null);
assert.strictEqual(Object.prototype.hasOwnProperty.call(terminalClear.toolResultsByCallId, 'tc'), false);
api.applyEvent(terminalClear, 'tool_call_complete', { call_id: 'tc', status: 'failed', data: { diagnostic: true }, error: { code: 'OTHER' } });
api.applyEvent(terminalClear, 'tool_call_complete', { call_id: 'tc', status: 'degraded' });
assert.strictEqual(terminalClear.timelineNodes[0].result, null);
assert.strictEqual(Object.prototype.hasOwnProperty.call(terminalClear.toolResultsByCallId, 'tc'), false);
api.applyEvent(terminalClear, 'tool_call_complete', { call_id: 'tc', status: 'failed', data: { diagnostic: true }, error: { code: 'OTHER' } });
api.applyEvent(terminalClear, 'tool_call_complete', { call_id: 'tc', status: 'failed' });
assert.strictEqual(terminalClear.timelineNodes[0].result.diagnostic, true);
const receivedTiming = api.createResponseState('received-timing');
api.applyEvent(receivedTiming, 'tool_call_start', { call_id: 'rt', started_at: 1000 });
api.applyEvent(receivedTiming, 'tool_call_complete', { call_id: 'rt', status: 'success', received_at: 1500 });
assert.strictEqual(receivedTiming.timelineNodes[0].elapsedMs, 500);

// --- 针对截图 Bug 的严格回归测试 ---
// 1. 验证 A 股股票数据（包含 code: '000001'）在 status: 'success' 时决不被误判为失败
const stockState = api.createResponseState('stock-quote-test');
api.applyEvent(stockState, 'tool_call_start', {
  call_id: 'quote-1',
  skill_id: 'astock_data_feed',
  title: '能力调用 astock_data_feed'
});
api.applyEvent(stockState, 'tool_call_complete', {
  call_id: 'quote-1',
  skill_id: 'astock_data_feed',
  status: 'success',
  summary: '现价 11.74 (-0.93%)',
  data: {
    code: '000001',
    name: '平安银行',
    price: 11.74,
    change_pct: -0.93,
    high: 11.86,
    low: 11.71,
    open: 11.82,
    prev_close: 11.85,
    turnover_pct: 0.43,
    pe: 5.24,
    market_cap: 2278.25,
    time: '20260911161454',
    skill_id: 'astock_data_feed',
    status: 'success'
  }
});
const node = stockState.timelineNodes.find(n => n.callId === 'quote-1');
assert.ok(node, '必须存在 quote-1 节点');
assert.strictEqual(node.status, 'succeeded', '成功返回股票行情时节点状态必须为 succeeded，绝不能为 failed');
assert.strictEqual(node.error, null, '节点 error 必须为 null');
assert.strictEqual(node.result.code, '000001');
assert.strictEqual(node.summary, '现价 11.74 (-0.93%)');

const htmlRendered = api.renderExecutionTimelineHtml(stockState);
assert.match(htmlRendered, /能力调用完成 astock_data_feed/, '必须渲染为能力调用完成');
assert.doesNotMatch(htmlRendered, /能力调用失败/, '绝不可渲染为能力调用失败');
assert.doesNotMatch(htmlRendered, /000001 · 请求失败/, '绝不可将股票代码误判为错误码输出请求失败');
assert.match(htmlRendered, /现价 11\.74 \(-0\.93%\)/, '必须正确展示行情摘要');

// 2. 验证即便发生真实错误，6位股票代码也绝对不可被当成错误代码输出
const stockErrState = api.createResponseState('stock-err-test');
api.applyEvent(stockErrState, 'tool_call_start', { call_id: 'err-1', skill_id: 'astock_data_feed' });
api.applyEvent(stockErrState, 'tool_call_complete', {
  call_id: 'err-1',
  status: 'error',
  data: { code: '000001', message: '数据源连接超时' }
});
const errNode = stockErrState.timelineNodes.find(n => n.callId === 'err-1');
assert.strictEqual(errNode.status, 'failed');
assert.notStrictEqual(errNode.error.code, '000001', '错误码绝对不能被设为股票代码 000001');
const errHtml = api.renderExecutionTimelineHtml(stockErrState);
assert.doesNotMatch(errHtml, /000001 · 请求失败/, '不可展示 000001 · 请求失败');

// 3. 验证流式推理思考内容平滑累加，杜绝拆分成数十个独立卡片
const streamThoughtState = api.createResponseState('thought-stream-test');
const thoughtDeltas = ['模型', '正在', '结合', '盘面', '特征', '分析', '大盘', '走势'];
for (const delta of thoughtDeltas) {
  api.applyEvent(streamThoughtState, 'thought', { content: delta });
}
assert.strictEqual(streamThoughtState.timelineNodes.length, 1, '多次流式 thought delta 必须累加至同一个思考节点');
assert.strictEqual(streamThoughtState.timelineNodes[0].summary, '模型正在结合盘面特征分析大盘走势');

// 测试长思考过程抽屉展示
const longThought = '用户再次提出全流程大盘行情深度研判诉求。结合当前深证成指与上证指数走势，准备调用底层量化引擎获取最新4级降级实时行情与技术形态指标，以便为用户生成严格符合实战三原则的操盘研报。';
const longThoughtState = api.createResponseState('thought-long-test');
api.applyEvent(longThoughtState, 'thought', { content: longThought });
// 4. 验证模型思考内容与过渡垫话不会在结果 Markdown 中展示
const rawPreambledReport = `我将先核查投资组合持仓数据（模拟账户 + 持仓池双通道），确认数据后再进行全景收益分析。

# 💼 投资组合全景收益分析 —— 执行报告

核查结果：❌ 当前账户为空仓状态，已终止收益分析`;

const cleanedReport = api.cleanMarkdownContent(rawPreambledReport);
assert.strictEqual(cleanedReport.startsWith('# 💼 投资组合全景收益分析'), true, '必须剥离工具调用前的思考垫话');
assert.strictEqual(cleanedReport.includes('我将先核查'), false, '清洗后正文绝不包含“我将先核查”');

// 验证 <think> 标签剥离
const thinkTaggedReport = `<think>用户要求评估持仓策略，先检查双通道数据。</think>
# 📋 持仓诊断执行报告

一、核查结果`;
const cleanedThinkReport = api.cleanMarkdownContent(thinkTaggedReport);
assert.strictEqual(cleanedThinkReport.startsWith('# 📋 持仓诊断执行报告'), true, '必须剥离 <think> 标签内容');
assert.strictEqual(cleanedThinkReport.includes('<think>'), false);
assert.strictEqual(cleanedThinkReport.includes('先检查双通道数据'), false);

// 5. 验证收到 tool_call_start 时清空 fullMarkdown 缓冲区
const toolStartState = api.createResponseState('pre-tool-clear-test');
api.applyEvent(toolStartState, 'content_delta', { text: '我将再次执行持仓核查...' });
assert.strictEqual(toolStartState.fullMarkdown, '我将再次执行持仓核查...');
api.applyEvent(toolStartState, 'tool_call_start', { call_id: 'c-test', skill_id: 'astock_pool_dashboard' });
assert.strictEqual(toolStartState.fullMarkdown, '', 'tool_call_start 必须重置 fullMarkdown 缓冲区');

// 6. 验证执行过程树形层级缩进框架 (Hierarchy & Tree Indentation Framework)
const planTree = api.decomposeTask('分析 600519 茅台并给出保本价与止损动作');
assert.ok(planTree.steps.length >= 3, '规划任务必须生成至少3个阶段步骤');
const execStep = planTree.steps.find(s => s.type === 'tool' || s.skill_id === 'astock-action-execution');
assert.ok(execStep, '必须包含动作执行与保本价精算工具节点');
assert.strictEqual(execStep.agentName, 'Action Execution Agent', '必须映射到 Action Execution Agent 子智能体');
assert.ok(Array.isArray(execStep.children) && execStep.children.length >= 2, '工具节点必须包含细化子步骤树');

// 验证树形 HTML 渲染：必须包含缩进容器、子智能体卡片与二级分支
const treeState = api.createResponseState('tree-test');
treeState.timelineNodes.push(execStep);
const treeHtml = api.renderExecutionTimelineHtml(treeState);

assert.match(treeHtml, /class="[^"]*timeline-branch-container[^"]*"/, '必须渲染 timeline-branch-container 树状缩进容器');
assert.match(treeHtml, /class="[^"]*subagent-node-card[^"]*"/, '必须渲染 subagent-node-card 子智能体卡片');
assert.match(treeHtml, /Action Execution Agent/, '必须展示子智能体名称');
assert.match(treeHtml, /class="[^"]*level-2-branch[^"]*"/, '必须渲染 level-2-branch 二级缩进导轨');
assert.match(treeHtml, /class="[^"]*step-summary-bar[^"]*"/, '必须渲染 step-summary-bar 步骤聚合摘要行');
assert.match(treeHtml, /class="[^"]*branch-toggle-btn[^"]*"/, '必须提供分支折叠/展开指示器');

// 验证分支折叠行为
const collapsedState = api.createResponseState('collapsed-tree-test');
const collapsedStep = Object.assign({}, execStep, { expanded: false });
collapsedState.timelineNodes.push(collapsedStep);
const collapsedHtml = api.renderExecutionTimelineHtml(collapsedState);
assert.match(collapsedHtml, /timeline-branch-container\s+collapsed/, '折叠时必须带有 collapsed 类名隐藏子树');
// 7. 验证在存在预设任务规划（末尾有 result 节点）时，流式 thought 增量绝不可被拆分成数十个独立卡片
const streamWithPlanState = api.createResponseState('stream-with-plan-test');
const taskPlan = api.decomposeTask('评估持股策略');
taskPlan.steps.forEach(s => streamWithPlanState.timelineNodes.push(Object.assign({}, s)));
const initialNodeCount = streamWithPlanState.timelineNodes.length;

// 模拟截图中触发 bug 的增量词片
const streamTokens = ['用户', '再次要求', '分析今日', '大盘', '行情。', '这是一个', '重复请求', '，但', '数据可能', '已经更新'];
for (const token of streamTokens) {
  api.applyEvent(streamWithPlanState, 'thought', { content: token });
}

// 验证：思考节点必须仅增加 1 个，绝不可拆分成 10 个！
const thoughtNodes = streamWithPlanState.timelineNodes.filter(n => n.type === 'thought');
assert.strictEqual(thoughtNodes.length, 1, '在存在预设计划时，流式思考必须聚合成 1 个节点，绝不可拆断成数十个卡片！');
assert.strictEqual(thoughtNodes[0].summary, '用户再次要求分析今日大盘行情。这是一个重复请求，但数据可能已经更新');

// 8. 验证连续多个同类工具调用（如截图中10个astock_data_feed）自动聚合为单智能体任务卡片
const batchToolsState = api.createResponseState('batch-tools-test');
const indexQuotes = [
  { code: '000001', name: '上证指数', price: '3888.11 (-1.18%)' },
  { code: '399001', name: '深证成指', price: '13471.26 (-1.08%)' },
  { code: '399006', name: '创业板指', price: '3322.04 (-0.49%)' },
  { code: '000688', name: '科创50', price: '4510.16 (-0.84%)' },
  { code: '000905', name: '中证500', price: '7580.54 (-1.78%)' },
  { code: '000852', name: '中证1000', price: '2465.84 (-1.45%)' }
];

indexQuotes.forEach((q, idx) => {
  api.applyEvent(batchToolsState, 'tool_call_start', { call_id: 'call_' + idx, skill_id: 'astock_data_feed' });
  api.applyEvent(batchToolsState, 'tool_call_complete', {
    call_id: 'call_' + idx,
    skill_id: 'astock_data_feed',
    status: 'success',
    summary: '现价 ' + q.price,
    data: { code: q.code, name: q.name }
  });
});

const batchHtml = api.renderExecutionTimelineHtml(batchToolsState);

// 断言：在 HTML 中绝不能出现 6 个平铺的独立一级卡片，而必须创建批量父任务卡片
assert.match(batchHtml, /能力调用astock_data_feed任务（批量6次调用）/, '必须生成标准格式的批量父任务标题（无【】包裹）');
assert(!batchHtml.includes('【能力调用'), '批量父任务标题无需包含【】括号');
assert.match(batchHtml, /Data Feed Agent/, '必须归属到同一个 Data Feed Agent 智能体卡片');
assert.match(batchHtml, /已聚合挂接 6 次子任务调用并汇总数据/, '必须包含批量聚合挂接子任务概要');
// 9. 验证批量子任务全部失败时的文案（必须显示全部执行失败，绝不能显示“并汇总数据”）
const allFailedBatchState = api.createResponseState('all-failed-batch');
['quote', 'tech', 'history'].forEach((act, idx) => {
  const callId = 'fail_call_' + idx;
  api.applyEvent(allFailedBatchState, 'tool_call_start', { call_id: callId, skill_id: 'astock_data_feed', args: { action: act, code: '000222' } });
  api.applyEvent(allFailedBatchState, 'tool_call_complete', {
    call_id: callId,
    skill_id: 'astock_data_feed',
    status: 'failed',
    summary: '调用失败',
    error: { error: 'DATA_UNAVAILABLE', detail: '未获取到目标股票数据' }
  });
});
const allFailedHtml = api.renderExecutionTimelineHtml(allFailedBatchState);
assert.match(allFailedHtml, /能力调用astock_data_feed任务（批量3次调用）/, '批量父任务标题正常生成');
assert.match(allFailedHtml, /已挂接 3 次子任务调用，全部执行失败/, '全失败时副标题必须显示全部执行失败');
assert(!allFailedHtml.includes('并汇总数据'), '全失败状态下绝严禁出现“并汇总数据”文案');

// 10. 验证内部错误码 CAPABILITY_EXECUTION_FAILED 不会以裸露前缀形式泄露
const rawErrState = api.createResponseState('raw-err-test');
api.applyEvent(rawErrState, 'tool_call_start', { call_id: 'err_call_1', skill_id: 'astock_platform_evaluate' });
api.applyEvent(rawErrState, 'tool_call_complete', {
  call_id: 'err_call_1',
  skill_id: 'astock_platform_evaluate',
  status: 'failed',
  error: { code: 'CAPABILITY_EXECUTION_FAILED', error: 'CAPABILITY_EXECUTION_FAILED', title: '能力执行失败' }
});
const rawErrHtml = api.renderExecutionTimelineHtml(rawErrState);
assert(!rawErrHtml.includes('CAPABILITY_EXECUTION_FAILED · 能力执行失败'), '内部错误码不得以裸露前缀拼接形式泄露');
assert.match(rawErrHtml, /能力执行失败/, '错误标题正常渲染');

console.log('PASS');





