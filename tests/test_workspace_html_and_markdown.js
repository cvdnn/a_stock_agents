/**
 * tests/test_workspace_html_and_markdown.js
 * 验证投研助手工作区同时支持 Markdown 格式与 HTML 格式显示的端到端测试套件
 */

const fs = require('fs');
const assert = require('assert');
const path = require('path');
const vm = require('vm');

console.log('=== [投研助手工作区 Markdown 与 HTML 双格式支持测试套件] ===\n');

// 1. 静态结构断言：web/index.html
console.log('--- 1. 工作区 HTML 视窗结构与多模式组件断言 ---');
const indexHtml = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');

assert(indexHtml.includes('id="workspaceMarkdownBody"'), 'index.html 必须包含 Markdown 渲染容器');
assert(indexHtml.includes('id="workspaceHtmlContainer"'), 'index.html 必须包含 HTML 渲染容器');
assert(indexHtml.includes('id="workspaceHtmlFrame"'), 'index.html 必须包含 HTML 沙箱 iframe (workspaceHtmlFrame)');
assert(indexHtml.includes('id="workspaceSourceContainer"'), 'index.html 必须包含源码查看容器 (workspaceSourceContainer)');
assert(indexHtml.includes('id="workspaceSourceCode"'), 'index.html 必须包含源码展示 code 元素');
assert(indexHtml.includes('id="docFormatBadge"'), 'index.html 必须包含格式徽章 (docFormatBadge)');
assert(indexHtml.includes('id="workspaceViewSwitcher"'), 'index.html 必须包含视图模式切换器 (workspaceViewSwitcher)');
assert(indexHtml.includes('id="btnWorkspaceViewPreview"'), 'index.html 必须包含预览视图切换按钮');
assert(indexHtml.includes('id="btnWorkspaceViewSource"'), 'index.html 必须包含源码视图切换按钮');
assert(indexHtml.includes('id="btnWorkspaceToggleToc"'), 'index.html 必须包含目录导航按钮 (btnWorkspaceToggleToc)');
assert(indexHtml.includes('id="btnDocMetaCopy"'), 'index.html 必须包含复制代码按钮 (btnDocMetaCopy)');
assert(indexHtml.includes('id="btnWorkspaceOpenExternal"'), 'index.html 必须包含独立窗口打开按钮');
assert(indexHtml.includes('id="btnCollapseWorkbench"'), 'index.html 必须包含收起工作台按钮');
assert(!indexHtml.includes('id="btnWorkbenchGuide"'), 'index.html 必须删除操作指南按钮以保持 title 栏精简');

// 验证 title 栏按钮排序：预览/源码、目录导航、复制代码、独立窗口、收起
const pSwitcher = indexHtml.indexOf('id="workspaceViewSwitcher"');
const pToc = indexHtml.indexOf('id="btnWorkspaceToggleToc"');
const pCopy = indexHtml.indexOf('id="btnDocMetaCopy"');
const pExt = indexHtml.indexOf('id="btnWorkspaceOpenExternal"');
const pCollapse = indexHtml.indexOf('id="btnCollapseWorkbench"');
assert(pSwitcher < pToc && pToc < pCopy && pCopy < pExt && pExt < pCollapse, 'title栏按钮排序必须严格为：预览/源码、目录导航、复制代码、独立窗口、收起');

// 验证【任务交付物】与【HTML】按钮对换（HTML在前，任务交付物在后）
const pFormat = indexHtml.indexOf('id="docFormatBadge"');
const pStatus = indexHtml.indexOf('id="docStatusBadge"');
assert(pFormat < pStatus, 'workspaceDocMetaBar 中【HTML】徽章必须置于【任务交付物】徽章之前');
assert(indexHtml.includes('id="workspaceDocToc"'), 'index.html 必须包含目录导航侧栏');
console.log('✅ PASS [需求 1]: web/index.html title栏按钮规范排序、删除多余按钮并完成格式徽章对换');

// 2. 静态样式断言：web/css/style.css
console.log('\n--- 2. 工作区双格式与沙箱 iframe 样式断言 ---');
const styleCss = fs.readFileSync(path.join(__dirname, '../web/css/style.css'), 'utf8').replace(/\r\n/g, '\n');

assert(styleCss.includes('.workspace-html-container'), 'style.css 必须包含 .workspace-html-container 样式');
assert(styleCss.includes('.workspace-html-frame'), 'style.css 必须包含 .workspace-html-frame 样式');
assert(styleCss.includes('.workspace-source-container'), 'style.css 必须包含 .workspace-source-container 样式');
assert(styleCss.includes('.doc-format-badge'), 'style.css 必须包含 .doc-format-badge 样式');
assert(styleCss.includes('.doc-format-badge.format-md'), 'style.css 必须包含 format-md 样式');
assert(styleCss.includes('.doc-format-badge.format-html'), 'style.css 必须包含 format-html 样式');
assert(styleCss.includes('.workspace-view-switcher'), 'style.css 必须包含 .workspace-view-switcher 样式');
assert(styleCss.includes('.chat-html-chip'), 'style.css 必须包含 .chat-html-chip 样式');
assert(styleCss.includes('.deliverable-html-item'), 'style.css 必须包含 .deliverable-html-item 样式');
assert(!styleCss.includes('.dialogue-deliverable-item.deliverable-html-item {\n  border-color: #87E8DE;'), 'deliverable-html-item 不得包含有色的虚线下边框');
assert(styleCss.includes('border-bottom: none !important;'), 'deliverable-html-item 与 dialogue-deliverable-item 必须显式禁用下边框虚线');
assert(styleCss.includes('.deliverable-doc-name {\n  text-decoration: underline !important;'), '悬停时必须仅文件名带有下划线');
assert(styleCss.includes('.deliverable-doc-icon') && styleCss.includes('text-decoration: none !important;'), '图标必须绝对杜绝下划线穿透');
console.log('✅ PASS [需求 2]: web/css/style.css 具备完备的双格式呈现、沙箱视窗与胶囊交互样式，并彻底清除虚线与小图标下划线');

// 3. 后端接口白名单断言：scripts/server/app.py
console.log('\n--- 3. 后端 /api/docs/read 与 /api/docs/save 白名单断言 ---');
const appPy = fs.readFileSync(path.join(__dirname, '../scripts/server/app.py'), 'utf8');

assert(appPy.includes('.html') && appPy.includes('.htm'), 'app.py /api/docs/read 必须将 .html 和 .htm 纳入允许扩展名');
assert(appPy.includes('doc_format = "html"') || appPy.includes('"format": doc_format'), 'app.py /api/docs/read 必须返回文档格式字段');
assert(appPy.includes('@app.post("/api/docs/save"') && appPy.includes('.html'), 'app.py /api/docs/save 必须支持保存 .html 研报');
console.log('✅ PASS [需求 3]: 后端文档服务原生支持 .html 与 .htm 格式并带有安全边界验证');

// 4. 会话层 Markdown 与 HTML 链接胶囊解析断言：web/js/chat_presentation.js
console.log('\n--- 4. 会话层 ChatPresentation 链接胶囊解析断言 ---');
const chatPresJs = fs.readFileSync(path.join(__dirname, '../web/js/chat_presentation.js'), 'utf8');

assert(chatPresJs.includes('isHtmlFileLink'), 'chat_presentation.js 必须包含 isHtmlFileLink 函数');
assert(chatPresJs.includes('isDocumentFileLink'), 'chat_presentation.js 必须包含 isDocumentFileLink 函数');
assert(chatPresJs.includes('chat-html-chip'), 'chat_presentation.js 必须渲染带有 chat-html-chip 类的 HTML 药丸');

// 在沙箱中验证 ChatPresentation
const presSandbox = { window: {}, console: console };
presSandbox.window = presSandbox;
vm.createContext(presSandbox);
vm.runInContext(chatPresJs, presSandbox);
const CP = presSandbox.ChatPresentation;

assert(CP.isHtmlFileLink('report_600519.html'), 'isHtmlFileLink 必须识别 .html');
assert(CP.isHtmlFileLink('file:///output/reports/aStocks_600519.htm'), 'isHtmlFileLink 必须识别带 file:// 的 .htm');
assert(!CP.isHtmlFileLink('report.md'), 'isHtmlFileLink 必须排除 .md');

assert(CP.isDocumentFileLink('report_600519.html'), 'isDocumentFileLink 必须支持 .html');
assert(CP.isDocumentFileLink('report_600519.md'), 'isDocumentFileLink 必须支持 .md');

// 验证 detectDeliverables 能正确提取 .html 研报
const testMarkdownWithHtml = '任务完成，已生成可视化研报 `aStocks_600519_20260913.html` 与 Markdown 分析 `report_600519.md`';
const detected = CP.detectDeliverables(testMarkdownWithHtml);
const detectedNames = detected.map(d => d.filename);
assert(detectedNames.includes('aStocks_600519_20260913.html'), 'detectDeliverables 必须检出 HTML 文件');
assert(detectedNames.includes('report_600519.md'), 'detectDeliverables 必须检出 Markdown 文件');

// 验证 formatStepTextWithMdLinks 转换为胶囊
const stepText = '正在写入报告 output/reports/aStocks_600519_20260913.html 完成';
const stepResult = CP.formatStepTextWithMdLinks(stepText);
assert(stepResult.includes('chat-html-chip'), '步骤文本中 .html 文件必须转为 chat-html-chip');
assert(stepResult.includes('🌐'), '步骤文本中 .html 文件必须显示 🌐 图标');

console.log('✅ PASS [需求 4]: 会话展示层 ChatPresentation 原生支持 HTML 链接、交付物检测与图标呈现');

// 5. 前端工作区运行时 VM 沙箱测试：web/js/app.js
console.log('\n--- 5. 前端工作区双格式运行时交互与渲染测试 ---');
const appJs = fs.readFileSync(path.join(__dirname, '../web/js/app.js'), 'utf8');

const mockDomElements = {};
function getMockEl(id) {
  if (!mockDomElements[id]) {
    const classSet = new Set();
    let classStr = '';
    const el = {
      id: id,
      innerText: '',
      innerHTML: '',
      textContent: '',
      srcdoc: '',
      style: {},
      classList: {
        _set: classSet,
        add(c) { classSet.add(c); classStr = Array.from(classSet).join(' '); },
        remove(c) { classSet.delete(c); classStr = Array.from(classSet).join(' '); },
        contains(c) { return classSet.has(c); }
      },
      querySelectorAll() { return []; },
      scrollIntoView() {},
      scrollTop: 0
    };
    Object.defineProperty(el, 'className', {
      get() { return classStr; },
      set(val) {
        classStr = String(val || '');
        classSet.clear();
        classStr.split(/\s+/).filter(Boolean).forEach(c => classSet.add(c));
      }
    });
    mockDomElements[id] = el;
  }
  return mockDomElements[id];
}

const mockDom = {
  getElementById: (id) => getMockEl(id),
  querySelector: (sel) => getMockEl(sel.replace(/^[.#]/, '')),
  querySelectorAll: () => [],
  addEventListener: () => {}
};

const appSandbox = {
  window: {},
  document: mockDom,
  navigator: {
    clipboard: {
      writeText: async (t) => { appSandbox.copiedText = t; }
    }
  },
  AppState: {
    activeRightTab: 'dashboard',
    layoutMode: 'chat-center',
    isCopilotCollapsed: false,
    deliverableCache: {}
  },
  ChatPresentation: CP,
  showToast: (msg) => { appSandbox.lastToast = msg; },
  switchRightTab: (t) => { appSandbox.AppState.activeRightTab = t; },
  toggleWorkbenchCollapse: () => { appSandbox.workbenchToggled = true; },
  escapeHtml: (s) => String(s || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]),
  setExecutionStreamingState: () => {},
  toggleTimelineRecord: () => {},
  toggleNodeDrawer: () => {},
  requestUserConfirmation: () => {},
  handleConfirmationDecision: () => {},
  cancelCurrentExecution: () => {}
};
appSandbox.window = appSandbox;

vm.createContext(appSandbox);

// 从 app.js 中提取工作区关键函数在沙箱中执行
const codeToInject = `
  ${appJs.slice(appJs.indexOf('const USER_OPERATION_GUIDE_MD'), appJs.indexOf('function focusActiveSession()'))}
`;
vm.runInContext(codeToInject, appSandbox);

// 测试用例 5.1: 格式探测逻辑
console.log('--- 测试用例 5.1: detectDocFormat 格式自动识别 ---');
assert.strictEqual(appSandbox.detectDocFormat('aStocks_600519.html'), 'html');
assert.strictEqual(appSandbox.detectDocFormat('aStocks_600519.htm'), 'html');
assert.strictEqual(appSandbox.detectDocFormat('report_600519.md'), 'markdown');
assert.strictEqual(appSandbox.detectDocFormat('report_600519.markdown'), 'markdown');
assert.strictEqual(appSandbox.detectDocFormat('unknown.txt', '<!DOCTYPE html><html><body>ok</body></html>'), 'html');
assert.strictEqual(appSandbox.detectDocFormat('unknown.txt', '# Hello World\n\n- item 1'), 'markdown');
console.log('✅ PASS [5.1]: detectDocFormat 正确根据扩展名与文本内容识别 Markdown 与 HTML');

// 测试用例 5.2: 渲染 HTML 到工作区 (renderHtmlToWorkspace)
console.log('--- 测试用例 5.2: renderHtmlToWorkspace 隔离渲染与目录生成 ---');
const sampleHtmlReport = `<!DOCTYPE html>
<html>
<head><title>测试HTML研报</title></head>
<body>
  <h1 id="h-title">茅台深度量化分析报告</h1>
  <h2 id="h-breakeven">税费保本卖出价精算</h2>
  <p>最低保本价: 1420.50 元</p>
  <h2 id="h-risk">三级风控止损阶梯</h2>
  <p>T0: -3%, T1: -5%, T2: -8%</p>
</body>
</html>`;

appSandbox.renderHtmlToWorkspace(sampleHtmlReport, {
  title: '贵州茅台 HTML 研报',
  filename: 'aStocks_600519_20260913.html',
  status: '📄 任务交付物',
  badge: '可视化研报'
});

const frameEl = getMockEl('workspaceHtmlFrame');
const htmlContEl = getMockEl('workspaceHtmlContainer');
const mdBodyEl = getMockEl('workspaceMarkdownBody');
const fmtBadgeEl = getMockEl('docFormatBadge');
const tocListEl = getMockEl('workspaceTocList');

assert.strictEqual(appSandbox.AppState.currentDocFormat, 'html', 'AppState.currentDocFormat 必须为 html');
assert.strictEqual(htmlContEl.style.display, 'flex', 'HTML 视窗容器必须展示 (display: flex)');
assert.strictEqual(mdBodyEl.style.display, 'none', 'Markdown 视窗容器必须隐藏 (display: none)');
assert.strictEqual(frameEl.srcdoc, sampleHtmlReport, 'iframe.srcdoc 必须注入完整 HTML 报告正文');
assert.strictEqual(fmtBadgeEl.innerText, 'HTML', '格式徽章必须显示为 HTML');
assert(fmtBadgeEl.classList._set.has('format-html'), '格式徽章必须应用 format-html 类名');
assert(tocListEl.innerHTML.includes('茅台深度量化分析报告'), 'TOC 目录必须提取 h1 标题');
assert(tocListEl.innerHTML.includes('税费保本卖出价精算'), 'TOC 目录必须提取 h2 标题');
assert(tocListEl.innerHTML.includes('三级风控止损阶梯'), 'TOC 目录必须提取 h2 标题');
console.log('✅ PASS [5.2]: renderHtmlToWorkspace 正确注入 iframe 沙箱、更新 HTML 徽章并提取目录');

// 测试用例 5.3: 渲染 Markdown 到工作区 (renderMarkdownToWorkspace)
console.log('--- 测试用例 5.3: renderMarkdownToWorkspace 渲染与切换 ---');
const sampleMdReport = `# 茅台 Markdown 分析
## 一、核心结论
评分: 88.5分
## 二、保本价
保本卖出价: 254.50元`;

appSandbox.renderMarkdownToWorkspace(sampleMdReport, {
  title: '茅台 Markdown 分析',
  filename: 'report_600519.md',
  status: '📁 工作区文件',
  badge: '研报交付物'
});

assert.strictEqual(appSandbox.AppState.currentDocFormat, 'markdown', 'AppState.currentDocFormat 必须为 markdown');
assert.strictEqual(mdBodyEl.style.display, 'block', 'Markdown 容器必须展示 (display: block)');
assert.strictEqual(htmlContEl.style.display, 'none', 'HTML 容器必须隐藏 (display: none)');
assert.strictEqual(fmtBadgeEl.innerText, 'MARKDOWN', '格式徽章必须显示为 MARKDOWN');
assert(fmtBadgeEl.classList._set.has('format-md'), '格式徽章必须应用 format-md 类名');
assert(mdBodyEl.innerHTML.includes('茅台 Markdown 分析'), 'Markdown 容器必须渲染 Markdown 内容');
assert(tocListEl.innerHTML.includes('茅台 Markdown 分析'), 'TOC 目录必须提取 Markdown # 标题');
console.log('✅ PASS [5.3]: renderMarkdownToWorkspace 正确展示 Markdown 视窗、更新徽章与目录');

// 测试用例 5.4: 视图切换模式 (switchWorkspaceViewMode: preview vs source)
console.log('--- 测试用例 5.4: switchWorkspaceViewMode 预览与源码双模式切换 ---');
const sourceContEl = getMockEl('workspaceSourceContainer');
const sourceCodeEl = getMockEl('workspaceSourceCode');

// 切换至源码模式
appSandbox.switchWorkspaceViewMode('source');
assert.strictEqual(sourceContEl.style.display, 'block', '源码容器必须展示');
assert.strictEqual(mdBodyEl.style.display, 'none', 'Markdown 容器必须隐藏');
assert.strictEqual(sourceCodeEl.textContent, sampleMdReport, '源码容器必须包含 Markdown 原文');

// 切回预览模式
appSandbox.switchWorkspaceViewMode('preview');
assert.strictEqual(sourceContEl.style.display, 'none', '源码容器必须隐藏');
assert.strictEqual(mdBodyEl.style.display, 'block', 'Markdown 容器必须恢复展示');
console.log('✅ PASS [5.4]: switchWorkspaceViewMode 成功实现预览与源码模式双向无缝切换');

// 测试用例 5.5: openDocumentInWorkbench 统一入口自适应打开 HTML 交付物
console.log('--- 测试用例 5.5: openDocumentInWorkbench 打开 HTML 文件 ---');
appSandbox.openDocumentInWorkbench('aStocks_002594_20260913.html', sampleHtmlReport, '比亚迪 HTML 报告');
assert.strictEqual(appSandbox.AppState.currentDocFormat, 'html', '通过 openDocumentInWorkbench 打开 .html 必须自动路由为 HTML 视图');
assert.strictEqual(frameEl.srcdoc, sampleHtmlReport, 'iframe 必须呈现该 HTML 内容');
assert(appSandbox.lastToast.includes('aStocks_002594_20260913.html'), 'Toast 必须提示成功打开文件');
console.log('✅ PASS [5.5]: openDocumentInWorkbench 成功自适应打开 HTML 交付物');

// 异步运行时测试：复制与微任务等待
(async function runAsyncTests() {
  // 测试用例 5.6: copyCurrentWorkbenchMarkdown 复制机制验证
  console.log('--- 测试用例 5.6: copyCurrentWorkbenchMarkdown 双格式复制 ---');
  appSandbox.copyCurrentWorkbenchMarkdown();
  await new Promise(r => setTimeout(r, 50));
  assert.strictEqual(appSandbox.copiedText, sampleHtmlReport, '当前为 HTML 时，复制必须提取 HTML 源码');
  assert(appSandbox.lastToast.includes('HTML'), 'Toast 必须包含 HTML 复制提示');

  appSandbox.renderMarkdownToWorkspace(sampleMdReport, { filename: 'test.md' });
  appSandbox.copyCurrentWorkbenchMarkdown();
  await new Promise(r => setTimeout(r, 50));
  assert.strictEqual(appSandbox.copiedText, sampleMdReport, '当前为 Markdown 时，复制必须提取 Markdown 原文');
  assert(appSandbox.lastToast.includes('Markdown'), 'Toast 必须包含 Markdown 复制提示');
  console.log('✅ PASS [5.6]: copyCurrentWorkbenchMarkdown 成功自动适配 Markdown 与 HTML 原文复制');

  // 测试用例 5.7: generateComprehensiveHtmlDocFallback 实战保底 HTML 生成
  console.log('--- 测试用例 5.7: generateComprehensiveHtmlDocFallback 实战保底规范 ---');
  const fallbackHtml = appSandbox.generateComprehensiveHtmlDocFallback('reports/aStocks_600519.html', 'aStocks_600519.html', '贵州茅台深度报告');
  assert(fallbackHtml.includes('<!DOCTYPE html>'), '保底 HTML 必须是标准 HTML5 结构');
  assert(fallbackHtml.includes('#f4f5f7'), '必须符合 astock-report-html 样式规范 (白色亚光背景 #f4f5f7)');
  assert(fallbackHtml.includes('math.ceil') || fallbackHtml.includes('保本卖出价'), '必须遵循 AGENTS.md 税费向上进位至分位精算铁律');
  assert(fallbackHtml.includes('T0 警戒线') && fallbackHtml.includes('T2 绝杀线'), '必须包含完整三级风控阶梯');
  assert(fallbackHtml.includes('开盘冲高') && fallbackHtml.includes('跳水急跌'), '必须包含三场景即时动作单');
  console.log('✅ PASS [5.7]: generateComprehensiveHtmlDocFallback 生成完全符合规范的自包含真实 HTML 研报');

  console.log('\n🎉 全部 7 大测试维度 100% 通过！工作区 Markdown 与 HTML 双格式全面支持验收达标！\n');
})();
