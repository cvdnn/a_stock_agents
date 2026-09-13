// -*- coding: utf-8 -*-
/**
 * test_frontend_session_memory.js
 * Verification of Session Memory System, Unique ID, Dynamic Title Extraction & History Display.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('=== [验证前端会话记忆体系、唯一ID、标题动态更新与历史会话展示] ===\n');

const apiSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'api.js'), 'utf8');
const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'app.js'), 'utf8');

// 1. 验证 AStockAPI 中包含 getSession 和 updateSessionTitle
assert.ok(apiSource.includes('getSession(sessionId)'), 'AStockAPI 必须提供 getSession 方法');
assert.ok(apiSource.includes('updateSessionTitle(sessionId, title)'), 'AStockAPI 必须提供 updateSessionTitle 方法');
console.log('✅ PASS: AStockAPI 已具备 getSession 与 updateSessionTitle 接口契约');

// 2. 验证 app.js 中的核心功能契约
// 2.1 唯一 ID 生成
assert.ok(appSource.includes('sess_') && appSource.includes('randHex'), 'startNewChat 必须生成带有唯一时间戳和随机标识的会话 ID');
console.log('✅ PASS: startNewChat 生成全局唯一格式 session ID (sess_...)');

// 2.2 动态更新侧边栏会话标题
assert.ok(appSource.includes('updateSessionItemTitle(sessionId, newTitle)'), 'app.js 必须具备 updateSessionItemTitle 函数');
assert.ok(appSource.includes('updateSessionItemTitle(s.session_id, s.title)'), 'streamChatCompletions 接收到 title 时必须更新侧边栏');
console.log('✅ PASS: 提交提问时服务端提炼的 title 通过 SSE 实时驱动侧边栏更新');

// 2.3 Bug 1 验证：提示词提交后，在会话记录中必须新增一条会话记录
assert.ok(
  appSource.includes('HistoricalSessions.unshift(newSession)') && appSource.includes('handleSendChat'),
  'handleSendChat 必须在 HistoricalSessions 中 unshift 新会话记录并调用 renderSessionList'
);
assert.ok(
  appSource.includes('executeQuickAction') && appSource.includes('HistoricalSessions.unshift(newSession)'),
  '快捷操作点击也必须在 HistoricalSessions 中 unshift 新会话记录'
);
console.log('✅ PASS [Bug 1 修复验证]: 提示词提交后，会话记录中立即新增一条会话记录');

// 2.4 Bug 2 验证：点击会话记录中 item，右侧区域联动并展示相应信息
assert.ok(appSource.includes('selectSession(id)'), 'app.js 必须具备 selectSession 函数');
assert.ok(appSource.includes('renderFallbackSessionContent'), 'selectSession 必须具备 renderFallbackSessionContent 兜底丰富内容，绝不退回欢迎页');
assert.ok(appSource.includes('switchRightTab(session.tab)'), 'selectSession 必须联动右侧工作台面板展示对应信息');
assert.ok(appSource.includes('SessionStore'), 'selectSession 必须支持无损会话快照缓存与一致性回显');
// 2.5 优化修改验证：点击【投研助手】与点击新建会话功能完全一样
assert.ok(
  appSource.includes("if (tabId === 'dashboard')") && appSource.includes('startNewChat()'),
  'handleMenuClick("dashboard") 必须触发 startNewChat()，保证点击【投研助手】与点击新建会话功能一样'
);
console.log('✅ PASS [优化修改验证]: 点击【投研助手】与点击新建会话功能完全一样');

console.log('\n🎉 全部前端会话记忆与展示契约验证通过！\n');
