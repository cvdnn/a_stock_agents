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
assert(nested.includes('<a href="https://example.com" target="_blank" rel="noopener noreferrer"><em>em</em> label</a>'));
assert(!nested.includes('\u0000'));
assert(!api.renderMarkdown('literal \u0000 text').includes('\u0000'));
const adjacentTable = api.renderMarkdown('Introduction\n| A | B |\n|---|---|\n| 1 | 2 |');
assert(adjacentTable.includes('<p>Introduction</p>') && adjacentTable.includes('<table>'));
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

for (const code of ['LLM_NOT_CONFIGURED','LLM_AUTH_FAILED','LLM_MODEL_UNAVAILABLE','LLM_CAPABILITY_UNSUPPORTED','LLM_TIMEOUT','SSE_HTTP_ERROR','SSE_INCOMPLETE']) {
  const result = api.presentError({ code, detail: 'Authorization: Bearer leaked token=bad' });
  assert(result.title && result.recovery && result.code === code && !/leaked|bad/.test(JSON.stringify(result)));
}
assert.strictEqual(api.presentError({ code: 'LLM_NOT_CONFIGURED' }).title, '模型尚未配置');
assert.strictEqual(api.presentError({ code: 'toString' }).code, 'toString');
assert(/暂时|重试|联系|配置/.test(api.presentError({ code: 'OTHER', detail: '<script>x</script>' }).recovery));
assert.strictEqual(api.escapeHtml('&<>"\''), '&amp;&lt;&gt;&quot;&#39;');
console.log('PASS');
