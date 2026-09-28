/**
 * 验证一级菜单工作区物理隔离、投研助手文档视窗与 AI 助手折叠契约。
 */

const fs = require('fs');
const assert = require('assert');

console.log('=== [一级菜单工作区与投研助手文档视窗隔离验证] ===\n');

const html = fs.readFileSync('web/index.html', 'utf8');
const css = fs.readFileSync('web/css/style.css', 'utf8');
const appJs = fs.readFileSync('web/js/app.js', 'utf8');

// --------------------------------------------------------------------------
// 1. 各一级菜单工作区物理隔离与唯一性
// --------------------------------------------------------------------------
console.log('--- 1. 一级菜单工作区物理隔离 ---');

const panes = [
  'pane-dashboard',
  'pane-market',
  'pane-watchlist',
  'pane-returns',
  'pane-skills',
  'pane-datasync',
];

panes.forEach((paneId) => {
  const matches = html.match(new RegExp(`id="${paneId}"`, 'g')) || [];
  assert.strictEqual(matches.length, 1, `工作区容器 #${paneId} 必须唯一存在于 index.html`);
  console.log(`✅ PASS: 独立工作区容器 #${paneId} 唯一存在`);
});

assert(appJs.includes('function switchRightTab(tabId)'), '需具备 switchRightTab 切换器');
assert(appJs.includes('document.getElementById(`pane-${tabId}`)'), 'switchRightTab 应通过独立 ID 索引 pane');
console.log('✅ PASS: 工作区切换机制遵循单 pane 激活与独立 ID 路由契约');

// --------------------------------------------------------------------------
// 2. 投研助手采用现行 Markdown / HTML 文档工作区
// --------------------------------------------------------------------------
console.log('\n--- 2. 投研助手文档工作区结构 ---');

const dashboardStart = html.indexOf('id="pane-dashboard"');
const marketStart = html.indexOf('id="pane-market"');
assert(dashboardStart >= 0 && marketStart > dashboardStart, '必须能隔离提取 dashboard 工作区');
const dashboardHtml = html.slice(dashboardStart, marketStart);

for (const id of [
  'workspaceMarkdownWrapper',
  'workspaceDocMetaBar',
  'workspaceDocLayout',
  'workspaceDocToc',
  'workspaceMarkdownBody',
  'workspaceHtmlContainer',
  'workspaceHtmlFrame',
  'workspaceSourceContainer',
  'workspaceSourceCode',
]) {
  assert(dashboardHtml.includes(`id="${id}"`), `dashboard 必须包含 #${id}`);
}

assert(!dashboardHtml.includes('id="section-portfolio-overview"'), 'dashboard 不得恢复已归档的旧六板块静态界面');
assert(appJs.includes('function openDocumentInWorkbench'), '需具备统一文档打开入口');
assert(appJs.includes('function renderMarkdownToWorkspace'), '需支持 Markdown 工作区渲染');
assert(appJs.includes('function renderHtmlToWorkspace'), '需支持 HTML 工作区渲染');
console.log('✅ PASS: dashboard 保持现行 Markdown / HTML / 源码三视图文档工作区');

// --------------------------------------------------------------------------
// 3. AI 助手默认收起规范
// --------------------------------------------------------------------------
console.log('\n--- 3. 非投研助手工作区默认收起 AI 助手 ---');

assert(appJs.includes("container.classList.add('copilot-collapsed')"), '进入其他工作区时应添加 copilot-collapsed');
assert(appJs.includes('AppState.isCopilotCollapsed = true'), '进入其他工作区时应记录折叠状态');
assert(appJs.includes("container.classList.remove('copilot-collapsed')"), '切回投研助手时应移除 copilot-collapsed');
assert(css.includes('.app-container.layout-workspace-main.copilot-collapsed'), 'CSS 必须提供全宽折叠布局');
assert(html.includes('id="btnCopilotLauncher"'), '页面必须具备 AI 助手唤起按钮');
assert(appJs.includes("tabId === 'datasync'") && appJs.includes("display = 'none'"), '数据同步工作区必须保持无 AI 隔离');
console.log('✅ PASS: 普通工作区折叠契约与数据同步无 AI 隔离均成立');

console.log('\n🎉 工作区物理隔离与现行文档视窗契约全部通过！\n');
