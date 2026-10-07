// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 引导与装配（C5 收口）。
 *
 * 覆盖 app.js 的 fail-closed 入口：选中「策略选股」页签时，从后端真实接口加载模型、
 * 版本、运行、结果、调度与数据水位；无数据则如实空态，绝不本地兜底。
 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const S = () => global.SelModels;
  let booting = false;
  let initialized = false;

  async function ensureMeta() {
    const st = S().store.get();
    if (!st.types.length) {
      const resp = await S().api.listTypes();
      if (resp.status === 'ok') S().store.set({ types: resp.data.types || [] });
    }
    if (!st.ruleTypes.length) {
      const resp = await S().api.listRuleTypes();
      if (resp.status === 'ok') S().store.set({ ruleTypes: resp.data.rule_types || [] });
    }
  }

  async function bootstrap() {
    if (booting) return;
    booting = true;
    S().store.set({ loading: true, error: null });
    S().modelCenter.render();
    try {
      await ensureMeta();
      const resp = await S().api.listModels();
      const data = S().stateViews.unwrap(DOM().getElementById('selectionModelList'), resp, { emptyLabel: '尚未创建任何选股模型' });
      const models = (data && data.models) || [];
      S().store.set({ models, loading: false });
      S().modelCenter.render();
      const current = S().store.get().activeModelId;
      const pick = models.find((m) => m.model_id === current) || models[0];
      if (pick) await loadDetail(pick.model_id);
      else { S().store.set({ activeModelId: null, detail: null, workingDefinition: null }); renderAll(); }
    } catch (err) {
      S().store.set({ loading: false, error: { message: err.message, error_code: err.name } });
      S().modelCenter.render();
    } finally {
      booting = false;
      initialized = true;
    }
  }

  async function loadDetail(modelId) {
    S().store.set({ activeModelId: modelId, detail: null, workingDefinition: null });
    S().modelCenter.render();
    try {
      const resp = await S().api.getModel(modelId);
      if (resp.status !== 'ok') { global.showToast && global.showToast(resp.message || '模型加载失败'); return; }
      const detail = resp.data;
      let definition = detail.draft && detail.draft.definition;
      if (!definition && detail.active_version != null) {
        const vresp = await S().api.getVersion(modelId, detail.active_version);
        if (vresp.status === 'ok') definition = vresp.data.definition;
      }
      S().store.set({
        detail,
        workingDefinition: definition || null,
        draftRevision: detail.draft ? detail.draft.draft_revision : 0,
      });
      const [versionsResp, runsResp, resultsResp, schedResp, healthResp] = await Promise.all([
        S().api.listVersions(modelId), S().api.listRuns(modelId, '?limit=20'),
        S().api.results(modelId), S().api.getSchedule(modelId), S().api.dataHealth(),
      ]);
      S().store.set({
        versions: (versionsResp.data && versionsResp.data.versions) || [],
        runs: (runsResp.data && runsResp.data.runs) || [],
        results: (resultsResp.data && resultsResp.data.results) || [],
        schedule: schedResp.data || null,
        dataHealth: healthResp.data || null,
      });
      renderAll();
    } catch (err) {
      global.showToast && global.showToast(err.message || '模型加载失败');
    }
  }

  function renderAll() {
    S().modelCenter.render();
    S().overview.render();
    const def = S().store.get().workingDefinition;
    if (def && def.model && def.model.model_type === 'condition_tree') S().conditionEditor.render();
    else if (def) S().funnelEditor.render();
    else {
      const wrap = DOM().getElementById('selectionFunnel');
      if (wrap) S().stateViews.empty(wrap, '该模型暂无可用定义（无草稿且未激活版本）');
    }
    S().candidateTrace.renderResultsPanel();
    S().resultAssessment.render();
    S().trackingCenter.render();
    S().modelEvaluation.render();
  }

  // ---------------------------------------------------------------- 工具栏动作
  const main = {
    openWizard: () => S().wizard.open(),
    openTextDraft: () => S().textDraft.open(),
    openVersions: () => S().versionManager.open(),
    openDebug: () => S().debugPanel.open(),
    openSchedule: () => S().scheduler.open(),
    openDataHealth: () => S().dataHealth.open(),
    openRunTimeline: () => S().runTimeline.open(),
    saveDraft: () => {
      const def = S().store.get().workingDefinition;
      if (!def) { global.showToast && global.showToast('无可保存的定义'); return; }
      if (def.model.model_type === 'condition_tree') S().conditionEditor.save();
      else S().funnelEditor.save();
    },
    validate: async () => {
      const id = S().store.get().activeModelId;
      if (!id) { global.showToast && global.showToast('请先选择模型'); return; }
      const resp = await S().api.validate(id);
      if (resp.status === 'ok') global.showToast && global.showToast(`校验通过 · ${resp.data.plan_hash.slice(0, 16)}…`);
      else global.showToast && global.showToast(resp.message || '校验失败');
    },
    publish: () => S().versionManager.publish(),
    createRun: async () => {
      const id = S().store.get().activeModelId;
      if (!id) { global.showToast && global.showToast('请先选择模型'); return; }
      global.showToast && global.showToast('已发起手工运行…');
      const resp = await S().api.createRun(id, {});
      if (resp.status !== 'ok') { global.showToast && global.showToast(resp.message || '运行失败'); return; }
      global.showToast && global.showToast(`运行结束：${resp.data.run.status}（入选 ${resp.data.selected_codes.length}）`);
      await loadDetail(id);
    },
    cancelRun: () => S().runTimeline.cancelActive(),
    exportResults: () => {
      const results = S().store.get().results || [];
      const rows = [['model_id', 'signal_trade_date', 'run_id', 'signal_code']];
      results.forEach((item) => (item.signal_codes || []).forEach((code) => {
        rows.push([item.model_id, item.signal_trade_date, item.run_id, code]);
      }));
      const csv = rows.map((r) => r.join(',')).join('\n');
      const blob = new global.Blob([csv], { type: 'text/csv' });
      const link = DOM().createElement('a');
      link.href = global.URL.createObjectURL(blob);
      link.download = 'selection-results.csv';
      link.click();
      global.URL.revokeObjectURL(link.href);
    },
    toggleAnalysis: (show) => {
      const col = DOM().getElementById('selectionAnalysisCol');
      const listCol = DOM().getElementById('selectionModelCol');
      if (col) col.classList.toggle('collapsed', !show);
      if (listCol) listCol.classList.toggle('collapsed', !!show);
    },
    /** 阶段 E 页签编排：切换漏斗工作台 / 结果研究 / 持续跟踪 / 模型评估。 */
    showStage: (stage) => {
      const panels = {
        workbench: 'selStagePanelWorkbench',
        research: 'selStagePanelResearch',
        tracking: 'selStagePanelTracking',
        evaluation: 'selStagePanelEvaluation',
      };
      Object.keys(panels).forEach((key) => {
        const panel = DOM().getElementById(panels[key]);
        if (panel) panel.hidden = key !== stage;
        const tab = DOM().getElementById('selStageTab' + key.charAt(0).toUpperCase() + key.slice(1));
        if (tab) {
          tab.classList.toggle('active', key === stage);
          tab.setAttribute('aria-selected', key === stage ? 'true' : 'false');
        }
      });
      if (stage === 'research') S().resultAssessment.render();
      else if (stage === 'tracking') S().trackingCenter.render();
      else if (stage === 'evaluation') S().modelEvaluation.render();
    },
  };

  global.SelModels.main = main;
  global.SelModels.bootstrap = bootstrap;
  global.SelModels.detailLoader = { load: loadDetail };

  // 覆盖 app.js 的 fail-closed 入口（脚本在 app.js 之后加载）
  global.initSelectionWorkbench = bootstrap;
  global.renderSelectionWorkbench = bootstrap;
  global.refreshSelectionWorkbench = () => { S().store.set({ models: [] }); bootstrap(); };

  function start() {
    if (initialized) return;
    bootstrap();
  }

  if (DOM().readyState === 'loading') DOM().addEventListener('DOMContentLoaded', start);
  else start();
})(window);