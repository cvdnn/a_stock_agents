// -*- coding: utf-8 -*-
/** 选股模型工作台 · 运行时间线（历史运行 / 阶段耗时 / 候选下钻 / SSE 事件流）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const A = () => global.SelModels.api;
  let stream = null;
  let selectedStage = null;
  let verdict = '';
  let keyword = '';
  let offset = 0;
  let requestSequence = 0;
  const pageSize = 50;

  function open() {
    const modelId = global.SelModels.store.get().activeModelId;
    if (!modelId) { global.showToast && global.showToast('请先选择模型'); return; }
    const wrap = DOM().createElement('div');
    wrap.className = 'sel-modal-mask';
    wrap.id = 'selectionRunModal';
    wrap.innerHTML = `
      <div class="sel-modal sel-modal-wide">
        <div class="sel-modal-head"><span>运行记录</span>
          <button type="button" class="sel-close-btn" onclick="SelModels.runTimeline.close()">✕</button></div>
        <div class="sel-modal-body">
          <div class="sel-run-layout">
            <div class="sel-run-list" id="selRunList"><div class="sel-state sel-state-loading">加载中…</div></div>
            <div class="sel-run-detail" id="selRunDetail">
              <div class="sel-state sel-state-empty">请选择一次运行查看阶段与候选轨迹</div></div>
          </div>
        </div>
        <div class="sel-modal-foot">
          <button type="button" class="sel-act-btn" onclick="SelModels.runTimeline.close()">关闭</button>
        </div>
      </div>`;
    DOM().body.appendChild(wrap);
    refresh();
  }

  async function refresh() {
    const modelId = global.SelModels.store.get().activeModelId;
    const list = DOM().getElementById('selRunList');
    if (!list) return;
    try {
      const resp = await A().listRuns(modelId, '?limit=50');
      const data = global.SelModels.stateViews.unwrap(list, resp, { emptyLabel: '该模型暂无运行记录' });
      if (!data) return;
      const currentRunId = global.SelModels.store.get().activeRunId;
      const picked = data.runs.find((run) => run.run_id === currentRunId) || data.runs[0];
      global.SelModels.store.set({ runs: data.runs });
      if (!data.runs.length) { global.SelModels.stateViews.empty(list, '该模型暂无运行记录'); return; }
      list.innerHTML = data.runs.map((r) => `
        <div class="sel-run-item" onclick="SelModels.runTimeline.select('${r.run_id}')">
          <div class="sel-run-item-top"><strong>${esc(r.status)}</strong><span>${esc(r.trigger_type)}</span></div>
          <div class="sel-run-item-sub sel-mono">${esc(r.run_id)}</div>
          <div class="sel-run-item-sub">${esc(r.started_at || r.created_at || '')}</div>
        </div>`).join('');
      select(picked.run_id);
    } catch (err) {
      global.SelModels.stateViews.error(list, { message: err.message });
    }
  }

  async function select(runId) {
    const detail = DOM().getElementById('selRunDetail');
    if (!detail) return;
    if (stream) { stream.close(); stream = null; }
    global.SelModels.store.set({ activeRunId: runId });
    await global.SelModels.runWorkspace.selectRun(runId);
    selectedStage = null; verdict = ''; keyword = ''; offset = 0;
    const sequence = ++requestSequence;
    detail.innerHTML = '<div class="sel-state sel-state-loading">加载运行明细…</div>';
    try {
      const nodesResp = await A().getRunNodes(runId);
      if (sequence !== requestSequence) return;
      if (nodesResp.status !== 'ok') throw new Error(nodesResp.message || '阶段读取失败');
      const nodes = (nodesResp.data && nodesResp.data.nodes) || [];
      selectedStage = nodes[0] ? nodes[0].stage_id : null;
      global.SelModels.store.set({ nodes, candidates: [] });
      detail.innerHTML = `
        <div class="sel-run-stages"><table class="sel-version-table"><thead><tr>
          <th>阶段</th><th>状态</th><th>输入</th><th>通过</th><th>淘汰</th><th>未知</th><th>透传</th></tr></thead><tbody>
          ${nodes.map((n) => `<tr><td><button type="button" class="sel-act-btn" data-stage-id="${esc(n.stage_id)}">${esc(n.name || n.stage_id)}</button></td><td>${esc(n.status)}</td>
            <td>${display(n.input_count)}</td><td>${display(n.passed_count)}</td>
            <td>${display(n.rejected_count)}</td><td>${display(n.unknown_count)}</td>
            <td>${display(n.forwarded_count)}</td></tr>`).join('')
            || '<tr><td colspan="7">无阶段明细</td></tr>'}</tbody></table></div>
        <div class="sel-run-candidate-controls">
          <label>判定 <select id="selRunVerdict"><option value="">全部</option><option value="PASS">通过</option><option value="FAIL">淘汰</option><option value="UNKNOWN">未知</option><option value="FORWARDED">跳过透传</option></select></label>
          <label>关键词 <input id="selRunKeyword" type="search" aria-label="按股票代码或名称搜索"></label>
          <button type="button" class="sel-act-btn" id="selRunSearch">搜索</button>
          <button type="button" class="sel-act-btn" id="selRunExport">导出当前层 CSV</button>
        </div>
        <div id="selRunCandidateSummary" class="sel-run-item-sub"></div>
        <div class="sel-run-candidates" id="selRunCandidateTrace"></div>
        <div class="sel-run-candidate-controls"><button type="button" class="sel-act-btn" id="selRunPrev">上一页</button>
          <span id="selRunPage"></span><button type="button" class="sel-act-btn" id="selRunNext">下一页</button></div>
        <div class="sel-run-events"><div class="sel-run-events-head">SSE 事件流</div>
          <div id="selRunEvents" class="sel-run-events-body">连接中…</div></div>`;
      detail.querySelectorAll('[data-stage-id]').forEach((button) => button.addEventListener('click', () => {
        selectedStage = button.dataset.stageId; offset = 0; loadCandidates();
      }));
      DOM().getElementById('selRunSearch').addEventListener('click', () => {
        keyword = DOM().getElementById('selRunKeyword').value.trim();
        verdict = DOM().getElementById('selRunVerdict').value;
        offset = 0; loadCandidates();
      });
      DOM().getElementById('selRunExport').addEventListener('click', exportCurrent);
      DOM().getElementById('selRunPrev').addEventListener('click', () => { offset = Math.max(0, offset - pageSize); loadCandidates(); });
      DOM().getElementById('selRunNext').addEventListener('click', () => { offset += pageSize; loadCandidates(); });
      await loadCandidates();
      if (global.SelModels.store.get().activeRunId === runId) subscribeEvents(runId);
    } catch (err) {
      global.SelModels.stateViews.error(detail, { message: err.message });
    }
  }

  async function loadCandidates() {
    const runId = global.SelModels.store.get().activeRunId;
    const container = DOM().getElementById('selRunCandidateTrace');
    if (!container || !runId || !selectedStage) return;
    const sequence = ++requestSequence;
    container.textContent = '加载候选…';
    try {
      const resp = await A().getRunCandidates(runId, {
        stage_id: selectedStage, verdict, keyword, limit: pageSize, offset,
      });
      if (sequence !== requestSequence) return;
      if (resp.status !== 'ok') throw new Error(resp.message || '候选读取失败');
      const data = resp.data;
      global.SelModels.store.set({ candidates: data.candidates });
      global.SelModels.candidateTrace.renderTrace(container, data.candidates);
      DOM().getElementById('selRunCandidateSummary').textContent =
        `${selectedStage} · 共 ${data.total} 条 · 来源 ${data.source || '未提供'} · 数据时点 ${data.as_of || '未提供（运行快照未标注）'} · 快照 ${data.data_snapshot_id || '未提供（运行输入未附快照）'}`;
      DOM().getElementById('selRunPage').textContent = `${data.total ? offset + 1 : 0}–${Math.min(offset + pageSize, data.total)} / ${data.total}`;
      DOM().getElementById('selRunPrev').disabled = offset === 0;
      DOM().getElementById('selRunNext').disabled = offset + pageSize >= data.total;
    } catch (err) {
      global.SelModels.stateViews.error(container, err);
    }
  }

  async function exportCurrent() {
    const runId = global.SelModels.store.get().activeRunId;
    if (!runId || !selectedStage) { global.showToast && global.showToast('请先在运行记录中选择层级'); return; }
    try {
      const blob = await A().exportRunCandidates(runId, { stage_id: selectedStage, verdict, keyword });
      const link = DOM().createElement('a');
      link.href = global.URL.createObjectURL(blob);
      link.download = `${runId}-${selectedStage}-candidates.csv`;
      link.click();
      global.URL.revokeObjectURL(link.href);
    } catch (err) { global.showToast && global.showToast(err.message || '导出失败'); }
  }

  function display(value) { return value == null ? '未提供' : esc(value); }

  function subscribeEvents(runId) {
    const box = DOM().getElementById('selRunEvents');
    if (!box || !global.EventSource) return;
    if (stream) { stream.close(); stream = null; }
    box.innerHTML = '';
    try {
      stream = new global.EventSource(A().eventsUrl(runId));
      const events = ['run.started', 'stage.completed', 'run.finished', 'run.failed', 'heartbeat'];
      events.forEach((name) => stream.addEventListener(name, (ev) => {
        const line = DOM().createElement('div');
        line.className = 'sel-run-event-line';
        line.innerText = `[${name}] ${ev.data}`;
        box.appendChild(line);
      }));
      stream.onerror = () => { if (stream) { stream.close(); stream = null; } };
    } catch (_) { box.innerText = '事件流不可用'; }
  }

  function close() {
    if (stream) { stream.close(); stream = null; }
    const modal = DOM().getElementById('selectionRunModal');
    if (modal) modal.remove();
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  global.SelModels.runTimeline = { open, close, refresh, select, exportCurrent };
})(window);
