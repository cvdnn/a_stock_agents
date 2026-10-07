// -*- coding: utf-8 -*-
/** 选股模型工作台 · 运行时间线（历史运行 / 阶段耗时 / 候选下钻 / SSE 事件流）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const A = () => global.SelModels.api;
  let stream = null;

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
      global.SelModels.store.set({ runs: data.runs, activeRunId: data.runs[0] ? data.runs[0].run_id : null });
      if (!data.runs.length) { global.SelModels.stateViews.empty(list, '该模型暂无运行记录'); return; }
      list.innerHTML = data.runs.map((r) => `
        <div class="sel-run-item" onclick="SelModels.runTimeline.select('${r.run_id}')">
          <div class="sel-run-item-top"><strong>${esc(r.status)}</strong><span>${esc(r.trigger_type)}</span></div>
          <div class="sel-run-item-sub sel-mono">${esc(r.run_id)}</div>
          <div class="sel-run-item-sub">${esc(r.started_at || r.created_at || '')}</div>
        </div>`).join('');
      select(data.runs[0].run_id);
    } catch (err) {
      global.SelModels.stateViews.error(list, { message: err.message });
    }
  }

  async function select(runId) {
    const detail = DOM().getElementById('selRunDetail');
    if (!detail) return;
    global.SelModels.store.set({ activeRunId: runId });
    detail.innerHTML = '<div class="sel-state sel-state-loading">加载运行明细…</div>';
    try {
      const [nodesResp, candResp] = await Promise.all([A().getRunNodes(runId), A().getRunCandidates(runId)]);
      const nodes = (nodesResp.data && nodesResp.data.nodes) || [];
      const candidates = (candResp.data && candResp.data.candidates) || [];
      global.SelModels.store.set({ nodes, candidates });
      detail.innerHTML = `
        <div class="sel-run-stages"><table class="sel-version-table"><thead><tr>
          <th>阶段</th><th>状态</th><th>输入</th><th>输出</th></tr></thead><tbody>
          ${nodes.map((n) => `<tr><td>${esc(n.stage_id)}</td><td>${esc(n.status)}</td>
            <td>${n.input_count == null ? '--' : n.input_count}</td>
            <td>${n.output_count == null ? '--' : n.output_count}</td></tr>`).join('')
            || '<tr><td colspan="4">无阶段明细</td></tr>'}</tbody></table></div>
        <div class="sel-run-events"><div class="sel-run-events-head">SSE 事件流</div>
          <div id="selRunEvents" class="sel-run-events-body">连接中…</div></div>
        <div class="sel-run-candidates" id="selRunCandidateTrace"></div>`;
      global.SelModels.candidateTrace.renderTrace(DOM().getElementById('selRunCandidateTrace'), candidates);
      subscribeEvents(runId);
    } catch (err) {
      global.SelModels.stateViews.error(detail, { message: err.message });
    }
  }

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

  async function cancelActive() {
    const runId = global.SelModels.store.get().activeRunId;
    if (!runId) { global.showToast && global.showToast('未选择运行'); return; }
    const resp = await A().cancelRun(runId);
    global.showToast && global.showToast(resp.status === 'ok' ? '已取消运行' : (resp.message || '取消失败'));
    refresh();
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

  global.SelModels.runTimeline = { open, close, refresh, select, cancelActive };
})(window);