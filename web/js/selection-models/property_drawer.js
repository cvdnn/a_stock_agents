// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 属性抽屉（按参数 Schema 动态生成规则表单，S-06）。
 * 表单字段完全来自后端 `form_annotations`，不为任何规则硬编码字段。
 */
(function (global) {
  'use strict';

  const DOM = () => global.document;

  function metaOf(typeId) {
    return (global.SelModels.store.get().ruleTypes || []).find((m) => m.type === typeId) || null;
  }

  function fieldHtml(name, spec, value) {
    const widget = spec['x-ui-widget'];
    const label = `${name}${spec.required ? ' *' : ''}`;
    const unit = spec['x-unit'] ? ` <em class="sel-unit">${spec['x-unit']}</em>` : '';
    if (widget === 'select' && Array.isArray(spec.enum)) {
      const opts = spec.enum.map((v) => `<option value="${v}" ${String(value) === String(v) ? 'selected' : ''}>${v}</option>`).join('');
      return `<label class="sel-field"><span>${label}${unit}</span><select data-param="${name}">${opts}</select></label>`;
    }
    if (spec.type === 'boolean') {
      return `<label class="sel-field sel-field-inline"><span>${label}</span>
        <input type="checkbox" data-param="${name}" ${value ? 'checked' : ''} /></label>`;
    }
    if (spec.type === 'integer' || spec.type === 'number') {
      const val = value == null ? '' : value;
      return `<label class="sel-field"><span>${label}${unit}</span>
        <input type="number" data-param="${name}" value="${val}"
          ${spec.min != null ? `min="${spec.min}"` : ''} ${spec.max != null ? `max="${spec.max}"` : ''} /></label>`;
    }
    if (spec.type === 'array') {
      const arr = Array.isArray(value) ? value.join(',') : '';
      return `<label class="sel-field"><span>${label}（逗号分隔）</span>
        <input type="text" data-param="${name}" value="${arr}" /></label>`;
    }
    const raw = value == null ? '' : value;
    return `<label class="sel-field"><span>${label}${unit}</span>
      <input type="text" data-param="${name}" value="${raw}" /></label>`;
  }

  function render(container, rule) {
    if (!container) return;
    const meta = metaOf(rule.type);
    if (!meta) { global.SelModels.stateViews.error(container, { message: `未知规则类型 ${rule.type}` }); return; }
    const ann = meta.form_annotations || {};
    const fields = Object.keys(ann).map((name) => {
      const spec = ann[name];
      const value = name in rule ? rule[name] : spec.default;
      return fieldHtml(name, spec, value);
    });
    container.innerHTML = `
      <div class="sel-drawer-head"><strong>${meta.label}</strong>
        <span class="sel-drawer-meta">${rule.id || ''} · v${meta.version}</span></div>
      <div class="sel-drawer-body">
        <label class="sel-field"><span>规则 ID</span><input type="text" data-param="id" value="${rule.id || ''}" /></label>
        ${fields.join('')}
      </div>
      <div class="sel-drawer-foot">
        <button type="button" class="sel-act-btn primary" onclick="SelModels.propertyDrawer.apply()">应用</button>
      </div>`;
  }

  function openNew(typeId) {
    const meta = metaOf(typeId);
    if (!meta) return;
    const rule = { id: `${typeId}_new`, type: typeId };
    Object.keys(meta.defaults || {}).forEach((k) => { rule[k] = meta.defaults[k]; });
    global.SelModels.store.set({ editingRule: rule, editingRuleStage: null });
    render(DOM().getElementById('selPropertyDrawer'), rule);
  }

  function apply() {
    const drawer = DOM().getElementById('selPropertyDrawer');
    if (!drawer) return;
    const rule = { type: currentTypeId() };
    drawer.querySelectorAll('[data-param]').forEach((el) => {
      const name = el.getAttribute('data-param');
      let value;
      if (el.type === 'checkbox') value = el.checked;
      else if (el.type === 'number') value = el.value === '' ? null : Number(el.value);
      else value = el.value;
      if (name === 'id') { rule.id = value; return; }
      if (value === '' || value === null) return; // 缺省交由后端 Schema 默认值
      const meta = metaOf(rule.type);
      const spec = meta && (meta.form_annotations || {})[name];
      if (spec && spec.type === 'array') value = String(value).split(',').map((s) => s.trim()).filter(Boolean);
      rule[name] = value;
    });
    const editor = global.SelModels.store.get().activeEditor;
    if (editor === 'condition') global.SelModels.conditionEditor.addRule(rule);
    else if (editor === 'funnel') global.SelModels.funnelEditor.addRule(rule);
  }

  function currentTypeId() {
    const rule = global.SelModels.store.get().editingRule;
    return (rule && rule.type) || 'field_compare';
  }

  global.SelModels.propertyDrawer = { render, openNew, apply };
})(window);