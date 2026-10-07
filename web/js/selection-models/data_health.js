// -*- coding: utf-8 -*-
/** 选股模型工作台 · 数据诊断（本地数据网关水位 / 交易日历 / 准入水印）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const A = () => global.SelModels.api;

  async function open() {
    close();
    const wrap = DOM().createElement('div');
    wrap.className = 'sel-modal-mask';
    wrap.id = 'selectionDataHealthModal';
    wrap.innerHTML = `
      <div class="sel-modal sel-modal-wide">
        <div class="sel-modal-head"><span>数据诊断</span>
          <button type="button" class="sel-close-btn" onclick="SelModels.dataHealth.close()">✕</button></div>
        <div class="sel-modal-body" id="selDataHealthBody">
          <div class="sel-state sel-state-loading">读取数据水位…</div></div>
        <div class="sel-modal-foot">
          <button type="button" class="sel-act-btn" onclick="SelModels.dataHealth.close()">关闭</button>
          <button type="button" class="sel-act-btn primary" onclick="SelModels.dataHealth.refresh()">刷新</button>
        </div>
      </div>`;
    DOM().body.appendChild(wrap);
    await refresh();
  }

  async function refresh() {
    const body = DOM().getElementById('selDataHealthBody');
    if (!body) return;
    try {
      const resp = await A().dataHealth();
      if (resp.status !== 'ok') { global.SelModels.stateViews.error(body, resp); return; }
      const data = resp.data;
      global.SelModels.store.set({ dataHealth: data });
      const gate = data.data_gate || {};
      const cal = data.calendar || {};
      body.innerHTML = `
        <div class="sel-health-note">水位状态：${gate.state || '--'} · 交易日：${gate.trade_date || '--'}
          · 水印：${resp.watermark.availability}（可发正式信号：${resp.watermark.eligible_for_signal}）</div>
        <div class="sel-health-note">交易日历版本：${cal.calendar_version || '--'}（可用：${cal.calendar_available}）</div>
        <details class="sel-health-raw"><summary>原始水位明细</summary>
          <pre>${escapeHtml(JSON.stringify(gate, null, 2))}</pre></details>`;
      if (global.SelModels.overview) global.SelModels.overview.render();
    } catch (err) {
      global.SelModels.stateViews.error(body, { message: err.message });
    }
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  }

  function close() {
    const modal = DOM().getElementById('selectionDataHealthModal');
    if (modal) modal.remove();
  }

  global.SelModels.dataHealth = { open, close, refresh };
})(window);