// -*- coding: utf-8 -*-
/** 选股模型工作台 · 新建模型向导（选择类型 → 名称说明 → 空白/模板）。SPEC §16。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const TEMPLATES = {
    funnel: [
      { id: 'blank', label: '空白漏斗' },
      { id: 'funnel_close_breakout', label: '收盘突破→早盘拐点模板' },
    ],
    condition_tree: [
      { id: 'blank', label: '空白条件组' },
      { id: 'condition_pullback', label: '趋势回踩模板' },
    ],
  };

  function open() {
    const types = (global.SelModels.store.get().types || []).filter((t) => t.publishable);
    if (!types.length) {
      global.showToast && global.showToast('暂无可用模型类型（P2 类型仅登记，不可创建）');
      return;
    }
    const modal = buildModal(types);
    DOM().body.appendChild(modal);
  }

  function buildModal(types) {
    const wrap = DOM().createElement('div');
    wrap.className = 'sel-modal-mask';
    wrap.id = 'selectionWizardModal';
    wrap.innerHTML = `
      <div class="sel-modal">
        <div class="sel-modal-head"><span>新建选股模型</span>
          <button type="button" class="sel-close-btn" onclick="SelModels.wizard.close()">✕</button></div>
        <div class="sel-modal-body">
          <label class="sel-field"><span>模型类型</span>
            <select id="selWizardType">${types.map((t) => `<option value="${t.type_id}">${t.label}</option>`).join('')}</select>
          </label>
          <label class="sel-field"><span>名称</span><input id="selWizardName" type="text" placeholder="例如：收盘突破漏斗" /></label>
          <label class="sel-field"><span>说明</span><input id="selWizardDesc" type="text" placeholder="可选" /></label>
          <label class="sel-field"><span>起始模板</span><select id="selWizardTemplate"></select></label>
        </div>
        <div class="sel-modal-foot">
          <button type="button" class="sel-act-btn" onclick="SelModels.wizard.close()">取消</button>
          <button type="button" class="sel-act-btn primary" onclick="SelModels.wizard.submit()">创建草稿</button>
        </div>
      </div>`;
    wrap.querySelector('#selWizardType').addEventListener('change', refreshTemplates);
    refreshTemplatesIn(wrap);
    return wrap;
  }

  function refreshTemplates() {
    const modal = DOM().getElementById('selectionWizardModal');
    if (modal) refreshTemplatesIn(modal);
  }

  function refreshTemplatesIn(scope) {
    const typeSel = scope.querySelector('#selWizardType');
    const tplSel = scope.querySelector('#selWizardTemplate');
    if (!typeSel || !tplSel) return;
    const options = TEMPLATES[typeSel.value] || [{ id: 'blank', label: '空白' }];
    tplSel.innerHTML = options.map((t) => `<option value="${t.id}">${t.label}</option>`).join('');
  }

  async function submit() {
    const modal = DOM().getElementById('selectionWizardModal');
    if (!modal) return;
    const payload = {
      model_type: modal.querySelector('#selWizardType').value,
      name: modal.querySelector('#selWizardName').value.trim(),
      description: modal.querySelector('#selWizardDesc').value.trim(),
      template: modal.querySelector('#selWizardTemplate').value,
    };
    if (!payload.name) { global.showToast && global.showToast('请填写模型名称'); return; }
    try {
      const resp = await global.SelModels.api.createModel(payload);
      if (resp.status !== 'ok') { global.showToast && global.showToast(resp.message || '创建失败'); return; }
      close();
      const created = resp.data;
      await global.SelModels.bootstrap();
      global.SelModels.modelCenter.select(created.model_id);
    } catch (err) {
      global.showToast && global.showToast(err.message || '创建失败');
    }
  }

  function close() {
    const modal = DOM().getElementById('selectionWizardModal');
    if (modal) modal.remove();
  }

  global.SelModels.wizard = { open, close, submit };
})(window);