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
assert.deepStrictEqual(state.toolResultsByCallId.c1, { price: 100 });
assert.deepStrictEqual(state.toolResultsByCallId.c2, { reason: 'down' });
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
console.log('PASS');
