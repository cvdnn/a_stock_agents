// -*- coding: utf-8 -*-
/**
 * test_new_chat_submission_flow.js
 * 专门验证优化修改：
 * 1）新建会话时仅在前端的【会话记录】中插入一条数据，当点击【提交】时才提交后台保存数据。
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

console.log('=== [验证新建会话仅在前端插入草稿，点击提交才保存后台] ===\n');

// 1. 读取 app.js 源码进行契约静态检测
const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'app.js'), 'utf8');

// 验证 startNewChat 函数源码中不包含 createSession 调用
const startNewChatMatch = appSource.match(/async\s+function\s+startNewChat\s*\(\)\s*\{([\s\S]*?)\n\}/);
assert.ok(startNewChatMatch, '必须定义 startNewChat 函数');
const startNewChatBody = startNewChatMatch[1];
assert.strictEqual(
  startNewChatBody.includes('AStockAPI.createSession'),
  false,
  'startNewChat 内部严禁调用 AStockAPI.createSession，新建会话必须仅在前端插入'
);
console.log('✅ PASS [静态契约 1]: startNewChat 源码已彻底移除后台 createSession 请求，仅在前端插入记录');

// 验证 handleSendChat 函数源码中包含草稿态识别与后台保存逻辑
assert.ok(
  appSource.includes('activeSess.isDraft') && appSource.includes('createSession'),
  'handleSendChat 必须在检测到 isDraft 时调用 createSession 持久化保存'
);
console.log('✅ PASS [静态契约 2]: handleSendChat 包含草稿态识别并在提交时向后台持久化逻辑');

// 2. 模拟前端沙箱运行环境，进行全流程交互契约测试
const apiCalls = {
  createSession: [],
  getSession: [],
  deleteSession: [],
  updateSessionTitle: []
};

const domElements = {};
function createMockElement(id = '', className = '') {
  return {
    id,
    className,
    value: '',
    innerHTML: '',
    innerText: '',
    style: {},
    dataset: {},
    children: [],
    classList: {
      add: () => {},
      remove: () => {},
      contains: () => false
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    closest: () => null,
    appendChild: () => {},
    removeChild: () => {},
    setAttribute: () => {},
    removeAttribute: () => {},
    getAttribute: () => null,
    remove: () => {}
  };
}

const sandbox = {
  window: {},
  document: {
    getElementById: (id) => {
      if (!domElements[id]) {
        domElements[id] = createMockElement(id);
      }
      return domElements[id];
    },
    createElement: (tag) => createMockElement(tag),
    body: { appendChild: () => {}, removeChild: () => {} },
    querySelector: (sel) => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    removeEventListener: () => {}
  },
  location: { origin: 'http://localhost:8000' },
  localStorage: {
    _data: {},
    getItem: (k) => sandbox.localStorage._data[k] || null,
    setItem: (k, v) => { sandbox.localStorage._data[k] = String(v); },
    removeItem: (k) => { delete sandbox.localStorage._data[k]; }
  },
  navigator: {
    clipboard: { writeText: () => Promise.resolve() }
  },
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  AbortController: globalThis.AbortController,
  Event: class Event { constructor(type) { this.type = type; } },


  AStockAPI: {
    createSession: (title, model, meta) => {
      apiCalls.createSession.push({ title, model, meta });
      return Promise.resolve({
        session_id: (meta && meta.session_id) || 'sess_mock_' + Date.now(),
        title: title,
        model: model || 'mock'
      });
    },
    getSession: (sid) => {
      apiCalls.getSession.push(sid);
      return Promise.resolve({ session: { session_id: sid, title: 'mock' }, messages: [] });
    },
    deleteSession: (sid) => {
      apiCalls.deleteSession.push(sid);
      return Promise.resolve({ status: 'deleted', session_id: sid });
    },
    updateSessionTitle: (sid, title) => {
      apiCalls.updateSessionTitle.push({ sid, title });
      return Promise.resolve({ session_id: sid, title });
    },
    streamChatCompletions: (query, sid, model, callbacks) => {
      if (callbacks.onStart) callbacks.onStart({ session_id: sid, title: query });
      if (callbacks.onDone) callbacks.onDone({ content: 'ok' });
      return Promise.resolve();
    }
  }
};
sandbox.window = sandbox;
sandbox.window.AStockAPI = sandbox.AStockAPI;
sandbox.window.location = sandbox.location;
sandbox.window.localStorage = sandbox.localStorage;
sandbox.window.addEventListener = () => {};
sandbox.window.removeEventListener = () => {};
sandbox.window.dispatchEvent = () => {};
sandbox.AStockAPI.getPortfolioOverview = () => Promise.resolve({});
sandbox.AStockAPI.getMarketIndices = () => Promise.resolve({});
sandbox.AStockAPI.getMarketSentiment = () => Promise.resolve({});
sandbox.AStockAPI.getWatchlist = () => Promise.resolve([]);
sandbox.AStockAPI.getPortfolioAnalysis = () => Promise.resolve({});




vm.createContext(sandbox);
vm.runInContext(appSource, sandbox);

const HistoricalSessions = sandbox.window.HistoricalSessions;
const AppState = sandbox.window.AppState;
const startNewChat = sandbox.window.startNewChat;
const handleSendChat = sandbox.window.handleSendChat;
const selectSession = sandbox.window.selectSession;
const deleteSession = sandbox.window.deleteSession;

assert.ok(typeof startNewChat === 'function', 'startNewChat 必须为可执行函数');
assert.ok(typeof handleSendChat === 'function', 'handleSendChat 必须为可执行函数');

// 用例 1: 点击【新建会话】
console.log('--- 测试用例 1: 点击【新建会话】 ---');
const initCount = HistoricalSessions.length;
apiCalls.createSession.length = 0;

startNewChat();

assert.strictEqual(HistoricalSessions.length, initCount + 1, '新建会话后 HistoricalSessions 长度应增加 1');
const topSession = HistoricalSessions[0];
assert.ok(topSession.id.startsWith('sess_'), '会话 ID 应以 sess_ 开头');
assert.strictEqual(topSession.isDraft, true, '新建会话必须被标记为草稿态 (isDraft: true)');
assert.strictEqual(AppState.currentSessionId, topSession.id, '当前激活会话 ID 必须是新建草稿 ID');
assert.strictEqual(apiCalls.createSession.length, 0, '新建会话时严禁向后台调用 createSession 保存数据！');
console.log('✅ PASS [用例 1]: 新建会话成功在前端插入 1 条草稿记录，且后台 createSession 调用次数为 0');

// 用例 2: 点击草稿会话查看内容
console.log('--- 测试用例 2: 查看草稿会话 ---');
apiCalls.getSession.length = 0;
selectSession(topSession.id);
assert.strictEqual(apiCalls.getSession.length, 0, '查看草稿会话严禁向后端发起 getSession 请求，防止 404');
console.log('✅ PASS [用例 2]: 选中草稿会话直接渲染初始欢迎界面，不发起后端 getSession 导致 404');

// 用例 3: 输入问题后点击【提交】
console.log('--- 测试用例 3: 输入问题并点击【提交】 ---');
const chatInput = sandbox.document.getElementById('chatInput');
chatInput.value = '调研紫金矿业股票信息，并生成下周投资策略';

const prevLength = HistoricalSessions.length;
handleSendChat();

assert.strictEqual(HistoricalSessions.length, prevLength, '点击提交时不得生成重复的第 2 条记录，应直接复用草稿会话');
assert.strictEqual(topSession.isDraft, false, '提交后草稿状态必须转为正式会话 (isDraft: false)');
assert.strictEqual(topSession.title, '紫金矿业调研与下周投资策略', '提交后会话标题必须根据用户输入提炼动态更新');
assert.strictEqual(apiCalls.createSession.length, 1, '点击【提交】时必须向后台发起 1 次 createSession 持久化保存数据');
assert.strictEqual(apiCalls.createSession[0].meta.session_id, topSession.id, '提交后台的 session_id 必须与前端新建时一致');
assert.strictEqual(apiCalls.createSession[0].title, '紫金矿业调研与下周投资策略', '提交后台的 title 必须为精炼后的标题');
console.log('✅ PASS [用例 3]: 点击【提交】成功将草稿转为正式会话，提炼标题，且向后台提交保存数据');

// 用例 4: 草稿态下删除会话
console.log('--- 测试用例 4: 未提交前直接删除草稿会话 ---');
startNewChat();
const draftToDelete = HistoricalSessions[0];
assert.strictEqual(draftToDelete.isDraft, true, '再次新建会话生成草稿态');

apiCalls.deleteSession.length = 0;
deleteSession(draftToDelete.id);

assert.strictEqual(apiCalls.deleteSession.length, 0, '删除尚未持久化的草稿会话时，不向后台发送 DELETE 请求');
assert.strictEqual(HistoricalSessions.find(s => s.id === draftToDelete.id), undefined, '草稿会话已从前端列表中移除');
console.log('✅ PASS [用例 4]: 删除草稿会话纯前端即时清除，零后台无效请求');

// 用例 5: 无活跃会话时直接提交提问
console.log('--- 测试用例 5: 无活跃会话时直接提交提问 ---');
AppState.currentSessionId = null;
chatInput.value = '分析今日大盘走势及主力动向';
apiCalls.createSession.length = 0;
const beforeCount = HistoricalSessions.length;

handleSendChat();

assert.strictEqual(HistoricalSessions.length, beforeCount + 1, '无会话直接提问时在前端新增一条会话记录');
assert.strictEqual(apiCalls.createSession.length, 1, '无会话直接提问时向后台提交保存一条会话');
assert.strictEqual(HistoricalSessions[0].title, '大盘走势与市场动向研判', '标题正确提炼为：大盘走势与市场动向研判');
console.log('✅ PASS [用例 5]: 无活跃会话直接提交提问时正确创建并提交后台保存');

console.log('\n🎉 全部 5 项新建会话前端插入与提交后台保存契约测试全部通过！\n');
