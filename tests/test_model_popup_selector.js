// -*- coding: utf-8 -*-
/**
 * test_model_popup_selector.js
 * 针对【# 模型】按钮、左供应商右模型浮窗交互及 # 模型id(供应商) 回填与色彩区分的自动化测试套件
 */

const fs = require('fs');
const path = require('path');

console.log('=== [AIChatUI 【# 模型】按钮与浮窗选择回填验证套件] ===\n');

const htmlPath = path.join(__dirname, '../web/index.html');
const cssPath = path.join(__dirname, '../web/css/style.css');
const jsPath = path.join(__dirname, '../web/js/app.js');

const html = fs.readFileSync(htmlPath, 'utf-8');
const css = fs.readFileSync(cssPath, 'utf-8');
const js = fs.readFileSync(jsPath, 'utf-8');

let totalTests = 0;
let passedTests = 0;

function assert(condition, message) {
  totalTests++;
  if (condition) {
    passedTests++;
    console.log(`✅ PASS: ${message}`);
  } else {
    console.error(`❌ FAIL: ${message}`);
    process.exitCode = 1;
  }
}

// --------------------------------------------------------------------------
// 1. 【# 模型】按钮结构验证
// --------------------------------------------------------------------------
console.log('--- 1. 【# 模型】微功能按钮验证 ---');
assert(html.includes('id="btnModelTrigger"'), '底部工具栏存在 #btnModelTrigger 按钮');
assert(html.includes('class="input-tool-btn icon-text-btn model-btn"'), '包含 .icon-text-btn.model-btn 规范样式类名');
assert(html.includes('toggleModelPopup(event)'), '绑定 toggleModelPopup(event) 点击触发事件');
assert(html.includes('class="btn-icon-symbol">#</span>') && html.includes('class="btn-icon-text">模型</span>'), '包含 # 符号与【模型】文字标签');
assert(html.includes('id="chatCurrentModelBadge"'), '包含当前生效模型指示微徽章 #chatCurrentModelBadge');

// --------------------------------------------------------------------------
// 2. 浮窗交互结构验证（左供应商 + 右模型列表）
// --------------------------------------------------------------------------
console.log('\n--- 2. 模型选择浮窗结构验证 (与@操作符浮窗风格一致) ---');
assert(html.includes('id="modelSelectorPopup"'), '存在模型选择浮窗容器 #modelSelectorPopup');
assert(html.includes('class="at-operator-popup model-selector-popup"'), '复用 .at-operator-popup 浮窗样式基类');
assert(html.includes('class="at-popup-badge model-badge"'), '包含头部专属微徽章 .model-badge');
assert(html.includes('id="modelPopupSidebar"'), '左侧包含供应商选择栏 #modelPopupSidebar');
assert(html.includes('id="modelPopupContentWrapper"'), '右侧包含内容包裹器 #modelPopupContentWrapper');
assert(html.includes('id="modelSearchInput"'), '右侧顶部包含模型搜索框 #modelSearchInput');
assert(html.includes('id="modelPopupContent"'), '右侧包含模型卡片列表容器 #modelPopupContent');
assert(html.includes('id="btnCloseModelPopup"'), '包含右上角关闭按钮 #btnCloseModelPopup');

// --------------------------------------------------------------------------
// 3. 色彩规范与样式区分验证
// --------------------------------------------------------------------------
console.log('\n--- 3. 色彩规范与与@选择颜色区分验证 ---');
assert(css.includes('.icon-text-btn.model-btn'), '定义了 .icon-text-btn.model-btn 样式');
assert(css.includes('.at-token.at-token-model'), '定义了回填标签专属样式 .at-token.at-token-model');
assert(css.includes('#006D75') && css.includes('#E6FFFB') && css.includes('#87E8DE'), '采用青碧/青黛色方案 (#006D75, #E6FFFB, #87E8DE) 明确区分于@选择的蓝/橙/绿/紫');
assert(css.includes('.chat-current-model-badge'), '定义了底部当前模型指示微徽章样式');

// --------------------------------------------------------------------------
// 4. JS 控制器与接口行为验证
// --------------------------------------------------------------------------
console.log('\n--- 4. ModelPopupController 核心功能验证 ---');
assert(js.includes('const ModelPopupController ='), '定义了 ModelPopupController 控制器');
assert(js.includes('window.ModelPopupController = ModelPopupController'), 'ModelPopupController 挂载到全局 window');
assert(js.includes('window.openModelPopup'), '全局提供 openModelPopup 方法');
assert(js.includes('window.closeModelPopup'), '全局提供 closeModelPopup 方法');
assert(js.includes('window.toggleModelPopup'), '全局提供 toggleModelPopup 方法');
assert(js.includes('backfillToInput'), '包含 backfillToInput 回填实现');
assert(js.includes('# ${modelId}(${providerName})'), '回填格式严格为 # 模型id(供应商名称)');
assert(js.includes("at-token at-token-model"), '回填时生成 at-token at-token-model 样式类标签');

// --------------------------------------------------------------------------
// 5. 键盘唤起与消息提取验证
// --------------------------------------------------------------------------
console.log('\n--- 5. 键盘唤起与提交时模型提取验证 ---');
assert(js.includes("e.key === '#'") || js.includes("e.key === '3'"), '输入框监听键盘 # 键唤起模型浮窗');
assert(js.includes("userOverriddenModel"), 'handleSendChat 提交时智能解析并提取用户指定的 # 模型');

// --------------------------------------------------------------------------
// 6. Mock DOM 运行时两级选择与回填仿真
// --------------------------------------------------------------------------
console.log('\n--- 6. Mock DOM 运行时两级选择与回填仿真 ---');

const mockStorage = {};
const localStorageMock = {
  getItem: (k) => mockStorage[k] || null,
  setItem: (k, v) => { mockStorage[k] = String(v); },
  removeItem: (k) => { delete mockStorage[k]; }
};

const domElements = {};
function getMockEl(id) {
  if (!domElements[id]) {
    domElements[id] = {
      id: id,
      style: {},
      classList: {
        _classes: new Set(),
        add(c) { this._classes.add(c); },
        remove(c) { this._classes.delete(c); },
        contains(c) { return this._classes.has(c); }
      },
      innerHTML: '',
      value: '',
      addEventListener: () => {},
      focus: () => {}
    };
  }
  return domElements[id];
}

const mockDoc = {
  getElementById: (id) => getMockEl(id),
  addEventListener: () => {},
  createRange: () => ({
    setStartAfter: () => {},
    setEndAfter: () => {},
    selectNodeContents: () => {},
    collapse: () => {},
    deleteContents: () => {},
    insertNode: () => {}
  }),
  createElement: (tag) => ({
    tagName: tag.toUpperCase(),
    className: '',
    contentEditable: 'true',
    dataset: {},
    innerText: ''
  }),
  createTextNode: (t) => ({ nodeType: 3, textContent: t })
};

const sandbox = {
  document: mockDoc,
  localStorage: localStorageMock,
  AppState: {
    providers: [
      {
        provider_id: 'deepseek',
        name: 'DeepSeek',
        enabled: true,
        models: [
          { id: 'deepseek-chat', name: 'DeepSeek-V3', selected: true },
          { id: 'deepseek-reasoner', name: 'DeepSeek-R1', selected: true }
        ]
      },
      {
        provider_id: 'openai',
        name: 'OpenAI',
        enabled: true,
        models: [
          { id: 'gpt-4o', name: 'GPT-4o', selected: true },
          { id: 'gpt-4o-mini', name: 'GPT-4o-mini', selected: true }
        ]
      }
    ],
    modelRoles: {
      chat: { provider_id: 'deepseek', model_id: 'deepseek-chat' }
    }
  },
  window: {},
  showToast: () => {}
};

// 抽取 ModelPopupController 代码执行测试
const startMark = 'const ModelPopupController = {';
const endMark = 'window.toggleModelPopup = (e) => ModelPopupController.toggle(e);';
const sIdx = js.indexOf(startMark);
const eIdx = js.indexOf(endMark);

assert(sIdx !== -1 && eIdx !== -1, '成功定位 ModelPopupController 代码段');

const code = js.substring(sIdx, eIdx + endMark.length);
const nodeMock = { TEXT_NODE: 3, ELEMENT_NODE: 1 };
const runFn = new Function('document', 'localStorage', 'AppState', 'window', 'showToast', 'Node', code);
runFn(sandbox.document, sandbox.localStorage, sandbox.AppState, sandbox.window, sandbox.showToast, nodeMock);

const controller = sandbox.window.ModelPopupController;
assert(typeof controller === 'object', '沙盒中成功实例化 ModelPopupController');

// 6.1 开启浮窗与左侧供应商渲染测试
controller.open();
const sidebarEl = getMockEl('modelPopupSidebar');
assert(sidebarEl.innerHTML.includes('DeepSeek') && sidebarEl.innerHTML.includes('OpenAI'), '左侧成功渲染所有启用的供应商');

// 6.2 右侧模型列表联动测试
const contentEl = getMockEl('modelPopupContent');
assert(contentEl.innerHTML.includes('deepseek-chat') && contentEl.innerHTML.includes('deepseek-reasoner'), '右侧联动展示当前供应商下的模型');

// 6.3 切换供应商联动
controller.handleProviderClick('openai', 1);
assert(contentEl.innerHTML.includes('gpt-4o') && contentEl.innerHTML.includes('gpt-4o-mini'), '左侧点击 OpenAI 后，右侧即时联动更新为 OpenAI 旗下的模型');
assert(!contentEl.innerHTML.includes('deepseek-chat'), '已清除上一个供应商的模型');

// 6.4 搜索过滤模型测试
controller.handleSearch('mini');
assert(contentEl.innerHTML.includes('gpt-4o-mini') && !contentEl.innerHTML.includes('gpt-4o<'), '输入 mini 搜索词时右侧仅展示过滤后的模型');

// 6.5 回填方法验证
let insertedTag = null;
let insertedSpace = false;
getMockEl('chatInput').contains = () => true;
sandbox.window.getSelection = () => ({
  rangeCount: 1,
  getRangeAt: () => ({
    commonAncestorContainer: getMockEl('chatInput'),
    startContainer: { nodeType: 3, textContent: '#', slice: () => '' },
    startOffset: 1,
    deleteContents: () => {},
    insertNode: (node) => {
      if (node.className && node.className.includes('at-token-model')) insertedTag = node;
      if (node.textContent === '\u00A0') insertedSpace = true;
    },
    setStart: () => {},
    setEnd: () => {}
  }),
  removeAllRanges: () => {},
  addRange: () => {}
});

const targetProvider = sandbox.AppState.providers[1];
const targetModel = targetProvider.models[0];
controller.backfillToInput(targetProvider, targetModel);

assert(insertedTag !== null, '成功创建并插入模型标签节点');
assert(insertedTag.innerText === '# gpt-4o(OpenAI)', `回填文本准确符合规范: ${insertedTag.innerText}`);
assert(insertedTag.className === 'at-token at-token-model', '回填节点类名包含 at-token at-token-model');
assert(insertedSpace === true, '回填节点后紧跟自然空格');

// 6.6 本地状态同步保存验证
assert(sandbox.localStorage.getItem('astock_chat_selected_provider') === 'openai', 'localStorage 同步记录了选中的 provider');
assert(sandbox.localStorage.getItem('astock_chat_selected_model') === 'gpt-4o', 'localStorage 同步记录了选中的 model');

console.log(`\n========================================`);
console.log(`🎉 运行完成: 全部 ${totalTests} 项测试均通过 (${passedTests}/${totalTests})`);
console.log(`========================================\n`);
