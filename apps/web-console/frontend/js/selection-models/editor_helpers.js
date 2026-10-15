// -*- coding: utf-8 -*-
/** Shared draft and expression operations for the two model builders. */
(function (global) {
  'use strict';
  const S = () => global.SelModels;
  const state = () => S().store.get();
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const notice = (message) => { if (global.showToast) global.showToast(message); };
  function changed() { S().store.markDirty(); }
  function ruleIds(def) {
    return (def.groups || def.stages || []).flatMap((item) => (item.rules || []).map((rule) => rule.id));
  }
  function freshId(prefix, used) {
    let n = 1;
    while (used.includes(`${prefix}_${n}`)) n += 1;
    return `${prefix}_${n}`;
  }
  function replaceRef(node, oldId, newId) {
    if (!node || typeof node !== 'object') return node;
    if (node.ref === oldId) return newId ? { ref: newId } : null;
    if (node.child) {
      const child = replaceRef(node.child, oldId, newId);
      return child ? { op: 'not', child } : null;
    }
    if (Array.isArray(node.children)) {
      const children = node.children.map((child) => replaceRef(child, oldId, newId)).filter(Boolean);
      return children.length > 1 ? { op: node.op, children } : (children[0] || null);
    }
    return node;
  }
  function parseExpression(raw, allowed) {
    let value;
    try { value = JSON.parse(raw); } catch (_) { throw new Error('表达式必须是合法 JSON'); }
    function visit(node) {
      if (!node || typeof node !== 'object' || Array.isArray(node)) throw new Error('表达式节点必须是对象');
      if (Object.keys(node).length === 1 && typeof node.ref === 'string') {
        if (!allowed.includes(node.ref)) throw new Error(`未知或已停用引用：${node.ref}`);
        return;
      }
      if (node.op === 'not' && node.child) { visit(node.child); return; }
      if (['and', 'or'].includes(node.op) && Array.isArray(node.children) && node.children.length >= 2) {
        node.children.forEach(visit); return;
      }
      throw new Error('表达式仅支持 ref、and、or、not 节点');
    }
    visit(value);
    return value;
  }
  async function save() {
    const st = state();
    if (!st.activeModelId || !st.workingDefinition) { notice('请先选择模型'); return false; }
    if (st.saving) return false;
    const snapshot = JSON.stringify(st.workingDefinition);
    const modelId = st.activeModelId;
    S().store.set({ saving: true });
    try {
      const response = await S().api.saveDraft(modelId, JSON.parse(snapshot), st.draftBaseVersion, st.draftRevision);
      if (response.status !== 'ok') { notice(S().stateViews.message(response)); return false; }
      if (state().activeModelId === modelId) {
        const detail = state().detail;
        if (detail) detail.draft = { definition: response.data.definition,
          base_version: response.data.base_version, draft_revision: response.data.draft_revision };
        S().store.set({ detail,
          draftBaseVersion: response.data.base_version,
          draftRevision: response.data.draft_revision,
          dirty: JSON.stringify(state().workingDefinition) !== snapshot,
        });
      }
      notice('草稿已保存');
      return true;
    } catch (err) { notice(S().stateViews.message(err)); return false; }
    finally { S().store.set({ saving: false }); }
  }
  S().editorHelpers = { esc, notice, changed, ruleIds, freshId, replaceRef, parseExpression, save };
})(window);
