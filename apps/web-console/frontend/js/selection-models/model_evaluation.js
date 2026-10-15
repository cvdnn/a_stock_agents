// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 模型评估与简单调优（阶段 E4 / E5 / SSOT §12.5-§12.6）。
 *
 * 评价默认只汇总同一版本；跟踪样本不足时后端返回 `EVALUATION_SAMPLE_INSUFFICIENT` 并禁止强结论，
 * 本模块如实呈现该降级态，不补写任何指标。优化建议只读，系统不会自动改版。
 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const A = () => global.SelModels.api;
  const SV = () => global.SelModels.stateViews;

  let lastModelId = null;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function fmt(value) {
    return value === null || value === undefined || value === '' ? '--' : String(value);
  }

  function pct(value) {
    return value === null || value === undefined || value === '' ? '--' : `${value}%`;
  }

  function evalBody() {
    return DOM().getElementById('selEvaluationBody');
  }

  function suggBody() {
    return DOM().getElementById('selSuggestionBody');
  }

  function modelId() {
    return global.SelModels.store.get().activeModelId;
  }

  /** 切换活动模型时清空上个模型的结果，避免跨模型串味。 */
  function render() {
    const current = modelId();
    if (current === lastModelId) return;
    lastModelId = current;
    SV().empty(evalBody(), '点击「生成评价」按活动版本汇总真实运行与跟踪样本');
    SV().empty(suggBody(), '点击「读取建议」查看只读优化建议');
  }

  async function evaluate() {
    const box = evalBody();
    if (!box) return;
    const id = modelId();
    if (!id) { global.showToast && global.showToast('请先选择模型'); return; }
    SV().loading(box, '按活动版本汇总评价…');
    try {
      const resp = await A().createEvaluation(id, {});
      if (resp.status !== 'ok') { renderUnavailable(box, resp); return; }
      renderEvaluation(box, resp.data.evaluation, resp.watermark);
    } catch (err) {
      SV().error(box, { message: err.message });
    }
  }

  async function loadTuning() {
    const box = suggBody();
    if (!box) return;
    const id = modelId();
    if (!id) { global.showToast && global.showToast('请先选择模型'); return; }
    SV().loading(box, '读取优化建议…');
    try {
      const resp = await A().listTuningSuggestions(id);
      if (resp.status !== 'ok') { renderUnavailable(box, resp); return; }
      renderSuggestions(box, resp.data);
    } catch (err) {
      SV().error(box, { message: err.message });
    }
  }

  async function generateTuning() {
    const box = suggBody();
    if (!box) return;
    const id = modelId();
    if (!id) { global.showToast && global.showToast('请先选择模型'); return; }
    SV().loading(box, '生成只读优化建议…');
    try {
      const resp = await A().createTuningSuggestions(id, {});
      if (resp.status !== 'ok') { renderUnavailable(box, resp); return; }
      renderSuggestions(box, resp.data);
    } catch (err) {
      SV().error(box, { message: err.message });
    }
  }

  async function markStatus(suggestionId, status) {
    const id = modelId();
    if (!id) return;
    const resp = await A().markTuningStatus(id, suggestionId, status);
    global.showToast && global.showToast(resp.status === 'ok' ? '已标记建议处理状态' : (resp.message || '标记失败'));
    await loadTuning();
  }

  function renderUnavailable(box, resp) {
    const notice = SV().availabilityNotice(resp.watermark, resp.error_code);
    SV().error(box, { message: `${resp.message || '模型评估不可用'}${notice ? ' · ' + notice : ''}` });
  }

  function renderEvaluation(box, ev, watermark) {
    if (!ev) { SV().empty(box, '暂无评价结果'); return; }
    const thresholds = ev.thresholds || {};
    const base = `<div class="sel-stage-meta">评价：${esc(ev.evaluation_id)} · 版本 v${fmt(ev.model_version)} · 期间 ${esc(ev.period)} · 基准 ${esc(ev.benchmark)}</div>
      <div class="sel-stage-meta">运行数：${fmt(ev.run_count)}（完成 ${fmt(ev.completed_run_count)}） · 跟踪样本：${fmt(ev.tracked_sample_count)} · 观察交易日：${fmt(ev.observation_days)} · 下限：样本 ${fmt(thresholds.min_samples)} / 观察 ${fmt(thresholds.min_observation_days)}</div>`;
    if (ev.status !== 'OK') {
      const notice = SV().availabilityNotice(watermark, ev.status);
      box.removeAttribute('data-degraded');
      box.setAttribute('data-degraded', ev.status);
      box.innerHTML = `${base}
        <div class="sel-stage-notice">样本不足，禁止强结论（strong_conclusion_allowed = ${ev.strong_conclusion_allowed === true}）：${esc(ev.reason || '')}${notice ? ' · ' + esc(notice) : ''}</div>`;
      return;
    }
    const sel = ev.selection_model_evaluation || {};
    const periodRows = Object.keys(sel.period_metrics || {}).sort((a, b) => Number(a) - Number(b)).map((key) => {
      const m = sel.period_metrics[key];
      return `<tr><td class="tabular-nums">T+${esc(key)}</td>
        <td class="tabular-nums">${fmt(m.sample_count)}</td>
        <td class="tabular-nums">${pct(m.mean_return_pct)}</td>
        <td class="tabular-nums">${pct(m.median_return_pct)}</td>
        <td class="tabular-nums">${fmt(m.up_ratio)}</td></tr>`;
    }).join('') || '<tr><td colspan="5">无分周期样本</td></tr>';
    box.removeAttribute('data-degraded');
    box.innerHTML = `${base}
      <div class="sel-stage-message">强结论允许：${ev.strong_conclusion_allowed === true} · 结论：${esc(ev.conclusion)}</div>
      <div class="sel-research-block"><h4>选股模型评价</h4>
        <div>${sel.available ? `样本 ${fmt(sel.sample_count)} · 均值收益 ${pct(sel.mean_return_pct)} · 中位 ${pct(sel.median_return_pct)} · 上涨比例 ${fmt(sel.up_ratio)} · 均值超额 ${pct(sel.mean_excess_return_pct)}` : '不可用（' + esc(sel.reason_code || '') + '）'}</div></div>
      <table class="sel-version-table"><thead><tr>
        <th>周期</th><th class="num">样本</th><th class="num">均值收益</th><th class="num">中位收益</th><th class="num">上涨比例</th></tr></thead>
        <tbody>${periodRows}</tbody></table>`;
  }

  function renderSuggestions(box, data) {
    const items = (data && data.suggestions) || [];
    if (!items.length) { SV().empty(box, '暂无优化建议，可点击「生成建议」按历史运行与跟踪样本生成'); return; }
    const head = `<div class="sel-stage-notice">建议只读：read_only=${data.read_only === true} · auto_apply=${data.auto_apply === true} · 来源版本 v${fmt(data.source_model_version || data.active_version)}</div>`;
    const cards = items.map((s) => {
      const status = String(s.status || '');
      const markable = status === 'pending';
      const actions = markable
        ? `<span class="sel-suggestion-actions">
            <button type="button" class="sel-mini-btn" onclick="SelModels.modelEvaluation.markStatus('${esc(s.suggestion_id)}', 'accepted')">采纳</button>
            <button type="button" class="sel-mini-btn" onclick="SelModels.modelEvaluation.markStatus('${esc(s.suggestion_id)}', 'ignored')">忽略</button>
          </span>`
        : '';
      return `<div class="sel-suggestion-card">
        <div class="sel-suggestion-head"><strong>${esc(s.suggestion_type)}</strong>
          <span class="sel-status-chip">${esc(status)}</span></div>
        <div>修改方向：${esc(s.direction)} · 置信等级：${esc(s.confidence)} · 适用周期：${esc(s.applicable_period)}</div>
        <div>观测：${esc(s.comparison_metric)} = ${fmt(s.observed_value)} · 样本 ${fmt(s.sample_count)} / 运行 ${fmt(s.run_count)}</div>
        <div>建议：${esc(s.suggested_change)}</div>
        <div class="sel-suggestion-risk">${esc(s.risk_notice)}</div>
        ${actions}</div>`;
    }).join('');
    box.innerHTML = head + cards;
  }

  global.SelModels.modelEvaluation = { render, evaluate, loadTuning, generateTuning, markStatus };
})(window);