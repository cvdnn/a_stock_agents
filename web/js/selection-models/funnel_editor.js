// -*- coding: utf-8 -*-
/** Ordered funnel stage builder, backed by the same draft revision as condition trees. */
(function (global) {
  'use strict';
  const S = () => global.SelModels;
  const H = () => S().editorHelpers;
  const st = () => S().store.get();
  const def = () => st().workingDefinition;
  const root = () => global.document.getElementById('selectionFunnel');
  function rebind() {
    def().stages.forEach((s, i) => {
      s.order = (i + 1) * 10;
      s.input_binding = i ? `${def().stages[i - 1].id}.candidates` : 'market.daily_universe';
    });
  }
  function render() {
    const wrap = root();
    if (!wrap || !def() || def().model.model_type !== 'funnel') return;
    const stages = def().stages;
    if (st().activeStageIndex == null || st().activeStageIndex >= stages.length) S().store.set({ activeStageIndex: 0 });
    S().store.set({ activeEditor: 'funnel' });
    const h = H().esc;
    const count = global.document.getElementById('selFunnelLayerCount');
    if (count) count.textContent = `共 ${stages.length} 层${st().dirty ? ' · 未保存' : ''}`;
    wrap.innerHTML = `<div class="sel-builder-actions"><button type="button" class="sel-act-btn" onclick="SelModels.funnelEditor.addStage()">＋新增阶段</button></div>
      ${stages.map((s, i) => `<section class="sel-builder-item ${i === st().activeStageIndex ? 'selected' : ''}">
        <div class="sel-builder-row"><button type="button" class="sel-mini-btn" onclick="SelModels.funnelEditor.select(${i})">${i + 1}. 选择为规则目标</button>
          <label>名称 <input class="sel-inline-input" value="${h(s.name)}" onchange="SelModels.funnelEditor.setField(${i},'name',this.value)"></label>
          <label>类型 <select onchange="SelModels.funnelEditor.setField(${i},'kind',this.value)"><option value="filter" ${s.kind === 'filter' ? 'selected' : ''}>筛选</option><option value="gate" ${s.kind === 'gate' ? 'selected' : ''}>门控</option><option value="output" ${s.kind === 'output' ? 'selected' : ''}>输出</option></select></label>
          <label>逻辑 <select onchange="SelModels.funnelEditor.setField(${i},'logic',this.value)"><option value="all" ${s.logic === 'all' ? 'selected' : ''}>全部 AND</option><option value="any" ${s.logic === 'any' ? 'selected' : ''}>任一 OR</option></select></label>
          <label><input type="checkbox" ${s.enabled !== false ? 'checked' : ''} onchange="SelModels.funnelEditor.setField(${i},'enabled',this.checked)">启用</label>
          <button type="button" class="sel-mini-btn" onclick="SelModels.funnelEditor.move(${i},-1)" ${i === 0 ? 'disabled' : ''}>上移</button>
          <button type="button" class="sel-mini-btn" onclick="SelModels.funnelEditor.move(${i},1)" ${i === stages.length - 1 ? 'disabled' : ''}>下移</button>
          <button type="button" class="sel-mini-btn" onclick="SelModels.funnelEditor.removeStage(${i})" ${stages.length === 1 ? 'disabled title="至少保留一个阶段"' : ''}>删除阶段</button></div>
        <div class="sel-builder-row"><label>触发时间窗 <input class="sel-inline-input" placeholder="HH:MM-HH:MM" value="${h(s.schedule || '')}" onchange="SelModels.funnelEditor.setField(${i},'schedule',this.value)"></label>
          <span>输入：${h(s.input_binding || 'market.daily_universe')}</span></div>
        <div class="sel-builder-rules">${(s.rules || []).map((r, ri) => { const chip = S().ruleLibrary.chip(r); return `<span class="sel-rule-pair"><button type="button" class="sel-rule-chip" title="${h(chip.title)}" onclick="SelModels.propertyDrawer.openExisting('funnel',${i},${ri})">${h(chip.label)}</button><button type="button" class="sel-mini-btn" aria-label="删除规则 ${h(chip.name)}" onclick="SelModels.funnelEditor.removeRule(${i},${ri})">×</button></span>`; }).join('') || '暂无规则，请从下方规则库添加'}</div>
        <label class="sel-builder-expression">阶段表达式 JSON（留空按上方逻辑组合已启用规则）<textarea data-funnel-expression="${i}" rows="2">${h(s.expression ? JSON.stringify(s.expression) : '')}</textarea></label>
        <button type="button" class="sel-mini-btn" onclick="SelModels.funnelEditor.applyExpression(${i})">应用阶段表达式</button>
      </section>`).join('')}
      <div class="sel-rule-library" id="selRuleLibrary" aria-label="规则库"></div>`;
    S().ruleLibrary.render(global.document.getElementById('selRuleLibrary'));
  }
  function select(index) { S().store.set({ activeStageIndex: index }); render(); }
  function addStage() {
    const stages = def().stages;
    const id = H().freshId('stage', stages.map((s) => s.id));
    stages.push({ id, name: `阶段 ${stages.length + 1}`, enabled: true, order: 0,
      scope: 'candidate_filter', kind: 'filter', logic: 'all', schedule: null,
      missing_data_policy: 'reject', input_binding: '', rules: [] });
    rebind(); S().store.set({ activeStageIndex: stages.length - 1 }); H().changed(); render();
  }
  function removeStage(index) {
    if (def().stages.length <= 1) return;
    def().stages.splice(index, 1); rebind();
    S().store.set({ activeStageIndex: Math.min(index, def().stages.length - 1) }); H().changed(); render();
  }
  function move(index, delta) {
    const stages = def().stages, next = index + delta;
    if (next < 0 || next >= stages.length) return;
    [stages[index], stages[next]] = [stages[next], stages[index]];
    rebind(); S().store.set({ activeStageIndex: next }); H().changed(); render();
  }
  function setField(index, key, value) {
    const stage = def().stages[index];
    if (key === 'name' && !value.trim()) { H().notice('阶段名称不能为空'); render(); return; }
    if (key === 'schedule') {
      if (value.trim() && !/^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$/.test(value.trim())) { H().notice('触发器格式应为 HH:MM-HH:MM'); render(); return; }
      value = value.trim() || null;
    }
    if (key === 'kind') stage.scope = value === 'gate' ? 'universe_gate' : (value === 'output' ? 'output_gate' : 'candidate_filter');
    stage[key] = value; H().changed(); render();
  }
  function removeRule(stageIndex, ruleIndex) {
    const stage = def().stages[stageIndex];
    const [rule] = stage.rules.splice(ruleIndex, 1);
    if (stage.expression) stage.expression = H().replaceRef(stage.expression, rule.id, null);
    if (!stage.expression) delete stage.expression;
    H().changed(); render();
  }
  function applyExpression(index) {
    const stage = def().stages[index];
    const raw = root().querySelector(`[data-funnel-expression="${index}"]`).value.trim();
    try {
      if (raw) stage.expression = H().parseExpression(raw, stage.rules.filter((r) => r.enabled !== false).map((r) => r.id));
      else delete stage.expression;
      H().changed(); render();
    } catch (err) { H().notice(err.message); }
  }
  S().funnelEditor = { render, select, addStage, removeStage, move, setField, removeRule, applyExpression, save: () => H().save() };
})(window);
