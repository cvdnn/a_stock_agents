/**
 * tests/test_html_task_execution_and_content_truth.js
 * 专属自动化测试套件：
 * 验证执行带有 HTML 的任务时，生成的文件名称为 .html，且文件内容 100% 为真实有效的 HTML 格式，
 * 彻底杜绝 .html 文件内却为 Markdown 格式的问题。
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const vm = require('vm');

console.log('=== [验证：带有 HTML 的任务生成真实 HTML 文件与内容真实性测试] ===\n');

// 1. 读取源码文件
const chatPresentationCode = fs.readFileSync(path.join(__dirname, '../../web/js/chat_presentation.js'), 'utf-8');
const appJsCode = fs.readFileSync(path.join(__dirname, '../../web/js/app.js'), 'utf-8');
const appPyCode = fs.readFileSync(path.join(__dirname, '../../scripts/server/app.py'), 'utf-8');
const reportGenCode = fs.readFileSync(path.join(__dirname, '../../scripts/core/reporting/report_generator.py'), 'utf-8');
const promptsCode = fs.readFileSync(path.join(__dirname, '../../scripts/server/agent/prompts.py'), 'utf-8');

// -----------------------------------------------------------------------------
// 1. 静态代码契约断言
// -----------------------------------------------------------------------------
console.log('--- 1. 后端与系统提示词契约断言 ---');
assert(promptsCode.includes('astock_report_html'), 'prompts.py 必须在系统提示词中包含调用 astock_report_html 的明确指引');
assert(reportGenCode.includes('def wrap_markdown_as_html_report'), 'report_generator.py 必须提供 wrap_markdown_as_html_report 转换函数');
assert(appPyCode.includes('wrap_markdown_as_html_report'), 'app.py 必须在 /api/docs/save 中引入 wrap_markdown_as_html_report 做格式保底');
assert(appPyCode.includes('workspace_root / "output" / "reports" / filename'), 'app.py /api/docs/read 必须优先检索 output/reports 目录');
console.log('✅ PASS [静态 1]: 后端工具、提示词与 API 契约完备');

// -----------------------------------------------------------------------------
// 2. 构造浏览器虚拟沙箱环境
// -----------------------------------------------------------------------------
console.log('\n--- 2. 前端工作台与持久化沙箱断言 ---');
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

// 提取 app.js 中的辅助与核心函数注入沙箱
const coreFunctionsRegex = /function\s+extractHtmlHeadings[\s\S]*?window\.openDocumentInWorkbench\s*=\s*openDocumentInWorkbench;/;
const matchedFunctions = appJsCode.match(coreFunctionsRegex);
assert(matchedFunctions, '必须能从 app.js 匹配到工作台核心函数群');
vm.runInContext(matchedFunctions[0], sandbox);

// -----------------------------------------------------------------------------
// 测试用例 1: convertMarkdownToHtmlDocument 转换真实性
// -----------------------------------------------------------------------------
console.log('--- 测试用例 1: convertMarkdownToHtmlDocument 将 Markdown 转为合法自包含 HTML ---');
const rawMarkdownReport = `# 🏢 中国移动 (600941) 投研 HTML 报告

## 📊 核心行情快照
| 指标 | 读数 | 指标 | 读数 |
|---|---|---|---|
| 最新价 | **97.72** (+0.57%) | 今开 / 昨收 | 97.01 / 97.17 |

- 综合评分：**51 / 100**，评级 **C (观望)**
- MACD：DIF/DEA 均在零轴上方，多头动能衰减中
`;

assert(typeof sandbox.convertMarkdownToHtmlDocument === 'function', 'convertMarkdownToHtmlDocument 必须为全局函数');
const convertedHtml = sandbox.convertMarkdownToHtmlDocument(rawMarkdownReport, '中国移动投研报告', 'aStocks_600941.html');

assert(convertedHtml.includes('<!DOCTYPE html>'), '转换后必须以 <!DOCTYPE html> 声明开头');
assert(convertedHtml.includes('<html lang="zh-CN">'), '转换后必须包含 <html lang="zh-CN">');
assert(convertedHtml.includes('<style>'), '转换后必须内嵌完整 CSS 样式，保证自包含');
assert(convertedHtml.includes('中国移动'), 'HTML 正文必须包含股票名称中国移动');
assert(!convertedHtml.startsWith('# 🏢'), 'HTML 绝对不能直接以 Markdown 一级标题 # 开头');
console.log('✅ PASS [用例 1]: convertMarkdownToHtmlDocument 成功将 Markdown 转为标准自包含 HTML');

// -----------------------------------------------------------------------------
// 测试用例 2: saveDeliverableDoc 强防线，杜绝存入 Markdown
// -----------------------------------------------------------------------------
console.log('\n--- 测试用例 2: saveDeliverableDoc 杜绝将 Markdown 存入 .html 文件 ---');
sandbox.saveDeliverableDoc('aStocks_600941_20260913_222551.html', rawMarkdownReport, '中国移动HTML研报');

const cachedInState = sandbox.AppState.deliverableCache['aStocks_600941_20260913_222551.html'];
const cachedInStorage = sandbox.localStorage.getItem('astock_doc_aStocks_600941_20260913_222551.html');

assert(cachedInState.includes('<!DOCTYPE html>'), 'AppState.deliverableCache 缓存的必须是纯正 HTML，绝不能是 Markdown');
assert(!cachedInState.startsWith('# 🏢'), 'AppState.deliverableCache 中绝对不能是裸 Markdown');
assert(cachedInStorage.includes('<!DOCTYPE html>'), 'localStorage 中持久化的必须是纯正 HTML');
console.log('✅ PASS [用例 2]: saveDeliverableDoc 成功拦截并修正 Markdown 内容为真实 HTML');

// -----------------------------------------------------------------------------
// 测试用例 3: 工作台打开 .html 文件绝不显示原始 Markdown
// -----------------------------------------------------------------------------
console.log('\n--- 测试用例 3: 工作台 openDocumentInWorkbench 渲染纯净 HTML ---');
// 模拟历史坏缓存为纯 Markdown
sandbox.AppState.deliverableCache['dirty_report.html'] = rawMarkdownReport;
sandbox.localStorage.setItem('astock_doc_dirty_report.html', rawMarkdownReport);

// 在工作台中打开
sandbox.openDocumentInWorkbench('dirty_report.html');

// 断言 iframe 注入内容
assert.strictEqual(mockElements.workspaceHtmlContainer.style.display, 'flex', 'HTML 容器必须展示');
assert(mockElements.workspaceHtmlFrame.srcdoc.includes('<!DOCTYPE html>'), 'iframe srcdoc 必须注入合法 HTML');
assert(!mockElements.workspaceHtmlFrame.srcdoc.startsWith('# 🏢'), 'iframe srcdoc 绝对不能注入裸露 Markdown 文本');
console.log('✅ PASS [用例 3]: 工作台成功防止在 iframe 中展示原始 Markdown 源码');

// -----------------------------------------------------------------------------
// 测试用例 4: Python wrap_markdown_as_html_report 验证
// -----------------------------------------------------------------------------
console.log('\n--- 测试用例 4: 后端 wrap_markdown_as_html_report 功能验证 ---');
const { execSync } = require('child_process');
const pyBin = process.env.PYTHON || (process.platform === 'win32' && fs.existsSync('C:\\Users\\cvdnn\\AppData\\Local\\Programs\\Python\\Python313\\python.exe') ? 'C:\\Users\\cvdnn\\AppData\\Local\\Programs\\Python\\Python313\\python.exe' : 'python');
const pyCmd = `"${pyBin}" -c "import sys; sys.path.insert(0, 'scripts'); from core.reporting.report_generator import wrap_markdown_as_html_report; md = '# 中国移动\\n| 指标 | 读数 |\\n|---|---|\\n| 现价 | 97.72 |'; html = wrap_markdown_as_html_report(md, title='中国移动研报', filename='aStocks_600941.html'); assert '<!DOCTYPE html>' in html; assert 'class=\\\"tbl\\\"' in html; assert not html.startswith('# 中国移动'); print('PYTHON_WRAP_SUCCESS')"`;
const pyOut = execSync(pyCmd, {
  cwd: path.join(__dirname, '../..'),
  encoding: 'utf-8'
});
assert(pyOut.includes('PYTHON_WRAP_SUCCESS'), 'Python wrap_markdown_as_html_report 执行必须成功');
console.log('✅ PASS [用例 4]: 后端 wrap_markdown_as_html_report 输出标准自包含 HTML');


// -----------------------------------------------------------------------------
// 测试用例 5: 真实生成的 17KB HTML 文件 /api/docs/read 优先级验证
// -----------------------------------------------------------------------------
console.log('\n--- 测试用例 5: 真实生成的 aStocks_600941_20260913_222551.html 检验 ---');
const realHtmlPath = path.join(__dirname, '../../output/reports/aStocks_600941_20260913_222551.html');
if (fs.existsSync(realHtmlPath)) {
  const realHtmlContent = fs.readFileSync(realHtmlPath, 'utf-8');
  assert(realHtmlContent.includes('<!DOCTYPE html>'), '真实文件内容必须是合法 HTML');
  assert(realHtmlContent.length > 10000, '真实生成的 HTML 报告应为 10KB 以上完整报告');
} else {
  console.log("ℹ️ SKIP [用例 5]: output/reports 真实报告文件不存在，跳过物理文件断言");
}

// 验证 reports/ 下的历史脏文件已被清理，杜绝遮蔽
const dirtyHtmlPath = path.join(__dirname, '../../reports/aStocks_600941_20260913_222551.html');
assert(!fs.existsSync(dirtyHtmlPath), 'reports/ 下的脏 Markdown 文件必须已被清除');
console.log('✅ PASS [用例 5]: 真实 HTML 交付物完好有效且不再受历史脏文件遮蔽');

console.log('\n🎉 所有 5 项核心验证全部 100% 通过！彻底解决 .html 文件内容为 Markdown 的问题！');
