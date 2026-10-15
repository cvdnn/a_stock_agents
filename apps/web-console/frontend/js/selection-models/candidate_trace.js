// -*- coding: utf-8 -*-
/** 选股模型工作台 · 运行记录候选轨迹（不合成数值）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;

  function renderTrace(container, candidates) {
    if (!container) return;
    if (!candidates || !candidates.length) {
      global.SelModels.stateViews.empty(container, '当前筛选无候选轨迹');
      return;
    }
    const field = (candidate, key) => candidate[key] == null || candidate[key] === ''
      ? `<span title="${esc((candidate.missing_reasons || {})[key] || '运行记录未提供')}">未提供</span>`
      : esc(candidate[key]);
    container.innerHTML = `<table class="sel-version-table"><thead><tr>
        <th>阶段</th><th>代码</th><th>名称</th><th>行业</th><th>价格</th><th>判定</th><th>失败规则</th><th>未知规则</th></tr></thead>
      <tbody>${candidates.map((c) => `<tr>
        <td>${esc(c.stage_id)}</td><td class="sel-mono">${esc(c.code)}</td>
        <td>${field(c, 'name')}</td><td>${field(c, 'industry')}</td>
        <td title="价格时点：${esc(c.price_as_of || '未提供')}；来源：${esc(c.source || '未提供')}">${field(c, 'price')}</td>
        <td>${esc(c.verdict)}</td>
        <td>${esc((c.failed_rules || []).join(', ') || '—')}</td>
        <td>${esc((c.unknown_rules || []).join(', ') || '—')}</td></tr>`).join('')}</tbody></table>`;
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  global.SelModels.candidateTrace = { renderTrace };
})(window);
