// -*- coding: utf-8 -*-
/**
 * tests/test_watchlist_deduplication.js
 * 验证自选股列表唯一性去重、选中态（避免同名同代码重复与多选激活）断言
 */
const assert = require('assert');
const fs = require('fs');

console.log('=== [验证：自选股列表唯一性去重与防同选中断言] ===');

// 构造简易 JSDOM 模拟环境
const mockContainer = {
  innerHTML: '',
};
const mockCountEl = {
  innerText: '',
};

const mockDocument = {
  getElementById(id) {
    if (id === 'watchStockList') return mockContainer;
    if (id === 'watchStockCount') return mockCountEl;
    return null;
  },
  querySelectorAll(selector) {
    return [];
  }
};

const mockAppState = {
  currentWatchlistStocks: [],
  selectedStock: '603259',
};

// 从 web/js/app.js 提取 renderWatchlistItems 逻辑并在沙箱中执行
const appJsContent = fs.readFileSync('web/js/app.js', 'utf8');

// 验证源码中包含唯一性去重逻辑
assert(appJsContent.includes('const seenCodes = new Set();'), 'renderWatchlistItems 必须包含 seenCodes 去重逻辑');
assert(appJsContent.includes('uniqueStocks.push(s);'), 'renderWatchlistItems 必须保存 uniqueStocks 列表');

// 构建隔离沙箱环境
const sandbox = {
  document: mockDocument,
  AppState: mockAppState,
  _watchlistSearchKeyword: '',
  _watchlistSortOrder: 'desc',
  selectWatchStock: () => {},
  requestAnimationFrame: () => 0,
  setTimeout: () => 0,
  scrollWatchlistToActiveItem: () => {},
};

// 提取 renderWatchlistItems 函数代码
const fnMatch = appJsContent.match(/function renderWatchlistItems\(stocks, selectedCode\) \{([\s\S]*?)\n\}/);
assert(fnMatch, '必须找到 renderWatchlistItems 函数定义');
const fnBody = fnMatch[1];
const renderWatchlistItems = new Function('stocks', 'selectedCode', `
  const document = this.document;
  const AppState = this.AppState;
  const _watchlistSearchKeyword = this._watchlistSearchKeyword;
  const _watchlistSortOrder = this._watchlistSortOrder;
  const selectWatchStock = this.selectWatchStock;
  const requestAnimationFrame = this.requestAnimationFrame;
  const setTimeout = this.setTimeout;
  const scrollWatchlistToActiveItem = this.scrollWatchlistToActiveItem;
  ${fnBody}
`).bind(sandbox);

// 构造包含重复股票的测试数据集（模拟原 93 只数据中重复的 603259 药明康德）
const testStocksWithDuplicates = [
  { code: '603259', name: '药明康德', badge: '药明', badgeBg: '#1677FF', price: 156.62, change_pct: 3.56 },
  { code: '603259', name: '药明康德', badge: '药明', badgeBg: '#1677FF', price: 156.62, change_pct: 3.56 },
  { code: '300750', name: '宁德时代', badge: '宁德', badgeBg: '#003B99', price: 340.43, change_pct: 3.00 },
  { code: '002594', name: '比亚迪', badge: '比亚', badgeBg: '#1677FF', price: 85.47, change_pct: 1.75 },
  { code: '600025', name: '华能水电', badge: '华能', badgeBg: '#1677FF', price: 9.97, change_pct: 1.42 },
];

console.log('--- 测试 1: 输入包含重复 603259 的 5 条数据 ---');
renderWatchlistItems(testStocksWithDuplicates, '603259');

// 断言 1: 去重后列表项数量必须为 4
const renderedRows = (mockContainer.innerHTML.match(/watchlist-stock-row/g) || []).length;
console.log(`渲染行数: ${renderedRows} (期望: 4)`);
assert.strictEqual(renderedRows, 4, '去重后必须只渲染 4 行，去除重复的药明康德');

// 断言 2: 药明康德在 HTML 中只出现一次（每行对应 data-code、onclick、文本共 3 处）
const ymCount = (mockContainer.innerHTML.match(/603259/g) || []).length;
console.log(`603259 出现次数: ${ymCount} 处 (单行对应 3 处引用)`);
assert.strictEqual(ymCount, 3, 'HTML中 603259 只能对应一行（data-code, onclick, text 共3处）');

// 断言 3: 只有一行带有 active 类名
const activeRows = (mockContainer.innerHTML.match(/watchlist-stock-row\s+active/g) || []).length;
console.log(`激活态行数: ${activeRows} (期望: 1)`);
assert.strictEqual(activeRows, 1, '只有且仅有一行药明康德被选中激活，彻底解决“同选中”问题');

// 断言 4: 标题栏统计数字必须准确反映去重后的实际股数 (4) 而非原始重复数 (5)
console.log(`统计标题文本: ${mockCountEl.innerText} (期望: 自选股 (4))`);
assert.strictEqual(mockCountEl.innerText, '自选股 (4)', '自选股统计数字必须显示去重后数量');

// 断言 5: AppState 存储的列表也是去重后的
assert.strictEqual(mockAppState.currentWatchlistStocks.length, 4, 'AppState.currentWatchlistStocks 必须去重');

console.log('\n🎉 所有自选股唯一性去重与防同选中断言 100% 通过！');
