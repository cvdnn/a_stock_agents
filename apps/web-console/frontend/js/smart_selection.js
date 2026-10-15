// 智能选股独立工作区：只展示已持久化的漏斗模型、运行和阶段证据。
(function (global) {
  'use strict';

  const BASE = '/api/selection-models';
  let pageSize = 10;
  const el = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value == null ? '' : value).replace(/[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const shown = (value) => value == null || value === '' ? '未记录' : String(value);
  let bound = false;
  let generation = 0;
  let searchTimer = null;
  let models = [];
  let runs = [];
  let run = null;
  let nodes = [];
  let stage = null;
  let offset = 0;
  let total = 0;
  let currentTab = 'runs';
  let currentModelId = null;
  let versionDefinition = null;
  let logReturnFocus = null;
  let analysisReturnFocus = null;
  let selectedModel = null;
  let versions = [];
  let schedule = null;
  let listPermissions = {};
  let dirty = false;
  let savedDraftText = '';
  let overviewLoading = false;
  let pendingMutation = false;
  let creatingModel = false;
  let startingRun = false;

  async function request(path, method = 'GET', body) {
    const options = method === 'GET' ? undefined : { method, body: JSON.stringify(body || {}) };
    let response;
    try { response = await global.AStockAPI._fetchJSON(BASE + path, options); }
    catch (error) {
      const detail = error?.detail?.detail;
      throw new Error(typeof detail === 'object' ? detail.message || '智能选股请求被拒绝' : detail || error.message);
    }
    if (!response || response.status !== 'ok') {
      throw new Error(response?.message || response?.error?.message || '智能选股数据读取失败');
    }
    return response.data || {};
  }
  const get = (path) => request(path);
  function text(id, value) { if (el(id)) el(id).textContent = value; }
  function message(value) {
    const notice = el('issMessage');
    if (!notice) return;
    notice.textContent = value || '';
    notice.hidden = !value;
  }
  function skeleton(id, kind = 'list') {
    const bar = '<span class="iss-skeleton-bar"></span>';
    const lines = `<span class="iss-skeleton-lines">${bar}${bar}${bar}</span>`;
    if (kind === 'table') {
      el(id).innerHTML = Array.from({ length: 6 }, () => `<tr aria-hidden="true">${Array.from({ length: 6 }, () => `<td>${bar}</td>`).join('')}</tr>`).join('');
      return;
    }
    const item = kind === 'funnel'
      ? `<div class="iss-skeleton-stage"><span class="iss-skeleton-dot"></span><span class="iss-skeleton-shape"></span>${lines}</div>`
      : `<div class="iss-skeleton-item">${lines}</div>`;
    el(id).innerHTML = `<div class="iss-skeleton" role="status" aria-label="正在加载"><span class="iss-loading-sr">正在加载</span><div aria-hidden="true">${item.repeat(kind === 'header' ? 1 : 4)}</div></div>`;
  }
  function skeletonRun() {
    skeleton('issRunMeta', 'header');
    text('issRunStatus', '加载中');
    text('issStageCount', '');
    text('issStageLabel', '');
    skeleton('issStages', 'funnel');
    skeleton('issCandidates', 'table');
  }
  function active(token) {
    return token === generation && el('pane-intelligent_selection')?.classList.contains('active');
  }
  function confirmDiscard() {
    if (pendingMutation || creatingModel || startingRun) { message('操作正在提交，请稍候。'); return false; }
    return !dirty || global.confirm('当前模型有未保存的草稿修改。放弃修改并继续吗？');
  }
  function setTab(which) {
    const changed = which !== currentTab;
    if (changed && !confirmDiscard()) return false;
    if (changed) {
      ++generation;
      message('');
      if (el('issModelDetail').querySelector('.iss-skeleton')) text('issModelDetail', '选择模型查看草稿、版本与调度。');
      dirty = false;
      if (selectedModel?.draft) {
        savedDraftText = JSON.stringify(selectedModel.draft.definition, null, 2);
        el('issDraftEditor').value = savedDraftText;
        el('issPublish').disabled = !selectedModel.permissions?.publish;
      }
    }
    currentTab = which;
    const isRuns = which === 'runs';
    el('issRunsPanel').hidden = !isRuns;
    el('issModelsPanel').hidden = isRuns;
    for (const [id, selected] of [['issTabRuns', isRuns], ['issTabModels', !isRuns]]) {
      el(id).classList.toggle('active', selected);
      el(id).setAttribute('aria-selected', String(selected));
      el(id).tabIndex = selected ? 0 : -1;
    }
    if (changed && !isRuns) clearRun();
    if (overviewLoading && changed) refresh();
    else if (changed && isRuns) {
      const latest = runs.find((item) => item.model_id === currentModelId) || runs[0];
      if (latest) selectRun(latest.run_id);
    }
    return true;
  }
  function clearRun() {
    closeAnalysis(false);
    run = null; nodes = []; stage = null; offset = 0; total = 0;
    versionDefinition = null;
    text('issContextModel', shown(models.find((model) => model.model_id === currentModelId)?.name || '选择模型实例'));
    text('issRunStatus', '未选择运行');
    el('issRunStatus').className = 'sel-status-badge status-pending';
    el('issStop').hidden = true;
    text('issRunMeta', '请选择一次运行记录查看逐层证据。');
    text('issStageCount', '尚无阶段');
    text('issStageLabel', '未选择阶段');
    text('issDataMeta', '数据来源与快照未记录');
    text('issTotal', '共 — 条');
    text('issPage', '—');
    el('issStages').innerHTML = '<p class="iss-empty">请先选择运行记录。</p>';
    el('issEvidence').textContent = '';
    el('issCandidates').innerHTML = '<tr><td colspan="6">请先选择运行与阶段。</td></tr>';
    el('issPageButtons').innerHTML = '';
    el('issPrev').disabled = true;
    el('issNext').disabled = true;
    el('issExport').disabled = true;
    el('issViewLog').disabled = true;
    renderInstanceList();
  }
  const countText = (value) => Number.isFinite(Number(value)) && value !== null && value !== ''
    ? Number(value).toLocaleString('zh-CN') : '未记录';
  const priceText = (value) => value == null || value === '' || !Number.isFinite(Number(value))
    ? '未记录' : Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function briefTime(value) {
    if (!value) return '未记录';
    const match = String(value).match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
    return match ? `${match[1]} ${match[2]}` : String(value);
  }
  const statusText = (value) => ({ RUNNING: '运行中', COMPLETED: '已完成', BLOCKED: '已阻断',
    WAITING_DATA: '等待数据', FAILED: '运行失败', SKIPPED: '已停用', PASSED: '已通过',
    PARTIAL: '部分完成' }[value] || shown(value));
  function renderInstanceList() {
    const container = el('issInstanceList');
    if (!container) return;
    el('issAddModel').hidden = !listPermissions.run;
    container.innerHTML = models.length ? models.map((model) => {
      const latest = runs.find((item) => item.model_id === model.model_id);
      const selected = currentModelId === model.model_id;
      const stateClass = latest?.status === 'RUNNING' ? 'running' : ['FAILED', 'BLOCKED'].includes(latest?.status) ? 'error' : latest ? 'done' : 'pending';
      return `<button type="button" class="sel-model-card ${selected ? 'active' : ''}" data-instance-id="${escapeHtml(model.model_id)}" aria-pressed="${selected}">
        <span class="sel-model-card-top"><strong class="sel-model-name">${escapeHtml(shown(model.name))}</strong><span class="sel-status-dot status-${stateClass}" aria-hidden="true"></span></span>
        <span class="iss-model-state-label">${escapeHtml(latest ? statusText(latest.status) : '近期无运行')}</span>
        <span class="sel-model-foot"><small class="sel-model-time">更新于 ${escapeHtml(briefTime(model.updated_at))}</small><span class="sel-model-arrow" aria-hidden="true">›</span></span></button>`;
    }).join('') : '<p class="iss-empty">尚无漏斗模型。</p>';
    container.querySelectorAll('[data-instance-id]').forEach((button) =>
      button.addEventListener('click', () => chooseInstance(button.dataset.instanceId)));
  }
  function chooseInstance(id) {
    if (!models.some((item) => item.model_id === id)) return;
    currentModelId = id;
    renderInstanceList();
    const latest = runs.find((item) => item.model_id === id);
    if (latest) selectRun(latest.run_id);
    else { ++generation; clearRun(); text('issRunMeta', '最近 200 条运行记录中没有该模型的记录。'); message(''); }
  }
  function stageRuleSummary(node) {
    const stages = versionDefinition?.stages;
    const configured = (Array.isArray(stages) ? stages : []).find((item) => item.id === node.stage_id);
    if (!configured) return '未记录';
    const rules = Array.isArray(configured.rules) ? configured.rules : [];
    const ruleLibrary = global.SelModels?.ruleLibrary;
    return rules.length ? rules.map((rule) => ruleLibrary?.chip(rule)?.label || '规则名称未记录').join('、') : '未记录';
  }
  function renderModels() {
    text('issModelCount', `${models.length} 个漏斗模型`);
    el('issCreateForm').hidden = !listPermissions.create;
    el('issModelList').innerHTML = models.length ? models.map((model) =>
      `<button type="button" class="iss-model-item" data-model-id="${escapeHtml(model.model_id)}"><strong>${escapeHtml(shown(model.name))}</strong><small>${escapeHtml(shown(model.status))} · ${escapeHtml(shown(model.updated_at))}</small></button>`).join('')
      : '<p class="iss-empty">尚无漏斗模型。</p>';
    el('issModelList').querySelectorAll('[data-model-id]').forEach((button) => {
      button.addEventListener('click', () => showModel(button.dataset.modelId));
    });
    renderInstanceList();
  }
  async function showModel(id) {
    if (!confirmDiscard()) return;
    const token = ++generation;
    if (selectedModel?.model_id !== id) clearRun();
    dirty = false;
    selectedModel = null;
    versions = [];
    schedule = null;
    el('issModelControls').hidden = true;
    message('');
    skeleton('issModelDetail');
    try {
      const path = `/${encodeURIComponent(id)}`;
      const [model, versionData, scheduleData] = await Promise.all([
        get(path), get(path + '/versions'), get(path + '/schedule'),
      ]);
      if (!active(token) || currentTab !== 'models') return;
      if (model.model_type !== 'funnel' || model.model_id !== id) throw new Error('模型类型或归属不匹配');
      currentModelId = id;
      selectedModel = model;
      versions = versionData.versions || [];
      schedule = scheduleData;
      el('issModelDetail').innerHTML = `<h4>${escapeHtml(shown(model.name))}</h4>
        <p>模型 ID：${escapeHtml(id)}</p><p>类型：漏斗</p>
        <p>状态：${escapeHtml(shown(model.status))}</p>
        <p>活动版本：${escapeHtml(shown(model.active_version))}</p>
        <p>更新：${escapeHtml(shown(model.updated_at))}</p>`;
      renderModelControls();
      el('issModelList').querySelectorAll('[data-model-id]').forEach((button) =>
        button.classList.toggle('active', button.dataset.modelId === id));
      message('');
    } catch (error) { if (active(token) && currentTab === 'models') { text('issModelDetail', '模型详情读取失败。'); message(error.message); } }
  }
  function renderModelControls() {
    const model = selectedModel;
    if (!model) return;
    const draft = model.draft;
    const permissions = model.permissions || {};
    el('issModelControls').hidden = false;
    savedDraftText = draft ? JSON.stringify(draft.definition, null, 2) : '';
    el('issDraftEditor').value = savedDraftText;
    el('issDraftEditor').disabled = !draft || !permissions.edit;
    text('issDraftRevision', draft ? `修订 ${draft.draft_revision} · 基线 ${shown(draft.base_version)}` : '无草稿；可从已发布版本复制');
    el('issValidate').disabled = !draft;
    el('issSaveDraft').hidden = !permissions.edit;
    el('issSaveDraft').disabled = !draft || !permissions.edit;
    el('issPublish').hidden = !permissions.publish;
    el('issPublish').disabled = !draft || !permissions.publish || dirty;
    el('issVersions').innerHTML = versions.length ? versions.map((item) => {
      const version = Number(item.version);
      return `<div class="iss-version"><span>v${version} · ${escapeHtml(shown(item.status))} · ${escapeHtml(shown(item.published_at))}</span>
        ${permissions.edit ? `<button type="button" data-copy-version="${version}">复制为草稿</button>` : ''}
        ${permissions.activate ? `<button type="button" data-activate-version="${version}" ${item.status !== 'ARCHIVED' && model.active_version !== version ? '' : 'disabled'}>激活</button>` : ''}</div>`;
    }).join('') : '<p class="iss-empty">尚无已发布版本。</p>';
    const daemon = schedule?.daemon || {};
    const canSchedule = !!permissions.schedule_admin && schedule?.active_version != null;
    el('issSchedule').innerHTML = `<p>计划：${schedule?.paused ? '已暂停' : '未暂停'} · 守护进程：${daemon.online ? '在线' : '离线或未启动'} · 下次窗口：${escapeHtml(shown(schedule?.next_run_at))}</p>
      <p>最后 Tick：${escapeHtml(shown(daemon.last_tick_at))} · 异常：${escapeHtml(shown(daemon.last_error || daemon.reason_code || schedule?.configuration_error))}</p>
      <div class="iss-schedule-windows">${(schedule?.windows || []).map((window) => `<label>${escapeHtml(window.stage_id)}
        <input data-iss-window="${escapeHtml(window.stage_id)}" value="${escapeHtml(schedule?.overrides?.[window.stage_id] || `${window.start}-${window.end}`)}" ${canSchedule ? '' : 'disabled'}></label>`).join('') || '<span class="iss-empty">无时间窗</span>'}</div>
      ${permissions.schedule_admin ? `<div class="iss-model-actions"><button type="button" id="issScheduleSave" ${canSchedule ? '' : 'disabled'}>保存时间窗</button>
      <button type="button" id="issSchedulePause" ${canSchedule ? '' : 'disabled'}>${schedule?.paused ? '恢复自动调度' : '暂停自动调度'}</button></div>` : ''}`;
    el('issVersions').querySelectorAll('[data-copy-version]').forEach((button) =>
      button.addEventListener('click', () => copyVersion(Number(button.dataset.copyVersion))));
    el('issVersions').querySelectorAll('[data-activate-version]').forEach((button) =>
      button.addEventListener('click', () => activateVersion(Number(button.dataset.activateVersion))));
    el('issScheduleSave')?.addEventListener('click', saveSchedule);
    el('issSchedulePause')?.addEventListener('click', toggleSchedule);
  }
  function draftDefinition() {
    try {
      const value = JSON.parse(el('issDraftEditor').value);
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
      return value;
    } catch (_) { throw new Error('草稿定义必须是 JSON 对象'); }
  }
  async function modelAction(work) {
    const id = selectedModel?.model_id;
    const token = generation;
    if (!id || currentTab !== 'models' || pendingMutation) return;
    pendingMutation = true;
    let reloaded = false;
    const controls = [...el('issModelControls').querySelectorAll('button, textarea, input')].map((element) => [element, element.disabled]);
    controls.forEach(([element]) => { element.disabled = true; });
    try {
      const result = await work(id);
      if (token !== generation || currentTab !== 'models' || selectedModel?.model_id !== id) return;
      dirty = false;
      pendingMutation = false;
      await showModel(id);
      reloaded = true;
      if (result && active(generation)) message(result);
    } catch (error) { if (token === generation && currentTab === 'models') message(error.message); }
    finally {
      pendingMutation = false;
      if (!reloaded) controls.forEach(([element, wasDisabled]) => { if (element.isConnected) element.disabled = wasDisabled; });
    }
  }
  async function createModel(event) {
    event.preventDefault();
    const name = el('issCreateName').value.trim();
    if (!name || !confirmDiscard()) return;
    const token = generation;
    creatingModel = true;
    const button = el('issCreateForm').querySelector('button');
    button.disabled = true;
    try {
      const created = await request('', 'POST', { model_type: 'funnel', name, template: 'blank' });
      if (token !== generation || currentTab !== 'models') return;
      dirty = false;
      creatingModel = false;
      el('issCreateName').value = '';
      currentModelId = created.model_id;
      await refresh();
      await showModel(created.model_id);
    } catch (error) { if (token === generation) message(error.message); }
    finally { creatingModel = false; button.disabled = false; }
  }
  async function validateDraft() {
    const id = selectedModel?.model_id;
    const token = generation;
    if (!id || !selectedModel.draft) return;
    try {
      const result = await request(`/${encodeURIComponent(id)}/validate`, 'POST', { definition: draftDefinition() });
      if (token === generation && selectedModel?.model_id === id) message(`校验通过：${shown(result.stage_count)} 个阶段，计划 ${shown(result.plan_hash)}`);
    } catch (error) { if (token === generation) message(error.message); }
  }
  function saveDraft() {
    if (!selectedModel?.draft || !selectedModel.permissions?.edit) return;
    let definition;
    try { definition = draftDefinition(); } catch (error) { message(error.message); return; }
    const draft = selectedModel.draft;
    modelAction(async (id) => {
      const saved = await request(`/${encodeURIComponent(id)}/draft`, 'PATCH', {
        definition, base_version: draft.base_version, draft_revision: draft.draft_revision,
      });
      return `草稿已保存，修订 ${saved.draft_revision}`;
    });
  }
  function publishDraft() {
    if (!selectedModel?.draft || !selectedModel.permissions?.publish || dirty) return;
    const draft = selectedModel.draft;
    modelAction(async (id) => {
      const published = await request(`/${encodeURIComponent(id)}/versions`, 'POST', {
        base_version: draft.base_version, draft_revision: draft.draft_revision,
      });
      return `已发布 v${published.version}；激活后才会进入自动调度。`;
    });
  }
  function copyVersion(version) {
    if (!selectedModel?.permissions?.edit || !confirmDiscard()) return;
    if (selectedModel.draft && !global.confirm(`复制 v${version} 将覆盖当前已保存草稿。继续吗？`)) return;
    const revision = selectedModel.draft?.draft_revision;
    modelAction(async (id) => {
      await request(`/${encodeURIComponent(id)}/versions/${version}/copy-to-draft`, 'POST', { draft_revision: revision });
      return `v${version} 已复制为草稿。`;
    });
  }
  function activateVersion(version) {
    if (!selectedModel?.permissions?.activate || !confirmDiscard()) return;
    modelAction(async (id) => {
      await request(`/${encodeURIComponent(id)}/activate/${version}`, 'POST');
      return `已激活 v${version}。`;
    });
  }
  function saveSchedule() {
    if (!selectedModel?.permissions?.schedule_admin || schedule?.active_version == null || !confirmDiscard()) return;
    const stages = {};
    el('issSchedule').querySelectorAll('[data-iss-window]').forEach((input) => {
      stages[input.dataset.issWindow] = input.value.trim();
    });
    modelAction(async (id) => {
      await request(`/${encodeURIComponent(id)}/schedule`, 'PUT', { stages, paused: !!schedule.paused });
      return '调度时间窗已保存。';
    });
  }
  function toggleSchedule() {
    if (!selectedModel?.permissions?.schedule_admin || schedule?.active_version == null || !confirmDiscard()) return;
    const paused = !!schedule.paused;
    modelAction(async (id) => {
      await request(`/${encodeURIComponent(id)}/${paused ? 'resume' : 'pause'}`, 'POST');
      return paused ? '自动调度已恢复。' : '自动调度已暂停。';
    });
  }
  async function refresh() {
    if (!confirmDiscard()) return;
    const token = ++generation;
    overviewLoading = true;
    dirty = false;
    const previousRunId = run?.run_id;
    const previousModelId = currentModelId;
    const previousDetailId = selectedModel?.model_id;
    selectedModel = null;
    versions = [];
    schedule = null;
    message('');
    clearRun();
    skeletonRun();
    skeleton('issInstanceList');
    el('issModelControls').hidden = true;
    text('issModelDetail', '选择模型查看草稿、版本与调度。');
    skeleton('issModelList');
    try {
      const [modelData, runData] = await Promise.all([get('?model_type=funnel'), get('/runs?limit=200')]);
      if (!active(token)) return;
      models = (modelData.models || []).filter((model) => model.model_type === 'funnel');
      listPermissions = modelData.permissions || {};
      const ids = new Set(models.map((model) => model.model_id));
      runs = (runData.runs || []).filter((item) => ids.has(item.model_id))
        .sort((a, b) => {
          const started = String(b.started_at || b.created_at || '').localeCompare(String(a.started_at || a.created_at || ''));
          return started || String(b.run_id || '').localeCompare(String(a.run_id || ''));
        });
      currentModelId = ids.has(previousModelId) ? previousModelId : runs[0]?.model_id || models[0]?.model_id || null;
      renderModels();
      if (!runs.length) message('最近 200 条运行中没有可显示的漏斗记录；完整类型分页待服务端支持。');
      overviewLoading = false;
      const chosen = runs.find((item) => item.run_id === previousRunId) || runs.find((item) => item.model_id === currentModelId);
      if (currentTab === 'runs' && chosen) await selectRun(chosen.run_id);
      else if (currentTab === 'models' && ids.has(previousDetailId)) { clearRun(); await showModel(previousDetailId); }
      else { clearRun(); if (runs.length) message(''); }
    } catch (error) { if (active(token)) { models = []; runs = []; currentModelId = null; listPermissions = {}; clearRun(); renderModels(); message(error.message); } }
    finally { if (token === generation) overviewLoading = false; }
  }
  function renderStages() {
    const configured = Array.isArray(versionDefinition?.stages) ? versionDefinition.stages : [];
    const views = configured.length ? configured.map((item) => nodes.find((node) => node.stage_id === item.id)
      || { stage_id: item.id, name: item.name || item.id, status: 'NOT_RECORDED', notRecorded: true }) : nodes;
    text('issStageCount', `共 ${views.length} 层筛选`);
    el('issStages').innerHTML = views.length ? views.map((node, index) => {
      const selected = stage?.stage_id === node.stage_id;
      const pending = node.notRecorded || ['NOT_REACHED', 'PENDING', 'SKIPPED'].includes(node.status);
      const output = node.output_count;
      const ratio = Number(node.input_count) > 0 && output != null ? ` (${(100 * Number(output) / Number(node.input_count)).toFixed(1)}%)` : '';
      const widths = [[100, 86], [82, 69], [68, 57], [61, 52], [59, 49]];
      const [top, bottom] = widths[Math.min(index, widths.length - 1)];
      const inset = ((top - bottom) / top * 50).toFixed(1);
      const color = pending ? 'l5' : `l${index % 4 + 1}`;
      const ruleSummary = escapeHtml(stageRuleSummary(node));
      const runtimeSummary = `${node.notRecorded ? '未记录' : escapeHtml(statusText(node.status))} · ${escapeHtml(shown(node.completed_at))}`;
      return `<button type="button" class="funnel-row ${pending ? 'funnel-idle' : 'funnel-done'} ${selected ? 'selected' : ''}" ${node.notRecorded ? 'disabled title="该阶段没有运行记录"' : `data-stage-id="${escapeHtml(node.stage_id)}"`} aria-pressed="${selected}">
        <span class="funnel-index-col"><span class="funnel-index-dot">${index + 1}</span></span>
        <span class="funnel-row-body"><span class="funnel-shape-wrap"><span class="funnel-bar ${color}" style="width:${top}%;clip-path:polygon(0 0,100% 0,${100 - inset}% 100%,${inset}% 100%)"><span class="funnel-bar-name" title="${escapeHtml(shown(node.name || node.stage_id))}">${escapeHtml(shown(node.name || node.stage_id))}</span><span class="funnel-bar-val">${node.notRecorded ? '—' : escapeHtml(countText(node.input_count))}</span></span></span>
        <span class="funnel-info-panel"><span class="funnel-info-line"><span class="funnel-info-label">运行信息</span><span class="funnel-info-val" title="${runtimeSummary}">${runtimeSummary}</span></span>
        <span class="funnel-info-line"><span class="funnel-info-label">选股规则</span><span class="funnel-info-val" title="${ruleSummary}">${ruleSummary}</span></span>
        <span class="funnel-info-line"><span class="funnel-info-label">筛选后</span><span class="funnel-info-val strong">${node.notRecorded ? '未记录' : escapeHtml(countText(output) + ratio)}</span></span></span>${selected ? '<span class="funnel-row-arrow" aria-hidden="true">›</span>' : ''}</span></button>`;
    }).join('') : '<p class="iss-empty">该运行没有阶段记录。</p>';
    el('issStages').querySelectorAll('[data-stage-id]').forEach((button) =>
      button.addEventListener('click', () => selectStage(button.dataset.stageId)));
  }
  async function selectRun(id) {
    const selected = runs.find((item) => item.run_id === id);
    const token = ++generation;
    clearRun();
    if (!selected) return;
    currentModelId = selected.model_id;
    renderInstanceList();
    text('issContextModel', shown(models.find((model) => model.model_id === currentModelId)?.name));
    message('');
    skeletonRun();
    try {
      const [runData, nodeData] = await Promise.all([
        get(`/runs/${encodeURIComponent(id)}`), get(`/runs/${encodeURIComponent(id)}/nodes`),
      ]);
      if (!active(token) || currentTab !== 'runs') return;
      if (runData.run?.run_id !== id || runData.run.model_id !== selected.model_id || nodeData.run_id !== id) {
        throw new Error('运行归属不匹配');
      }
      run = runData.run;
      nodes = nodeData.nodes || [];
      text('issRunStatus', statusText(run.status));
      el('issRunStatus').className = `sel-status-badge status-${run.status === 'RUNNING' ? 'running' : ['FAILED', 'BLOCKED'].includes(run.status) ? 'error' : 'done'}`;
      el('issStop').hidden = run.status !== 'RUNNING';
      text('issRunMeta', `模型 ${shown(models.find((model) => model.model_id === run.model_id)?.name)} · 版本 ${shown(run.model_version)} · 运行 ${id}`);
      el('issViewLog').disabled = false;
      message('');
      if (run.model_version != null) {
        try {
          const version = await get(`/${encodeURIComponent(run.model_id)}/versions/${encodeURIComponent(run.model_version)}`);
          if (!active(token) || run?.run_id !== id) return;
          if (version.definition?.model?.id === run.model_id
              && Number(version.record?.version) === Number(run.model_version)
              && (!run.plan_hash || version.record?.plan_hash === run.plan_hash)) {
            versionDefinition = version.definition || null;
          }
        } catch (_) { /* 阶段规则读取失败时明确显示未记录，运行证据仍可查看。 */ }
      }
      if (!active(token) || run?.run_id !== id) return;
      if (nodes.length) await selectStage(nodes[0].stage_id);
      else { renderStages(); el('issCandidates').innerHTML = '<tr><td colspan="6">该运行没有阶段记录。</td></tr>'; }
    } catch (error) { if (active(token) && currentTab === 'runs') { clearRun(); message(error.message); } }
  }
  async function selectStage(id) {
    stage = nodes.find((item) => item.stage_id === id) || null;
    if (!stage || !run) return;
    closeAnalysis(false);
    offset = 0;
    el('issSearch').value = '';
    el('issVerdict').value = stage.status === 'SKIPPED' ? 'FORWARDED' : 'PASS';
    text('issStageLabel', `第 ${nodes.indexOf(stage) + 1} 层：${shown(stage.name || id)}`);
    const rejected = stage.result?.rejected_records || [];
    text('issEvidence', `阶段证据：输入 ${countText(stage.input_count)} · 通过 ${countText(stage.passed_count)} · 淘汰 ${countText(stage.rejected_count)} · 未知 ${countText(stage.unknown_count)} · 透传 ${countText(stage.forwarded_count)}；逐股淘汰依据 ${rejected.length} 条。`);
    renderStages();
    await loadCandidates();
  }
  function renderPageButtons() {
    const pageCount = Math.ceil(total / pageSize);
    if (!pageCount) { el('issPageButtons').innerHTML = ''; return; }
    const current = Math.floor(offset / pageSize) + 1;
    const visible = new Set([1, pageCount]);
    const start = current <= 4 ? 1 : current - 2;
    const end = current <= 4 ? Math.min(5, pageCount) : Math.min(pageCount, current + 2);
    for (let page = start; page <= end; page++) visible.add(page);
    let previous = 0;
    el('issPageButtons').innerHTML = [...visible].filter((page) => page > 0).sort((a, b) => a - b).map((page) => {
      const gap = page - previous > 1 ? '<span class="iss-page-ellipsis" aria-hidden="true">…</span>' : '';
      previous = page;
      return `${gap}<button type="button" data-page="${page}" class="${page === current ? 'current' : ''}" ${page === current ? 'aria-current="page"' : ''} aria-label="第 ${page} 页">${page}</button>`;
    }).join('');
    el('issPageButtons').querySelectorAll('[data-page]').forEach((button) => button.addEventListener('click', () => {
      const nextOffset = (Number(button.dataset.page) - 1) * pageSize;
      if (nextOffset !== offset) { offset = nextOffset; loadCandidates(); }
    }));
  }
  async function loadCandidates() {
    if (!run || !stage) return;
    closeAnalysis(false);
    const token = ++generation;
    const id = run.run_id;
    const stageId = stage.stage_id;
    const params = new URLSearchParams({ stage_id: stageId, limit: String(pageSize), offset: String(offset) });
    if (el('issSearch').value.trim()) params.set('keyword', el('issSearch').value.trim());
    if (el('issVerdict').value) params.set('verdict', el('issVerdict').value);
    message('');
    skeleton('issCandidates', 'table');
    el('issPrev').disabled = true;
    el('issNext').disabled = true;
    el('issExport').disabled = true;
    try {
      const data = await get(`/runs/${encodeURIComponent(id)}/candidates?${params}`);
      if (!active(token) || currentTab !== 'runs' || run?.run_id !== id || stage?.stage_id !== stageId) return;
      if (data.run_id !== id || data.stage_id !== stageId) throw new Error('候选归属不匹配');
      total = Number(data.total) || 0;
      text('issTotal', `共 ${total} 条`);
      text('issPage', `${total ? offset + 1 : 0}–${Math.min(offset + pageSize, total)} / ${total}`);
      text('issDataMeta', `来源 ${shown(data.source)} · 数据时点 ${shown(data.as_of)} · 快照 ${shown(data.data_snapshot_id)}`);
      el('issPrev').disabled = offset === 0;
      el('issNext').disabled = offset + pageSize >= total;
      renderPageButtons();
      el('issExport').disabled = false;
       const candidates = data.candidates || [];
       el('issCandidates').innerHTML = candidates.length ? candidates.map((item, index) => {
        const change = item.change_pct == null || item.change_pct === '' ? null : Number(item.change_pct);
        const changeText = change == null || !Number.isFinite(change) ? '未记录' : `${change > 0 ? '+' : ''}${change.toFixed(2)}%`;
         return `<tr><td>${offset + index + 1}</td><td><button type="button" class="iss-stock-code" data-candidate-index="${index}" aria-expanded="false" aria-controls="issAnalysis" aria-label="查看 ${escapeHtml(shown(item.code))} 的分析信息">${escapeHtml(shown(item.code))}</button></td><td class="sel-name-cell">${escapeHtml(shown(item.name))}</td><td class="num">${escapeHtml(priceText(item.price))}</td>
           <td class="num ${change > 0 ? 'iss-up' : change < 0 ? 'iss-down' : ''}">${escapeHtml(changeText)}</td><td>${escapeHtml(shown(item.industry))}</td></tr>`;
       }).join('') : '<tr><td colspan="6">当前筛选无候选。</td></tr>';
       el('issCandidates').querySelectorAll('[data-candidate-index]').forEach((button) =>
         button.closest('tr').addEventListener('click', () => showAnalysis(candidates[Number(button.dataset.candidateIndex)], button)));
      message('');
    } catch (error) { if (active(token) && currentTab === 'runs') { message(error.message); el('issCandidates').innerHTML = '<tr><td colspan="6">读取失败。</td></tr>'; } }
  }
  function closeAnalysis(restoreFocus = true) {
    const panel = el('issAnalysis');
    if (!panel) return;
    panel.classList.add('collapsed');
    panel.setAttribute('aria-hidden', 'true');
    panel.inert = true;
    el('issModelCol')?.classList.remove('collapsed');
    if (el('issModelCol')) el('issModelCol').inert = false;
    el('issCandidates')?.querySelectorAll('[data-candidate-index]').forEach((button) =>
      button.setAttribute('aria-expanded', 'false'));
    if (restoreFocus && analysisReturnFocus?.isConnected) analysisReturnFocus.focus();
    analysisReturnFocus = null;
  }
  function showAnalysis(item, button) {
    if (!item || !run || !stage) return;
    analysisReturnFocus = button;
    const change = item.change_pct == null || item.change_pct === '' ? null : Number(item.change_pct);
    const changeText = change == null || !Number.isFinite(change) ? '未记录' : `${change > 0 ? '+' : ''}${change.toFixed(2)}%`;
    const verdict = { PASS: '通过', FAIL: '淘汰', UNKNOWN: '未知', FORWARDED: '透传' }[item.verdict] || shown(item.verdict);
    const failed = (item.failed_rules || []).filter(Boolean).join('、') || '未记录';
    const unknown = (item.unknown_rules || []).filter(Boolean).join('、') || '未记录';
    const missing = Object.entries(item.missing_reasons || {}).map(([field, reason]) =>
      `<li><strong>${escapeHtml(field)}</strong>：${escapeHtml(shown(reason))}</li>`).join('');
    el('issAnalysisContent').innerHTML = `<div class="sel-stock-head"><div class="sel-stock-name-row"><strong class="sel-stock-name">${escapeHtml(shown(item.name))}</strong><span class="sel-stock-code">${escapeHtml(shown(item.code))}</span></div><button type="button" class="sel-add-watch" disabled title="当前工作台尚未接入自选写入">＋ 自选</button></div>
      <div class="sel-stock-tags"><span class="sel-tag-pill">${escapeHtml(shown(item.industry))}</span><span class="sel-tag-pill">${escapeHtml(verdict)}</span></div>
      <div class="sel-stock-price-row"><div class="sel-stock-price-col"><div class="sel-stock-price-line"><strong class="sel-stock-price ${change > 0 ? 'text-up' : change < 0 ? 'text-down' : ''}">${escapeHtml(priceText(item.price))}</strong><span class="sel-stock-delta ${change > 0 ? 'text-up' : change < 0 ? 'text-down' : ''}">${escapeHtml(changeText)}</span></div><div class="sel-stock-updatetime">价格时点：${escapeHtml(shown(item.price_as_of))}</div></div><div class="sel-score-box iss-score-unrecorded"><span class="sel-score-label">综合评分</span><strong class="sel-score-val">—</strong><span class="sel-score-grade">未记录</span></div></div>
      <div class="sel-analysis-tabs" aria-label="分析分类"><button type="button" class="sel-tab active">综合分析</button><button type="button" class="sel-tab" disabled>基本面</button><button type="button" class="sel-tab" disabled>技术面</button><button type="button" class="sel-tab" disabled>估值分析</button><button type="button" class="sel-tab" disabled>资金面</button></div>
      <div class="sel-price-chart-block"><div class="sel-chart-head"><span class="sel-chart-title">价格走势</span><span class="sel-period-switch"><button type="button" class="sel-period" disabled>5日</button><button type="button" class="sel-period" disabled>20日</button><button type="button" class="sel-period" disabled>60日</button><button type="button" class="sel-period" disabled>120日</button></span></div><div class="iss-chart-empty">未记录连续价格数据，无法生成可追溯走势。</div></div>
      <div class="sel-analysis-body"><section class="sel-block"><h4 class="sel-block-title">筛选依据</h4><p class="sel-block-text">${escapeHtml(shown(stage.name || stage.stage_id))} · ${escapeHtml(verdict)}</p><p class="sel-block-text">未通过规则：${escapeHtml(failed)}；未知规则：${escapeHtml(unknown)}</p></section>
      <section class="sel-block"><h4 class="sel-block-title">数据来源</h4><p class="sel-block-text">数据时点：${escapeHtml(shown(item.as_of))}<br>来源：${escapeHtml(shown(item.source))}<br>快照：${escapeHtml(shown(item.data_snapshot_id))}</p></section>
      <section class="sel-block"><h4 class="sel-block-title">基本面与技术面摘要</h4><p class="sel-block-text">未记录；当前运行没有保存可核查的分析文本。</p></section>
      ${missing ? `<section class="sel-block"><h4 class="sel-block-title">未记录字段</h4><ul class="iss-missing-list">${missing}</ul></section>` : ''}</div>`;
    el('issCandidates').querySelectorAll('[data-candidate-index]').forEach((candidateButton) =>
      candidateButton.setAttribute('aria-expanded', String(candidateButton === button)));
    el('issAnalysis').classList.remove('collapsed');
    el('issAnalysis').setAttribute('aria-hidden', 'false');
    el('issAnalysis').inert = false;
    el('issModelCol').classList.add('collapsed');
    el('issModelCol').inert = true;
    el('issCloseAnalysis').focus();
  }
  async function exportCurrent() {
    if (!run || !stage || currentTab !== 'runs') return;
    const token = generation;
    const id = run.run_id, stageId = stage.stage_id;
    const params = new URLSearchParams({ stage_id: stageId });
    if (el('issSearch').value.trim()) params.set('keyword', el('issSearch').value.trim());
    if (el('issVerdict').value) params.set('verdict', el('issVerdict').value);
    try {
      const response = await global.fetch(`${global.AStockAPI.baseUrl}${BASE}/runs/${encodeURIComponent(id)}/candidates/export?${params}`, { credentials: 'same-origin' });
      if (!response.ok || !String(response.headers.get('content-type') || '').includes('text/csv')) throw new Error('导出失败');
      const blob = await response.blob();
      if (!active(token) || currentTab !== 'runs' || run?.run_id !== id || stage?.stage_id !== stageId) return;
      const url = global.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `智能选股_${id}_${stageId}.csv`;
      link.click();
      global.setTimeout(() => global.URL.revokeObjectURL(url), 1000);
    } catch (error) { if (active(token) && currentTab === 'runs') message(error.message); }
  }
  function closeLog() {
    el('issLogDialog').hidden = true;
    logReturnFocus?.focus();
    logReturnFocus = null;
  }
  function viewLog() {
    if (!run || currentTab !== 'runs') return;
    logReturnFocus = document.activeElement;
    text('issLogTitle', `运行记录 · ${shown(run.run_id)}`);
    el('issLogContent').innerHTML = `<p class="iss-data-meta">仅显示已持久化的运行与阶段记录；逐行执行日志未记录。</p>
      <dl><dt>模型</dt><dd>${escapeHtml(shown(models.find((item) => item.model_id === run.model_id)?.name))}</dd>
      <dt>版本</dt><dd>${escapeHtml(shown(run.model_version))}</dd><dt>状态</dt><dd>${escapeHtml(statusText(run.status))}</dd>
      <dt>开始时间</dt><dd>${escapeHtml(shown(run.started_at))}</dd><dt>结束时间</dt><dd>${escapeHtml(shown(run.finished_at))}</dd>
      <dt>触发方式</dt><dd>${escapeHtml(shown(run.trigger_type))}</dd><dt>数据时点</dt><dd>${escapeHtml(shown(run.input_as_of))}</dd>
      <dt>快照</dt><dd>${escapeHtml(shown(run.data_snapshot_id))}</dd><dt>异常</dt><dd>${escapeHtml(shown(run.error))}</dd></dl>
      <h4>阶段记录</h4><ol>${nodes.map((item) => `<li>${escapeHtml(shown(item.name || item.stage_id))} · ${escapeHtml(statusText(item.status))} · 输入 ${escapeHtml(countText(item.input_count))} → 输出 ${escapeHtml(countText(item.output_count))} · ${escapeHtml(shown(item.completed_at))}</li>`).join('') || '<li>未记录阶段。</li>'}</ol>`;
    el('issLogDialog').hidden = false;
    el('issCloseLog').focus();
  }
  function closeNewRun() {
    if (startingRun) return;
    el('issNewRunDialog').close();
    el('issAddModel').focus();
  }
  function openNewRun() {
    if (!listPermissions.run || !confirmDiscard()) return;
    const available = models.filter((model) => model.active_version != null && model.status !== 'ARCHIVED');
    el('issRunModel').innerHTML = available.length
      ? available.map((model) => `<option value="${escapeHtml(model.model_id)}">${escapeHtml(model.name || model.model_id)} · 版本 ${escapeHtml(model.active_version)}</option>`).join('')
      : '<option value="">暂无可运行模型</option>';
    if (available.some((model) => model.model_id === currentModelId)) el('issRunModel').value = currentModelId;
    el('issRunModel').disabled = !available.length;
    el('issStartRun').disabled = !available.length;
    text('issNewRunMessage', available.length ? '仅显示已激活的模型；数据不足时会显示具体原因。' : '暂无已激活的漏斗模型，请先在模型管理中发布并激活模型。');
    el('issNewRunDialog').showModal();
    el(available.length ? 'issRunModel' : 'issCancelNewRun').focus();
  }
  async function startRun(event) {
    event.preventDefault();
    if (startingRun || !listPermissions.run) return;
    const model = models.find((item) => item.model_id === el('issRunModel').value);
    if (!model || model.active_version == null) return;
    startingRun = true;
    for (const id of ['issStartRun', 'issRunModel', 'issCancelNewRun', 'issCloseNewRun']) el(id).disabled = true;
    text('issStartRun', '运行中…');
    text('issNewRunMessage', '正在执行选股，请稍候…');
    let result;
    try {
      result = await request(`/${encodeURIComponent(model.model_id)}/runs`, 'POST', {
        version: model.active_version, all_market: true,
      });
    } catch (error) {
      text('issNewRunMessage', error.message);
    } finally {
      startingRun = false;
      for (const id of ['issStartRun', 'issRunModel', 'issCancelNewRun', 'issCloseNewRun']) el(id).disabled = false;
      text('issStartRun', '开始运行');
    }
    if (!result) return;
    closeNewRun();
    currentModelId = model.model_id;
    run = null;
    await refresh();
    const runId = result.run_id || result.run?.run_id;
    if (runId && currentTab === 'runs' && el('pane-intelligent_selection')?.classList.contains('active')) await selectRun(runId);
  }
  function bind() {
    if (bound) return;
    bound = true;
    el('issTabRuns').addEventListener('click', () => setTab('runs'));
    el('issTabModels').addEventListener('click', () => setTab('models'));
    [el('issTabRuns'), el('issTabModels')].forEach((tab, index, tabs) => tab.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const target = tabs[event.key === 'ArrowRight' ? (index + 1) % tabs.length : (index + tabs.length - 1) % tabs.length];
      if (setTab(target === tabs[0] ? 'runs' : 'models')) target.focus();
    }));
    el('issRefresh').addEventListener('click', refresh);
    el('issAddModel').addEventListener('click', openNewRun);
    el('issNewRunForm').addEventListener('submit', startRun);
    el('issCloseNewRun').addEventListener('click', closeNewRun);
    el('issCancelNewRun').addEventListener('click', closeNewRun);
    el('issNewRunDialog').addEventListener('cancel', (event) => { event.preventDefault(); closeNewRun(); });
    el('issViewLog').addEventListener('click', viewLog);
    el('issCloseAnalysis').addEventListener('click', () => closeAnalysis());
    el('issAnalysis').addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { event.preventDefault(); closeAnalysis(); }
    });
    el('issCloseLog').addEventListener('click', closeLog);
    el('issLogDialog').addEventListener('click', (event) => { if (event.target === el('issLogDialog')) closeLog(); });
    el('issLogDialog').addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { event.preventDefault(); closeLog(); }
      if (event.key === 'Tab') { event.preventDefault(); el('issCloseLog').focus(); }
    });
    el('issCreateForm').addEventListener('submit', createModel);
    el('issDraftEditor').addEventListener('input', () => {
      dirty = el('issDraftEditor').value !== savedDraftText;
      el('issPublish').disabled = dirty || !selectedModel?.draft || !selectedModel.permissions?.publish;
    });
    el('issValidate').addEventListener('click', validateDraft);
    el('issSaveDraft').addEventListener('click', saveDraft);
    el('issPublish').addEventListener('click', publishDraft);
    global.addEventListener('beforeunload', (event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    });
    el('issExport').addEventListener('click', exportCurrent);
    el('issVerdict').addEventListener('change', () => { offset = 0; loadCandidates(); });
    el('issPageSize').addEventListener('change', (event) => { pageSize = Number(event.target.value) || 10; offset = 0; loadCandidates(); });
    el('issSearch').addEventListener('input', () => {
      if (searchTimer) global.clearTimeout(searchTimer);
      searchTimer = global.setTimeout(() => { offset = 0; loadCandidates(); }, 250);
    });
    el('issPrev').addEventListener('click', () => { if (offset >= pageSize) { offset -= pageSize; loadCandidates(); } });
    el('issNext').addEventListener('click', () => { if (offset + pageSize < total) { offset += pageSize; loadCandidates(); } });
  }
  global.SmartSelection = {
    bootstrap() { bind(); overviewLoading = false; setTab('runs'); refresh(); },
    refresh,
    confirmDiscard,
    leave() { ++generation; overviewLoading = false; if (searchTimer) global.clearTimeout(searchTimer); searchTimer = null; dirty = false; selectedModel = null; el('issLogDialog').hidden = true; clearRun(); message(''); },
  };
})(window);
