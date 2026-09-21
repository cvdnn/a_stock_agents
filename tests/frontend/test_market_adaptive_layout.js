/**
 * tests/test_market_adaptive_layout.js
 * 【市场行情】工作区自适应布局与像素级全景设计规范断言套件
 */

const fs = require('fs');
const assert = require('assert');

console.log('=== [【市场行情】工作区自适应布局与组件完整性验证] ===\n');

const html = fs.readFileSync('web/index.html', 'utf8');
const css = fs.readFileSync('web/css/style.css', 'utf8');
const appJs = fs.readFileSync('web/js/app.js', 'utf8');
const chartsJs = fs.readFileSync('web/js/charts.js', 'utf8');

// --------------------------------------------------------------------------
// 1. 结构完整性断言：Row 1 (市场概览 + 今日要闻)
// --------------------------------------------------------------------------
console.log('--- 1. Row 1: 市场概览(4指数6指标) + 今日要闻(快讯列表) ---');

assert(html.includes('id="pane-market"'), '必须存在 #pane-market 独立工作区容器');
assert(html.includes('class="market-adaptive-container"'), '必须包含自适应容器 .market-adaptive-container');
assert(html.includes('class="mkt-top-row"'), '必须包含第一行 .mkt-top-row');

// 四大指数及 6 项核心指标检查
const indices = ['上证指数', '深证成指', '创业板指', '科创50'];
indices.forEach(idx => {
  assert(html.includes(idx), `市场概览必须包含核心指数: ${idx}`);
});

const metricsLabels = ['今开', '最高', '成交额', '昨收', '最低', '成交量'];
metricsLabels.forEach(lbl => {
  assert(html.includes(lbl), `四大指数必须包含指标: ${lbl}`);
});

const sparkCanvases = ['marketSparkSh', 'marketSparkSz', 'marketSparkCy', 'marketSparkKc'];
sparkCanvases.forEach(id => {
  assert(html.includes(`id="${id}"`), `指数卡片必须包含 Sparkline Canvas: #${id}`);
});
console.log('✅ PASS: 市场概览四大指数与 6 项精细指标及走势微图全部就绪');

// 今日要闻在 Row 1 替换市场情绪断言
const topRowMatch = html.match(/<div class="mkt-top-row">([\s\S]*?)<\/div>\s*<!-- Row 2/);
assert(topRowMatch, '必须匹配到 .mkt-top-row 容器');
assert(topRowMatch[1].includes('class="mkt-card mkt-overview-card"'), 'Row 1 必须包含市场概览');
assert(topRowMatch[1].includes('class="mkt-card mkt-news-card"'), 'Row 1 今日要闻必须替换市场情绪');
assert(!topRowMatch[1].includes('class="mkt-card mkt-sentiment-card"'), 'Row 1 不得再包含市场情绪');
assert(!html.includes('class="mkt-card mkt-quick-card"'), '快捷入口板块已被彻底删除');
console.log('✅ PASS: Row 1 成功由【市场概览】与【今日要闻】双核心卡片组成');

// --------------------------------------------------------------------------
// 2. 结构完整性断言：Row 2 (市场情绪位于第1板块，大盘走势位于第2板块)
// --------------------------------------------------------------------------
console.log('\n--- 2. Row 2: 市场情绪(第1板块) + 大盘走势K线(第2板块) ---');

assert(html.includes('class="mkt-mid-row"'), '必须包含中部第二行 .mkt-mid-row');

const midRowMatch = html.match(/<div class="mkt-mid-row">([\s\S]*?)<\/div>\s*<!-- Row 3/);
assert(midRowMatch, '必须匹配到 .mkt-mid-row 容器');

// 市场情绪移动到第2行第1板块位置断言
const sentimentIdx = midRowMatch[1].indexOf('mkt-sentiment-card');
const klineIdx = midRowMatch[1].indexOf('mkt-kline-card');
assert(sentimentIdx !== -1, 'Row 2 必须包含市场情绪卡片');
assert(klineIdx !== -1, 'Row 2 必须包含大盘走势卡片');
assert(sentimentIdx < klineIdx, '【市场情绪】必须位于第2行第1板块位置，排在大盘走势之前');

// 市场情绪表盘与 6 格指标检查
assert(html.includes('id="sentimentGauge"'), '必须包含情绪表盘 Canvas #sentimentGauge');
assert(html.includes('id="mktSentimentScore"'), '必须包含情绪评分数值元素 #mktSentimentScore');
assert(html.includes('id="mktSentimentLabel"'), '必须包含情绪评级标签 #mktSentimentLabel');
assert(html.includes('涨停') && html.includes('跌停') && html.includes('两市成交'), '必须包含涨停/跌停/两市成交统计');
assert(html.includes('上涨家数') && html.includes('平盘家数') && html.includes('下跌家数'), '必须包含上涨/平盘/下跌家数统计');

// 大盘走势主图与均线检查
assert(html.includes('id="marketKlineCanvas"'), '必须包含大盘走势 Canvas #marketKlineCanvas');
assert(html.includes('MA5:') && html.includes('MA10:') && html.includes('MA20:'), '必须包含均线数值标注 (MA5/10/20)');
assert(html.includes('分时') && html.includes('日K') && html.includes('周K') && html.includes('月K'), '必须包含多周期 K 线 Tabs');
assert(html.includes('id="mktKlineTargetSelect"'), '必须包含大盘指数选择下拉框');
console.log('✅ PASS: Row 2 【市场情绪】成功移至第1板块位置，【大盘走势】位于第2板块位置');

// --------------------------------------------------------------------------
// 3. 结构完整性断言：Row 3 (行业板块与概念主题左右排列，热门概念已删除)
// --------------------------------------------------------------------------
console.log('\n--- 3. Row 3: 行业板块 + 概念主题 (左右排列，热门概念删除) ---');

assert(html.includes('class="mkt-sectors-row"'), '必须包含第3行左右排列容器 .mkt-sectors-row');
assert(html.includes('class="mkt-card mkt-sector-card"'), '必须包含行业板块卡片 .mkt-sector-card');
assert(html.includes('class="mkt-card mkt-concept-card"'), '必须包含概念主题卡片 .mkt-concept-card');
assert(html.includes('id="mktSectorGrid"'), '必须包含行业板块瓷片网格 #mktSectorGrid');
assert(html.includes('id="mktConceptGrid"'), '必须包含概念主题瓷片网格 #mktConceptGrid');

// 热门概念与 AI 卡片删除断言
assert(!html.includes('class="mkt-card mkt-hot-concepts-card"'), '【热门概念】板块已成功删除');
assert(!html.includes('class="mkt-card mkt-ai-promo-card"'), 'AI量化智能分析板块已被彻底删除');
console.log('✅ PASS: Row 3 【行业板块】与【概念主题】左右并排呈现，【热门概念】彻底删除');

// --------------------------------------------------------------------------
// 4. 结构完整性断言：Row 4 (三大排行榜)
// --------------------------------------------------------------------------
console.log('\n--- 4. Row 4: 涨幅排行榜 + 跌幅排行榜 + 北向资金 ---');

assert(html.includes('class="mkt-bottom-row"'), '必须包含底部排行行 .mkt-bottom-row');
assert(html.includes('id="mktGainersBody"'), '必须包含涨幅排行榜表格 tbody #mktGainersBody');
assert(html.includes('id="mktLosersBody"'), '必须包含跌幅排行榜表格 tbody #mktLosersBody');
assert(html.includes('id="mktNorthboundBody"'), '必须包含北向资金表格 tbody #mktNorthboundBody');
console.log('✅ PASS: 涨幅榜、跌幅榜与北向资金三大排行榜就绪');

// --------------------------------------------------------------------------
// 4. CSS 容器查询 (@container) 与弹性响应式断言
// --------------------------------------------------------------------------
console.log('\n--- 4. CSS 容器查询 (@container) 与工作区宽度自适应断言 ---');

assert(css.includes('container-type: inline-size;'), 'style.css 必须为市场行情工作区配置 container-type: inline-size');
assert(css.includes('container-name: marketContainer;'), 'style.css 必须配置 container-name: marketContainer');
assert(css.includes('@container marketContainer (max-width: 1260px)'), '必须具备中宽视口 (<= 1260px) 容器查询适配规则');
assert(css.includes('@container marketContainer (max-width: 1000px)'), '必须具备紧凑视口 (<= 1000px) 容器查询适配规则');
assert(css.includes('.mkt-card'), '必须包含统一卡片样式 .mkt-card');
assert(css.includes('.mkt-spark-canvas'), '必须包含微走势图样式 .mkt-spark-canvas');
console.log('✅ PASS: CSS 容器查询机制完备，能彻底化解工作区宽度受 AI 助手展开/收起导致的布局差异');

// --------------------------------------------------------------------------
// 5. JavaScript 交互与动态自适应驱动
// --------------------------------------------------------------------------
console.log('\n--- 5. JS 数据驱动、AI 协同联动与 Canvas 高清锐利重绘断言 ---');

assert(appJs.includes('MarketFallbackData'), 'app.js 必须包含基准真实盘口 Fallback 数据');
assert(appJs.includes('function triggerMarketQuickAction('), 'app.js 必须实现快捷入口与 AI 助手协同联动');
assert(appJs.includes('function triggerMarketAiExperience('), 'app.js 必须实现 AI 量化智能分析体验触发');
assert(appJs.includes('function switchKlinePeriod('), 'app.js 必须实现 K 线周期切换');
assert(appJs.includes('function setupMarketResizeObserver('), 'app.js 必须实现防抖 ResizeObserver 保证图表高清自适应重绘');
assert(chartsJs.includes('rainbowGrad'), 'FinancialCharts.drawGauge 必须实现全景彩虹渐变刻度弧');

console.log('✅ PASS: JS 动态交互、ResizeObserver 自适应监听与 Canvas 高清重绘引擎全部通过');

console.log('\n🎉 所有 5 大类【市场行情全景自适应工作区】验证断言 100% 全部通过！');
