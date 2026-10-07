// -*- coding: utf-8 -*-
/** 选股模型工作台 · 漏斗编辑器（阶段画布：规则 / 逻辑 / 时间触发器，草稿保存）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const W = () => global.SelModels.store.get();

  function working() {
    return W().workingDefinition;
  }

  function render() {
    const wrap = DOM().getElementById('selectionFunnel');
    if (!wrap) return;
    const def = working();
    if (!def || def.model.model_type !== 'funnel') {
      global.SelModels.stateViews.empty(wrap, '当前模型不是漏斗模型，无阶段画布');
      return;
    }
    const sub = DOM().getElementById('selFunnelLayerCount');
    if (sub) sub.innerText = `共 ${def.stages.length} 层`;
    global.SelModels.store.set({ activeEditor: 'funnel' });
    wrap.innerHTML = def.stages.map((stage, idx) => `
      <div class="funnel-row" data-stage-id="${stage.id}">
        <div class="funnel-index-col"><span class="funnel-index-dot">${idx + 1}</span></div>
        <div class="funnel-row-body">
          <div class="funnel-shape-wrap">
            <div class="funnel-bar funnel-done" style="width:${Math.max(50, 100 - idx * 10)}%">
              <span class="funnel-bar-name">${esc(stage.name)}</span>
              <span class="funnel-bar-val">${esc(stage.kind)}/${esc(stage.scope)}</span>
            </div>
          </div>
          <div class="funnel-info-panel">
            <div class="funnel-info-line"><span class="funnel-info-label">逻辑</span><span>${esc(stage.logic)}</span></div>
            <div class="funnel-info-line"><span class="funnel-info-label">触发器</span>
              <input type="text" class="sel-inline-input" data-stage="${stage.id}" value="${stage.schedule || ''}"
                placeholder="HH:MM-HH:MM" /></div>
            <div class="funnel-info-line"><span class="funnel-info-label">规则</span>
              <span>${stage.rules.map((r, ri) => `<button type="button" class="sel-rule-chip"
                onclick="SelModels.funnelEditor.editRule('${stage.id}',${ri})">${esc(r.id)}·${esc(r.type)}</button>`).join('') || '无'}</span></div>
          </div>
        </div>
      </div>`).join('');
  }

  function editRule(stageId, ruleIdx) {
    const def = working();
    const stage = def.stages.find((s) => s.id === stageId);
    if (!stage || !stage.rules[ruleIdx]) return;
    const rule = stage.rules[ruleIdx];
    global.SelModels.store.set({ editingRule: rule, editingStageId: stageId, editingRuleIdx: ruleIdx });
    global.SelModels.propertyDrawer.render(DOM().getElementById('selPropertyDrawer'), rule);
  }

  function addRule(rule) {
    const def = working();
    const stageId = W().activeStageId || (def.stages[0] && def.stages[0].id);
    const stage = def.stages.find((s) => s.id === stageId);
    if (!stage) { global.showToast && global.showToast('请先选择阶段'); return; }
    stage.rules = stage.rules || [];
    stage.rules.push(rule);
    global.SelModels.store.set({ workingDefinition: def });
    render();
    global.showToast && global.showToast(`已加入规则 ${rule.id}`);
  }

  function collectSchedule() {
    const def = working();
    DOM().querySelectorAll('[data-stage]').forEach((el) => {
      const stage = def.stages.find((s) => s.id === el.getAttribute('data-stage'));
      if (stage) stage.schedule = el.value.trim() || null;
    });
    return def;
  }

  async function save() {
    const def = collectSchedule();
    const st = W();
    if (!st.activeModelId) { global.showToast && global.showToast('未选择模型'); return; }
    const model = global.SelModels.store.activeModel();
    try {
      const resp = await global.SelModels.api.saveDraft(
        st.activeModelId, def, model && model.active_version != null ? model.active_version : null,
        def.__draft_revision || 0,
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

  global.SelModels.funnelEditor = { render, editRule, addRule, save, collectSchedule };
})(window);