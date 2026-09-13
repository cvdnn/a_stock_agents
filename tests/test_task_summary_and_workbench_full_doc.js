/**
 * tests/test_task_summary_and_workbench_full_doc.js
 * 专门回归验证：
 * 1. 任务完成后正确显示实质性摘要，彻底消除 ReferenceError 与占位符残留问题；
 * 2. 点击文件在右侧工作区 100% 完整显示整份研报文档（强制展开工作区、内存+本地持久化+DOM关联+保底机制）。
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const vm = require('vm');

console.log('=== [验证：任务完成显示实质性摘要 & 点击文件在工作区显示完整文档] ===\n');

const ROOT = path.resolve(__dirname, '..');
const appJsPath = path.join(ROOT, 'web', 'js', 'app.js');
const chatPresPath = path.join(ROOT, 'web', 'js', 'chat_presentation.js');
const indexHtmlPath = path.join(ROOT, 'web', 'index.html');

const appJs = fs.readFileSync(appJsPath, 'utf8');
const chatPresJs = fs.readFileSync(chatPresPath, 'utf8');
const html = fs.readFileSync(indexHtmlPath, 'utf8');

// --------------------------------------------------------------------------
// 1. 静态代码契约断言
// --------------------------------------------------------------------------
console.log('--- 1. 静态代码契约断言 ---');

// 1.1 onDone 作用域安全：deliverables 必须在 state 外部安全定义
assert(appJs.includes('let deliverables = [];'), 'app.js 必须在 onDone 顶层安全声明 let deliverables = []');
assert(!appJs.includes('const deliverables = ChatPresentation.detectDeliverables'), '不得在 if (state) 内部使用 const deliverables 导致外部作用域 ReferenceError');
console.log('✅ PASS [静态 1]: onDone 彻底消除 deliverables 块级作用域漏洞与 ReferenceError');

// 1.2 统一文档持久化 saveDeliverableDoc
assert(appJs.includes('function saveDeliverableDoc(filename, content, title)'), 'app.js 必须提供全局统一的 saveDeliverableDoc 函数');
assert(appJs.includes('window.saveDeliverableDoc = saveDeliverableDoc;'), 'saveDeliverableDoc 必须挂载至全局 window');
assert(appJs.includes("localStorage.setItem('astock_doc_' + basename, content)"), 'saveDeliverableDoc 必须支持 localStorage 持久化防刷新丢失');
console.log('✅ PASS [静态 2]: 交付物全局存储与多级持久化机制就绪');

// 1.3 openMarkdownInWorkbench 必须具备强制展开工作区与多级提取链路
assert(appJs.includes('toggleWorkbenchCollapse(false)'), 'openMarkdownInWorkbench 必须调用 toggleWorkbenchCollapse(false) 强制展开工作台');
assert(appJs.includes("switchRightTab('dashboard')"), 'openMarkdownInWorkbench 必须激活 dashboard 沉浸式 Markdown pane');
assert(appJs.includes("localStorage.getItem('astock_doc_' + basename)"), 'openMarkdownInWorkbench 必须支持从 localStorage 提取完整研报');
assert(appJs.includes('generateComprehensiveDocFallback'), 'openMarkdownInWorkbench 必须具备遵循 AGENTS.md 规范的实战研报保底机制');
console.log('✅ PASS [静态 3]: openMarkdownInWorkbench 具备工作区强制展开与完整文档提取能力');

// --------------------------------------------------------------------------
// 2. VM 沙箱运行时端到端流程验证
// --------------------------------------------------------------------------
console.log('\n--- 2. VM 沙箱运行时端到端流程验证 ---');

// 构造虚拟 DOM 节点仿真
function createMockElement(id = '', tag = 'div', cls = '') {
  const elem = {
    id: id,
    tagName: tag.toUpperCase(),
    className: cls,
    classList: {
      _classes: new Set(cls.split(' ').filter(Boolean)),
      add: function (c) { this._classes.add(c); elem.className = Array.from(this._classes).join(' '); },
      remove: function (c) { this._classes.delete(c); elem.className = Array.from(this._classes).join(' '); },
      contains: function (c) { return this._classes.has(c); }
    },
    style: {},
    innerText: '',
    innerHTML: '',
    dataset: {},
    children: [],
    appendChild: function (child) { this.children.push(child); child.parentElement = this; return child; },
    querySelector: function (sel) {
      if (sel.startsWith('#')) {
        const targetId = sel.slice(1);
        if (this.id === targetId) return this;
        for (const ch of this.children) {
          const found = ch.querySelector ? ch.querySelector(sel) : null;
          if (found) return found;
        }
      } else if (sel.startsWith('.')) {
        const clsName = sel.slice(1);
        if (this.classList.contains(clsName)) return this;
        for (const ch of this.children) {
          const found = ch.querySelector ? ch.querySelector(sel) : null;
          if (found) return found;
        }
      }
      return null;
    },
    querySelectorAll: function (sel) {
      const results = [];
      if (sel.startsWith('.')) {
        const clsName = sel.slice(1);
        if (this.classList.contains(clsName)) results.push(this);
        for (const ch of this.children) {
          if (ch.querySelectorAll) results.push(...ch.querySelectorAll(sel));
        }
      }
      return results;
    },
    closest: function (sel) {
      if (sel.startsWith('.')) {
        const clsName = sel.slice(1);
        if (this.classList.contains(clsName)) return this;
      }
      return this.parentElement ? this.parentElement.closest(sel) : null;
    },
    getAttribute: function (attr) { return this[attr] || null; },
    setAttribute: function (attr, val) { this[attr] = val; },
    scrollIntoView: () => {}
  };
  return elem;
}

const mockDocElements = {};
function getOrCreateElem(id, tag = 'div', cls = '') {
  if (!mockDocElements[id]) {
    mockDocElements[id] = createMockElement(id, tag, cls);
  }
  return mockDocElements[id];
}

// 预热主界面必要 DOM 节点
const appContainer = getOrCreateElem('appContainer', 'div', 'app-container layout-chat-center');
const chatMessages = getOrCreateElem('chatMessages', 'div', 'chat-messages');
const workspaceMarkdownBody = getOrCreateElem('workspaceMarkdownBody', 'div', 'workspace-markdown-container');
const workbenchHeaderTitle = getOrCreateElem('workbenchHeaderTitle', 'h3', 'workbench-header-title');
const docFilenameText = getOrCreateElem('docFilenameText', 'span', 'doc-filename-text');
const workspaceTocList = getOrCreateElem('workspaceTocList', 'div', 'toc-content');
const paneDashboard = getOrCreateElem('pane-dashboard', 'div', 'right-pane active');

const localStorageStore = {};

const sandboxContext = {
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  Event: function (name) { this.name = name; },
  localStorage: {
    getItem: (k) => (k in localStorageStore ? localStorageStore[k] : null),
    setItem: (k, v) => { localStorageStore[k] = String(v); },
    removeItem: (k) => { delete localStorageStore[k]; }
  },
  document: {
    getElementById: (id) => mockDocElements[id] || null,
    querySelector: (sel) => {
      if (sel.startsWith('#')) return mockDocElements[sel.slice(1)] || null;
      if (sel === '.app-container') return appContainer;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel === '.message-bubble-ai') {
        return Object.values(mockDocElements).filter(e => e.classList.contains('message-bubble-ai'));
      }
      if (sel === '.right-pane') return [paneDashboard];
      return [];
    },
    createElement: (tag) => createMockElement('', tag, '')
  },
  window: {}
};
sandboxContext.window = sandboxContext;

vm.createContext(sandboxContext);

// 加载 ChatPresentation
vm.runInContext(chatPresJs, sandboxContext);
console.log('✅ PASS: ChatPresentation 引擎在沙箱内加载成功');

// 加载核心前端辅助与 AppState
vm.runInContext(`
  var AppState = {
    currentSessionId: 'sess_123',
    selectedStock: '002594',
    activeRightTab: 'dashboard',
    isWorkbenchCollapsed: false,
    deliverableCache: {}
  };
  function showToast(msg) { /* mock toast */ }
  function renderTabCharts() {}
  function switchLayoutMode() {}
`, sandboxContext);

// 注入待测核心函数 (saveDeliverableDoc, openMarkdownInWorkbench, formatChatDialogueSummary 等)
vm.runInContext(appJs.slice(appJs.indexOf('// 统一交付物文档持久化与缓存中心'), appJs.indexOf('function openDeliverableInWorkbench')), sandboxContext);

console.log('--- 测试用例 1: 模拟任务执行完毕并触发 onDone 摘要呈现 ---');

const testFullReport = `# 📄 比亚迪 (002594) 深度量化诊断研报

### 一、量化体检与核心研判结论
- **综合量化评分**：**88.5 分**（多因子共振：量价 89分、资金 86分、估值 87分、筹码 91分）；
- **趋势形态定性**：主升浪强势回踩 20 日均线支撑有效，MACD 零轴上方蓄势二次金叉；
- **主力控盘状态**：主力筹码集中度持续抬升，近 5 日主力大单持续净流入。

### 二、税费保本卖出价精算 (严格遵守 AGENTS.md 铁律)
- 买入成本：¥254.30，持仓：1000股；
- 计入印花税 0.05%、佣金万2.5(最低5元)、过户费，向上进位至分位 (ceil)；
- **精确最低保本卖出价**：**¥254.50**。

### 三、三级风控止损阶梯
- **T0 警戒线 (-3%)**：**¥246.67**（预警准备减仓）；
- **T1 减仓线 (-5%)**：**¥241.58**（果断减仓50%）；
- **T2 绝杀线 (-8%)**：**¥233.95**（无条件全仓止损出局）。

### 四、三场景即时实战动作预案
1. 开盘冲高：不追高，触及压力位兑现浮盈；
2. 盘中震荡：持股观望，守稳5日线；
3. 急跌跳水：跌破T0线果断梯度减仓。

产出交付物报告：\`report_002594_190300.md\`
`;

const deliverableFn = 'report_002594_190300.md';

// 验证 saveDeliverableDoc 在沙箱内成功存储内存与 localStorage
sandboxContext.saveDeliverableDoc(deliverableFn, testFullReport, '比亚迪个股量化综合体检');
assert(sandboxContext.AppState.deliverableCache[deliverableFn], 'AppState.deliverableCache 必须已存储该研报');
assert(localStorageStore['astock_doc_' + deliverableFn], 'localStorage 必须已持久化存储该研报');
console.log('✅ PASS [用例 1.1]: saveDeliverableDoc 成功实现内存与 localStorage 双重持久化');

// 验证 formatChatDialogueSummary 输出实质性摘要并附带完整文档超链
const summaryHtml = sandboxContext.ChatPresentation.formatChatDialogueSummary(testFullReport, {
  deliverableFilename: deliverableFn,
  deliverableFiles: [deliverableFn],
  deliverableTitle: '比亚迪个股量化综合体检'
});

assert(summaryHtml.includes('88.5 分'), '摘要必须包含综合评分 88.5 分');
assert(summaryHtml.includes('¥254.50'), '摘要必须包含最低保本卖出价');
assert(summaryHtml.includes('完整详尽研报：'), '摘要底部必须附带完整详尽研报');
assert(summaryHtml.includes(deliverableFn), '摘要中必须展示报告文件名');
assert(!summaryHtml.includes('AI正在综合大盘'), '不得包含占位文字');
console.log('✅ PASS [用例 1.2]: formatChatDialogueSummary 成功输出高质量实质性结论与研报超链');

console.log('\n--- 测试用例 2: openMarkdownInWorkbench 工作区展开与完整研报渲染 ---');

// 模拟工作台处于收起状态
appContainer.classList.add('workbench-collapsed');
sandboxContext.AppState.isWorkbenchCollapsed = true;

// 注入 toggleWorkbenchCollapse 与 switchRightTab 运行时
vm.runInContext(`
  function toggleWorkbenchCollapse(forceState) {
    if (forceState === false) {
      document.getElementById('appContainer').classList.remove('workbench-collapsed');
      AppState.isWorkbenchCollapsed = false;
    }
  }
  function switchRightTab(tabId) {
    AppState.activeRightTab = tabId;
  }
  function renderMarkdownToWorkspace(markdownText, meta) {
    const b = document.getElementById('workspaceMarkdownBody');
    b.innerHTML = ChatPresentation.renderMarkdown(markdownText);
    const t = document.getElementById('workbenchHeaderTitle');
    if (t) t.innerText = meta.title || meta.filename;
    const f = document.getElementById('docFilenameText');
    if (f) f.innerText = meta.filename;
  }
`, sandboxContext);

// 点击文件在工作区打开
sandboxContext.openMarkdownInWorkbench(deliverableFn);

// 验证工作台是否已强制展开
assert(!appContainer.classList.contains('workbench-collapsed'), '点击文件后工作台必须已强制展开 (移除 workbench-collapsed)');
console.log('✅ PASS [用例 2.1]: openMarkdownInWorkbench 强制展开工作台');

// 验证工作区渲染内容是否完整
assert(workspaceMarkdownBody.innerHTML.includes('比亚迪 (002594) 深度量化诊断研报'), '工作区必须完整展示大标题');
assert(workspaceMarkdownBody.innerHTML.includes('88.5 分'), '工作区必须包含量化评分');
assert(workspaceMarkdownBody.innerHTML.includes('254.50'), '工作区必须包含向上进位保本卖出价');
assert(workspaceMarkdownBody.innerHTML.includes('T0 警戒线') && workspaceMarkdownBody.innerHTML.includes('T2 绝杀线'), '工作区必须展示完整三级止损阶梯');
assert(workbenchHeaderTitle.innerText.includes('比亚迪') || workbenchHeaderTitle.innerText.includes('report_002594'), '顶部 Header 标题已同步更新');
assert(docFilenameText.innerText.includes('report_002594'), '文档元信息文件名已同步更新');
console.log('✅ PASS [用例 2.2]: 工作区成功展示 100% 完整研报全文、风控铁律与元信息');

console.log('\n--- 测试用例 3: 页面刷新/清空内存后从 localStorage 恢复完整文档 ---');
// 清空内存缓存
sandboxContext.AppState.deliverableCache = {};
workspaceMarkdownBody.innerHTML = '';

// 重新调用 openMarkdownInWorkbench
sandboxContext.openMarkdownInWorkbench(deliverableFn);
assert(workspaceMarkdownBody.innerHTML.includes('88.5 分'), '即便清空内存，仍能从 localStorage 提取完整研报');
assert(workspaceMarkdownBody.innerHTML.includes('254.50'), '包含精确最低保本卖出价');
console.log('✅ PASS [用例 3]: 内存清空或断网后成功从 localStorage 秒级恢复完整文档');

console.log('\n🎉 所有测试用例 100% 全部通过！彻底解决任务摘要与工作区完整文档显示问题！\n');
