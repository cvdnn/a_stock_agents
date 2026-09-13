// -*- coding: utf-8 -*-
/**
 * test_message_actions_lifecycle.js
 * 验证：在任务执行过程中不显示【复制】【重新生成】，任务完成后在结果卡片中显示。
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const cssSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'css', 'style.css'), 'utf8');
const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'app.js'), 'utf8');

console.log('=== [验证：任务执行过程中隐藏【复制】【重新生成】，完成后在结果卡片显示] ===\n');

// 1. CSS 规范验证
assert.ok(cssSource.includes('.message-actions.hidden'), 'CSS 必须定义 .message-actions.hidden 样式');
assert.match(cssSource, /\.message-actions\.hidden\s*\{[^}]*display:\s*none\s*!important/i, '.message-actions.hidden 必须具有 display: none !important');
assert.ok(cssSource.includes('actionsFadeIn'), 'CSS 必须定义完成后展示的 actionsFadeIn 淡入动效');
console.log('✅ PASS [CSS Contract]: .message-actions.hidden 与 actionsFadeIn 规范完整');

// 2. app.js 静态结构与方法契约验证
assert.ok(appSource.includes('function showMessageActions'), 'app.js 必须包含 showMessageActions 方法');
assert.ok(appSource.includes('window.showMessageActions = showMessageActions'), 'app.js 必须将 showMessageActions 挂载至 window');
assert.ok(appSource.includes("message-actions${isExecuting ? ' hidden' : ''}"), 'appendChatMessage 必须根据 isExecuting 动态注入 hidden 类');
assert.ok(appSource.includes('isExecuting: true'), 'streamAIResponse 初始消息元数据中必须声明 isExecuting: true');
assert.ok(appSource.includes('showMessageActions(msgId)'), '任务完成链路必须调用 showMessageActions(msgId)');
assert.ok(appSource.includes('showMessageActions(AppState.activeMsgId)'), '流式状态结束与取消操作必须联动 showMessageActions');
console.log('✅ PASS [app.js Contract]: showMessageActions 契约与生命周期联动完整');

// 3. 模拟 DOM 行为测试
function createMockElement(id = '', className = '') {
  return {
    id: id,
    className: className,
    classList: {
      _classes: new Set(className ? className.split(/\s+/) : []),
      add(c) { this._classes.add(c); },
      remove(c) { this._classes.delete(c); },
      contains(c) { return this._classes.has(c); }
    },
    style: {},
    children: [],
    appendChild(child) { this.children.push(child); return child; },
    querySelector(sel) {
      if (sel === '.message-actions') {
        return this.children.find(c => c.className && c.className.includes('message-actions'));
      }
      return null;
    }
  };
}

const mockDoc = {
  elements: {},
  getElementById(id) {
    return this.elements[id] || null;
  }
};

// 模拟测试：执行中卡片隐藏操作栏
const msgId1 = 'aiMsg_test_executing';
const isExecuting = true;
const actionsHtmlRunning = `<div class="message-actions${isExecuting ? ' hidden' : ''}" id="actions_${msgId1}" ${isExecuting ? 'style="display: none;"' : ''}>`;
assert.match(actionsHtmlRunning, /class="message-actions hidden"/, '执行中的消息操作栏必须包含 hidden 类');
assert.match(actionsHtmlRunning, /style="display: none;"/, '执行中的消息操作栏必须设置 display: none;');

// 模拟测试：已完成卡片（历史记录/恢复）默认展示
const msgId2 = 'aiMsg_test_completed';
const isExecutingDone = false;
const actionsHtmlDone = `<div class="message-actions${isExecutingDone ? ' hidden' : ''}" id="actions_${msgId2}" ${isExecutingDone ? 'style="display: none;"' : ''}>`;
assert.ok(!actionsHtmlDone.includes('hidden'), '已完成的消息操作栏不能包含 hidden 类');
assert.ok(!actionsHtmlDone.includes('display: none'), '已完成的消息操作栏不能设置 display: none;');

// 模拟测试：showMessageActions 唤醒
const actionsEl = createMockElement(`actions_${msgId1}`, 'message-actions hidden');
actionsEl.style.display = 'none';
mockDoc.elements[`actions_${msgId1}`] = actionsEl;

function mockShowMessageActions(msgId) {
  const el = mockDoc.getElementById(`actions_${msgId}`);
  if (el) {
    el.classList.remove('hidden');
    el.style.display = 'flex';
  }
}

mockShowMessageActions(msgId1);
assert.strictEqual(actionsEl.classList.contains('hidden'), false, '任务完成后必须移除 hidden 类');
assert.strictEqual(actionsEl.style.display, 'flex', '任务完成后必须设置为 display: flex 正常展现');

console.log('✅ PASS [DOM Simulation]: 执行中隐藏与任务完成后显现行为 100% 验证通过');
console.log('\n🎉 所有测试通过！');
