// 智能选股独立工作区：只展示已持久化的漏斗模型、运行和阶段证据。
(function (global) {
  'use strict';

  const BASE = '/api/selection-models';
  const PAGE_SIZE = 10;
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

  async function get(path) {
    const response = await global.AStockAPI._fetchJSON(BASE + path);
    if (!response || response.status !== 'ok') {
      throw new Error(response?.message || response?.error?.message || '智能选股数据读取失败');
    }
    return response.data || {};
  }
  function text(id, value) { if (el(id)) el(id).textContent = value; }
  function message(value) { text('issMessage', value || ''); }
  function active(token) {
    return token === generation && el('pane-intelligent_selection')?.classList.contains('active');
  }
  function setTab(which) {
    const isRuns = which === 'runs';
    el('issRunsPanel').hidden = !isRuns;
    el('issModelsPanel').hidden = isRuns;
    for (const [id, selected] of [['issTabRuns', isRuns], ['issTabModels', !isRuns]]) {
      el(id).classList.toggle('active', selected);
      el(id).setAttribute('aria-selected', String(selected));
    }
  }
  function clearRun() {
    run = null; nodes = []; stage = null; offset = 0; total = 0;
    text('issRunStatus', '未选择运行');
    text('issRunMeta', '请选择一次运行记录查看逐层证据。');
    text('issStageCount', '尚无阶段');
    text('issStageLabel', '未选择阶段');
    text('issDataMeta', '数据来源与快照未记录');
    text('issTotal', '共 — 条');
    text('issPage', '—');
    el('issStages').innerHTML = '<p class="iss-empty">请先选择运行记录。</p>';
    el('issEvidence').textContent = '';
    el('issCandidates').innerHTML = '<tr><td colspan="6">请先选择运行与阶段。</td></tr>';
    el('issPrev').disabled = true;
    el('issNext').disabled = true;
    el('issExport').disabled = true;
  }
  function renderModels() {
    text('issModelCount', `${models.length} 个漏斗模型`);
    el('issModelList').innerHTML = models.length ? models.map((model) =>
      `<button type="button" class="iss-model-item" data-model-id="${escapeHtml(model.model_id)}"><strong>${escapeHtml(shown(model.name))}</strong><small>${escapeHtml(shown(model.status))} · ${escapeHtml(shown(model.updated_at))}</small></button>`).join('')
      : '<p class="iss-empty">尚无漏斗模型。</p>';
    el('issModelList').querySelectorAll('[data-model-id]').forEach((button) => {
      button.addEventListener('click', () => showModel(button.dataset.modelId));
    });
  }
  async function showModel(id) {
    const token = ++generation;
    text('issModelDetail', '正在读取模型详情…');
    try {
      const data = await get(`/${encodeURIComponent(id)}`);
      if (!active(token)) return;
      const model = data;
      if (model.model_type !== 'funnel' || model.model_id !== id) throw new Error('模型类型或归属不匹配');
      el('issModelDetail').innerHTML = `<h4>${escapeHtml(shown(model.name))}</h4>
        <p>模型 ID：${escapeHtml(id)}</p><p>类型：漏斗</p>
        <p>状态：${escapeHtml(shown(model.status))}</p>
        <p>活动版本：${escapeHtml(shown(model.active_version))}</p>
        <p>更新：${escapeHtml(shown(model.updated_at))}</p>`;
      el('issModelList').querySelectorAll('[data-model-id]').forEach((button) =>
        button.classList.toggle('active', button.dataset.modelId === id));
    } catch (error) { if (active(token)) message(error.message); }
  }
  function renderRuns() {
    const select = el('issRunSelect');
    const oldValue = select.value;
    select.innerHTML = '<option value="">选择运行记录</option>' + runs.map((item) =>
      `<option value="${escapeHtml(item.run_id)}">${escapeHtml(shown(item.model_name || models.find((model) => model.model_id === item.model_id)?.name))} · ${escapeHtml(shown(item.status))} · ${escapeHtml(shown(item.started_at || item.created_at))}</option>`).join('');
    select.value = runs.some((item) => item.run_id === oldValue) ? oldValue : '';
    if (!runs.length) message('最近 200 条运行中没有可显示的漏斗记录；完整类型分页待服务端支持。');
  }
  async function refresh() {
    const token = ++generation;
    message('正在读取漏斗模型与运行记录…');
    clearRun();
    try {
      const [modelData, runData] = await Promise.all([get('?model_type=funnel'), get('/runs?limit=200')]);
      if (!active(token)) return;
      models = (modelData.models || []).filter((model) => model.model_type === 'funnel');
      const ids = new Set(models.map((model) => model.model_id));
      runs = (runData.runs || []).filter((item) => ids.has(item.model_id));
      renderModels();
      renderRuns();
      if (runs.length) message('');
    } catch (error) { if (active(token)) message(error.message); }
  }
  function renderStages() {
    text('issStageCount', `共 ${nodes.length} 层筛选`);
    el('issStages').innerHTML = nodes.length ? nodes.map((node, index) => {
      const selected = stage?.stage_id === node.stage_id;
      return `<button type="button" class="iss-stage ${selected ? 'active' : ''}" data-stage-id="${escapeHtml(node.stage_id)}" aria-pressed="${selected}">
        <span class="iss-stage-index">${index + 1}</span><span class="iss-stage-shape"><strong>${escapeHtml(shown(node.name || node.stage_id))}</strong><b>${escapeHtml(shown(node.input_count))}</b></span>
        <span class="iss-stage-detail"><span>运行信息　${escapeHtml(shown(node.status))}</span><span>筛选后　${escapeHtml(shown(node.passed_count))}</span><span>淘汰 ${escapeHtml(shown(node.rejected_count))} · 未知 ${escapeHtml(shown(node.unknown_count))}</span></span></button>`;
    }).join('') : '<p class="iss-empty">该运行没有阶段记录。</p>';
    el('issStages').querySelectorAll('[data-stage-id]').forEach((button) =>
      button.addEventListener('click', () => selectStage(button.dataset.stageId)));
  }
  async function selectRun(id) {
    const selected = runs.find((item) => item.run_id === id);
    const token = ++generation;
    clearRun();
    if (!selected) return;
    el('issRunSelect').value = id;
    message('正在读取运行详情…');
    try {
      const [runData, nodeData] = await Promise.all([
        get(`/runs/${encodeURIComponent(id)}`), get(`/runs/${encodeURIComponent(id)}/nodes`),
      ]);
      if (!active(token)) return;
      if (runData.run?.run_id !== id || runData.run.model_id !== selected.model_id || nodeData.run_id !== id) {
        throw new Error('运行归属不匹配');
      }
      run = runData.run;
      nodes = nodeData.nodes || [];
      text('issRunStatus', shown(run.status));
      text('issRunMeta', `模型 ${shown(models.find((model) => model.model_id === run.model_id)?.name)} · 版本 ${shown(run.model_version)} · 运行 ${id}`);
      message('');
      if (nodes.length) await selectStage(nodes[0].stage_id);
      else renderStages();
    } catch (error) { if (active(token)) message(error.message); }
  }
  async function selectStage(id) {
    stage = nodes.find((item) => item.stage_id === id) || null;
    if (!stage || !run) return;
    offset = 0;
    el('issSearch').value = '';
    el('issVerdict').value = '';
    text('issStageLabel', `第 ${nodes.indexOf(stage) + 1} 层：${shown(stage.name || id)}`);
    const rejected = stage.result?.rejected_records || [];
    text('issEvidence', `阶段证据：淘汰 ${shown(stage.rejected_count)}，未知 ${shown(stage.unknown_count)}；逐股依据记录 ${rejected.length} 条。`);
    renderStages();
    await loadCandidates();
  }
  async function loadCandidates() {
    if (!run || !stage) return;
    const token = ++generation;
    const id = run.run_id;
    const stageId = stage.stage_id;
    const params = new URLSearchParams({ stage_id: stageId, limit: String(PAGE_SIZE), offset: String(offset) });
    if (el('issSearch').value.trim()) params.set('keyword', el('issSearch').value.trim());
    if (el('issVerdict').value) params.set('verdict', el('issVerdict').value);
    el('issCandidates').innerHTML = '<tr><td colspan="6">正在读取候选…</td></tr>';
    el('issPrev').disabled = true;
    el('issNext').disabled = true;
    el('issExport').disabled = true;
    try {
      const data = await get(`/runs/${encodeURIComponent(id)}/candidates?${params}`);
      if (!active(token) || run?.run_id !== id || stage?.stage_id !== stageId) return;
      if (data.run_id !== id || data.stage_id !== stageId) throw new Error('候选归属不匹配');
      total = Number(data.total) || 0;
      text('issTotal', `共 ${total} 条`);
      text('issPage', `${total ? offset + 1 : 0}–${Math.min(offset + PAGE_SIZE, total)} / ${total}`);
      text('issDataMeta', `来源 ${shown(data.source)} · 数据时点 ${shown(data.as_of)} · 快照 ${shown(data.data_snapshot_id)}`);
      el('issPrev').disabled = offset === 0;
      el('issNext').disabled = offset + PAGE_SIZE >= total;
      el('issExport').disabled = false;
      el('issCandidates').innerHTML = (data.candidates || []).length ? data.candidates.map((item) =>
        `<tr><td>${escapeHtml(shown(item.code))}</td><td>${escapeHtml(shown(item.name))}</td><td>${escapeHtml(shown(item.price))}</td>
        <td>${escapeHtml(shown(item.change_pct))}</td><td>${escapeHtml(shown(item.industry))}</td><td>${escapeHtml(shown(item.verdict))}</td></tr>`).join('')
        : '<tr><td colspan="6">当前筛选无候选。</td></tr>';
      message('');
    } catch (error) { if (active(token)) { message(error.message); el('issCandidates').innerHTML = '<tr><td colspan="6">读取失败。</td></tr>'; } }
  }
  async function exportCurrent() {
    if (!run || !stage) return;
    const id = run.run_id, stageId = stage.stage_id;
    const params = new URLSearchParams({ stage_id: stageId });
    if (el('issSearch').value.trim()) params.set('keyword', el('issSearch').value.trim());
    if (el('issVerdict').value) params.set('verdict', el('issVerdict').value);
    try {
      const response = await global.fetch(`${global.AStockAPI.baseUrl}${BASE}/runs/${encodeURIComponent(id)}/candidates/export?${params}`, { credentials: 'same-origin' });
      if (!response.ok || !String(response.headers.get('content-type') || '').includes('text/csv')) throw new Error('导出失败');
      const blob = await response.blob();
      if (run?.run_id !== id || stage?.stage_id !== stageId) return;
      const url = global.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `智能选股_${id}_${stageId}.csv`;
      link.click();
      global.setTimeout(() => global.URL.revokeObjectURL(url), 1000);
    } catch (error) { message(error.message); }
  }
  function bind() {
    if (bound) return;
    bound = true;
    el('issTabRuns').addEventListener('click', () => setTab('runs'));
    el('issTabModels').addEventListener('click', () => setTab('models'));
    el('issRefresh').addEventListener('click', refresh);
    el('issExport').addEventListener('click', exportCurrent);
    el('issRunSelect').addEventListener('change', (event) => selectRun(event.target.value));
    el('issVerdict').addEventListener('change', () => { offset = 0; loadCandidates(); });
    el('issSearch').addEventListener('input', () => {
      if (searchTimer) global.clearTimeout(searchTimer);
      searchTimer = global.setTimeout(() => { offset = 0; loadCandidates(); }, 250);
    });
    el('issPrev').addEventListener('click', () => { if (offset >= PAGE_SIZE) { offset -= PAGE_SIZE; loadCandidates(); } });
    el('issNext').addEventListener('click', () => { if (offset + PAGE_SIZE < total) { offset += PAGE_SIZE; loadCandidates(); } });
  }
  global.SmartSelection = {
    bootstrap() { bind(); setTab('runs'); refresh(); },
    refresh,
    leave() { ++generation; if (searchTimer) global.clearTimeout(searchTimer); searchTimer = null; clearRun(); message(''); },
  };
})(window);
