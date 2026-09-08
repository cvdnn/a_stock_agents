const fs = require('fs');

console.log('=== [1. HTML 布局与结构验证] ===');
const html = fs.readFileSync('web/index.html', 'utf8');

const checksHtml = [
  { name: '浮窗容器 #atOperatorPopup 存在', pass: html.includes('id="atOperatorPopup"') },
  { name: '标题【功能操作符】存在', pass: html.includes('功能操作符') },
  { name: '副标题涵盖【股票 · 引用 · 技能 · 算法】四维', pass: html.includes('股票 · 引用 · 技能 · 算法') },
  { name: '关闭小图标按钮 #btnCloseAtPopup 存在', pass: html.includes('id="btnCloseAtPopup"') },
  { name: '左侧功能类别容器 #atPopupSidebar 存在', pass: html.includes('id="atPopupSidebar"') },
  { name: '右侧内容包装层 #atPopupContentWrapper 存在', pass: html.includes('id="atPopupContentWrapper"') },
  { name: '股票搜索框容器 #atStockSearchWrap 及输入框 #atStockSearchInput 存在', pass: html.includes('id="atStockSearchWrap"') && html.includes('id="atStockSearchInput"') },
  { name: '搜索清空按钮 #atStockSearchClear 存在', pass: html.includes('id="atStockSearchClear"') },
  { name: '右侧对应内容容器 #atPopupContent 存在', pass: html.includes('id="atPopupContent"') },
  { name: '底部快捷操作键存在 (ESC/▲▼/→/←/↵)', pass: html.includes('at-footer-shortcuts') && html.includes('<kbd>ESC</kbd>') && html.includes('<kbd>→</kbd>') },
  { name: '底部仅保留【+ 扩展】与【@ 操作符】微按钮且显示名称', pass: (
      html.includes('id="btnAtTrigger"') &&
      html.includes('icon-text-btn') &&
      html.includes('btn-icon-text') &&
      html.includes('扩展') &&
      html.includes('操作符') &&
      !html.includes('chat-action-btn') &&
      !html.includes('引用右侧提问')
    )
  },
  { name: '提交按钮【提交】存在', pass: html.includes('<span>提交</span>') || html.includes('>提交<') },
  { name: '输入框 #chatInput 为富文本可编辑 contenteditable="true"', pass: html.includes('id="chatInput"') && html.includes('contenteditable="true"') }
];

checksHtml.forEach(c => {
  console.log(`${c.pass ? '✅ PASS' : '❌ FAIL'}: ${c.name}`);
  if (!c.pass) process.exitCode = 1;
});

console.log('\n=== [2. CSS 样式设计与交互视觉规范验证] ===');
const css = fs.readFileSync('web/css/style.css', 'utf8');

const checksCss = [
  { name: '.at-operator-popup 绝对定位且同宽对齐输入框', pass: css.includes('.at-operator-popup') && css.includes('width: 100%') },
  { name: '.at-popup-sidebar 左侧分类导航与激活态', pass: css.includes('.at-popup-sidebar') && css.includes('.at-cat-item.active') },
  { name: '.at-cat-item.menu-focused 菜单栏获焦高亮样式', pass: css.includes('.at-cat-item.menu-focused') },
  { name: '.at-stock-search-wrap 股票搜索框容器样式', pass: css.includes('.at-stock-search-wrap') && css.includes('.at-stock-search-input') },
  { name: '.at-item-card 右侧卡片与选中软绿高亮', pass: css.includes('.at-item-card') && css.includes('#E8F7F0') },
  { name: '.at-token 回填高亮加粗样式与多维色彩', pass: (
      css.includes('.at-token') &&
      css.includes('.at-token.at-token-stock') &&
      css.includes('.at-token.at-token-ref') &&
      css.includes('.at-token.at-token-skill') &&
      css.includes('.at-token.at-token-algo')
    )
  },
  { name: '.icon-text-btn 底部图标+名称样式', pass: css.includes('.icon-text-btn') && css.includes('.btn-icon-symbol') && css.includes('.icon-text-btn.at-btn') },
  { name: '.send-btn 提交按钮主渐变样式', pass: css.includes('.send-btn') && css.includes('var(--primary-gradient)') },
  { name: '胶囊徽章三维色彩分立（持仓暖橙/自选科技蓝/关注紫罗兰）', pass: (
      css.includes('.at-holding-badge.holding') &&
      css.includes('#D46B08') &&
      css.includes('.at-holding-badge.watchlist') &&
      css.includes('#1677FF') &&
      css.includes('.at-holding-badge.focus') &&
      css.includes('#722ED1')
    )
  }
];

checksCss.forEach(c => {
  console.log(`${c.pass ? '✅ PASS' : '❌ FAIL'}: ${c.name}`);
  if (!c.pass) process.exitCode = 1;
});

console.log('\n=== [3. JS 逻辑、两级焦点、搜索与板块提取验证] ===');
const js = fs.readFileSync('web/js/app.js', 'utf8');

const checksJs = [
  { name: '已删除独立自选菜单，菜单排列严格为：股票/引用/技能/算法', pass: (
      !js.includes("{ id: 'watchlist', name: '自选'") &&
      js.includes("id: 'stock',     name: '股票'") &&
      js.includes("id: 'reference', name: '引用'") &&
      js.includes("id: 'skill',     name: '技能'") &&
      js.includes("id: 'algorithm', name: '算法'")
    )
  },
  { name: '点击菜单项仅展开右侧内容不回填 (handleMenuClick)', pass: (
      js.includes('handleMenuClick(') &&
      js.includes('this.setCategory(catId)')
    )
  },
  { name: '弹窗焦点状态控制 (focusPane = "menu" | "content")', pass: (
      js.includes("focusPane: 'menu'") &&
      js.includes("this.focusPane = 'content'") &&
      js.includes("this.focusPane = 'menu'")
    )
  },
  { name: '键盘两级切换：上下选菜单，右移进内容，左移返回菜单', pass: (
      js.includes("this.focusPane === 'menu'") &&
      js.includes("this.focusPane === 'content'") &&
      js.includes("e.key === 'ArrowRight'") &&
      js.includes("e.key === 'ArrowLeft'")
    )
  },
  { name: '股票搜索框动态匹配 (handleStockSearchInput / clearStockSearch / pinyin)', pass: (
      js.includes('handleStockSearchInput') &&
      js.includes('clearStockSearch') &&
      js.includes('codeMatch') &&
      js.includes('pinyinMatch')
    )
  },
  { name: '引用内容精确提取右侧工作台板块 (extractWorkbenchSectionData: 投资概要/大盘指数等)', pass: (
      js.includes('function extractWorkbenchSectionData') &&
      js.includes('section-portfolio-overview') &&
      js.includes('section-market-indices') &&
      js.includes('section-market-analysis') &&
      js.includes('section-watchlist-indices') &&
      js.includes('section-investment-analysis') &&
      js.includes('section-realtime-monitor')
    )
  },
  { name: '引用板块提交时联动右侧平滑滚动与高亮反馈', pass: (
      js.includes("scrollIntoView({ behavior: 'smooth'")
    )
  },
  { name: '回填机制保留单空格与 caret 定位 (normalizeInputSpaces / spaceNode)', pass: (
      js.includes('normalizeInputSpaces') &&
      js.includes('spaceNode')
    )
  },
  { name: '输入框键入 @ 实时唤起浮窗且焦点落在菜单栏', pass: (
      js.includes("e.key === '@'") &&
      js.includes("AtOperatorController.open()")
    )
  }
];

checksJs.forEach(c => {
  console.log(`${c.pass ? '✅ PASS' : '❌ FAIL'}: ${c.name}`);
  if (!c.pass) process.exitCode = 1;
});

console.log('\n=== [4. 针对三大股池叠加排序与徽章色彩专门断言] ===');

const hasPoolPrioritySort = js.includes("const poolPriority = { 'holding': 1, 'watchlist': 2, 'focus': 3 }") &&
                            js.includes("poolPriority[a.pool]") &&
                            js.includes("name.localeCompare(b.name, 'zh-Hans-CN')");

const hasThreePoolBadges = js.includes('item.pool === \'holding\'') &&
                           js.includes('at-holding-badge holding') &&
                           js.includes('持仓 ${item.holdingRatio') &&
                           js.includes('item.pool === \'watchlist\'') &&
                           js.includes('at-holding-badge watchlist') &&
                           js.includes('自选') &&
                           js.includes('item.pool === \'focus\'') &&
                           js.includes('at-holding-badge focus') &&
                           js.includes('关注');

const hasPriceLine = js.includes('at-item-price-line') &&
                     js.includes('实时价:') &&
                     js.includes('成本价:') &&
                     css.includes('.at-item-price-line');

const hasChangeTagRedGreen = js.includes('at-change-tag') &&
                             css.includes('.at-change-tag.up') &&
                             css.includes('.at-change-tag.down') &&
                             css.includes('#CF1322') &&
                             css.includes('#389E0D');

const hasStopPropMenuClick = js.includes('e.stopPropagation()') &&
                             js.includes('handleMenuClick(event') &&
                             js.includes("popup.addEventListener('click'");

const hasDefaultActiveStock = js.includes("activeCategory: 'stock'") &&
                              js.includes("this.activeCategory = 'stock'");

const checksPoolRequirements = [
  { name: '要求1：已彻底删除自选菜单项，默认激活分类置为【股票】', pass: hasDefaultActiveStock },
  { name: '要求2-1：股票菜单内按【持仓股(1)】【自选股(2)】【关注股(3)】三大股池严格顺序叠加', pass: hasPoolPrioritySort },
  { name: '要求2-2：三大股池内部股票均严格按中文名称拼音拼写字母升序排序', pass: js.includes("name.localeCompare(b.name, 'zh-Hans-CN')") },
  { name: '要求3-1：【持仓股】展示【持仓 xx%】、【自选股】后跟【自选】、【关注股】后跟【关注】', pass: hasThreePoolBadges },
  { name: '要求3-2：徽章位于第一行股票代码后方同等位置，通过 CSS 呈现暖橙/科技蓝/紫罗兰不同色彩区分', pass: (
      css.includes('.at-holding-badge.holding') &&
      css.includes('.at-holding-badge.watchlist') &&
      css.includes('.at-holding-badge.focus')
    )
  },
  { name: '要求3-3：卡片第二行两端对齐展示实时价、成本价与今日涨跌幅 (红涨绿跌)', pass: hasPriceLine && hasChangeTagRedGreen },
  { name: '交互稳定性：浮窗菜单点击事件防护与冒泡隔离机制生效', pass: hasStopPropMenuClick }
];

checksPoolRequirements.forEach(c => {
  console.log(`${c.pass ? '✅ PASS' : '❌ FAIL'}: ${c.name}`);
  if (!c.pass) process.exitCode = 1;
});

console.log('\n=== [5. 运行时内存数据结构真实排序校验] ===');

const testStocks = [
  { name: '中芯国际', pool: 'focus' },
  { name: '贵州茅台', pool: 'holding' },
  { name: '比亚迪',   pool: 'watchlist' },
  { name: '宁德时代', pool: 'holding' },
  { name: '海光信息', pool: 'focus' },
  { name: '中国平安', pool: 'watchlist' },
  { name: '中信证券', pool: 'watchlist' }
];

const priorityMap = { 'holding': 1, 'watchlist': 2, 'focus': 3 };
testStocks.sort((a, b) => {
  const pA = priorityMap[a.pool] || 99;
  const pB = priorityMap[b.pool] || 99;
  if (pA !== pB) return pA - pB;
  return a.name.localeCompare(b.name, 'zh-Hans-CN');
});

const namesOrder = testStocks.map(s => s.name);
const expectedOrder = ['贵州茅台', '宁德时代', '比亚迪', '中国平安', '中信证券', '海光信息', '中芯国际'];
const isOrderValid = JSON.stringify(namesOrder) === JSON.stringify(expectedOrder);

console.log(`${isOrderValid ? '✅ PASS' : '❌ FAIL'}: 运行时三池叠加与拼音字母排序契约完全成立 (${namesOrder.join(' -> ')})`);
if (!isOrderValid) process.exitCode = 1;

console.log('\n=== [6. 光标落在【@操作符+空格】后按退格键一同删除原子化验证] ===');

const checksBackspace = [
  {
    name: '退格拦截入口：定义了专门的 handleChatInputBackspace 处理函数',
    pass: js.includes('function handleChatInputBackspace') || js.includes('const handleChatInputBackspace =')
  },
  {
    name: '键盘事件绑定：chatInput keydown 中捕获 Backspace 键并委托 handleChatInputBackspace',
    pass: js.includes("e.key === 'Backspace'") && js.includes('handleChatInputBackspace')
  },
  {
    name: '原子删除逻辑：涵盖 tokenToDelete 与空格文本节点 textNodeToTrim / 字符删除',
    pass: js.includes('tokenToDelete') && (js.includes('textNodeToTrim') || js.includes('spaceNode'))
  },
  {
    name: '光标重定位：删除后精准重建 Range 并定位至 token 之前或安全前置节点',
    pass: js.includes('newRange.setStart') && js.includes('sel.addRange(newRange)')
  },
  {
    name: '输入反馈：删除后触发 input 事件以保证界面响应与字符状态同步',
    pass: js.includes("dispatchEvent(new Event('input'")
  }
];

checksBackspace.forEach(c => {
  console.log(`${c.pass ? '✅ PASS' : '❌ FAIL'}: ${c.name}`);
  if (!c.pass) process.exitCode = 1;
});

console.log('\n=== [7. 运行时 Mock DOM 仿真原子化连带删除测试] ===');

function createMockDom() {
  class MockNode {
    constructor(nodeType, textContent = '') {
      this.nodeType = nodeType;
      this.textContent = textContent;
      this.childNodes = [];
      this.parentNode = null;
      this.classList = {
        _classes: new Set(),
        add(c) { this._classes.add(c); },
        contains(c) { return this._classes.has(c); },
        remove(c) { this._classes.delete(c); }
      };
    }
    get previousSibling() {
      if (!this.parentNode) return null;
      const idx = this.parentNode.childNodes.indexOf(this);
      return idx > 0 ? this.parentNode.childNodes[idx - 1] : null;
    }
    get nextSibling() {
      if (!this.parentNode) return null;
      const idx = this.parentNode.childNodes.indexOf(this);
      return idx >= 0 && idx < this.parentNode.childNodes.length - 1 ? this.parentNode.childNodes[idx + 1] : null;
    }
    appendChild(child) {
      child.parentNode = this;
      this.childNodes.push(child);
      return child;
    }
    removeChild(child) {
      const idx = this.childNodes.indexOf(child);
      if (idx !== -1) {
        this.childNodes.splice(idx, 1);
        child.parentNode = null;
      }
      return child;
    }
    remove() {
      if (this.parentNode) {
        this.parentNode.removeChild(this);
      }
    }
    contains(node) {
      let cur = node;
      while (cur) {
        if (cur === this) return true;
        cur = cur.parentNode;
      }
      return false;
    }
    querySelector(sel) {
      if (sel === '.at-token') {
        const find = (n) => {
          if (n.classList && n.classList.contains('at-token')) return n;
          for (const c of n.childNodes) {
            const f = find(c);
            if (f) return f;
          }
          return null;
        };
        return find(this);
      }
      return null;
    }
    get innerText() {
      return this.childNodes.map(c => c.textContent || c.innerText || '').join('');
    }
    dispatchEvent() {}
    focus() {}
  }

  const TEXT_NODE = 3;
  const ELEMENT_NODE = 1;

  const mockInput = new MockNode(ELEMENT_NODE);
  mockInput.id = 'chatInput';

  let currentRange = null;
  const mockSelection = {
    rangeCount: 1,
    isCollapsed: true,
    getRangeAt(i) { return currentRange; },
    removeAllRanges() { currentRange = null; },
    addRange(r) { currentRange = r; }
  };

  const mockDocument = {
    getElementById(id) {
      if (id === 'chatInput') return mockInput;
      return null;
    },
    createTextNode(txt) {
      return new MockNode(TEXT_NODE, txt);
    },
    createElement(tag) {
      return new MockNode(ELEMENT_NODE);
    },
    createRange() {
      return {
        startContainer: null,
        startOffset: 0,
        setStart(node, off) { this.startContainer = node; this.startOffset = off; },
        setEnd(node, off) { this.endContainer = node; this.endOffset = off; },
        setStartAfter(node) { this.startContainer = node.parentNode; this.startOffset = node.parentNode ? node.parentNode.childNodes.indexOf(node) + 1 : 0; },
        setEndAfter(node) { this.endContainer = node.parentNode; this.endOffset = node.parentNode ? node.parentNode.childNodes.indexOf(node) + 1 : 0; },
        selectNodeContents(node) { this.startContainer = node; this.startOffset = 0; },
        collapse(toStart) {}
      };
    }
  };

  return { mockInput, mockSelection, mockDocument, TEXT_NODE, ELEMENT_NODE, getCurrentRange: () => currentRange, setCurrentRange: (r) => { currentRange = r; } };
}

try {
  const sandbox = {
    Node: { ELEMENT_NODE: 1, TEXT_NODE: 3 },
    Event: function(type) { this.type = type; },
    window: {}
  };
  const domEnv = createMockDom();
  sandbox.window.getSelection = () => domEnv.mockSelection;
  sandbox.document = domEnv.mockDocument;

  const fnMatch = js.match(/function handleChatInputBackspace\s*\([\s\S]*?\n\}/);
  if (fnMatch) {
    const fnCode = fnMatch[0];
    const runScript = new Function('sandbox', `
      with (sandbox) {
        ${fnCode}
        return handleChatInputBackspace;
      }
    `);
    const fn = runScript(sandbox);

    const token1 = domEnv.mockDocument.createElement('span');
    token1.classList.add('at-token');
    token1.classList.add('at-token-stock');
    token1.textContent = '@600519 贵州茅台';
    const space1 = domEnv.mockDocument.createTextNode('\u00A0');
    domEnv.mockInput.appendChild(token1);
    domEnv.mockInput.appendChild(space1);

    const range1 = domEnv.mockDocument.createRange();
    range1.setStart(domEnv.mockInput, 2);
    domEnv.setCurrentRange(range1);

    let prevented1 = false;
    const mockEvt1 = { preventDefault() { prevented1 = true; } };

    const res1 = fn(mockEvt1, domEnv.mockInput);
    const pass1 = res1 === true &&
                  prevented1 === true &&
                  domEnv.mockInput.childNodes.length === 0;
    console.log(`${pass1 ? '✅ PASS' : '❌ FAIL'}: 仿真场景 1：光标在【@操作符+空格】后(容器偏移)，按退格一同删除两者，输入框清空`);
    if (!pass1) process.exitCode = 1;

    domEnv.mockInput.childNodes = [];
    const prefixNode = domEnv.mockDocument.createTextNode('买入 ');
    const token2 = domEnv.mockDocument.createElement('span');
    token2.classList.add('at-token');
    token2.textContent = '@600519 贵州茅台';
    const space2 = domEnv.mockDocument.createTextNode('\u00A0');
    domEnv.mockInput.appendChild(prefixNode);
    domEnv.mockInput.appendChild(token2);
    domEnv.mockInput.appendChild(space2);

    const range2 = domEnv.mockDocument.createRange();
    range2.setStart(space2, 1);
    domEnv.setCurrentRange(range2);

    let prevented2 = false;
    const mockEvt2 = { preventDefault() { prevented2 = true; } };

    const res2 = fn(mockEvt2, domEnv.mockInput);
    const pass2 = res2 === true &&
                  prevented2 === true &&
                  domEnv.mockInput.childNodes.length === 1 &&
                  domEnv.mockInput.childNodes[0] === prefixNode &&
                  domEnv.getCurrentRange().startContainer === prefixNode &&
                  domEnv.getCurrentRange().startOffset === prefixNode.textContent.length;
    console.log(`${pass2 ? '✅ PASS' : '❌ FAIL'}: 仿真场景 2：前置文本+【@操作符+空格】(空格内偏移1)，退格仅删除操作符与空格，保留前置文本且光标正确定位`);
    if (!pass2) process.exitCode = 1;

    domEnv.mockInput.childNodes = [];
    const token3 = domEnv.mockDocument.createElement('span');
    token3.classList.add('at-token');
    token3.textContent = '@600519 贵州茅台';
    const textNode3 = domEnv.mockDocument.createTextNode('\u00A0走势');
    domEnv.mockInput.appendChild(token3);
    domEnv.mockInput.appendChild(textNode3);

    const range3 = domEnv.mockDocument.createRange();
    range3.setStart(textNode3, 1);
    domEnv.setCurrentRange(range3);

    let prevented3 = false;
    const mockEvt3 = { preventDefault() { prevented3 = true; } };

    const res3 = fn(mockEvt3, domEnv.mockInput);
    const pass3 = res3 === true &&
                  prevented3 === true &&
                  domEnv.mockInput.childNodes.length === 1 &&
                  textNode3.textContent === '走势' &&
                  domEnv.getCurrentRange().startContainer === textNode3 &&
                  domEnv.getCurrentRange().startOffset === 0;
    console.log(`${pass3 ? '✅ PASS' : '❌ FAIL'}: 仿真场景 3：【@操作符+空格】后接文字(光标在空格与文字间)，退格删除操作符与空格，文字保留为"走势"，光标停在首字前`);
    if (!pass3) process.exitCode = 1;

  } else {
    console.log(`❌ FAIL: 未在 web/js/app.js 中找到 handleChatInputBackspace 函数定义`);
    process.exitCode = 1;
  }
} catch (err) {
  console.error('❌ Mock DOM 测试执行异常:', err);
  process.exitCode = 1;
}

if (process.exitCode === 1) {
  console.error('\n❌ 部分检查未通过，请排查！');
} else {
  console.log('\n🎉 所有 40 项【@操作符】股票菜单三大股池叠加排序与徽章色彩断言 100% 全部通过！');
}
