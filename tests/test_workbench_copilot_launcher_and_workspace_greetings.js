/**
 * tests/test_workbench_copilot_launcher_and_workspace_greetings.js
 * 
 * 验证：
 * 1. 除了【投研助手】外，其他菜单的工作区 title 栏最后增加【AI助手】按钮；
 * 2. 点击【AI助手】后侧边滑出 AI 助手，点击【收起】按钮收起 AI 助手；
 * 3. 在不同的菜单功能工作区，滑出的 AI 助手问候提示语与推荐操作各不相同。
 */

const fs = require('fs');
const assert = require('assert');
const path = require('path');
const vm = require('vm');

console.log('=== [验证：除投研助手外各工作区Title栏【AI助手】按钮与专属问候语/推荐操作测试] ===\n');

// 1. 静态 HTML 检测
console.log('--- 1. web/index.html 结构断言 ---');
const indexHtml = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');

assert(indexHtml.includes('id="btnCopilotLauncher"'), 'index.html 必须包含 btnCopilotLauncher 按钮');
assert(indexHtml.includes('handleWorkbenchCopilotBtn()'), 'btnCopilotLauncher 必须绑定 handleWorkbenchCopilotBtn() 点击事件');
assert(!indexHtml.includes('id="btnCopilotLauncher" onclick="toggleCopilot()" title="展开AI助手" style="display: none;"'), 'btnCopilotLauncher 不得携带 inline display:none 阻止展示');
assert(indexHtml.includes('id="btnCollapseChat"'), 'index.html 必须包含收起按钮 btnCollapseChat');
assert(indexHtml.includes('handleChatCollapseBtn()'), 'btnCollapseChat 必须绑定 handleChatCollapseBtn() 事件');
console.log('✅ PASS [静态 1]: HTML 结构中 btnCopilotLauncher 与收起按钮配置正确！');

// 2. 静态 CSS 样式检测
console.log('\n--- 2. web/css/style.css 样式断言 ---');
const styleCss = fs.readFileSync(path.join(__dirname, '../web/css/style.css'), 'utf8');

assert(styleCss.includes('.app-container.layout-chat-center .btn-copilot-launcher'), 'style.css 必须包含投研助手模式下隐藏 AI助手按钮规则');
assert(styleCss.includes('.app-container.layout-workspace-main .btn-copilot-launcher'), 'style.css 必须包含主工作区模式下展示 AI助手按钮规则');
assert(styleCss.includes('.app-container.layout-workspace-main.copilot-collapsed .app-middle-chat'), 'style.css 必须包含主工作区收起状态样式');
assert(styleCss.includes('.app-container.layout-workspace-main .app-middle-chat'), 'style.css 必须包含主工作区展开状态平滑过渡样式');
console.log('✅ PASS [静态 2]: CSS 样式表中投研助手隐藏、其他工作区展示及平滑抽屉滑动样式完备！');

// 3. 动态 JS 沙箱断言：TabCopilotConfigs 与 getWelcomeMessageHtml
console.log('\n--- 3. 动态多工作区专属问候提示语与推荐操作断言 ---');
const appJs = fs.readFileSync(path.join(__dirname, '../web/js/app.js'), 'utf8');

// 构造模拟 DOM 沙箱
class MockClassList extends Set {
  contains(cls) { return this.has(cls); }
  remove(cls) { return this.delete(cls); }
}

class MockElement {
  constructor(id, tag = 'div') {
    this.id = id;
    this.tagName = tag.toUpperCase();
    this.style = { display: '' };
    this.innerText = '';
    this.innerHTML = '';
    this.value = '';
    this.title = '';
    this.children = [];
    this.classList = new MockClassList();
  }
  getAttribute(name) { return this[name] || null; }
  setAttribute(name, val) { this[name] = val; }
  querySelector(selector) {
    if (selector === '.welcome-intro-card') {
      return this.innerHTML.includes('welcome-intro-card') ? new MockElement('welcome-card') : null;
    }
    if (selector === '.bg-indicator-text') return new MockElement('bg-text');
    return null;
  }
  querySelectorAll(selector) {
    if (selector === '.header-action-group') {
      return Object.keys(mockElements)
        .filter(k => k.startsWith('actions'))
        .map(k => mockElements[k]);
    }
    if (selector === '.sidebar-nav-section .nav-item') return [];
    if (selector === '.right-pane') return [];
    return [];
  }
  scrollIntoView() {}
  focus() {}
  appendChild(child) { this.children.push(child); }
  remove() {}
}

const mockElements = {
  appContainer: new MockElement('appContainer'),
  btnCopilotLauncher: new MockElement('btnCopilotLauncher', 'button'),
  copilotBtnArrow: new MockElement('copilotBtnArrow', 'span'),
  btnCollapseWorkbench: new MockElement('btnCollapseWorkbench', 'button'),
  btnCollapseChat: new MockElement('btnCollapseChat', 'button'),
  chatHeaderTitle: new MockElement('chatHeaderTitle', 'h3'),
  chatHeaderStatus: new MockElement('chatHeaderStatus', 'span'),
  collapseIcon: new MockElement('collapseIcon', 'span'),
  collapseText: new MockElement('collapseText', 'span'),
  chatMessages: new MockElement('chatMessages', 'div'),
  workbenchHeaderTitle: new MockElement('workbenchHeaderTitle', 'h3'),
  workbenchHeaderTag: new MockElement('workbenchHeaderTag', 'span'),
  workbenchIconBadge: new MockElement('workbenchIconBadge', 'div'),
  actionsDashboard: new MockElement('actionsDashboard', 'div'),
  actionsMarket: new MockElement('actionsMarket', 'div'),
  actionsWatchlist: new MockElement('actionsWatchlist', 'div'),
  actionsReturns: new MockElement('actionsReturns', 'div'),
  actionsSkills: new MockElement('actionsSkills', 'div'),
  actionsProjectedAction: new MockElement('actionsProjectedAction', 'div'),
  btnWorkspaceOpenExternal: new MockElement('btnWorkspaceOpenExternal', 'button'),
  sessionList: new MockElement('sessionList', 'div'),
  chatInput: new MockElement('chatInput', 'textarea')
};

const sandbox = {
  console,
  setTimeout: (fn) => fn(),
  clearTimeout: () => {},
  setInterval: () => {},
  clearInterval: () => {},
  document: {
    createElement: (tag) => new MockElement('created-' + tag, tag),
    getElementById: (id) => mockElements[id] || null,
    querySelector: (sel) => {
      if (sel === '#appContainer' || sel === '.app-container') return mockElements.appContainer;
      if (sel === '#chatMessages') return mockElements.chatMessages;
      if (sel === '#btnCopilotLauncher') return mockElements.btnCopilotLauncher;
      if (sel === '.welcome-intro-card') return mockElements.chatMessages.querySelector('.welcome-intro-card');
      return null;
    },
    querySelectorAll: (sel) => mockElements.appContainer.querySelectorAll(sel),
    addEventListener: () => {},
    removeEventListener: () => {},
    body: new MockElement('body')
  },
  window: {
    location: { origin: 'http://localhost:8000', href: 'http://localhost:8000' },
    dispatchEvent: () => {},
    addEventListener: () => {},
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} }
  },
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  Event: function(type) { this.type = type; },
  showToast: () => {},
  renderSessionList: () => {},
  renderTabCharts: () => {},
  initSkillsGovernance: () => {},
  loadUserGuideToWorkbench: () => {}
};
sandbox.window.document = sandbox.document;

vm.createContext(sandbox);
vm.runInContext(appJs, sandbox);

// 3.1 验证 TabCopilotConfigs 数据结构
const configs = sandbox.window.TabCopilotConfigs || sandbox.TabCopilotConfigs;
assert(configs, 'TabCopilotConfigs 必须被定义');
assert(configs['dashboard'], '必须包含 dashboard 问候语配置');
assert(configs['market'], '必须包含 market 问候语配置');
assert(configs['watchlist'], '必须包含 watchlist 问候语配置');
assert(configs['returns'], '必须包含 returns 问候语配置');
assert(configs['skills'], '必须包含 skills 问候语配置');

// 断言各工作区的标题互不相同且与各自业务领域高度契合
assert.strictEqual(configs['dashboard'].title, '您好！我是您的 A股智能投研助手');
assert.strictEqual(configs['market'].title, '您好！我是您的 市场盘面研判助手');
assert.strictEqual(configs['watchlist'].title, '您好！我是您的 自选个股量化诊断助手');
assert.strictEqual(configs['returns'].title, '您好！我是您的 投资收益与归因分析助手');
assert.strictEqual(configs['skills'].title, '您好！我是您的 量化技能治理与编排助手');

// 断言各工作区推荐操作互不相同
const marketActions = configs['market'].quickActions.map(a => a.title);
const watchlistActions = configs['watchlist'].quickActions.map(a => a.title);
const returnsActions = configs['returns'].quickActions.map(a => a.title);
const skillsActions = configs['skills'].quickActions.map(a => a.title);

assert(marketActions.includes('今日盘面量价研判'), '市场行情必须推荐今日盘面量价研判');
assert(marketActions.includes('主力资金主线扫描'), '市场行情必须推荐主力资金主线扫描');
assert(watchlistActions.includes('诊断当前自选标的'), '自选个股必须推荐诊断当前自选标的');
assert(watchlistActions.includes('透视主力筹码分布'), '自选个股必须推荐透视主力筹码分布');
assert(returnsActions.includes('投资组合多因子归因'), '收益分析必须推荐投资组合多因子归因');
assert(skillsActions.includes('17项技能契约全量审计'), '技能治理必须推荐17项技能契约全量审计');

console.log('✅ PASS [3.1]: 6 大模块 TabCopilotConfigs 问候语与快捷操作定义全部独立且精准定制！');

// 3.2 验证 getWelcomeMessageHtml(tabId) 动态渲染
const getWelcomeHtml = sandbox.window.getWelcomeMessageHtml || sandbox.getWelcomeMessageHtml;
const mktWelcomeHtml = getWelcomeHtml('market');
assert(mktWelcomeHtml.includes('您好！我是您的 市场盘面研判助手'), 'market 欢迎语必须渲染专属标题');
assert(mktWelcomeHtml.includes('今日盘面量价研判'), 'market 欢迎语必须包含专属快捷操作');

const watchWelcomeHtml = getWelcomeHtml('watchlist');
assert(watchWelcomeHtml.includes('您好！我是您的 自选个股量化诊断助手'), 'watchlist 欢迎语必须渲染专属标题');
assert(watchWelcomeHtml.includes('透视主力筹码分布'), 'watchlist 欢迎语必须包含专属快捷操作');

console.log('✅ PASS [3.2]: getWelcomeMessageHtml(tabId) 能够按工作区动态输出差异化问候卡片！');

// 4. 运行时联动测试：Title 栏【AI助手】按钮在各模块的可见性
console.log('\n--- 4. Title 栏【AI助手】按钮在不同工作区的显示/隐藏断言 ---');

const updateHeader = sandbox.window.updateWorkbenchHeaderActions || sandbox.updateWorkbenchHeaderActions;
const handleBtn = sandbox.window.handleWorkbenchCopilotBtn || sandbox.handleWorkbenchCopilotBtn;
const handleCollapse = sandbox.window.handleChatCollapseBtn || sandbox.handleChatCollapseBtn;

// 4.1 在【投研助手】下
updateHeader('dashboard');
assert.strictEqual(mockElements.btnCopilotLauncher.style.display, 'none', '【投研助手】下 btnCopilotLauncher 必须隐藏 (display: none)');
assert.strictEqual(mockElements.btnCollapseWorkbench.style.display, 'inline-flex', '【投研助手】下 btnCollapseWorkbench 必须展示');
console.log('✅ PASS [4.1]: 【投研助手】工作区 title 栏正确隐藏【AI助手】按钮！');

// 4.2 在【市场行情】下
updateHeader('market');
assert.strictEqual(mockElements.btnCopilotLauncher.style.display, 'inline-flex', '【市场行情】下 btnCopilotLauncher 必须显示 (display: inline-flex)');
assert.strictEqual(mockElements.btnCollapseWorkbench.style.display, 'none', '【市场行情】下 btnCollapseWorkbench 必须隐藏');
console.log('✅ PASS [4.2]: 【市场行情】工作区 title 栏正确展示【AI助手】按钮！');

// 4.3 在【自选个股】下
updateHeader('watchlist');
assert.strictEqual(mockElements.btnCopilotLauncher.style.display, 'inline-flex', '【自选个股】下 btnCopilotLauncher 必须显示');
console.log('✅ PASS [4.3]: 【自选个股】工作区 title 栏正确展示【AI助手】按钮！');

// 4.4 在【收益分析】下
updateHeader('returns');
assert.strictEqual(mockElements.btnCopilotLauncher.style.display, 'inline-flex', '【收益分析】下 btnCopilotLauncher 必须显示');
console.log('✅ PASS [4.4]: 【收益分析】工作区 title 栏正确展示【AI助手】按钮！');

// 4.5 在【技能治理】下
updateHeader('skills');
assert.strictEqual(mockElements.btnCopilotLauncher.style.display, 'inline-flex', '【技能治理】下 btnCopilotLauncher 必须显示');
console.log('✅ PASS [4.5]: 【技能治理】工作区 title 栏正确展示【AI助手】按钮！');

// 5. 点击【AI助手】滑出展开与点击【收起】收起 AI 助手逻辑测试
console.log('\n--- 5. 点击【AI助手】滑出展开与点击【收起】折叠联动断言 ---');

// 初始置为收起状态
mockElements.appContainer.classList.add('copilot-collapsed');
mockElements.appContainer.classList.add('layout-workspace-main');
sandbox.window.AppState.layoutMode = 'workspace-main';
sandbox.window.AppState.isCopilotCollapsed = true;
sandbox.window.AppState.activeRightTab = 'market';
mockElements.chatMessages.innerHTML = getWelcomeHtml('market');

// 5.1 点击工作区 title 栏的【AI助手】按钮
handleBtn();
assert(!mockElements.appContainer.classList.contains('copilot-collapsed'), '点击【AI助手】后必须移除 copilot-collapsed 类以滑出展开 AI 助手');
assert.strictEqual(sandbox.window.AppState.isCopilotCollapsed, false, 'AppState.isCopilotCollapsed 必须变为 false');
assert(mockElements.btnCopilotLauncher.classList.contains('active'), '展开后 btnCopilotLauncher 必须添加 active 类');
assert.strictEqual(mockElements.copilotBtnArrow.innerText, '▶', '展开后箭头转为折叠指示 ▶');
assert(mockElements.chatMessages.innerHTML.includes('市场盘面研判助手'), '滑出的 AI 助手必须展示对应市场行情的问候语');
console.log('✅ PASS [5.1]: 点击 title 栏【AI助手】按钮成功滑出 AI 助手，并呈现市场行情问候语与激活态！');

// 5.2 点击 AI 助手顶部的【收起】按钮
handleCollapse();
assert(mockElements.appContainer.classList.contains('copilot-collapsed'), '点击【收起】按钮后必须添加 copilot-collapsed 类以收起 AI 助手');
assert.strictEqual(sandbox.window.AppState.isCopilotCollapsed, true, 'AppState.isCopilotCollapsed 必须变为 true');
assert(!mockElements.btnCopilotLauncher.classList.contains('active'), '收起后 btnCopilotLauncher 必须移除 active 类');
assert.strictEqual(mockElements.copilotBtnArrow.innerText, '◀', '收起后箭头转为呼出指示 ◀');
console.log('✅ PASS [5.2]: 点击【收起】按钮成功收起 AI 助手，按钮恢复待呼出状态！');

// 5.3 切换至【自选个股】后再次点击【AI助手】滑出
sandbox.window.AppState.activeRightTab = 'watchlist';
handleBtn();
assert(!mockElements.appContainer.classList.contains('copilot-collapsed'), '再次点击【AI助手】成功滑出');
assert(mockElements.chatMessages.innerHTML.includes('自选个股量化诊断助手'), '自选个股工作区滑出的 AI 助手必须展示自选个股专属问候语');
assert(mockElements.chatMessages.innerHTML.includes('透视主力筹码分布'), '必须包含自选个股专属推荐操作');
console.log('✅ PASS [5.3]: 在自选个股工作区滑出 AI 助手，问候提示语与推荐操作与自选个股完全契合！');

console.log('\n🎉 所有新增测试用例 100% 全部通过！');
