// -*- coding: utf-8 -*-
/** 选股模型工作台 · 候选轨迹与正式结果（表内只呈现后端运行记录，不合成数值）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;

  function renderResultsPanel() {
    const body = DOM().getElementById('selResultBody');
    const total = DOM().getElementById('selResultTotal');
    if (!body) return;
    const results = global.SelModels.store.get().results || [];
    if (total) total.innerText = results.length ? String(results.length) : '--';
    if (!results.length) {
      body.innerHTML = '<tr><td colspan="6" class="sel-empty-row">无真实正式结果，不展示任何示例标的</td></tr>';
      return;
    }
    const rows = results.flatMap((item) => (item.signal_codes || []).map((code) => ({
      code,
      model: item.model_id,
      date: item.signal_trade_date,
    })));
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="6" class="sel-empty-row">已加载运行记录，但无锁存正式信号</td></tr>';
      return;
    }
    body.innerHTML = rows.map((r, i) => `<tr onclick="SelModels.candidateTrace.openCode('${r.code}')">
      <td class="tabular-nums">${i + 1}</td>
      <td class="tabular-nums sel-code-cell">${esc(r.code)}</td>
      <td class="sel-name-cell">${esc(r.model)}</td>
      <td class="num tabular-nums">${esc(r.date)}</td>
      <td class="num tabular-nums">--</td>
      <td>--</td></tr>`).join('');
  }

  function renderTrace(container, candidates) {
    if (!container) return;
    if (!candidates || !candidates.length) {
      global.SelModels.stateViews.empty(container, '本次运行无候选轨迹');
      return;
    }
    container.innerHTML = `<table class="sel-version-table"><thead><tr>
        <th>阶段</th><th>代码</th><th>判定</th><th>失败规则</th><th>未知规则</th></tr></thead>
      <tbody>${candidates.map((c) => `<tr>
        <td>${esc(c.stage_id)}</td><td class="sel-mono">${esc(c.code)}</td><td>${esc(c.verdict)}</td>
        <td>${(c.failed_rules || []).join(', ') || '--'}</td>
        <td>${(c.unknown_rules || []).join(', ') || '--'}</td></tr>`).join('')}</tbody></table>`;
  }

  function openCode(code) {
    const el = DOM().getElementById('selStockCode');
    if (el) el.innerText = code;
    const nameEl = DOM().getElementById('selStockName');
    if (nameEl) nameEl.innerText = '--';
    if (global.SelModels.main) global.SelModels.main.toggleAnalysis(true);
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  global.SelModels.candidateTrace = { renderResultsPanel, renderTrace, openCode };
})(window);