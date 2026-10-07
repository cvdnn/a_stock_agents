// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 持续跟踪（阶段 E3 / SSOT §12.4）。
 *
 * 创建跟踪计划必须提供真实基准价与运行记录，否则后端失败关闭；观察序列只追加、不覆盖历史。
 * 本模块只读取 `/tracking-plans/*` 的真实响应，不合成任何观察值。
 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const A = () => global.SelModels.api;
  const SV = () => global.SelModels.stateViews;

  let currentRunId = null;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function fmt(value) {
    return value === null || value === undefined || value === '' ? '--' : String(value);
  }

  function body() {
    return DOM().getElementById('selTrackingBody');
  }

  function render() {
    const select = DOM().getElementById('selTrackingRunSelect');
    if (!select) return;
    const runs = global.SelModels.store.get().runs || [];
    const keep = currentRunId || select.value || '';
    select.innerHTML = '<option value="">--</option>' + runs.map((run) => (
      `<option value="${esc(run.run_id)}">${esc(run.run_id)} · ${esc(run.status || '')}</option>`
    )).join('');
    if (keep && runs.some((run) => run.run_id === keep)) select.value = keep;
  }

  function selectRun(runId) {
    currentRunId = runId || null;
  }

  /** 解析「代码:价格」文本为真实基准价映射；空串返回空对象（由后端失败关闭）。 */
  function parseBasePrices(text) {
    const prices = {};
    String(text || '').split(/[\s,;，、]+/).forEach((pair) => {
      const parts = pair.split(':');
      if (parts.length !== 2) return;
      const code = parts[0].trim();
      const price = Number(parts[1].trim());
      if (code && Number.isFinite(price) && price > 0) prices[code] = price;
    });
    return prices;
  }

  async function create() {
    const box = body();
    if (!box) return;
    const runId = currentRunId || (global.SelModels.store.get().activeRunId) || '';
    if (!runId) { global.showToast && global.showToast('请先选择一次运行'); return; }
    const prices = parseBasePrices((DOM().getElementById('selTrackingBasePrices') || {}).value);
    const codes = Object.keys(prices);
    SV().loading(box, '创建跟踪计划…');
    try {
      const resp = await A().createTrackingPlan({ run_id: runId, codes, base_prices: prices, mode: 't_plus_n' });
      if (resp.status !== 'ok') { renderUnavailable(box, resp); return; }
      const plan = (resp.data && resp.data.plan) || {};
      const idInput = DOM().getElementById('selTrackingId');
      if (idInput && plan.tracking_id) idInput.value = plan.tracking_id;
      await loadPlan(plan.tracking_id, box);
    } catch (err) {
      SV().error(box, { message: err.message });
    }
  }

  async function load() {
    const box = body();
    if (!box) return;
    const trackingId = ((DOM().getElementById('selTrackingId') || {}).value || '').trim();
    if (!trackingId) { SV().empty(box, '请输入跟踪计划 ID 后读取'); return; }
    SV().loading(box, '读取跟踪计划…');
    await loadPlan(trackingId, box);
  }

  async function loadPlan(trackingId, box) {
    try {
      const [planResp, obsResp] = await Promise.all([
        A().getTrackingPlan(trackingId), A().getTrackingObservations(trackingId),
      ]);
      if (planResp.status !== 'ok') { renderUnavailable(box, planResp); return; }
      const plan = (planResp.data && planResp.data.plan) || {};
      const observations = (obsResp.status === 'ok' && obsResp.data && obsResp.data.observations) || [];
      const obsNotice = obsResp.status === 'ok' ? '' : SV().availabilityNotice(obsResp.watermark, obsResp.error_code);
      renderPlan(box, plan, observations, obsNotice);
    } catch (err) {
      SV().error(box, { message: err.message });
    }
  }

  function renderUnavailable(box, resp) {
    const notice = SV().availabilityNotice(resp.watermark, resp.error_code);
    SV().error(box, { message: `${resp.message || '跟踪计划不可用'}${notice ? ' · ' + notice : ''}` });
  }

  function renderPlan(box, plan, observations, obsNotice) {
    if (!plan || !plan.tracking_id) { SV().empty(box, '该跟踪计划不存在或不可读'); return; }
    const basePrices = plan.base_prices || {};
    const priceRows = Object.keys(basePrices).map((code) => (
      `<tr><td class="sel-mono">${esc(code)}</td><td class="num tabular-nums">${fmt(basePrices[code])}</td></tr>`
    )).join('') || '<tr><td colspan="2">无基准价格</td></tr>';
    const obsRows = observations.map((o) => (`<tr>
      <td class="sel-mono">${esc(o.code)}</td>
      <td class="tabular-nums">${fmt(o.period)}</td>
      <td class="tabular-nums">${fmt(o.raw_return_pct)}</td>
      <td class="tabular-nums">${fmt(o.mfe_pct)}</td>
      <td class="tabular-nums">${fmt(o.mae_pct)}</td>
      <td class="tabular-nums">${fmt(o.rel_index_return_pct)}</td>
      <td>${esc(o.recorded_at)}</td></tr>`)).join('')
      || '<tr><td colspan="7" class="sel-empty-row">尚无观察点：观察值由跟踪调度在水位就绪后只追加写入</td></tr>';
    box.innerHTML = `
      <div class="sel-stage-notice">跟踪计划 ${esc(plan.tracking_id)} · 观察序列只追加，不覆盖历史（发布门禁 14）。${obsNotice ? ' · ' + esc(obsNotice) : ''}</div>
      <div class="sel-stage-meta">状态：${esc(plan.status)} · 模式：${esc(plan.mode)} · 来源运行：${esc(plan.run_id)} · 信号日：${esc(plan.signal_date)} · 基准：${esc(plan.benchmark)}</div>
      <div class="sel-track-grid">
        <div><h4 class="sel-track-title">基准价格（来自真实信号价）</h4>
          <table class="sel-version-table"><thead><tr><th>代码</th><th class="num">基准价</th></tr></thead>
            <tbody>${priceRows}</tbody></table></div>
        <div><h4 class="sel-track-title">观察点</h4>
          <table class="sel-version-table"><thead><tr>
            <th>代码</th><th>T+N</th><th class="num">收益%</th><th class="num">MFE%</th>
            <th class="num">MAE%</th><th class="num">相对基准%</th><th>记录时间</th></tr></thead>
            <tbody>${obsRows}</tbody></table></div>
      </div>`;
  }

  global.SelModels.trackingCenter = { render, selectRun, load, create };
})(window);