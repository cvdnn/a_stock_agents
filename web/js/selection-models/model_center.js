// -*- coding: utf-8 -*-
/** 选股模型工作台 · 模型中心（列表 / 选择 / 空态）。 */
(function (global) {
  'use strict';

  const S = () => global.SelModels;
  const DOM = () => global.document;

  const STATUS_LABEL = {
    active: '已激活',
    published: '已发布',
    draft: '草稿',
    empty: '空模型',
  };

  function render() {
    const list = DOM().getElementById('selectionModelList');
    if (!list) return;
    const st = S().store.get();
    if (st.loading) { S().stateViews.loading(list); return; }
    if (st.error) { S().stateViews.error(list, st.error); return; }
    if (!st.models.length) {
      S().stateViews.empty(list, '尚未创建任何选股模型，点击“新建选股模型”从空白或模板创建');
      return;
    }
    list.innerHTML = st.models.map((m) => {
      const active = m.model_id === st.activeModelId;
      const label = STATUS_LABEL[m.status] || m.status;
      return `<div class="sel-model-card ${active ? 'active' : ''}" data-model-id="${m.model_id}"
          onclick="SelModels.modelCenter.select('${m.model_id}')">
        <div class="sel-model-card-top">
          <span class="sel-model-name">${escapeHtml(m.name)}</span>
          <span class="sel-model-type">${escapeHtml(m.model_type)}</span>
        </div>
        <div class="sel-model-foot">
          <span class="sel-model-status">${escapeHtml(label)}</span>
          <span class="sel-model-arrow">›</span>
        </div>
      </div>`;
    }).join('');
  }

  function select(modelId) {
    S().store.set({ activeModelId: modelId });
    render();
    const loader = S().detailLoader;
    if (loader) loader.load(modelId);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  global.SelModels.modelCenter = { render, select, escapeHtml };
})(window);