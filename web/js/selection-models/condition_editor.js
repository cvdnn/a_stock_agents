// -*- coding: utf-8 -*-
/** 选股模型工作台 · 条件树编辑器（维度组 + AND/OR/NOT 逻辑树结构渲染与草稿保存）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const W = () => global.SelModels.store.get();

  function working() { return W().workingDefinition; }

  function render() {
    const wrap = DOM().getElementById('selectionFunnel');
    if (!wrap) return;
    const def = working();
    if (!def || def.model.model_type !== 'condition_tree') {
      global.SelModels.stateViews.empty(wrap, '当前模型不是条件模型，无逻辑树画布');
      return;
    }
    const sub = DOM().getElementById('selFunnelLayerCount');
    if (sub) sub.innerText = `维度组 ${def.groups.length} 个`;
    global.SelModels.store.set({ activeEditor: 'condition' });
    const rootRefs = collectRefs(def.expression);
    wrap.innerHTML = def.groups.map((group) => `
      <div class="funnel-row" data-group-id="${group.id}">
        <div class="funnel-index-col"><span class="funnel-index-dot">§</span></div>
        <div class="funnel-row-body">
          <div class="funnel-shape-wrap">
            <div class="funnel-bar funnel-done" style="width:72%">
              <span class="funnel-bar-name">${esc(group.name)}</span>
              <span class="funnel-bar-val">${esc(group.logic)}</span>
            </div>
          </div>
          <div class="funnel-info-panel">
            <div class="funnel-info-line"><span class="funnel-info-label">规则</span>
              <span>${group.rules.map((r, ri) => `<button type="button" class="sel-rule-chip"
                onclick="SelModels.conditionEditor.editRule('${group.id}',${ri})">${esc(r.id)}·${esc(r.type)}</button>`).join('') || '无'}</span></div>
            <div class="funnel-info-line"><span class="funnel-info-label">根引用</span>
              <span>${rootRefs.includes(group.id) ? '参与根表达式' : '未被根表达式引用'}</span></div>
          </div>
        </div>
      </div>`).join('');
  }

  function collectRefs(node, acc) {
    const out = acc || [];
    if (!node || typeof node !== 'object') return out;
    if (node.ref) out.push(node.ref);
    if (node.child) collectRefs(node.child, out);
    (node.children || []).forEach((c) => collectRefs(c, out));
    return out;
  }

  function editRule(groupId, ruleIdx) {
    const def = working();
    const group = def.groups.find((g) => g.id === groupId);
    if (!group || !group.rules[ruleIdx]) return;
    const rule = group.rules[ruleIdx];
    global.SelModels.store.set({ editingRule: rule, editingGroupId: groupId, editingRuleIdx: ruleIdx });
    global.SelModels.propertyDrawer.render(DOM().getElementById('selPropertyDrawer'), rule);
  }

  function addRule(rule) {
    const def = working();
    const groupId = W().activeGroupId || (def.groups[0] && def.groups[0].id);
    const group = def.groups.find((g) => g.id === groupId);
    if (!group) { global.showToast && global.showToast('请先选择维度组'); return; }
    group.rules = group.rules || [];
    group.rules.push(rule);
    global.SelModels.store.set({ workingDefinition: def });
    render();
    global.showToast && global.showToast(`已加入规则 ${rule.id}`);
  }

  async function save() {
    const def = working();
    const st = W();
    if (!st.activeModelId) { global.showToast && global.showToast('未选择模型'); return; }
    const model = global.SelModels.store.activeModel();
    try {
      const resp = await global.SelModels.api.saveDraft(
        st.activeModelId, def, model && model.active_version != null ? model.active_version : null,
        st.draftRevision || 0,
      );
      if (resp.status !== 'ok') { global.showToast && global.showToast(resp.message || '保存失败'); return; }
      global.SelModels.store.set({ workingDefinition: def, draftRevision: resp.data.draft_revision });
      global.showToast && global.showToast('草稿已保存');
    } catch (err) {
      global.showToast && global.showToast(err.message || '保存失败');
    }
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  global.SelModels.conditionEditor = { render, addRule, editRule, save };
})(window);