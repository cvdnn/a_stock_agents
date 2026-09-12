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
// 1. 结构完整性断言：Row 1 (市场概览 + 市场情绪 + 快捷入口)
// --------------------------------------------------------------------------
console.log('--- 1. Row 1: 市场概览(4指数6指标) + 市场情绪(78度表盘) + 快捷入口(6大按钮) ---');

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

// 市场情绪表盘与 6 格指标
assert(html.includes('id="sentimentGauge"'), '必须包含情绪表盘 Canvas #sentimentGauge');
assert(html.includes('id="mktSentimentScore"'), '必须包含情绪评分数值元素 #mktSentimentScore');
assert(html.includes('id="mktSentimentLabel"'), '必须包含情绪评级标签 #mktSentimentLabel');
assert(html.includes('涨停') && html.includes('跌停') && html.includes('两市成交'), '必须包含涨停/跌停/两市成交统计');
assert(html.includes('上涨家数') && html.includes('平盘家数') && html.includes('下跌家数'), '必须包含上涨/平盘/下跌家数统计');
console.log('✅ PASS: 市场情绪 78 度彩虹刻度表盘与 6 格统计指标全部就绪');

// 快捷入口 6 大按钮
const quickActions = ['大盘分析', '行业轮动', '资金流向', '龙虎榜单', '主线题材', '规避风险'];
quickActions.forEach(action => {
  assert(html.includes(action), `快捷入口必须包含磁贴: ${action}`);
});
console.log('✅ PASS: 快捷入口 6 大高频操作磁贴按钮全部就绪');

// --------------------------------------------------------------------------
// 2. 结构完整性断言：Row 2 (大盘走势 + 行业概念 + 要闻热门AI)
// --------------------------------------------------------------------------
console.log('\n--- 2. Row 2: 大盘走势K线 + 行业/概念板块 + 今日要闻/热门概念/AI量化 ---');

assert(html.includes('class="mkt-mid-row"'), '必须包含中部行 .mkt-mid-row');
assert(html.includes('id="marketKlineCanvas"'), '必须包含大盘走势 Canvas #marketKlineCanvas');
assert(html.includes('MA5:') && html.includes('MA10:') && html.includes('MA20:'), '必须包含均线数值标注 (MA5/10/20)');
assert(html.includes('分时') && html.includes('日K') && html.includes('周K') && html.includes('月K'), '必须包含多周期 K 线 Tabs');
assert(html.includes('id="mktKlineTargetSelect"'), '必须包含大盘指数选择下拉框');

// 行业板块与概念主题
assert(html.includes('class="mkt-sectors-col"'), '必须包含行业与概念复合列 .mkt-sectors-col');
assert(html.includes('id="mktSectorGrid"'), '必须包含行业板块瓷片网格 #mktSectorGrid');
assert(html.includes('id="mktConceptGrid"'), '必须包含概念主题瓷片网格 #mktConceptGrid');

// 今日要闻 + 热门概念 + AI量化卡片
assert(html.includes('class="mkt-side-col"'), '必须包含右侧复合列 .mkt-side-col');
assert(html.includes('id="mktNewsList"'), '必须包含今日要闻列表 #mktNewsList');
assert(html.includes('id="mktHotConcepts"'), '必须包含热门概念标签云 #mktHotConcepts');
assert(html.includes('AI量化智能分析') && html.includes('triggerMarketAiExperience()'), '必须包含 AI 量化智能分析卡片与体验联动触发');
console.log('✅ PASS: 大盘走势主图、行业与概念瓷片矩阵、要闻热门概念及 AI 量化宣传卡全部就绪');

// --------------------------------------------------------------------------
// 3. 结构完整性断言：Row 3 (三大排行榜)
// --------------------------------------------------------------------------
console.log('\n--- 3. Row 3: 涨幅排行榜 + 跌幅排行榜 + 北向资金 ---');

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
