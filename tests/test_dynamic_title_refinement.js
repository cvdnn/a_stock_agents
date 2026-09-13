// -*- coding: utf-8 -*-
/**
 * test_dynamic_title_refinement.js
 * 专门验证：截图中标记 title 根据用户提交的内容做提炼摘要进行应答
 * 涵盖：
 * 1. "调研紫金矿业股票信息，并生成下周投资策略" -> 提炼为 "紫金矿业调研与下周投资策略"
 * 2. 常见股票与各类意图（保本止损、大盘行情、5A选股、持仓解套等）动态提炼契约
 * 3. 前端 streamAIResponse 初始化渲染与 onStart 动态更新卡片标题机制
 * 4. 彻底杜绝死板固定的 "当前A股市场行情分析" 误报
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('=== [验证用户提交内容智能提炼摘要与卡片 Title 动态应答] ===\n');

// 加载前端 app.js 源码环境
const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'app.js'), 'utf8');

// 构造沙箱上下文以测试 refineTitleAndSummaryFromInput
const vm = require('vm');
const sandbox = {
  window: {},
  addEventListener: () => {},
  removeEventListener: () => {},
  location: { origin: 'http://localhost:8000' },
  localStorage: {
    getItem: () => null,
    setItem: () => null,
    removeItem: () => null
  },
  document: {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    removeEventListener: () => {}
  },
  console: console,
  AppState: {},
  HistoricalSessions: [],
  PromptTemplates: {
    '行情分析': { title: '当前A股市场行情分析', summary: '等待后端返回可验证行情证据', body: '' },
    '评估持股策略': { title: '持股策略与实战三原则量化诊断报告', summary: '', body: '' },
    '收益分析': { title: '投资组合全景收益与多因子归因报告', summary: '', body: '' },
    '技术指标': { title: '全市场技术形态与指标共振扫描', summary: '', body: '' },
    '选股模型': { title: '5A五维共振旋转选股输出', summary: '', body: '' }
  }
};
sandbox.window = sandbox;
sandbox.window.location = sandbox.location;
sandbox.window.localStorage = sandbox.localStorage;

vm.createContext(sandbox);

// 提取 refineTitleAndSummaryFromInput 函数进行沙箱执行
vm.runInContext(appSource, sandbox);

const refine = sandbox.window.refineTitleAndSummaryFromInput;
assert.ok(typeof refine === 'function', '必须导出 refineTitleAndSummaryFromInput 提炼函数');

// 1. 验证用户截图核心用例：调研紫金矿业股票信息，并生成下周投资策略
const caseZijin = refine('调研紫金矿业股票信息，并生成下周投资策略');
console.log('用例 1 测试结果:', caseZijin);
assert.ok(caseZijin.title.includes('紫金矿业'), '标题必须包含标的名称紫金矿业');
assert.ok(caseZijin.title.includes('下周') || caseZijin.title.includes('策略'), '标题必须提炼下周投资策略意图');
assert.strictEqual(caseZijin.title, '紫金矿业调研与下周投资策略', '核心标题必须精准为：紫金矿业调研与下周投资策略');
assert.ok(caseZijin.title !== '当前A股市场行情分析', '严禁降级为死板的“当前A股市场行情分析”');
console.log('✅ PASS [用例 1]: 成功将“调研紫金矿业股票信息，并生成下周投资策略”提炼为“' + caseZijin.title + '”');

// 2. 验证多场景智能提炼测试集
const testCases = [
  {
    input: '请分析一下贵州茅台后市走势',
    expectTitleContains: ['贵州茅台', '后市走势'],
    desc: '分析个股走势'
  },
  {
    input: '帮我算下600519的保本价和止损位',
    expectTitleContains: ['600519', '保本价与三级止损精算'],
    desc: '保本价止损精算'
  },
  {
    input: '分析今日大盘走势及主力动向',
    expectTitleContains: ['大盘走势与市场动向研判'],
    desc: '大盘指数研判'
  },
  {
    input: '用5A模型选出下周高潜力股票',
    expectTitleContains: ['5A多因子选股与轮动'],
    desc: '5A多因子选股'
  },
  {
    input: '海光信息成本140被套了怎么解套',
    expectTitleContains: ['海光信息', '解套'],
    desc: '持仓解套预案'
  },
  {
    input: '水下二次金叉与MACD底背离形态筛选',
    expectTitleContains: ['MACD底背离与二次金叉'],
    desc: 'MACD技术指标战法'
  }
];

testCases.forEach((tc, idx) => {
  const res = refine(tc.input);
  console.log(`用例 ${idx + 2} [${tc.desc}]: "${tc.input}" -> "${res.title}"`);
  tc.expectTitleContains.forEach(sub => {
    assert.ok(res.title.includes(sub), `标题 "${res.title}" 必须包含 "${sub}"`);
  });
  assert.ok(res.title !== '当前A股市场行情分析', `严禁输出死板默认标题`);
});
console.log('✅ PASS: 全部 6 类典型投资意图与标的提炼契约均严格成立');

// 3. 验证 streamAIResponse 源码契约：若未指定或为默认标题，且有 userText 时优先使用提炼标题
assert.ok(
  appSource.includes('const refined = userText ? refineTitleAndSummaryFromInput(userText, metaParam.operators) : null;'),
  'streamAIResponse 必须自动依据 userText 提取提炼摘要'
);
assert.ok(
  appSource.includes("title === '当前A股市场行情分析'") && appSource.includes('title = refined.title;'),
  'streamAIResponse 必须用提炼标题覆盖写死的默认标题'
);
console.log('✅ PASS: streamAIResponse 初始化生成时自动依据用户提交内容做提炼摘要');

// 4. 验证 onStart 动态刷新卡片 Title 契约
assert.ok(
  appSource.includes('const cardTitleEl = aiCard.querySelector(\'.ai-msg-title\');') &&
  appSource.includes('cardTitleEl.textContent = s.title;'),
  'onStart 回调中必须动态同步更新当前 AI 卡片的 .ai-msg-title'
);
console.log('✅ PASS: 后端流式响应握手返回精炼标题时，实时驱动界面卡片标题更新');

// 5. 验证降级路由中同样应用提炼标题
assert.ok(
  appSource.includes('const title = (refined && refined.title) ? refined.title : tpl.title;'),
  'executeOperatorTask 降级路由中必须传入动态提炼标题'
);
console.log('✅ PASS: 默认降级路由彻底摆脱固定写死标题');

console.log('\n🎉 所有动态提炼摘要与卡片 Title 契约测试全部通过！\n');
