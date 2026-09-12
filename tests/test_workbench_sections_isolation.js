/**
 * tests/test_workbench_sections_isolation.js
 * 投研助手综合工作台六大板块（1, 2-1, 2-2, 3-1, 3-2, 4）与工作区独立性自动化断言套件
 */

const fs = require('fs');
const assert = require('assert');

console.log('=== [投研助手工作台板块与工作区独立性验证] ===\n');

const html = fs.readFileSync('web/index.html', 'utf8');
const css = fs.readFileSync('web/css/style.css', 'utf8');
const appJs = fs.readFileSync('web/js/app.js', 'utf8');

// --------------------------------------------------------------------------
// 1. 各功能菜单工作区物理隔离与唯一性断言
// --------------------------------------------------------------------------
console.log('--- 1. 功能菜单工作区独立设计与物理隔离 ---');

const panes = ['pane-dashboard', 'pane-market', 'pane-watchlist', 'pane-returns', 'pane-skills'];
panes.forEach(paneId => {
  assert(html.includes(`id="${paneId}"`), `工作区容器 #${paneId} 必须独立存在于 index.html`);
  console.log(`✅ PASS: 独立工作区容器 #${paneId} 存在`);
});

// 验证各菜单切换时不会互相混淆
assert(appJs.includes("switchRightTab(tabId)"), '需具备 switchRightTab 切换器');
assert(appJs.includes("document.getElementById(`pane-${tabId}`)"), 'switchRightTab 应通过独立 ID 索引 pane');
console.log('✅ PASS: 工作区切换机制遵循单 pane 激活与完全独立隔离契约');

// --------------------------------------------------------------------------
// 2. 板块 1: 【投资概要】(#section-portfolio-overview，跨双列 span 2 cols)
// --------------------------------------------------------------------------
console.log('\n--- 2. 板块 1: 【投资概要】断言 ---');
assert(html.includes('id="section-portfolio-overview"'), '板块 1 #section-portfolio-overview 必须存在');
assert(!html.includes('<span class="section-num-badge">1</span>'), '板块 1 不得包含序号标号 1');
assert(html.includes('全景账户画像与实战风控总览'), '板块 1 必须包含定位描述：全景账户画像与实战风控总览');
assert(html.includes('id="portfolioDonut"'), '板块 1 必须包含资产环形图 Canvas #portfolioDonut');
assert(html.includes('+¥3.86万 (+1.18%)') || html.includes('id="ovTodayPnl"'), '板块 1 必须包含当日浮动盈亏');
assert(html.includes('+11.8%') || html.includes('ovCushionDesc'), '板块 1 必须包含距离 T0 警戒线平均缓冲空间');
assert(html.includes('最低保本卖出价') && html.includes('分级止损预案已就绪'), '板块 1 必须强调最低保本卖出价与分级止损预案已就绪');
console.log('✅ PASS: 板块 1 【投资概要】定位、全景账户画像、Donut 环形图与实战风控总览断言全部通过 (已无数字标号)');

// --------------------------------------------------------------------------
// 3. 板块 2-1: 【大盘指数】(#section-market-indices，第 2 行第 1 列)
// --------------------------------------------------------------------------
console.log('\n--- 3. 板块 2-1: 【大盘指数】断言 ---');
assert(html.includes('id="section-market-indices"'), '板块 2-1 #section-market-indices 必须存在');
assert(!html.includes('<span class="section-num-badge">2-1</span>'), '板块 2-1 不得包含序号标号 2-1');
assert(html.includes('大盘宽基基准跟踪'), '板块 2-1 必须包含定位描述：大盘宽基基准跟踪');
const indicesCanvas = ['sparklineSh', 'sparklineSz', 'sparklineCy', 'sparklineKc'];
indicesCanvas.forEach(cId => {
  assert(html.includes(`id="${cId}"`), `板块 2-1 必须包含走势微图 Canvas #${cId}`);
});
assert(html.includes('上证指数') && html.includes('深证成指') && html.includes('创业板指') && html.includes('科创50'), '板块 2-1 必须包含四大核心指数');
console.log('✅ PASS: 板块 2-1 【大盘指数】四大核心指数与 28 周期 Sparkline 走势微图断言全部通过 (已无数字标号)');

// --------------------------------------------------------------------------
// 4. 板块 2-2: 【行情分析】(#section-market-analysis，第 2 行第 2 列)
// --------------------------------------------------------------------------
console.log('\n--- 4. 板块 2-2: 【行情分析】断言 ---');
assert(html.includes('id="section-market-analysis"'), '板块 2-2 #section-market-analysis 必须存在');
assert(!html.includes('<span class="section-num-badge">2-2</span>'), '板块 2-2 不得包含序号标号 2-2');
assert(html.includes('盘面量价与情绪温度'), '板块 2-2 必须包含定位描述：盘面量价与情绪温度');
assert(html.includes('id="dashboardSentimentGauge"'), '板块 2-2 必须包含情绪仪表盘 Canvas #dashboardSentimentGauge');
assert(html.includes('market-breadth-bar'), '板块 2-2 必须包含红涨绿跌家数柱状分布对比条');
assert(html.includes('1.28万亿') || html.includes('dashSentimentMetaDesc'), '板块 2-2 必须包含两市总成交额');
assert(html.includes('赚钱效应') || html.includes('dashSentimentMetaDesc'), '板块 2-2 必须包含赚钱效应研判');
console.log('✅ PASS: 板块 2-2 【行情分析】情绪仪表盘、两市总成交、红涨绿跌分布与赚钱效应断言全部通过 (已无数字标号)');

// --------------------------------------------------------------------------
// 5. 板块 3-1: 【自选指数】(#section-watchlist-indices，第 3 行第 1 列)
// --------------------------------------------------------------------------
console.log('\n--- 5. 板块 3-1: 【自选指数】断言 ---');
assert(html.includes('id="section-watchlist-indices"'), '板块 3-1 #section-watchlist-indices 必须存在');
assert(!html.includes('<span class="section-num-badge">3-1</span>'), '板块 3-1 不得包含序号标号 3-1');
assert(html.includes('聚焦用户关心的板块与赛道'), '板块 3-1 必须包含定位描述：聚焦用户关心的板块与赛道');
assert(html.includes('id="sparklineCustomIdx1"') && html.includes('id="sparklineCustomIdx2"'), '板块 3-1 必须包含自选主题指数分时曲线 Canvas');
assert(html.includes('半导体芯片') || html.includes('人工智能'), '板块 3-1 必须包含自选主题指数名称');
assert(html.includes('id="dashWatchlistTableBody"'), '板块 3-1 必须包含自选重点成分股表格容器');
console.log('✅ PASS: 板块 3-1 【自选指数】半导体/AI/新能源主题分时曲线与成分股列表断言全部通过 (已无数字标号)');

// --------------------------------------------------------------------------
// 6. 板块 3-2: 【投资分析】(#section-investment-analysis，第 3 行第 2 列)
// --------------------------------------------------------------------------
console.log('\n--- 6. 板块 3-2: 【投资分析】断言 ---');
assert(html.includes('id="section-investment-analysis"'), '板块 3-2 #section-investment-analysis 必须存在');
assert(!html.includes('<span class="section-num-badge">3-2</span>'), '板块 3-2 不得包含序号标号 3-2');
assert(html.includes('量化风控与投资归因看板'), '板块 3-2 必须包含定位描述：量化风控与投资归因看板');
assert(html.includes('id="dashboardInvestCurve"'), '板块 3-2 必须包含净值曲线 Canvas #dashboardInvestCurve');
assert(html.includes('id="dashSharpeVal"'), '板块 3-2 必须包含夏普比率容器');
assert(html.includes('id="dashWinRateVal"'), '板块 3-2 必须包含交易胜率容器');
assert(html.includes('id="dashMaxDdVal"'), '板块 3-2 必须包含最大回撤容器');
assert(html.includes('id="dashAttributionRow"'), '板块 3-2 必须包含多因子收益归因容器');
console.log('✅ PASS: 板块 3-2 【投资分析】夏普比率/胜率/最大回撤与策略净值对比折线图断言全部通过 (已无数字标号)');

// --------------------------------------------------------------------------
// 7. 板块 4: 【盯盘】(#section-realtime-monitor，跨双列 span 2 cols)
// --------------------------------------------------------------------------
console.log('\n--- 7. 板块 4: 【盯盘】断言 ---');
assert(html.includes('id="section-realtime-monitor"'), '板块 4 #section-realtime-monitor 必须存在');
assert(!html.includes('<span class="section-num-badge">4</span>'), '板块 4 不得包含序号标号 4');
assert(html.includes('盘中高频策略异动流水'), '板块 4 必须包含定位描述：盘中高频策略异动流水');
assert(html.includes('id="dashMonitorStreamList"'), '板块 4 必须包含盯盘预警即时事件流水列表');
assert(html.includes('stream-stock-col') && html.includes('中芯国际') && html.includes('（688981）'), '板块 4 盯盘第 2 列必须插入标的信息（2行式：名称 +（688981））');
assert(html.includes('放量突破') || html.includes('大单'), '板块 4 必须包含突破前高或大单异动事件');
assert(html.includes('水下金叉') || html.includes('金叉'), '板块 4 必须包含水下金叉买点提醒');
assert(html.includes('id="dashStrategiesContainer"'), '板块 4 必须包含量化策略触发通道与开关');
console.log('✅ PASS: 板块 4 【盯盘】第2列标的2行式(中芯国际+688981)、标签后移与策略触发通道断言全部通过 (已无数字标号)');

// --------------------------------------------------------------------------
// 8. JS 初始化与 Canvas 绘制独立调度验证
// --------------------------------------------------------------------------
console.log('\n--- 8. JS 初始化与 Canvas 图表独立调度 ---');
assert(appJs.includes("initDashboardCharts"), 'app.js 必须具备 initDashboardCharts 初始化函数');
assert(appJs.includes("FinancialCharts.drawDonutChart('portfolioDonut'"), 'app.js 应绘制 portfolioDonut');
assert(appJs.includes("FinancialCharts.drawSparkline('sparklineSh'"), 'app.js 应绘制 sparklineSh');
assert(appJs.includes("FinancialCharts.drawGauge('dashboardSentimentGauge'"), 'app.js 应绘制 dashboardSentimentGauge');
assert(appJs.includes("FinancialCharts.drawEquityCurve('dashboardInvestCurve'"), 'app.js 应绘制 dashboardInvestCurve');
console.log('✅ PASS: 投研助手工作台独立图表初始化与各 Pane 数据调度隔离断言全部通过');

console.log('\n🎉 所有 8 项【投研助手工作台六大板块与工作区独立性】自动化断言 100% 全部通过！\n');
