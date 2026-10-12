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
    if (st.selectionMode === 'runs') {
      const runs = st.recentRuns || [];
      if (!runs.length) {
        S().stateViews.empty(list, '暂无选股记录。点击“新建选股”，选择已发布模型后直接运行。');
        return;
      }
      list.innerHTML = runs.map((run) => {
        const model = st.models.find((item) => item.model_id === run.model_id);
        const active = run.run_id === st.activeRunId;
        return `<button type="button" class="sel-model-card ${active ? 'active' : ''}" data-run-id="${escapeHtml(run.run_id)}"
            aria-current="${active ? 'true' : 'false'}" onclick="SelModels.modelCenter.selectRun('${escapeHtml(run.run_id)}')">
          <div class="sel-model-card-top"><span class="sel-model-name">${escapeHtml(model ? model.name : run.model_id)}</span>
          <span class="sel-model-type">v${escapeHtml(run.model_version)}</span></div>
          <div class="sel-model-foot"><span class="sel-model-status">${escapeHtml(run.status || '未知')} · ${escapeHtml(run.started_at || run.created_at || '时间未提供')}</span>
          <span class="sel-model-arrow">›</span></div></button>`;
      }).join('');
      return;
    }
    if (!st.models.length) {
      S().stateViews.empty(list, '尚未创建模型，点击“新建模型”从空白或模板创建');
      return;
    }
    list.innerHTML = st.models.map((m) => {
      const active = m.model_id === st.activeModelId;
      const label = STATUS_LABEL[m.status] || m.status;
      return `<button type="button" class="sel-model-card ${active ? 'active' : ''}" data-model-id="${escapeHtml(m.model_id)}"
          aria-current="${active ? 'true' : 'false'}" onclick="SelModels.modelCenter.select('${escapeHtml(m.model_id)}')">
        <div class="sel-model-card-top">
          <span class="sel-model-name">${escapeHtml(m.name)}</span>
          <span class="sel-model-type">${escapeHtml(m.model_type)}</span>
        </div>
        <div class="sel-model-foot">
          <span class="sel-model-status">${escapeHtml(label)}</span>
          <span class="sel-model-arrow">›</span>
        </div>
      </button>`;
    }).join('');
  }

  function select(modelId) {
    if (modelId !== S().store.get().activeModelId && !S().store.confirmDiscard()) return;
    S().store.set({ activeModelId: modelId });
    render();
    const loader = S().detailLoader;
    if (loader) loader.load(modelId);
  }

  function selectRun(runId) {
    const run = (S().store.get().recentRuns || []).find((item) => item.run_id === runId);
    if (run && S().main) S().main.openRun(run);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  global.SelModels.modelCenter = { render, select, selectRun, escapeHtml };
})(window);
