/**
 * tests/test_workbench_header_module_actions.js
 * 验证：【预览/源码、目录导航、复制代码、独立窗口】按钮仅在【投研助手】工作区显示，其他菜单模块的 title 栏显示各自专属的功能按钮
 */

const fs = require('fs');
const assert = require('assert');
const path = require('path');
const vm = require('vm');

console.log('=== [验证：工作台 Title 栏各菜单模块专属功能按钮与投研助手隔离断言] ===\n');

// 1. 静态结构检测：web/index.html
console.log('--- 1. web/index.html Title 栏各模块专属 Action Group 结构断言 ---');
const indexHtml = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');

assert(indexHtml.includes('id="workbenchHeaderActions"'), 'index.html 必须包含 workbenchHeaderActions');
assert(indexHtml.includes('id="actionsDashboard"'), 'index.html 必须包含投研助手专属 actionsDashboard 分组');
assert(indexHtml.includes('id="actionsMarket"'), 'index.html 必须包含市场行情专属 actionsMarket 分组');
assert(indexHtml.includes('id="actionsWatchlist"'), 'index.html 必须包含自选个股专属 actionsWatchlist 分组');
assert(indexHtml.includes('id="actionsReturns"'), 'index.html 必须包含收益分析专属 actionsReturns 分组');
assert(indexHtml.includes('id="actionsSkills"'), 'index.html 必须包含技能治理专属 actionsSkills 分组');
assert(indexHtml.includes('id="actionsProjectedAction"'), 'index.html 必须包含实战动作单专属 actionsProjectedAction 分组');

// 断言 actionsDashboard 内部包含【预览/源码、目录导航、复制代码、独立窗口】4项按钮
const dashIdx = indexHtml.indexOf('id="actionsDashboard"');
const marketIdx = indexHtml.indexOf('id="actionsMarket"');
const dashHtml = indexHtml.slice(dashIdx, marketIdx);

assert(dashHtml.includes('id="workspaceViewSwitcher"'), 'actionsDashboard 必须包含预览/源码切换器');
assert(dashHtml.includes('id="btnWorkspaceViewPreview"'), 'actionsDashboard 必须包含预览按钮');
assert(dashHtml.includes('id="btnWorkspaceViewSource"'), 'actionsDashboard 必须包含源码按钮');
assert(dashHtml.includes('id="btnWorkspaceToggleToc"'), 'actionsDashboard 必须包含目录导航按钮');
assert(dashHtml.includes('id="btnDocMetaCopy"'), 'actionsDashboard 必须包含复制代码按钮');
assert(dashHtml.includes('id="btnWorkspaceOpenExternal"'), 'actionsDashboard 必须包含独立窗口按钮');

// 断言各其他模块具备专属功能按钮
const mktHtml = indexHtml.slice(marketIdx, indexHtml.indexOf('id="actionsWatchlist"'));
assert(mktHtml.includes('刷新行情'), 'actionsMarket 必须包含【刷新行情】功能按钮');
assert(mktHtml.includes('盘面研判'), 'actionsMarket 必须包含【盘面研判】功能按钮');
assert(mktHtml.includes('指标设置'), 'actionsMarket 必须包含【指标设置】功能按钮');
assert(mktHtml.includes('对比指数'), 'actionsMarket 必须包含【对比指数】功能按钮');

const watchHtml = indexHtml.slice(indexHtml.indexOf('id="actionsWatchlist"'), indexHtml.indexOf('id="actionsReturns"'));
assert(watchHtml.includes('添加自选'), 'actionsWatchlist 必须包含【添加自选】功能按钮');
assert(watchHtml.includes('刷新自选'), 'actionsWatchlist 必须包含【刷新自选】功能按钮');
assert(watchHtml.includes('个股研判'), 'actionsWatchlist 必须包含【个股研判】功能按钮');
assert(watchHtml.includes('分组管理'), 'actionsWatchlist 必须包含【分组管理】功能按钮');

const retHtml = indexHtml.slice(indexHtml.indexOf('id="actionsReturns"'), indexHtml.indexOf('id="actionsSkills"'));
assert(retHtml.includes('刷新收益'), 'actionsReturns 必须包含【刷新收益】功能按钮');
assert(retHtml.includes('收益归因'), 'actionsReturns 必须包含【收益归因】功能按钮');
assert(retHtml.includes('切换周期'), 'actionsReturns 必须包含【切换周期】功能按钮');
assert(retHtml.includes('导出报表'), 'actionsReturns 必须包含【导出报表】功能按钮');

const skillsHtml = indexHtml.slice(indexHtml.indexOf('id="actionsSkills"'), indexHtml.indexOf('id="actionsProjectedAction"'));
assert(skillsHtml.includes('刷新状态'), 'actionsSkills 必须包含【刷新状态】功能按钮');
assert(skillsHtml.includes('全部启用'), 'actionsSkills 必须包含【全部启用】功能按钮');
assert(skillsHtml.includes('在线调试'), 'actionsSkills 必须包含【在线调试】功能按钮');
assert(skillsHtml.includes('治理咨询'), 'actionsSkills 必须包含【治理咨询】功能按钮');

console.log('✅ PASS [静态 1]: HTML 结构中全部 6 大模块的专属功能按钮组定义完备且精准封装！');

// 2. 静态样式断言：web/css/style.css
console.log('\n--- 2. web/css/style.css 样式隔离断言 ---');
const styleCss = fs.readFileSync(path.join(__dirname, '../web/css/style.css'), 'utf8');
assert(styleCss.includes('.workbench-header-actions .header-action-group'), 'style.css 必须包含 .header-action-group 样式声明');
assert(styleCss.includes('.header-action-group[style*="display: none"]'), 'style.css 必须包含强隐藏保障规则');
console.log('✅ PASS [静态 2]: CSS 样式表中 .header-action-group 具备标准间距与强制隐藏规则！');

// 3. 动态沙箱运行时断言：菜单切换与按钮可见性联动
console.log('\n--- 3. 前端运行时 switchRightTab / updateWorkbenchHeaderActions 状态切换沙箱断言 ---');
const appJs = fs.readFileSync(path.join(__dirname, '../web/js/app.js'), 'utf8');

// 模拟 DOM 元素
class MockElement {
  constructor(id, tag = 'div') {
    this.id = id;
    this.tagName = tag.toUpperCase();
    this.style = { display: '' };
    this.innerText = '';
    this.classList = new Set();
  }
}

const mockElements = {
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
  appContainer: new MockElement('appContainer', 'div')
};

const allGroupElems = [
  mockElements.actionsDashboard,
  mockElements.actionsMarket,
  mockElements.actionsWatchlist,
  mockElements.actionsReturns,
  mockElements.actionsSkills,
  mockElements.actionsProjectedAction
];

const sandbox = {
  window: {},
  document: {
    getElementById: (id) => mockElements[id] || null,
    querySelectorAll: (sel) => {
      if (sel === '.header-action-group') return allGroupElems;
      if (sel.includes('.nav-item')) return [];
      if (sel.includes('.right-pane')) return [];
      return [];
    },
    querySelector: () => null,
    addEventListener: () => {}
  },
  AppState: {
    activeRightTab: 'dashboard',
    currentDocFormat: 'markdown',
    layoutMode: 'chat-center',
    isChatStreaming: false
  },
  setTimeout: (fn) => fn(),
  clearTimeout: () => {},
  console: console,
  showToast: () => {},
  switchLayoutMode: () => {},
  initSkillsGovernance: () => {},
  renderTabCharts: () => {}
};

vm.createContext(sandbox);

// 提取 ViewHeaderInfo 与 updateWorkbenchHeaderActions、switchRightTab
const snippet = `
${appJs.slice(appJs.indexOf('const ViewHeaderInfo = {'), appJs.indexOf('// Dynamically open a new tab on the right'))}
`;

vm.runInContext(snippet, sandbox);

// 测试 3.1: 激活 dashboard
console.log('--- 测试 3.1: 激活【投研助手】(dashboard) ---');
sandbox.switchRightTab('dashboard');
assert.strictEqual(mockElements.actionsDashboard.style.display, 'inline-flex', '【投研助手】下 actionsDashboard 必须显示');
assert.strictEqual(mockElements.actionsMarket.style.display, 'none', '【投研助手】下 actionsMarket 必须隐藏');
assert.strictEqual(mockElements.actionsWatchlist.style.display, 'none', '【投研助手】下 actionsWatchlist 必须隐藏');
assert.strictEqual(mockElements.actionsReturns.style.display, 'none', '【投研助手】下 actionsReturns 必须隐藏');
assert.strictEqual(mockElements.actionsSkills.style.display, 'none', '【投研助手】下 actionsSkills 必须隐藏');
console.log('✅ PASS [3.1]: 【投研助手】下预览/源码/目录/复制/独立窗口组可见，其他模块按钮完全隐藏');

// 测试 3.2: 切换至【市场行情】(market)
console.log('--- 测试 3.2: 切换至【市场行情】(market) ---');
sandbox.switchRightTab('market');
assert.strictEqual(mockElements.actionsDashboard.style.display, 'none', '【市场行情】下 actionsDashboard 必须隐藏');
assert.strictEqual(mockElements.actionsMarket.style.display, 'inline-flex', '【市场行情】下 actionsMarket 必须显示');
assert.strictEqual(mockElements.actionsWatchlist.style.display, 'none', '【市场行情】下 actionsWatchlist 必须隐藏');
assert.strictEqual(mockElements.workbenchHeaderTitle.innerText, '市场行情全景', '标题必须更新为【市场行情全景】');
assert.strictEqual(mockElements.workbenchHeaderTag.innerText, '实时行情与主力资金流向', '副标题必须更新为【实时行情与主力资金流向】');
console.log('✅ PASS [3.2]: 【市场行情】下仅展示市场行情专属按钮，投研助手按钮组已隐藏');

// 测试 3.3: 切换至【自选个股】(watchlist)
console.log('--- 测试 3.3: 切换至【自选个股】(watchlist) ---');
sandbox.switchRightTab('watchlist');
assert.strictEqual(mockElements.actionsDashboard.style.display, 'none', '【自选个股】下 actionsDashboard 必须隐藏');
assert.strictEqual(mockElements.actionsWatchlist.style.display, 'inline-flex', '【自选个股】下 actionsWatchlist 必须显示');
assert.strictEqual(mockElements.actionsMarket.style.display, 'none', '【自选个股】下 actionsMarket 必须隐藏');
assert.strictEqual(mockElements.workbenchHeaderTitle.innerText, '自选个股深度研判', '标题必须更新为【自选个股深度研判】');
console.log('✅ PASS [3.3]: 【自选个股】下仅展示自选个股专属按钮，投研助手按钮组已隐藏');

// 测试 3.4: 切换至【收益分析】(returns)
console.log('--- 测试 3.4: 切换至【收益分析】(returns) ---');
sandbox.switchRightTab('returns');
assert.strictEqual(mockElements.actionsDashboard.style.display, 'none', '【收益分析】下 actionsDashboard 必须隐藏');
assert.strictEqual(mockElements.actionsReturns.style.display, 'inline-flex', '【收益分析】下 actionsReturns 必须显示');
assert.strictEqual(mockElements.workbenchHeaderTitle.innerText, '投资收益全景分析', '标题必须更新为【投资收益全景分析】');
console.log('✅ PASS [3.4]: 【收益分析】下仅展示收益分析专属按钮，投研助手按钮组已隐藏');

// 测试 3.5: 切换至【技能治理】(skills)
console.log('--- 测试 3.5: 切换至【技能治理】(skills) ---');
sandbox.switchRightTab('skills');
assert.strictEqual(mockElements.actionsDashboard.style.display, 'none', '【技能治理】下 actionsDashboard 必须隐藏');
assert.strictEqual(mockElements.actionsSkills.style.display, 'inline-flex', '【技能治理】下 actionsSkills 必须显示');
assert.strictEqual(mockElements.workbenchHeaderTitle.innerText, '技能治理中心', '标题必须更新为【技能治理中心】');
console.log('✅ PASS [3.5]: 【技能治理】下仅展示技能治理专属按钮，投研助手按钮组已隐藏');

// 测试 3.6: 重新切回【投研助手】(dashboard)
console.log('--- 测试 3.6: 重新切回【投研助手】(dashboard) ---');
sandbox.switchRightTab('dashboard');
assert.strictEqual(mockElements.actionsDashboard.style.display, 'inline-flex', '重新切回【投研助手】actionsDashboard 必须再次显示');
assert.strictEqual(mockElements.actionsMarket.style.display, 'none', '重新切回【投研助手】actionsMarket 必须隐藏');
assert.strictEqual(mockElements.actionsSkills.style.display, 'none', '重新切回【投研助手】actionsSkills 必须隐藏');
assert.strictEqual(mockElements.workbenchHeaderTitle.innerText, '用户操作指南', '标题必须恢复为【用户操作指南】');
console.log('✅ PASS [3.6]: 重新切回【投研助手】后操作按钮组无缝恢复');

console.log('\n🎉 全部测试用例 100% 通过！各模块 title 栏按钮隔离与动态路由完全符合要求！');
