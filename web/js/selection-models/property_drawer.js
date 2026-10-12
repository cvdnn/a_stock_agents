// -*- coding: utf-8 -*-
/** Rule form driven by /rule-types; edits keep the original array position. */
(function (global) {
  'use strict';
  const S = () => global.SelModels;
  const H = () => S().editorHelpers;
  const box = () => global.document.getElementById('selPropertyDrawer');
  const metaOf = (type) => (S().store.get().ruleTypes || []).find((m) => m.type === type);
  function anyValue(value) {
    try { return JSON.parse(value); } catch (_) { return value; }
  }
  function field(name, spec, value) {
    const h = H().esc;
    const label = `${h(name)}${spec.required ? ' *' : ''}`;
    const attrs = `data-param="${h(name)}" ${spec.required ? 'required' : ''}`;
    if (spec.enum) return `<label class="sel-field"><span>${label}</span><select ${attrs}>${spec.enum.map((v) => `<option value="${h(v)}" ${String(v) === String(value) ? 'selected' : ''}>${h(v)}</option>`).join('')}</select></label>`;
    if (spec.type === 'boolean') return `<label class="sel-field sel-field-inline"><span>${label}</span><input type="checkbox" ${attrs} ${value ? 'checked' : ''}></label>`;
    if (spec.type === 'integer' || spec.type === 'number') return `<label class="sel-field"><span>${label}</span><input type="number" ${attrs} value="${h(value == null ? '' : value)}" ${spec.type === 'integer' ? 'step="1"' : 'step="any"'} ${spec.min != null ? `min="${h(spec.min)}"` : ''} ${spec.max != null ? `max="${h(spec.max)}"` : ''}></label>`;
    const shown = spec.type === 'array' ? (Array.isArray(value) ? value.join(',') : '') : (value == null ? '' : value);
    return `<label class="sel-field"><span>${label}${spec.type === 'array' ? '（逗号分隔）' : ''}</span><input type="text" ${attrs} value="${h(shown)}"></label>`;
  }
  function render(rule) {
    const container = box();
    if (!container) return;
    const meta = metaOf(rule.type);
    if (!meta) { S().stateViews.error(container, { message: `未知规则类型 ${rule.type}` }); return; }
    const h = H().esc;
    container.innerHTML = `<div class="sel-drawer-head"><strong>${h(S().ruleLibrary.displayName(rule))}</strong><span class="sel-drawer-meta">${h(meta.label)} · ID：${h(rule.id)} · v${h(meta.version)}</span></div>
      <div class="sel-drawer-body"><label class="sel-field"><span>规则 ID *</span><input type="text" data-param="id" required value="${h(rule.id)}"></label>
      <label class="sel-field sel-field-inline"><span>启用规则</span><input type="checkbox" data-param="enabled" ${rule.enabled !== false ? 'checked' : ''}></label>
      ${Object.entries(meta.form_annotations || {}).map(([name, spec]) => field(name, spec, rule[name] === undefined ? spec.default : rule[name])).join('')}</div>
      <div class="sel-drawer-foot"><button type="button" class="sel-act-btn primary" onclick="SelModels.propertyDrawer.apply()">应用到草稿</button>
      <span class="sel-drawer-meta">应用后仍需保存草稿</span></div>`;
  }
  function openNew(type) {
    const meta = metaOf(type);
    const st = S().store.get();
    if (!meta || !st.workingDefinition) return;
    const rule = { id: H().freshId(type.replace(/[^a-z0-9_]/gi, '_'), H().ruleIds(st.workingDefinition)), type, enabled: true, ...(meta.defaults || {}) };
    S().store.set({ editingRule: rule, editingTarget: null });
    render(rule);
  }
  function openExisting(kind, ownerIndex, ruleIndex) {
    const st = S().store.get();
    const owner = (kind === 'condition' ? st.workingDefinition.groups : st.workingDefinition.stages)[ownerIndex];
    const rule = owner && owner.rules[ruleIndex];
    if (!rule) return;
    S().store.set({ editingRule: { ...rule }, editingTarget: { kind, ownerIndex, ruleIndex } });
    render(rule);
  }
  function apply() {
    const container = box();
    const st = S().store.get();
    if (!container || !st.editingRule || !st.workingDefinition) return;
    const meta = metaOf(st.editingRule.type);
    const next = { type: st.editingRule.type };
    for (const el of container.querySelectorAll('[data-param]')) {
      const name = el.dataset.param;
      const spec = (meta.form_annotations || {})[name];
      if (!el.checkValidity()) { el.reportValidity(); return; }
      let value = el.type === 'checkbox' ? el.checked : el.value.trim();
      if (name === 'id') {
        if (!value) { H().notice('规则 ID 不能为空'); return; }
        next.id = value; continue;
      }
      if (name === 'enabled') { next.enabled = value; continue; }
      if (value === '') { if (spec && spec.required) { H().notice(`${name} 不能为空`); return; } continue; }
      if (spec && ['integer', 'number'].includes(spec.type)) {
        value = Number(value);
        if (!Number.isFinite(value) || (spec.type === 'integer' && !Number.isInteger(value))) { H().notice(`${name} 数值无效`); return; }
      } else if (spec && spec.type === 'array') {
        value = value.split(',').map((s) => s.trim()).filter(Boolean);
        if (spec.minItems != null && value.length < spec.minItems) { H().notice(`${name} 至少需要 ${spec.minItems} 项`); return; }
        if (spec.items && spec.items.type === 'any') value = value.map(anyValue);
        if (spec.items && ['integer', 'number'].includes(spec.items.type)) {
          value = value.map(Number);
          if (value.some((v) => !Number.isFinite(v) || (spec.items.type === 'integer' && !Number.isInteger(v)))) { H().notice(`${name} 数组数值无效`); return; }
        }
        if (spec.items && spec.items.enum && value.some((v) => !spec.items.enum.includes(v))) {
          H().notice(`${name} 包含不允许的选项`); return;
        }
      } else if (spec && spec.type === 'any') {
        value = anyValue(value);
      }
      next[name] = value;
    }
    const owners = st.activeEditor === 'condition' ? st.workingDefinition.groups : st.workingDefinition.stages;
    const target = st.editingTarget;
    const ownerIndex = target ? target.ownerIndex : (st.activeEditor === 'condition' ? st.activeGroupIndex : st.activeStageIndex);
    const owner = owners[ownerIndex == null ? 0 : ownerIndex];
    if (!owner) { H().notice('请先选择条件组或漏斗阶段'); return; }
    const old = target && owners[target.ownerIndex].rules[target.ruleIndex];
    if (H().ruleIds(st.workingDefinition).some((id) => id === next.id && (!old || id !== old.id))) { H().notice(`规则 ID ${next.id} 已存在`); return; }
    if (old) {
      owner.rules[target.ruleIndex] = next;
      if (old.id !== next.id) for (const item of owners) if (item.expression) item.expression = H().replaceRef(item.expression, old.id, next.id);
    } else owner.rules.push(next);
    H().changed();
    S().store.set({ editingRule: null, editingTarget: null });
    if (st.activeEditor === 'condition') S().conditionEditor.render(); else S().funnelEditor.render();
    container.innerHTML = '<div class="sel-state">规则已应用到草稿，请保存。</div>';
  }
  S().propertyDrawer = { render, openNew, openExisting, apply };
})(window);
