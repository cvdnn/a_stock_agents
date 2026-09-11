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

const unsafe = api.renderMarkdown('<img src=x onerror=alert(1)> [bad](javascript:alert(1)) [data](data:text/html,x)');
assert(!/<img|href="javascript:|href="data:/.test(unsafe));
assert(/&lt;img src=x onerror=alert\(1\)&gt;/.test(unsafe));

const summary = api.summarizeMarkdown('# 核心结论\n\n- First useful point\n- First useful point\n\n## 风险\n\nRisk item\n\n普通段落');
assert.strictEqual(JSON.stringify(summary), JSON.stringify(['First useful point', 'Risk item', '普通段落']));
assert(api.summarizeMarkdown('普通段落\n\n- list item\n\n```x\nnoise\n```').length >= 2);
assert(api.summarizeMarkdown('x'.repeat(500), 5)[0].length <= 120);

const redacted = api.redactSensitive('Authorization: Bearer abc123 api_key=secret token: xyz cookie=foo secret=bar');
assert(!/abc123|=secret|: xyz|=foo|=bar/.test(redacted));

for (const code of ['LLM_NOT_CONFIGURED','LLM_AUTH_FAILED','LLM_MODEL_UNAVAILABLE','LLM_CAPABILITY_UNSUPPORTED','LLM_TIMEOUT','SSE_HTTP_ERROR','SSE_INCOMPLETE']) {
  const result = api.presentError({ code, detail: 'Authorization: Bearer leaked token=bad' });
  assert(result.title && result.recovery && !/leaked|bad/.test(JSON.stringify(result)));
}
assert(/暂时|重试|联系|配置/.test(api.presentError({ code: 'OTHER', detail: '<script>x</script>' }).recovery));
assert.strictEqual(api.escapeHtml('&<>"\''), '&amp;&lt;&gt;&quot;&#39;');
console.log('PASS');
