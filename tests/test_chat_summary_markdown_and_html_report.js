/**
 * tests/test_chat_summary_markdown_and_html_report.js
 * 专属自动化测试套件：
 * 1. 会话摘要始终采用 Markdown 格式说明（彻底解决图 1 中大模型输出整屏原始 HTML 代码块与复制按钮问题）
 * 2. 按照用户意图最后生成的报告格式是 HTML（修改图 2 中错误的 report_300750_184672.md 为 .html）
 * 3. 点击后在工作台显示具体 HTML 页面报告（沙箱 iframe 注入纯净自包含 HTML）
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const vm = require('vm');

console.log('=== [验证：会话摘要 Markdown 纯净说明 & HTML 研报工作台页面渲染] ===\n');

// 1. 读取源码文件
const chatPresentationCode = fs.readFileSync(path.join(__dirname, '../web/js/chat_presentation.js'), 'utf-8');
const appJsCode = fs.readFileSync(path.join(__dirname, '../web/js/app.js'), 'utf-8');

// 2. 构造浏览器虚拟环境 (VM Sandbox)
const domStorage = {};
const mockElements = {
  rightContentScroll: { scrollTop: 0 },
  workspaceMarkdownBody: { style: { display: 'none' }, innerHTML: '' },
  workspaceHtmlContainer: { style: { display: 'none' } },
  workspaceHtmlFrame: { srcdoc: '' },
  workspaceSourceContainer: { style: { display: 'none' } },
  workbenchHeaderTitle: { innerText: '' },
  workbenchIconBadge: { innerText: '' },
  workbenchHeaderTag: { innerText: '' },
  docFilenameText: { innerText: '' },
  docStatusBadge: { innerText: '' },
  docFormatBadge: { innerText: '', className: '', style: {}, title: '' },
  docTypeBadge: { innerText: '' },
  docUpdatedTime: { innerText: '' },
  btnWorkspaceViewPreview: { classList: { add: () => {}, remove: () => {} } },
  btnWorkspaceViewSource: { classList: { add: () => {}, remove: () => {} } },
  btnWorkspaceOpenExternal: { style: {} },
  workspaceTocList: { innerHTML: '' }
};

const sandbox = {
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  Date: Date,
  RegExp: RegExp,
  Set: Set,
  Array: Array,
  Object: Object,
  String: String,
  Number: Number,
  Math: Math,
  JSON: JSON,
  localStorage: {
    getItem: (k) => domStorage[k] || null,
    setItem: (k, v) => { domStorage[k] = String(v); },
    removeItem: (k) => { delete domStorage[k]; }
  },
  document: {
    getElementById: (id) => mockElements[id] || null,
    querySelectorAll: () => []
  },
  location: { origin: 'http://localhost:8000', href: 'http://localhost:8000' },
  window: {},
  AppState: {
    activeRightTab: 'dashboard',
    deliverableCache: {},
    currentWorkbenchHtml: '',
    currentWorkbenchContent: ''
  },
  showToast: () => {},
  switchRightTab: () => {},
  toggleWorkbenchCollapse: () => {}
};
sandbox.window = sandbox;
sandbox.window.location = sandbox.location;

vm.createContext(sandbox);
vm.runInContext(chatPresentationCode, sandbox);

// 从 app.js 中提取与文档格式、交付物缓存及工作台展示相关的核心函数先注入沙箱
const coreFunctionsRegex = /function\s+extractHtmlHeadings[\s\S]*?window\.openDocumentInWorkbench\s*=\s*openDocumentInWorkbench;/;
const matchedFunctions = appJsCode.match(coreFunctionsRegex);
assert(matchedFunctions, '必须能从 app.js 匹配到工作台核心函数群');
vm.runInContext(matchedFunctions[0], sandbox);

const CP = sandbox.ChatPresentation;
assert(CP, 'ChatPresentation 模块必须成功加载');
assert.strictEqual(typeof CP.formatChatDialogueSummary, 'function', 'formatChatDialogueSummary 必须为函数');
assert.strictEqual(typeof CP.detectDeliverables, 'function', 'detectDeliverables 必须为函数');
assert.strictEqual(typeof sandbox.detectDocFormat, 'function', 'detectDocFormat 必须存在');
assert.strictEqual(typeof sandbox.renderHtmlToWorkspace, 'function', 'renderHtmlToWorkspace 必须存在');
assert.strictEqual(typeof sandbox.openDocumentInWorkbench, 'function', 'openDocumentInWorkbench 必须存在');

async function runTests() {
  console.log('--- 测试用例 1: 会话摘要始终采用 Markdown 格式说明（解决图 1 问题） ---');

  // 模拟图 1 中的真实场景：大模型输出包含了整份自包含 HTML 单文件代码块
  const mockModelOutputWithHtmlBlock = `HTML 报告工具当前能力受限 (CAPABILITY_NOT_IMPLEMENTED) ，我已获取全部真实行情与多维度研判数据，下面直接以自包含 HTML 单文件形式输出顶点软件投研报告。

\`\`\`html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>顶点软件(603383) — 分析报告</title>
</head>
<body>
<div class="header">
  <h1>顶点软件(603383) 分析报告</h1>
  <div class="stats">
    <div class="hstat"><div class="v">+45.20</div><div class="l">现价 (涨跌)</div></div>
    <div class="hstat"><div class="v">A</div><div class="l">综合评级</div></div>
    <div class="hstat"><div class="v">82/100</div><div class="l">策略评分</div></div>
  </div>
</div>
<div class="card">
  <table class="tbl">
    <tbody>
      <tr><td>动量趋势</td><td>22/25</td><td>均线多头排列良好</td></tr>
      <tr><td>筹码结构</td><td>21/25</td><td>筹码高度集中获利盘85%</td></tr>
    </tbody>
  </table>
  <span class="tag">积极增持</span>
</div>
<div class="card">
  <div class="level">
    <div class="ll">止损位</div><div class="lp">42.50</div><div class="ls">约 -5.9%</div>
  </div>
  <div class="level">
    <div class="ll">MA20</div><div class="lp">43.10</div>
  </div>
</div>
</body>
</html>
\`\`\`
`;

  const summaryHtml = CP.formatChatDialogueSummary(mockModelOutputWithHtmlBlock, {
    deliverableFilename: 'report_603383_184672.md', // 模拟初始被错误命名的 .md 文件
    deliverableTitle: '顶点软件量化投研报告'
  });

  // 断言 1.1：会话摘要中绝不能出现图 1 中的原始 HTML 代码块或复制按钮
  assert(!summaryHtml.includes('<code class="language-html">'), '会话摘要中绝不能出现 <code class="language-html"> 代码块');
  assert(!summaryHtml.includes('<!DOCTYPE html>'), '会话摘要中绝不能直接暴露原始 <!DOCTYPE html> 源码');
  assert(!summaryHtml.includes('class="code-block-copy-btn"'), '会话摘要中绝不能出现 HTML 代码块复制按钮');
  console.log('✅ PASS [用例 1.1]: 会话摘要彻底剥离 HTML 原始代码块与复制按钮');

  // 断言 1.2：会话摘要必须始终采用结构化 Markdown 说明
  assert(summaryHtml.includes('顶点软件'), '会话摘要必须包含标的名称顶点软件');
  assert(summaryHtml.includes('603383'), '会话摘要必须包含标的代码603383');
  assert(summaryHtml.includes('综合评级') || summaryHtml.includes('策略评分'), '会话摘要必须包含量化评级与评分说明');
  assert(summaryHtml.includes('实战交易三原则') || summaryHtml.includes('止损'), '会话摘要必须包含实战交易原则说明');
  assert(summaryHtml.includes('完整研报'), '会话摘要必须包含完整研报引导提示');
  console.log('✅ PASS [用例 1.2]: 会话摘要成功以纯正优雅的 Markdown 说明呈现');


  console.log('\n--- 测试用例 2: 交付物格式自动规范为 HTML（解决图 2 问题） ---');

  // 断言 2.1: 交付物列表不能是图 2 中的 .md 格式，必须规范为 .html
  assert(!summaryHtml.includes('report_603383_184672.md'), '图 2 中错误的 .md 格式必须被自动纠正');
  assert(summaryHtml.includes('.html'), '交付物超链必须为 .html 格式');
  assert(summaryHtml.includes('deliverable-html-item'), '交付物必须拥有 HTML 样式类名');
  assert(summaryHtml.includes('🌐'), '交付物必须带有 HTML 专属网页图标 🌐，绝非普通文档 📄');
  console.log('✅ PASS [用例 2.1]: 图 2 中报告格式错误成功修正为 .html 并呈现 🌐 图标');


  console.log('\n--- 测试用例 3: 工作台页面渲染与纯净 HTML 注入 ---');

  // 模拟用户点击超链，在工作台中打开生成的 HTML 报告
  const deliverablePathMatch = summaryHtml.match(/data-path="([^"]+\.html)"/);
  assert(deliverablePathMatch, '必须能从摘要中提取到 .html 交付物文件路径');
  const htmlDocPath = deliverablePathMatch[1];

  await sandbox.openDocumentInWorkbench(htmlDocPath);

  // 验证工作台是否以 HTML 沙箱 iframe 模式呈现具体页面
  assert.strictEqual(mockElements.workspaceHtmlContainer.style.display, 'flex', '工作台 HTML 视窗必须显示为 flex');
  assert.strictEqual(mockElements.workspaceMarkdownBody.style.display, 'none', '工作台 Markdown 视窗必须隐藏');
  assert(mockElements.workspaceHtmlFrame.srcdoc.includes('<!DOCTYPE html>'), '工作台 iframe 沙箱必须注入合法 HTML 内容');
  assert(!mockElements.workspaceHtmlFrame.srcdoc.startsWith('```html'), '注入 iframe 的 HTML 必须为纯净代码，绝不能被 markdown 代码块包裹');
  assert.strictEqual(mockElements.docFormatBadge.innerText, 'HTML', '文档格式徽章必须为 HTML');

  console.log('✅ PASS [用例 3]: 工作台成功通过 iframe 隔离渲染自包含 HTML 页面报告');

  console.log('\n🎉 所有 3 项核心需求测试用例 100% 全部通过！');
}

runTests().catch(err => {
  console.error('测试运行失败:', err);
  process.exit(1);
});
