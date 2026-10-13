// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 引导与装配（C5 收口）。
 *
 * 选中「策略选股」页签时，从后端真实接口加载模型、
 * 版本、运行、结果、调度与数据水位；无数据则如实空态，绝不本地兜底。
 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const S = () => global.SelModels;
  let booting = false;
  let bootstrapSequence = 0;
  let loadSequence = 0;
  let publishedChoices = [];

  function requireOk(response) {
    if (!response || response.status !== 'ok') {
      throw new Error(S().stateViews.message(response));
    }
    return response.data;
  }

  async function ensureMeta(sequence) {
    const st = S().store.get();
    if (!st.types.length) {
      const resp = await S().api.listTypes();
      if (sequence !== loadSequence) return;
      S().store.set({ types: requireOk(resp).types || [] });
    }
    if (!st.ruleTypes.length) {
      const resp = await S().api.listRuleTypes();
      if (sequence !== loadSequence) return;
      S().store.set({ ruleTypes: requireOk(resp).rule_types || [] });
    }
  }

  async function bootstrap() {
    if (booting) return;
    booting = true;
    const bootstrapToken = ++bootstrapSequence;
    const sequence = ++loadSequence;
    showWorkbenchView(S().store.get().selectionMode === 'runs' ? 'run' : 'edit');
    S().stateViews.clearError();
    S().store.set({ loading: true, error: null });
    S().modelCenter.render();
    S().stateViews.loading(DOM().getElementById('selectionFunnel'), '加载选股模型…');
    try {
      await ensureMeta(sequence);
      if (sequence !== loadSequence) return;
      const [resp, recentResp] = await Promise.all([S().api.listModels(), S().api.listRecentRuns()]);
      if (sequence !== loadSequence) return;
      const data = requireOk(resp);
      const recent = requireOk(recentResp);
      const models = data.models || [];
      S().store.set({ models, listPermissions: data.permissions || {}, recentRuns: recent.runs || [], loading: false });
      S().modelCenter.render();
      const firstRun = (recent.runs || [])[0];
      const current = S().store.get().activeModelId;
      const pick = S().store.get().selectionMode === 'runs'
        ? models.find((m) => m.model_id === (firstRun && firstRun.model_id))
        : (models.find((m) => m.model_id === current) || models[0]);
      if (pick) await loadDetail(pick.model_id,
        S().store.get().selectionMode === 'runs' && firstRun && firstRun.model_id === pick.model_id ? firstRun.run_id : null);
      else { S().store.set({ activeModelId: null, detail: null, workingDefinition: null,
        versions: [], runs: [], results: [], schedule: null, dataHealth: null }); S().runWorkspace.clear(); renderAll(); showWorkbenchView('run'); }
    } catch (err) {
      if (sequence !== loadSequence) return;
      S().store.set({ loading: false, error: err, models: [], listPermissions: {}, activeModelId: null,
        detail: null, workingDefinition: null, versions: [], runs: [], recentRuns: [], results: [] });
      S().runWorkspace.clear();
      S().modelCenter.render();
      renderAll();
      S().stateViews.error(DOM().getElementById('selectionFunnel'), err);
    } finally {
      if (bootstrapToken === bootstrapSequence) booting = false;
    }
  }

  async function loadDetail(modelId, requestedRunId = null) {
    const sequence = ++loadSequence;
    showWorkbenchView(S().store.get().selectionMode === 'runs' ? 'run' : 'edit');
    S().runTimeline.close();
    S().stateViews.clearError();
    S().store.set({ activeModelId: modelId, detail: null, workingDefinition: null,
      versions: [], runs: [], results: [], schedule: null, dataHealth: null,
      activeRunId: null, nodes: [], candidates: [], activeGroupIndex: 0,
      activeStageIndex: 0, detailLoading: true });
    S().runWorkspace.clear();
    S().modelCenter.render();
    renderAll();
    S().stateViews.loading(DOM().getElementById('selectionFunnel'), '加载模型详情…');
    try {
      const resp = await S().api.getModel(modelId);
      const detail = requireOk(resp);
      if (sequence !== loadSequence) return;
      let definition = detail.draft && detail.draft.definition;
      if (!definition && detail.active_version != null) {
        const vresp = await S().api.getVersion(modelId, detail.active_version);
        definition = requireOk(vresp).definition;
      }
      if (sequence !== loadSequence) return;
      S().store.set({ detail });
      S().store.setDraft(detail, definition);
      renderAll();
      const [versionsResp, runsResp, resultsResp, schedResp, healthResp] = await Promise.all([
        S().api.listVersions(modelId), S().api.listRuns(modelId, '?limit=50'),
        S().api.results(modelId), S().api.getSchedule(modelId), S().api.dataHealth(),
      ]);
      if (sequence !== loadSequence) return;
      S().store.set({
        versions: requireOk(versionsResp).versions || [],
        runs: requireOk(runsResp).runs || [],
        results: requireOk(resultsResp).results || [],
        schedule: requireOk(schedResp),
        dataHealth: requireOk(healthResp),
        detailLoading: false,
      });
      renderAll();
      await S().runWorkspace.syncModel();
      if (sequence === loadSequence && requestedRunId) await S().runWorkspace.selectRun(requestedRunId);
      if (sequence === loadSequence) {
        S().modelCenter.render();
        S().overview.render();
        showWorkbenchView(S().store.get().selectionMode === 'runs' ? 'run' : 'edit');
      }
    } catch (err) {
      if (sequence !== loadSequence) return;
      S().store.set({ detailLoading: false });
      if (S().store.get().workingDefinition) {
        S().stateViews.notifyError(err);
      } else {
        S().stateViews.error(DOM().getElementById('selectionFunnel'), err);
      }
    }
  }

  function renderAll() {
    renderMode();
    S().modelCenter.render();
    S().overview.render();
    const st = S().store.get();
    const def = st.workingDefinition;
    if (def && def.model && def.model.model_type === 'condition_tree') S().conditionEditor.render();
    else if (def) S().funnelEditor.render();
    else if (!st.detailLoading) {
      const wrap = DOM().getElementById('selectionFunnel');
      if (wrap) S().stateViews.empty(wrap, '该模型暂无可用定义（无草稿且未激活版本）');
      const library = DOM().getElementById('selRuleLibrary');
      if (library) library.innerHTML = '';
    }
    S().resultAssessment.render();
    S().trackingCenter.render();
    S().modelEvaluation.render();
  }

  function showWorkbenchView(view) {
    ['run', 'edit'].forEach((name) => {
      const panel = DOM().getElementById(name === 'run' ? 'selRunWorkspace' : 'selEditWorkspace');
      if (panel) panel.hidden = name !== view;
    });
  }

  function renderMode() {
    const mode = S().store.get().selectionMode;
    const root = DOM().getElementById('selStagePanelWorkbench');
    if (root) root.dataset.selectionMode = mode;
    DOM().querySelectorAll('#pane-selection [data-sel-mode]').forEach((element) => {
      element.hidden = element.dataset.selMode !== mode;
    });
    ['runs', 'models'].forEach((name) => {
      const tab = DOM().getElementById(name === 'runs' ? 'selPurposeRuns' : 'selPurposeModels');
      if (tab) { tab.classList.toggle('active', mode === name); tab.setAttribute('aria-selected', mode === name ? 'true' : 'false'); }
    });
    const title = DOM().getElementById('selListTitle');
    if (title) title.textContent = mode === 'runs' ? '选股记录' : '模型资产';
    const permissions = S().store.get().listPermissions || {};
    [['selNewSelectionButton', 'run', '当前身份无选股运行权限'],
      ['selTextDraftButton', 'create', '当前身份无创建模型权限'],
      ['selNewModelButton', 'create', '当前身份无创建模型权限']].forEach(([id, action, denied]) => {
      const button = DOM().getElementById(id);
      if (!button) return;
      if (!button.hasAttribute('data-enabled-title')) button.setAttribute('data-enabled-title', button.title);
      button.disabled = !permissions[action];
      button.title = permissions[action] ? button.getAttribute('data-enabled-title') : denied;
    });
  }

  function switchMode(mode) {
    if (!['runs', 'models'].includes(mode) || mode === S().store.get().selectionMode) return;
    if (mode === 'runs' && !S().store.confirmDiscard()) return;
    S().store.set({ selectionMode: mode });
    renderAll();
    showWorkbenchView(mode === 'runs' ? 'run' : 'edit');
  }

  async function openRun(run) {
    if (!run) return;
    if (S().store.get().selectionMode !== 'runs') switchMode('runs');
    if (S().store.get().selectionMode !== 'runs') return;
    if (S().store.get().activeModelId === run.model_id &&
        (S().store.get().runs || []).some((item) => item.run_id === run.run_id)) {
      await S().runWorkspace.selectRun(run.run_id);
      S().modelCenter.render();
      S().overview.render();
    } else await loadDetail(run.model_id, run.run_id);
    showWorkbenchView('run');
  }

  function closeNewSelection() {
    const modal = DOM().getElementById('selNewSelectionModal');
    if (modal) modal.remove();
  }

  function renderPublishedVersions() {
    const modelId = DOM().getElementById('selNewSelectionModel')?.value;
    const versions = publishedChoices.find((item) => item.model_id === modelId)?.versions || [];
    const select = DOM().getElementById('selNewSelectionVersion');
    if (!select) return;
    select.innerHTML = versions.map((item) => `<option value="${item.version}">v${item.version}${item.status === 'ACTIVE' ? ' · 自动调度使用中' : ''}</option>`).join('');
    if (versions[0]) select.value = String(versions[0].version);
  }

  async function openNewSelection() {
    const workspaceToken = bootstrapSequence;
    if (!S().store.get().listPermissions.run) {
      global.showToast && global.showToast('当前身份无选股运行权限');
      return;
    }
    closeNewSelection();
    const wrap = DOM().createElement('div');
    wrap.className = 'sel-modal-mask';
    wrap.id = 'selNewSelectionModal';
    wrap.innerHTML = `<div class="sel-modal">
      <div class="sel-modal-head"><span>新建选股</span><button type="button" class="sel-close-btn" aria-label="关闭" onclick="SelModels.main.closeNewSelection()">✕</button></div>
      <div class="sel-modal-body"><p class="sel-new-selection-help">选择已发布模型，点击后立即扫描本地全市场股票数据；15:35 仅是自动调度时间。修改参数请到“模型管理”发布新版本。</p>
        <label class="sel-field"><span>已发布模型</span><select id="selNewSelectionModel"></select></label>
        <label class="sel-field"><span>使用版本</span><select id="selNewSelectionVersion"></select></label>
        <div class="sel-new-selection-status" id="selNewSelectionStatus" role="status">加载已发布模型…</div></div>
      <div class="sel-modal-foot"><button type="button" class="sel-act-btn" onclick="SelModels.main.closeNewSelection()">取消</button>
        <button type="button" class="sel-act-btn primary" id="selNewSelectionRun" onclick="SelModels.main.runNewSelection()" disabled>▶ 运行选股</button></div></div>`;
    DOM().body.appendChild(wrap);
    try {
      const candidates = S().store.get().models.filter((model) => model.latest_version > 0);
      const responses = await Promise.all(candidates.map(async (model) => ({
        model_id: model.model_id, versions: requireOk(await S().api.listVersions(model.model_id)).versions
          .filter((version) => version.status !== 'ARCHIVED').sort((a, b) => b.version - a.version),
      })));
      if (workspaceToken !== bootstrapSequence || DOM().getElementById('selNewSelectionModal') !== wrap) return;
      publishedChoices = responses.filter((item) => item.versions.length);
      const select = DOM().getElementById('selNewSelectionModel');
      const esc = S().modelCenter.escapeHtml;
      select.innerHTML = publishedChoices.map((item) => {
        const model = candidates.find((candidate) => candidate.model_id === item.model_id);
        return `<option value="${esc(item.model_id)}">${esc(model.name)}</option>`;
      }).join('');
      select.addEventListener('change', renderPublishedVersions);
      renderPublishedVersions();
      DOM().getElementById('selNewSelectionRun').disabled = !publishedChoices.length;
      DOM().getElementById('selNewSelectionStatus').textContent = publishedChoices.length
        ? '运行使用所选版本，不会改变自动调度使用的活动版本。'
        : '尚无可运行的已发布模型。请先到“模型管理”创建并发布模型。';
    } catch (err) {
      if (workspaceToken !== bootstrapSequence) return;
      const status = DOM().getElementById('selNewSelectionStatus');
      if (status) { status.textContent = S().stateViews.message(err); status.classList.add('error'); }
    }
  }

  async function runNewSelection() {
    const workspaceToken = bootstrapSequence;
    const modelId = DOM().getElementById('selNewSelectionModel')?.value;
    const version = Number(DOM().getElementById('selNewSelectionVersion')?.value);
    const choice = publishedChoices.find((item) => item.model_id === modelId);
    if (!choice || !choice.versions.some((item) => item.version === version)) return;
    const button = DOM().getElementById('selNewSelectionRun');
    const status = DOM().getElementById('selNewSelectionStatus');
    button.disabled = true;
    status.classList.remove('error');
    status.textContent = `正在运行 v${version}…`;
    try {
      const resp = await S().api.createRun(modelId, { version, all_market: true });
      if (workspaceToken !== bootstrapSequence) return;
      if (resp.status !== 'ok') { status.textContent = S().stateViews.message(resp); status.classList.add('error'); return; }
      closeNewSelection();
      rememberRun(resp.data.run);
      await loadDetail(modelId, resp.data.run_id);
      if (workspaceToken !== bootstrapSequence) return;
      S().modelCenter.render();
      refreshRecentRuns();
      global.showToast && global.showToast(`选股完成：${resp.data.run.status}（入选 ${resp.data.selected_codes.length}）`);
    } catch (err) {
      if (workspaceToken !== bootstrapSequence) return;
      if (status.isConnected) { status.textContent = S().stateViews.message(err); status.classList.add('error'); }
      else S().stateViews.notifyError(err);
    } finally { if (button.isConnected) button.disabled = false; }
  }

  function rememberRun(run) {
    if (!run || !run.run_id) return;
    const existing = S().store.get().recentRuns || [];
    S().store.set({ recentRuns: [run, ...existing.filter((item) => item.run_id !== run.run_id)].slice(0, 50),
      selectionMode: 'runs' });
  }

  async function refreshRecentRuns() {
    const sequence = loadSequence;
    try {
      const listed = requireOk(await S().api.listRecentRuns());
      if (sequence !== loadSequence) return;
      S().store.set({ recentRuns: listed.runs || [] });
      S().modelCenter.render();
    } catch (err) { if (sequence === loadSequence) S().stateViews.notifyError(err); }
  }

  // ---------------------------------------------------------------- 工具栏动作
  const main = {
    leaveWorkspace: () => {
      ++bootstrapSequence;
      ++loadSequence;
      booting = false;
      S().runWorkspace.clear();
      S().runTimeline.close();
      ['selNewSelectionModal', 'selectionWizardModal', 'selectionTextDraftModal',
        'selectionVersionModal', 'selectionScheduleModal', 'selectionDebugModal',
        'selectionDataHealthModal'].forEach((id) => DOM().getElementById(id)?.remove());
      S().store.set({ selectionMode: 'runs', activeModelId: null, detail: null,
        workingDefinition: null, dirty: false, draftBaseVersion: null, draftRevision: 0,
        activeRunId: null, nodes: [], candidates: [], versions: [], runs: [], results: [],
        schedule: null, dataHealth: null, detailLoading: false, loading: false });
      renderMode();
      showWorkbenchView('run');
    },
    switchMode,
    openRun,
    openNewSelection,
    closeNewSelection,
    runNewSelection,
    editSelectedModel: () => {
      switchMode('models');
      if (S().store.get().selectionMode !== 'models') return;
      if (S().store.get().detail && !S().store.get().detail.draft) {
        global.showToast && global.showToast('先在版本管理中把已发布版本复制到草稿，再修改参数并发布新版本');
        S().versionManager.open();
      }
    },
    openWizard: () => S().wizard.open(),
    openTextDraft: () => S().textDraft.open(),
    openVersions: () => S().versionManager.open(),
    openDebug: () => S().debugPanel.open(),
    openSchedule: () => S().scheduler.open(),
    openDataHealth: () => S().dataHealth.open(),
    openRunTimeline: () => S().runTimeline.open(),
    showWorkbenchView,
    refresh: () => { if (S().store.confirmDiscard()) bootstrap(); },
    saveDraft: () => {
      const def = S().store.get().workingDefinition;
      if (!def) { global.showToast && global.showToast('无可保存的定义'); return; }
      if (def.model.model_type === 'condition_tree') S().conditionEditor.save();
      else S().funnelEditor.save();
    },
    validate: async () => {
      const id = S().store.get().activeModelId;
      if (!id) { global.showToast && global.showToast('请先选择模型'); return; }
      try {
        const resp = await S().api.validate(id, S().store.get().workingDefinition);
        if (resp.status === 'ok') global.showToast && global.showToast(`校验通过 · ${resp.data.plan_hash.slice(0, 16)}…`);
        else global.showToast && global.showToast(S().stateViews.message(resp));
      } catch (err) {
        global.showToast && global.showToast(S().stateViews.message(err));
      }
    },
    publish: () => S().versionManager.publish(),
    createRun: async () => {
      const workspaceToken = bootstrapSequence;
      const current = (S().store.get().recentRuns || []).find((item) => item.run_id === S().store.get().activeRunId);
      if (!current) { global.showToast && global.showToast('请先选择选股记录，或点击“新建选股”'); return; }
      try {
        const resp = await S().api.createRun(current.model_id, { version: current.model_version, all_market: true });
        if (workspaceToken !== bootstrapSequence) return;
        if (resp.status !== 'ok') { global.showToast && global.showToast(S().stateViews.message(resp)); return; }
        global.showToast && global.showToast(`运行结束：${resp.data.run.status}（入选 ${resp.data.selected_codes.length}）`);
        rememberRun(resp.data.run);
        await loadDetail(current.model_id, resp.data.run_id);
        if (workspaceToken !== bootstrapSequence) return;
        refreshRecentRuns();
        showWorkbenchView('run');
      } catch (err) {
        if (workspaceToken === bootstrapSequence) global.showToast && global.showToast(S().stateViews.message(err));
      }
    },
    exportResults: () => S().runWorkspace.exportCurrent(),
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

})(window);
