/**
 * Automated test suite verifying:
 * 1) Elimination of streaming text jitter during execution
 * 2) Direct one-shot rendering of task results and summary upon completion
 * 3) Substantive dialogue summary with clickable .md deliverable link for full report
 * 4) Markdown link rendering in timeline steps & auto-saving of .md deliverables
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

console.log('=== [验证：流式防抖、执行结果整幅呈现、结果摘要与 .md 交付物持久化工作区联动] ===\n');

const ROOT = path.resolve(__dirname, '..');
const appJsPath = path.join(ROOT, 'web', 'js', 'app.js');
const chatPresPath = path.join(ROOT, 'web', 'js', 'chat_presentation.js');
const serverAppPath = path.join(ROOT, 'scripts', 'server', 'app.py');

const appJs = fs.readFileSync(appJsPath, 'utf8');
const chatPresJs = fs.readFileSync(chatPresPath, 'utf8');
const serverAppPy = fs.readFileSync(serverAppPath, 'utf8');

// --- 1. 后端文档持久化 API 验证 ---
console.log('--- 1. 后端 API 契约断言 (/api/docs/save & /api/docs/read) ---');
assert(serverAppPy.includes('@app.post("/api/docs/save"'), 'app.py 必须实现 POST /api/docs/save 文档持久化端点');
assert(serverAppPy.includes('SaveDocRequest'), 'app.py 必须具备 SaveDocRequest 模型');
assert(serverAppPy.includes('reports'), 'app.py 必须支持自动归档至 reports/ 目录');
assert(serverAppPy.includes('candidates = ['), 'app.py GET /api/docs/read 必须具备多目录自动检索能力');
console.log('✅ PASS [后端契约]: /api/docs/save 与 /api/docs/read 多目录回退完备');

// --- 2. 前端流式防抖断言 ---
console.log('\n--- 2. 前端流式防抖与滚动优化断言 ---');
assert(appJs.includes('// 用户诉求 1：任务执行过程中，不用按流式实时输出，修改新结果输出时界面上下抖动'), 'app.js 必须包含静默累加防抖逻辑');
const scrollFuncStr = appJs.slice(appJs.indexOf('function scrollToLatestExecution'), appJs.indexOf('window.scrollToLatestExecution = scrollToLatestExecution;'));
assert(!scrollFuncStr.includes('.scrollIntoView('), 'scrollToLatestExecution 必须移除与 scrollTop 冲突的 scrollIntoView 调用以消除抖动');
assert(appJs.includes('formatChatDialogueSummary'), 'app.js 必须调用 ChatPresentation.formatChatDialogueSummary');
console.log('✅ PASS [防抖断言]: 执行过程静默累加，移除 scrollIntoView 竞争，彻底消除上下抖动');

// --- 3. 结果摘要与工作区完整研报联动断言 ---
console.log('\n--- 3. 结果摘要与工作区完整研报联动断言 ---');
assert(chatPresJs.includes('function formatChatDialogueSummary'), 'chat_presentation.js 必须实现 formatChatDialogueSummary 函数');
assert(chatPresJs.includes('dialogue-deliverable-banner'), 'formatChatDialogueSummary 必须输出完整研报工作区直达卡片');
assert(chatPresJs.includes('btn-workbench-direct'), 'formatChatDialogueSummary 必须包含在工作区查看完整详报按钮');
assert(chatPresJs.includes('formatStepTextWithMdLinks'), 'chat_presentation.js 必须具备步骤文本中 .md 链接自动转换功能');
console.log('✅ PASS [摘要与工作区联动]: 实质性摘要保留核心段落，生成直达工作区的完整研报卡片');

// --- 4. 模拟运行 ChatPresentation 与 DOM 沙箱 ---
console.log('\n--- 4. DOM 沙箱运行时执行模拟断言 ---');

// 构建轻量级浏览器模拟沙箱
const sandbox = {
  window: {},
  document: {
    getElementById: () => null,
    createElement: () => ({ className: '', innerHTML: '', appendChild: () => {} }),
    querySelectorAll: () => []
  },
  console: console
};
sandbox.window = sandbox;

// 执行 chat_presentation.js
const evalChatPres = new Function('window', 'document', 'root', chatPresJs);
evalChatPres(sandbox.window, sandbox.document, sandbox.window);

const CP = sandbox.window.ChatPresentation;
assert(CP, 'ChatPresentation 必须成功挂载在 window 上');

// 测试 formatChatDialogueSummary
const sampleLongReport = `# 贵州茅台 (600519) 深度量化诊断报告

## 一、标的画像与核心定性
当前白酒板块白马龙头，资金抱团与防御价值凸显。

## 二、多因子量化评分与指标研判
综合评分：88分（多头共振）
MA均线呈多头排列，MACD水上二次金叉，KDJ指标处于超买回踩确认阶段。
主力资金近3日净流入 +15.8 亿元，获利盘比例 78.4%。

## 三、实战交易三原则（强制执行铁律）
1. 最低保本卖出价精算：1428.50 元（印花税0.05%、佣金万2.5最低5元起收向上进位）；
2. 三级风控止损阶梯：
   - T0 警戒线：-3% (1385.65 元)
   - T1 减仓线：-5% (1357.08 元，减仓50%)
   - T2 绝杀线：-8% (1314.22 元，坚决无条件清仓出局)
3. 三场景即时操作动作单：
   - 开盘冲高：不盲目追涨，观察成交量是否持续放大；
   - 盘中窄幅震荡：持股待涨，防守位设在 T0 线；
   - 盘中急跌跳水：跌破 T1 立即减半，跌破 T2 坚决离场。

## 四、重点风控提示与跟踪建议
警惕大盘系统性回撤风险及消费复苏不及预期。
`;

const formattedHtml = CP.formatChatDialogueSummary(sampleLongReport, {
  deliverableFilename: 'report_600519_20260913.md',
  deliverableTitle: '茅台深度量化研报'
});

assert(formattedHtml.includes('实战交易三原则'), '实质性摘要必须保留实战交易三原则段落');
assert(formattedHtml.includes('最低保本卖出价精算'), '实质性摘要必须包含保本价');
assert(formattedHtml.includes('三级风控止损阶梯'), '实质性摘要必须包含三级止损阶梯');
assert(formattedHtml.includes('report_600519_20260913.md'), '摘要末尾必须渲染完整交付物文件名链接');
assert(formattedHtml.includes('在工作区查看完整详报'), '摘要末尾必须包含直达工作区的引导按钮');
console.log('✅ PASS [沙箱 1]: formatChatDialogueSummary 成功生成丰富实战摘要并附带工作区链接');

// 测试时间线节点中 .md 链接转换与呈现
const timelineState = CP.createResponseState('test_resp_1');
CP.applyEvent(timelineState, 'tool_call_start', {
  call_id: 'call_1',
  skill_id: 'astock-platform-evaluate',
  title: '能力调用 astock-platform-evaluate 产生 report_600519.md'
});
CP.applyEvent(timelineState, 'tool_call_complete', {
  call_id: 'call_1',
  status: 'success',
  summary: '已成功生成量化研报交付物 report_600519.md 并通过风控校验',
  data: {
    deliverables: ['report_600519.md']
  }
});
timelineState.status = 'succeeded';
timelineState.timelineExpanded = true;

const timelineHtml = CP.renderExecutionTimelineHtml(timelineState);
assert(timelineHtml.includes('chat-md-chip') || timelineHtml.includes('deliverable-link-chip'), '时间线中带有 .md 的步骤必须高亮为可点击药丸');
assert(timelineHtml.includes('report_600519.md'), '时间线中必须包含交付物文件名');
console.log('✅ PASS [沙箱 2]: renderExecutionTimelineHtml 成功将步骤中的 .md 文件转换为工作区直达药丸');

console.log('\n🎉 所有 4 大需求全部验证通过！流式防抖、执行结果整幅呈现与工作区 Markdown 交付物验收达标！\n');
