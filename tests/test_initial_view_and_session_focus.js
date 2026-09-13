// -*- coding: utf-8 -*-
/**
 * test_initial_view_and_session_focus.js
 * 验证：打开系统界面时，焦点在【投研助手】，会话记录中无任何选中或焦点状态
 * 
 * 1. 初始状态：AppState.currentSessionId 为 null
 * 2. 初始渲染：renderSessionList() 渲染的历史会话中无任何项具备 active 类名
 * 3. 后端加载：initSessionsFromBackend() 拉取会话列表后，不自动选中第一条或任何历史会话
 * 4. 界面焦点：初始打开时导航焦点锁定在【投研助手】(data-tab="dashboard")，工作台处于投研助手居中模式
 * 5. 欢迎页面：中间对话区域完整保留默认的投研助手欢迎与功能介绍卡片，不被历史会话冲刷
 * 6. 后续交互：用户主动点击某个会话或新建时，才激活对应选中状态
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

console.log('=== [验证打开系统界面时焦点在【投研助手】且会话记录无选中状态] ===\n');

const htmlSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const cssSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'css', 'style.css'), 'utf8');
const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'app.js'), 'utf8');

// --------------------------------------------------------------------------
// 1. HTML 静态结构断言
// --------------------------------------------------------------------------
assert.ok(
  htmlSource.includes('class="nav-item active" data-tab="dashboard"'),
  'HTML 中【投研助手】导航项必须预设 active 类名，保证打开即聚焦在投研助手'
);
assert.ok(
  htmlSource.includes('id="sessionList"'),
  'HTML 中必须包含会话记录容器 #sessionList'
);
assert.ok(
  htmlSource.includes('welcome-intro-card'),
  'HTML 中中间栏必须预置投研助手欢迎卡片'
);
console.log('✅ PASS [静态结构]: HTML 预设焦点在【投研助手】，且中间栏预置欢迎卡片');

// --------------------------------------------------------------------------
// 2. CSS 样式断言 (outline 与焦点状态)
// --------------------------------------------------------------------------
assert.ok(
  cssSource.includes('.session-item:focus') && cssSource.includes('outline: none'),
  'CSS 必须对 .session-item:focus 定义 outline: none，杜绝浏览器默认聚焦蓝框'
);
assert.ok(
  cssSource.includes('.session-more-btn:focus') && cssSource.includes('outline: none'),
  'CSS 必须对 .session-more-btn:focus 定义 outline: none'
);
console.log('✅ PASS [CSS 聚焦规范]: 会话条目与更多按钮无突兀 outline 焦点框');

// --------------------------------------------------------------------------
// 3. 源码契约断言 (app.js)
// --------------------------------------------------------------------------
// 3.1 renderSessionList 中不得使用 idx === 0 兜底激活
assert.ok(
  !appSource.includes('AppState.currentSessionId : idx === 0'),
  'renderSessionList 严禁在 currentSessionId 为空时使用 idx === 0 默认激活第一项'
);
assert.ok(
  appSource.includes('Boolean(AppState.currentSessionId && s.id === AppState.currentSessionId)'),
  'renderSessionList 必须严格根据 currentSessionId 匹配激活状态'
);

// 3.2 initSessionsFromBackend 不得在初始化时强行选中第一条
assert.ok(
  !appSource.includes('selectSession(HistoricalSessions[0].id)'),
  'initSessionsFromBackend 严禁在数据载入后自动调用 selectSession(HistoricalSessions[0].id)'
);
assert.ok(
  appSource.includes('AppState.currentSessionId: null') || appSource.includes('currentSessionId: null'),
  'AppState 必须初始声明 currentSessionId 为 null'
);
console.log('✅ PASS [代码契约]: 移除了 idx === 0 与 selectSession 首项自动选中逻辑');

// --------------------------------------------------------------------------
// 4. 沙箱运行时模拟断言
// --------------------------------------------------------------------------
class MockClassList {
  constructor() {
    this.classes = new Set();
  }
  add(...cls) { cls.forEach(c => this.classes.add(c)); }
  remove(...cls) { cls.forEach(c => this.classes.delete(c)); }
  contains(c) { return this.classes.has(c); }
  get value() { return Array.from(this.classes).join(' '); }
}

class MockElement {
  constructor(id = '', tagName = 'div') {
    this.id = id;
    this.tagName = tagName;
    this.classList = new MockClassList();
    this.style = {};
    this.dataset = {};
    this._innerHTML = '';
    this.children = [];
  }
  get innerHTML() { return this._innerHTML; }
  set innerHTML(val) {
    this._innerHTML = val;
  }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  focus() {}
  scrollIntoView() {}
  remove() {}
  appendChild(child) { this.children.push(child); }
  removeChild(child) {
    const idx = this.children.indexOf(child);
    if (idx !== -1) this.children.splice(idx, 1);
  }
}

const mockElements = {
  appContainer: new MockElement('appContainer'),
  sessionList: new MockElement('sessionList'),
  sessionLoadMore: new MockElement('sessionLoadMore'),
  chatMessages: new MockElement('chatMessages'),
  chatHeaderTitle: new MockElement('chatHeaderTitle'),
  chatHeaderStatus: new MockElement('chatHeaderStatus'),
  paneDashboard: new MockElement('pane-dashboard'),
  workbenchHeaderTitle: new MockElement('workbenchHeaderTitle'),
  workbenchIconBadge: new MockElement('workbenchIconBadge'),
  chatInput: new MockElement('chatInput', 'textarea')
};
mockElements.chatMessages.innerHTML = '<div class="welcome-intro-card"><h3>您好！我是您的 A股智能投研助手</h3></div>';

const sandbox = {
  window: {},
  document: {
    getElementById: (id) => mockElements[id] || null,
    createElement: (tag) => new MockElement('', tag),
    body: new MockElement('body'),
    querySelector: (sel) => {
      if (sel.includes('data-tab="dashboard"')) {
        const el = new MockElement();
        el.dataset.tab = 'dashboard';
        return el;
      }
      if (sel === '#chatMessages' || sel === '.chat-messages') return mockElements.chatMessages;
      if (sel === '#chatInput') return mockElements.chatInput;
      return null;
    },
    querySelectorAll: (sel) => {
      if (sel.includes('.sidebar-nav-section .nav-item')) {
        const d = new MockElement(); d.dataset.tab = 'dashboard';
        const m = new MockElement(); m.dataset.tab = 'market';
        return [d, m];
      }
      if (sel.includes('.session-item')) return [];
      if (sel.includes('.right-pane')) return [mockElements.paneDashboard];
      return [];
    },
    addEventListener: () => {},
    removeEventListener: () => {}
  },
  location: { origin: 'http://localhost:8000', hash: '' },
  localStorage: {
    getItem: () => null,
    setItem: () => null,
    removeItem: () => null
  },
  console: console,
  setTimeout: (fn) => fn(),
  clearTimeout: () => {},
  AbortController: class { abort() {} },
  Event: class { constructor(type) { this.type = type; } }
};
sandbox.window = sandbox;
sandbox.addEventListener = () => {};
sandbox.removeEventListener = () => {};
sandbox.dispatchEvent = () => {};

vm.createContext(sandbox);
vm.runInContext(appSource, sandbox);

// 4.1 验证 AppState 初始状态
assert.strictEqual(sandbox.AppState.currentSessionId, null, '初始 AppState.currentSessionId 必须为 null');
assert.strictEqual(sandbox.AppState.activeRightTab, 'dashboard', '初始 activeRightTab 必须为 dashboard (投研助手)');
assert.strictEqual(sandbox.AppState.layoutMode, 'chat-center', '初始 layoutMode 必须为 chat-center (投研助手居中)');
console.log('✅ PASS [运行时初始状态]: AppState.currentSessionId 为 null，工作区锁定投研助手居中');

// 4.2 验证初始调用 renderSessionList() 时无任何 session-item 带有 active 类
sandbox.renderSessionList();
const renderedHtml = mockElements.sessionList.innerHTML;
assert.ok(renderedHtml.includes('session-item'), 'sessionList 必须渲染了会话条目');
assert.ok(!renderedHtml.includes('session-item active'), '初始渲染时严禁任何条目包含 session-item active 类名');
console.log('✅ PASS [会话列表初始渲染]: renderSessionList() 渲染结果中 0 个条目被选中或高亮');

// 4.3 验证模拟后端加载后，会话列表已更新但依然无任何条目被选中
sandbox.window.AStockAPI = {
  listSessions: async () => [
    { session_id: 'sess_db_001', title: '后端真实历史会话1', time: '刚刚' },
    { session_id: 'sess_db_002', title: '后端真实历史会话2', time: '昨天' }
  ],
  getSession: async () => ({ session_id: 'sess_db_001', messages: [] }),
  getPortfolioOverview: async () => null,
  getMarketIndices: async () => [],
  getMarketOverview: async () => null
};

sandbox.initSessionsFromBackend().then(() => {
  assert.strictEqual(sandbox.AppState.currentSessionId, null, '后端列表加载后 currentSessionId 依然保持 null');
  const backendRenderedHtml = mockElements.sessionList.innerHTML;
  assert.ok(backendRenderedHtml.includes('sess_db_001'), '渲染了后端会话1');
  assert.ok(!backendRenderedHtml.includes('session-item active'), '后端载入后条目依然绝无 active 状态');
  assert.ok(
    mockElements.chatMessages.innerHTML.includes('welcome-intro-card'),
    '中间对话区域依然保留欢迎卡片，绝不被历史会话覆盖'
  );
  console.log('✅ PASS [后端数据加载后]: 保持无选中状态，欢迎介绍卡片完整保留');

  // 4.4 验证当用户主动点击某一条会话后，才呈现 active 状态
  sandbox.selectSession('sess_db_001');
  assert.strictEqual(sandbox.AppState.currentSessionId, 'sess_db_001', '主动点击后 currentSessionId 变为选中项 ID');
  sandbox.renderSessionList();
  assert.ok(
    mockElements.sessionList.innerHTML.includes('data-id="sess_db_001"') &&
    mockElements.sessionList.innerHTML.includes('active'),
    '主动点击后该条会话呈现 active 状态'
  );
  console.log('✅ PASS [交互联动验证]: 用户主动点击某条历史会话后正确触发选中与激活');

  console.log('\n🎉 所有关于【打开系统界面时焦点在投研助手且会话记录无选中】断言 100% 全部通过！\n');
});
