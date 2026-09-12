// -*- coding: utf-8 -*-
/**
 * test_task_execution_ui.js
 * Verification test suite for the 8 requirements of AIChat Task Execution Process UI.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const cssSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'css', 'style.css'), 'utf8');
const presSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'chat_presentation.js'), 'utf8');
const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'app.js'), 'utf8');

console.log('=== [AIChat 任务执行过程 UI 设计与全流程交互验证] ===\n');

// --------------------------------------------------------------------------
// 1. 验证 ChatPresentation 模块拓展能力与纯函数测试
// --------------------------------------------------------------------------
const presSandbox = { window: {}, console };
vm.runInNewContext(presSource, presSandbox, { filename: 'chat_presentation.js' });
const P = presSandbox.window.ChatPresentation;

assert.ok(P, 'ChatPresentation 必须正常挂载至全局');
assert.strictEqual(typeof P.decomposeTask, 'function', 'ChatPresentation.decomposeTask 必须为函数');
assert.strictEqual(typeof P.renderExecutionTimelineHtml, 'function', 'ChatPresentation.renderExecutionTimelineHtml 必须为函数');
assert.strictEqual(typeof P.detectDeliverables, 'function', 'ChatPresentation.detectDeliverables 必须为函数');

// Req 1: 任务分解与制定执行计划
const plan1 = P.decomposeTask('请帮我分析 600519 贵州茅台的持股策略，核算最低保本卖出价与止损阶梯');
assert.ok(plan1.steps.length >= 4, '任务分解必须产生至少 4 个执行步骤');
assert.strictEqual(plan1.targetSkill, 'astock-action-execution', '保本诉求应路由至 astock-action-execution 技能');
assert.match(plan1.steps[0].title, /判断意图/);
assert.match(plan1.steps[1].title, /选择SOP/);
assert.match(plan1.steps[2].title, /能力调用/);
assert.ok(plan1.steps[2].deliverable && plan1.steps[2].deliverable.filename.endsWith('.md'), '步骤中应明确交付物产物 .md');
console.log('✅ PASS [Req 1]: 任务分解器正常生成 SOP、规定执行内容及调用技能');

// Req 2: 展开显示步骤与子任务执行情况，下方显示【working...】动画，异常红色提示
const stateRunning = P.createResponseState('test-run-1');
stateRunning.status = 'streaming';
stateRunning.timelineExpanded = true;
stateRunning.timelineNodes.push({
  nodeId: 'node-1',
  type: 'intent',
  title: '判断意图 600519 走势评估',
  status: 'succeeded',
  summary: '用户需求匹配 SOP「A股全流程综合研报」'
});
stateRunning.timelineNodes.push({
  nodeId: 'node-2',
  type: 'tool',
  title: '能力调用 astock-data-feed',
  skill_id: 'astock-data-feed',
  status: 'running',
  summary: '第 1 个动作 · 正在执行行情抓取'
});

const htmlRunning = P.renderExecutionTimelineHtml(stateRunning);
assert.match(htmlRunning, /timeline-working-indicator/, '正在执行时必须展示 working 指示条');
assert.match(htmlRunning, /working\.\.\./, '必须包含 working... 文字动效');
assert.match(htmlRunning, /能力调用中 astock-data-feed/, '运行中的能力调用状态应正确渲染');

// 异常测试
const stateError = P.createResponseState('test-err-1');
stateError.status = 'failed';
stateError.timelineNodes.push({
  nodeId: 'node-err-1',
  type: 'tool',
  title: '能力调用失败 exec_command',
  skill_id: 'exec_command',
  status: 'failed',
  error: { code: 'COMMAND_DENIED', detail: 'Bash command chaining is not supported' }
});
const htmlError = P.renderExecutionTimelineHtml(stateError);
assert.match(htmlError, /has-error|error-mode/, '执行异常时整体卡片必须为错误高亮样式');
assert.match(htmlError, /执行遇到问题/, '异常时顶部折叠头必须显示【执行遇到问题】');
assert.match(htmlError, /能力调用失败 exec_command/, '步骤标题必须显示红色调用失败');
assert.match(htmlError, /COMMAND_DENIED/, '必须呈现具体错误原因');
console.log('✅ PASS [Req 2]: 展开步骤、working... 动效与错误红色高亮警示均符合规范');

// Req 3: 步骤执行完成收起，支持手动展开能力结果抽屉，异常折叠重点标记
const stateWithResult = P.createResponseState('test-res-1');
stateWithResult.timelineNodes.push({
  nodeId: 'node-tool-1',
  type: 'tool',
  title: '能力调用完成 astock-data-feed',
  skill_id: 'astock-data-feed',
  status: 'succeeded',
  summary: '第 1 个动作',
  result: { price: 1420.5, success: true },
  expanded: false
});
const htmlWithResult = P.renderExecutionTimelineHtml(stateWithResult);
assert.match(htmlWithResult, /查看能力结果/, '步骤必须包含【查看能力结果】抽屉折叠按钮');
assert.match(htmlWithResult, /json-code-box/, '抽屉内必须包含格式化代码展示框');
assert.match(htmlWithResult, /1420\.5/, '抽屉内必须包含能力返回的数据');
console.log('✅ PASS [Req 3]: 步骤执行结果抽屉折叠与手动展开机制完整');

// Req 5: 任务执行完成自动收起全部过程，支持手动展开
const stateFinished = P.createResponseState('test-done-1');
stateFinished.status = 'succeeded';
stateFinished.timelineExpanded = false; // 完成后自动收起
stateFinished.timelineNodes.push({
  nodeId: 'node-fin-1',
  type: 'result',
  title: '整理任务结果',
  status: 'succeeded',
  summary: '完成'
});
const htmlFinished = P.renderExecutionTimelineHtml(stateFinished);
assert.match(htmlFinished, /timeline-nodes-list hidden/, '完成时步骤列表应默认折叠');
assert.match(htmlFinished, /执行记录/, '顶部应呈现折叠的执行记录栏');
console.log('✅ PASS [Req 5]: 任务完成全部收起与可手动展开机制成立');

// Req 6: 结果返回的文件可点击在右侧工作台查看 (如 xxx.md)
const detectedFiles = P.detectDeliverables('详见研报文件 `report_600519.md` 以及 `risk_plan.md`', {
  deliverable_file: 'summary_result.json'
});
assert.ok(detectedFiles.some(f => f.filename === 'report_600519.md'), '应提取出 report_600519.md 交付物');
assert.ok(detectedFiles.some(f => f.filename === 'risk_plan.md'), '应提取出 risk_plan.md 交付物');
assert.ok(detectedFiles.some(f => f.filename === 'summary_result.json'), '应提取出 summary_result.json 交付物');

stateRunning.timelineNodes[0].deliverable = { filename: 'report_600519.md' };
const htmlDeliverable = P.renderExecutionTimelineHtml(stateRunning);
assert.match(htmlDeliverable, /deliverable-link-chip/, '步骤中应渲染交付物链接芯片');
assert.match(htmlDeliverable, /openDeliverableInWorkbench/, '点击应调用 openDeliverableInWorkbench 打开工作台');
console.log('✅ PASS [Req 6]: 交付物识别与右侧工作区打开挂载点验证成功');

// --------------------------------------------------------------------------
// 2. 验证 HTML 结构契约 (Req 4, 6, 7, 8)
// --------------------------------------------------------------------------
assert.ok(htmlSource.includes('chatConfirmationPanel'), 'HTML 中必须存在人机确认面板 #chatConfirmationPanel');
assert.ok(htmlSource.includes('btnConfirmYes'), 'HTML 中必须存在确认按钮 #btnConfirmYes');
assert.ok(htmlSource.includes('btnConfirmNo'), 'HTML 中必须存在拒绝按钮 #btnConfirmNo');
assert.ok(htmlSource.includes('headerBgIndicator'), 'HTML 顶栏必须存在后台执行微状态指示器 #headerBgIndicator');
assert.ok(htmlSource.includes('pane-deliverable'), 'HTML 右侧工作台中必须存在交付物预览面板 #pane-deliverable');
assert.ok(htmlSource.indexOf('js/chat_presentation.js') < htmlSource.indexOf('js/app.js'), 'chat_presentation.js 必须在 app.js 之前加载');
console.log('✅ PASS [HTML Contract]: 人机确认面板、后台微状态与右侧工作台交付物面板完整存在');

// --------------------------------------------------------------------------
// 3. 验证 CSS 视觉与交互样式规范 (Req 2, 3, 4, 7, 8)
// --------------------------------------------------------------------------
assert.ok(cssSource.includes('.execution-record-box'), 'CSS 必须定义执行记录卡片');
assert.ok(cssSource.includes('.timeline-working-indicator'), 'CSS 必须定义 working 动效条');
assert.ok(cssSource.includes('.working-spinner-ring'), 'CSS 必须定义 working 旋转动画');
assert.ok(cssSource.includes('.has-error'), 'CSS 必须定义异常红色警示');
assert.ok(cssSource.includes('.chat-confirmation-panel'), 'CSS 必须定义人机确认面板样式');
assert.ok(cssSource.includes('.send-btn.btn-cancelling'), 'CSS 必须定义提交按钮取消态样式');
assert.ok(cssSource.includes('.header-bg-indicator'), 'CSS 必须定义后台执行指示器样式');
assert.ok(cssSource.includes('.deliverable-viewer-card'), 'CSS 必须定义交付物预览卡片样式');
console.log('✅ PASS [CSS Styles]: 8 维视觉规范与动效样式 100% 具备');

// --------------------------------------------------------------------------
// 4. 验证 app.js 运行时方法与契约
// --------------------------------------------------------------------------
for (const fnName of [
  'setExecutionStreamingState',
  'cancelCurrentExecution',
  'requestUserConfirmation',
  'handleConfirmationDecision',
  'toggleTimelineRecord',
  'toggleNodeDrawer',
  'openDeliverableInWorkbench',
  'closeDeliverablePane',
  'copyDeliverableContent',
  'focusActiveSession'
]) {
  assert.ok(appSource.includes(`function ${fnName}`), `app.js 必须包含 ${fnName} 方法`);
  assert.ok(appSource.includes(`window.${fnName} = ${fnName}`), `app.js 必须将 ${fnName} 挂载至 window`);
}

// Req 7: 按钮状态联动断言
assert.ok(appSource.includes("btnSend.classList.add('btn-cancelling')"), '执行中提交按钮需切换为取消样式');
assert.ok(appSource.includes("btnSend.innerHTML = '<span>取消</span>'"), '执行中按钮文本需变为取消');
assert.ok(appSource.includes("btn.classList.add('btn-disabled')"), '执行中工具按钮需被禁用');

// Req 8: 后台运行断言
assert.ok(appSource.includes("bgInd.style.display = 'inline-flex'"), '切换菜单时需点亮后台执行提示');

console.log('✅ PASS [app.js Contract]: 8 项业务控制器与生命周期调度均正常就绪');

console.log('\n🎉 所有 8 项【会话任务执行过程 UI 与交互设计】自动化断言 100% 全部通过！');
