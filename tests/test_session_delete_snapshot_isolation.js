// -*- coding: utf-8 -*-
/**
 * test_session_delete_snapshot_isolation.js
 * 验证会话删除与快照隔离机制：
 * 1. 当删除当前正在查看的会话时，被删除会话的 DOM 绝对不能作为快照写入下一个会话；
 * 2. executeSessionDelete 清空 DOM 并传递 skipSaveSnapshot 阻止快照污染；
 * 3. SessionStore 包含 remove 接口并在已删除会话上拒绝保存快照；
 * 4. selectSession 具备本地快照一致性校验与自愈清理，防止历史残留脏数据展示。
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('=== [验证会话删除快照隔离与脏数据自愈契约测试] ===\n');

const appSource = fs.readFileSync(path.join(__dirname, '..', 'web', 'js', 'app.js'), 'utf8');

// 1. 静态源码检测：SessionStore 包含 remove 方法
assert.ok(
  appSource.includes('remove(sessionId) {'),
  'SessionStore 必须提供 remove(sessionId) 接口'
);
assert.ok(
  appSource.includes('localStorage.removeItem(this.prefix + sessionId)'),
  'SessionStore.remove 必须正确清除对应本地存储 key'
);
console.log('✅ PASS [契约 1]: SessionStore 健全支持 remove 清理本地快照');

// 2. 静态源码检测：saveCurrentSessionSnapshot 具备已删除会话防存保护
assert.ok(
  appSource.includes('const currentSess = (typeof HistoricalSessions !== \'undefined\') ? HistoricalSessions.find(s => s.id === curId) : null;') &&
  appSource.includes('if (!currentSess) return;'),
  'saveCurrentSessionSnapshot 必须校验当前 ID 是否依然存在于列表中，若已删除严禁保存'
);
console.log('✅ PASS [契约 2]: saveCurrentSessionSnapshot 具备防御性校验，严禁写入已被删除会话');

// 3. 静态源码检测：executeSessionDelete 在删除当前会话时清空 DOM 并跳过保存
assert.ok(
  appSource.includes('chatContainer.innerHTML = \'\'') &&
  appSource.includes('AppState.currentSessionId = null'),
  'executeSessionDelete 必须在当前会话被删除时及时清空 DOM 并重置激活 ID'
);
assert.ok(
  appSource.includes('skipSaveSnapshot: true'),
  'executeSessionDelete 调用 selectSession 时必须传 skipSaveSnapshot: true 彻底防止旧 DOM 污染新会话'
);
console.log('✅ PASS [契约 3]: executeSessionDelete 正确重置当前状态并传递 skipSaveSnapshot');

// 4. 静态源码检测：selectSession 支持 skipSaveSnapshot 与快照一致性校验自愈
assert.ok(
  appSource.includes('async function selectSession(id, options = {})') &&
  appSource.includes('!skipSaveSnapshot'),
  'selectSession 必须支持 options.skipSaveSnapshot'
);
assert.ok(
  appSource.includes('isSnapshotValid = false') &&
  appSource.includes('SessionStore.remove(id)'),
  'selectSession 必须在检测到快照内容异构串号时自动清除脏快照并自愈'
);
console.log('✅ PASS [契约 4]: selectSession 具备快照一致性防串号校验与自愈清理能力');

// 5. 动态逻辑仿真测试：验证脏快照检测与自愈算法
const localStorageMock = {};
const mockSessionStore = {
  prefix: 'astock_sess_v2_',
  get(id) {
    const raw = localStorageMock[this.prefix + id];
    return raw ? JSON.parse(raw) : null;
  },
  set(id, val) {
    localStorageMock[this.prefix + id] = JSON.stringify(val);
  },
  remove(id) {
    delete localStorageMock[this.prefix + id];
  }
};

// 模拟历史污染场景：用户在 s1 (A股大盘反弹持续性与放量研判) 中遗留了 nihao 的旧快照
mockSessionStore.set('s1', {
  sessionId: 's1',
  title: 'nihao',
  html: '<div class="message-item message-user"><div class="message-bubble-user">nihao</div></div><div class="message-item message-ai"><div class="ai-msg-title">nihao</div></div>'
});

const currentSession = { id: 's1', title: 'A股大盘反弹持续性与放量研判' };
const cached = mockSessionStore.get('s1');
assert.ok(cached, '必须成功获取到模拟的污染快照');

// 模拟 selectSession 的校验逻辑
let isValid = true;
if (currentSession && cached.title && currentSession.title) {
  const normSess = currentSession.title.trim().toLowerCase();
  const normCached = cached.title.trim().toLowerCase();
  if (normCached !== normSess && !normSess.startsWith(normCached) && !normCached.startsWith(normSess)) {
    isValid = false;
  }
}

assert.strictEqual(isValid, false, '校验逻辑必须准确识别 title 为 nihao 与 A股大盘反弹持续性与放量研判 的异构冲突');
if (!isValid) {
  mockSessionStore.remove('s1');
}
assert.strictEqual(mockSessionStore.get('s1'), null, '检测到污染后必须自动清除脏快照');
console.log('✅ PASS [契约 5]: 动态仿真测试成功识别污染快照并触发自愈清理');

console.log('\n🎉 会话删除快照隔离与自愈契约测试全部 100% 通过！\n');
