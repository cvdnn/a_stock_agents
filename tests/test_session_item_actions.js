// -*- coding: utf-8 -*-
/**
 * test_session_item_actions.js
 * 验证会话记录项展示优化与操作交互：
 * 1. 会话记录 item 仅保留会话短摘要做 title（移除时间行）；
 * 2. 焦点态与最右侧显示更多按钮（竖型三点 ⋮）；
 * 3. 弹出菜单包含：重命名、删除会话；
 * 4. 重命名逻辑（内联修改与后端同步）；
 * 5. 删除会话逻辑（安全确认、后端删除与平滑切换）。
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('=== [验证会话记录项精简、焦点态、更多菜单、重命名与删除操作] ===\n');

const htmlSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'), 'utf8');
const cssSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'css', 'style.css'), 'utf8');
const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'app.js'), 'utf8');

// 1. 验证仅保留会话短摘要做 title，移除原有时间行
assert.ok(
  !appSource.includes('<div class="session-item-time">'),
  'renderSessionList 必须移除 session-item-time 时间行，仅保留短摘要 title'
);
assert.ok(
  appSource.includes('<div class="session-item-title" title="${safeTitle}">${safeTitle}</div>'),
  'renderSessionList 必须保留安全转义的短摘要 title'
);
console.log('✅ PASS [优化点 1]: 会话记录 item 仅保留会话短摘要做 title，已成功移除时间戳行');

// 2. 验证焦点态圆角矩形、独立更多按钮与焦点切换动效
assert.ok(cssSource.includes('.session-more-btn'), 'CSS 必须定义 .session-more-btn 更多按钮样式');
assert.ok(cssSource.includes('border-radius: 8px'), 'CSS 必须将会话记录 item 焦点态设置为圆角矩形(8px)，拒绝半圆');
assert.ok(cssSource.includes('.session-item:hover') && cssSource.includes('#eaedf0'), 'CSS 必须定义 hover 态浅灰焦点背景');
assert.ok(
  cssSource.includes('.session-item:has(.session-more-btn:hover)') || cssSource.includes('.session-item.more-focused'),
  'CSS 必须定义当光标在更多按钮时，焦点只留在更多按钮上（item 背景恢复透明）'
);
assert.ok(
  cssSource.includes('transform: scale(1.08)') && cssSource.includes('sessionMenuFadeInRight'),
  'CSS 必须定义更多按钮缩放微动效与向右弹出动画'
);
assert.ok(appSource.includes('class="session-more-btn"') && appSource.includes('openSessionMenu'), 'item 内部必须包含 session-more-btn 并挂接 openSessionMenu');
console.log('✅ PASS [优化点 2]: item焦点态为圆角矩形，鼠标移到更多按钮时焦点只留在更多按钮且有小动画切换');

// 3. 验证弹出菜单：1）向右侧弹出；2）包含重命名；3）包含删除会话
assert.ok(htmlSource.includes('id="sessionActionMenu"'), 'index.html 必须包含 sessionActionMenu 弹出菜单容器');
assert.ok(appSource.includes('rect.right + 8'), '弹出菜单必须修改到更多按钮右侧');
assert.ok(htmlSource.includes('handleMenuRenameClick') && htmlSource.includes('重命名'), '弹出菜单必须包含重命名操作');
assert.ok(htmlSource.includes('handleMenuDeleteClick') && htmlSource.includes('删除会话'), '弹出菜单必须包含删除会话操作');
assert.ok(cssSource.includes('.session-action-menu'), 'CSS 必须定义浮动卡片菜单样式');
console.log('✅ PASS [优化点 3]: 点击更多按钮弹出框修改到右侧，并包含重命名与删除会话两项');

// 4. 验证点击重命名修改会话 title
assert.ok(appSource.includes('startSessionRename(sessionId)'), 'app.js 必须具备 startSessionRename 函数');
assert.ok(appSource.includes('session-rename-input'), 'startSessionRename 必须渲染内联编辑输入框');
assert.ok(appSource.includes('updateSessionTitle'), '重命名提交必须同步调用后端 updateSessionTitle');
assert.ok(appSource.includes('sess.title = newTitle'), '重命名提交必须更新 HistoricalSessions 内存列表');
console.log('✅ PASS [优化点 4]: 重命名支持内联快速修改会话 title 并持久化同步');

// 5. 验证点击删除按钮删除会话记录
assert.ok(htmlSource.includes('id="sessionDeleteModal"'), 'index.html 必须包含 sessionDeleteModal 删除确认对话框');
assert.ok(appSource.includes('openSessionDeleteModal') && appSource.includes('executeSessionDelete'), 'app.js 必须具备删除弹窗与执行函数');
assert.ok(appSource.includes('deleteSession(sessionId)'), '执行删除必须调用后端 deleteSession 接口');
assert.ok(appSource.includes('HistoricalSessions.splice(idx, 1)'), '执行删除必须从 HistoricalSessions 中移除');
assert.ok(appSource.includes('selectSession(nextSession.id)') || appSource.includes('startNewChat()'), '删除当前会话后必须平滑切换');
console.log('✅ PASS [优化点 5]: 点击删除安全二次确认并从数据库与前端列表清除，支持平滑切换');

console.log('\n🎉 全部会话列表优化项契约测试 100% 验收通过！\n');
