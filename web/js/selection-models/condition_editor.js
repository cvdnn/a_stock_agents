// -*- coding: utf-8 -*-
/** Condition group builder. Compilation remains the authority for validity. */
(function (global) {
  'use strict';
  const S = () => global.SelModels;
  const H = () => S().editorHelpers;
  const st = () => S().store.get();
  const def = () => st().workingDefinition;
  const root = () => global.document.getElementById('selectionFunnel');
  const refs = () => def().groups.filter((g) => g.enabled !== false).map((g) => g.id);
  function appendRoot(id) {
    const old = def().expression;
    def().expression = old ? { op: 'and', children: [old, { ref: id }] } : { ref: id };
  }
  function render() {
    const wrap = root();
    if (!wrap || !def() || def().model.model_type !== 'condition_tree') return;
    const groups = def().groups;
    if (st().activeGroupIndex == null || st().activeGroupIndex >= groups.length) S().store.set({ activeGroupIndex: 0 });
    S().store.set({ activeEditor: 'condition' });
    const h = H().esc;
    const count = global.document.getElementById('selFunnelLayerCount');
    if (count) count.textContent = `维度组 ${groups.length} 个${st().dirty ? ' · 未保存' : ''}`;
    wrap.innerHTML = `<div class="sel-builder-actions"><button type="button" class="sel-act-btn" onclick="SelModels.conditionEditor.addGroup()">＋新增条件组</button></div>
      ${groups.map((g, i) => `<section class="sel-builder-item ${i === st().activeGroupIndex ? 'selected' : ''}">
        <div class="sel-builder-row"><button type="button" class="sel-mini-btn" onclick="SelModels.conditionEditor.select(${i})">${i + 1}. 选择为规则目标</button>
          <label>名称 <input class="sel-inline-input" value="${h(g.name)}" onchange="SelModels.conditionEditor.setField(${i},'name',this.value)"></label>
          <label>逻辑 <select onchange="SelModels.conditionEditor.setField(${i},'logic',this.value)"><option value="all" ${g.logic === 'all' ? 'selected' : ''}>全部 AND</option><option value="any" ${g.logic === 'any' ? 'selected' : ''}>任一 OR</option></select></label>
          <label><input type="checkbox" ${g.enabled !== false ? 'checked' : ''} onchange="SelModels.conditionEditor.setField(${i},'enabled',this.checked)">启用</label>
          <button type="button" class="sel-mini-btn" onclick="SelModels.conditionEditor.move(${i},-1)" ${i === 0 ? 'disabled' : ''}>上移</button>
          <button type="button" class="sel-mini-btn" onclick="SelModels.conditionEditor.move(${i},1)" ${i === groups.length - 1 ? 'disabled' : ''}>下移</button>
          <button type="button" class="sel-mini-btn" onclick="SelModels.conditionEditor.removeGroup(${i})" ${groups.length === 1 ? 'disabled title="至少保留一个条件组"' : ''}>删除组</button></div>
        <div class="sel-builder-rules">${(g.rules || []).map((r, ri) => { const chip = S().ruleLibrary.chip(r); return `<span class="sel-rule-pair"><button type="button" class="sel-rule-chip" title="${h(chip.title)}" onclick="SelModels.propertyDrawer.openExisting('condition',${i},${ri})">${h(chip.label)}</button><button type="button" class="sel-mini-btn" aria-label="删除规则 ${h(chip.name)}" onclick="SelModels.conditionEditor.removeRule(${i},${ri})">×</button></span>`; }).join('') || '暂无规则，请从下方规则库添加'}</div>
        <label class="sel-builder-expression">组表达式 JSON（留空按上方逻辑组合已启用规则）<textarea data-condition-expression="${i}" rows="2">${h(g.expression ? JSON.stringify(g.expression) : '')}</textarea></label>
        <button type="button" class="sel-mini-btn" onclick="SelModels.conditionEditor.applyExpression(${i})">应用组表达式</button>
      </section>`).join('')}
      <label class="sel-builder-expression">根表达式 JSON（引用启用的条件组）<textarea id="selConditionRootExpression" rows="3">${h(JSON.stringify(def().expression))}</textarea></label>
      <button type="button" class="sel-mini-btn" onclick="SelModels.conditionEditor.applyRootExpression()">应用根表达式</button>
      <div class="sel-rule-library" id="selRuleLibrary" aria-label="规则库"></div>`;
    S().ruleLibrary.render(global.document.getElementById('selRuleLibrary'));
  }
  function select(index) { S().store.set({ activeGroupIndex: index }); render(); }
  function addGroup() {
    const groups = def().groups;
    const id = H().freshId('group', groups.map((g) => g.id));
    groups.push({ id, name: `条件组 ${groups.length + 1}`, enabled: true, logic: 'all', rules: [] });
    appendRoot(id);
    S().store.set({ activeGroupIndex: groups.length - 1 }); H().changed(); render();
  }
  function removeGroup(index) {
    if (def().groups.length <= 1) return;
    if (def().groups[index].enabled !== false && refs().length === 1) { H().notice('请先启用另一个条件组'); return; }
    const [removed] = def().groups.splice(index, 1);
    def().expression = H().replaceRef(def().expression, removed.id, null) || { ref: def().groups[0].id };
    S().store.set({ activeGroupIndex: Math.min(index, def().groups.length - 1) }); H().changed(); render();
  }
  function move(index, delta) {
    const groups = def().groups, next = index + delta;
    if (next < 0 || next >= groups.length) return;
    [groups[index], groups[next]] = [groups[next], groups[index]];
    S().store.set({ activeGroupIndex: next }); H().changed(); render();
  }
  function setField(index, key, value) {
    const group = def().groups[index];
    if (key === 'name' && !value.trim()) { H().notice('条件组名称不能为空'); render(); return; }
    if (key === 'enabled' && !value && group.enabled !== false && refs().length === 1) {
      H().notice('至少保留一个启用的条件组'); render(); return;
    }
    if (key === 'enabled' && group.enabled !== value) {
      def().expression = value ? (def().expression ? { op: 'and', children: [def().expression, { ref: group.id }] } : { ref: group.id }) : H().replaceRef(def().expression, group.id, null);
    }
    group[key] = value; H().changed(); render();
  }
  function removeRule(groupIndex, ruleIndex) {
    const group = def().groups[groupIndex];
    const [rule] = group.rules.splice(ruleIndex, 1);
    if (group.expression) group.expression = H().replaceRef(group.expression, rule.id, null);
    if (!group.expression) delete group.expression;
    H().changed(); render();
  }
  function applyExpression(index) {
    const group = def().groups[index];
    const raw = root().querySelector(`[data-condition-expression="${index}"]`).value.trim();
    try {
      if (raw) group.expression = H().parseExpression(raw, group.rules.filter((r) => r.enabled !== false).map((r) => r.id));
      else delete group.expression;
      H().changed(); render();
    } catch (err) { H().notice(err.message); }
  }
  function applyRootExpression() {
    try {
      def().expression = H().parseExpression(global.document.getElementById('selConditionRootExpression').value, refs());
      H().changed(); render();
    } catch (err) { H().notice(err.message); }
  }
  S().conditionEditor = { render, select, addGroup, removeGroup, move, setField, removeRule, applyExpression, applyRootExpression, save: () => H().save() };
})(window);
