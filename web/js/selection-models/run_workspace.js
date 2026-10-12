// -*- coding: utf-8 -*-
/** The run workspace reads one persisted run and one stage at a time. */
(function (global) {
  'use strict';

  const S = () => global.SelModels;
  const el = (id) => global.document.getElementById(id);
  const esc = (value) => String(value == null ? '' : value).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pageSize = 50;
  let generation = 0;
  let modelId = null;
  let runId = null;
  let stageId = null;
  let nodes = [];
  let offset = 0;
  let total = 0;
  let keyword = '';
  let runWatermark = '未提供';
  let searchTimer = null;
  let evidenceByCode = new Map();

  function text(id, value) { if (el(id)) el(id).textContent = value; }
  function missing(candidate, key) {
    const value = candidate[key];
    if (value != null && value !== '') return esc(value);
    const reason = (candidate.missing_reasons || {})[key] || '运行记录未提供';
    return `<span title="${esc(reason)}">未提供</span>`;
  }
  function evidenceValue(value) {
    if (value == null) return '未记录';
    if (typeof value === 'object') return esc(JSON.stringify(value));
    return esc(value);
  }
  function renderRuleEvidence(rule) {
    const status = rule.field_status && Object.keys(rule.field_status).length
      ? `<span>字段状态 ${evidenceValue(rule.field_status)}</span>` : '';
    return `<div class="sel-rule-evidence">
      <strong>${esc(rule.rule_id || '未命名规则')} · ${esc(rule.verdict || '判定未记录')}</strong>
      <span>${esc(rule.reason || '具体原因未记录')}</span>
      <small>观测值 ${evidenceValue(rule.observed)} · 比较值 ${evidenceValue(rule.expected)} · 原因码 ${esc(rule.reason_code || '未记录')}</small>
      ${status}</div>`;
  }
  function renderStageEvidence(node) {
    const root = el('selStageEvidence');
    if (!root) return;
    const result = node.result || {};
    const rejected = result.rejected_records || [];
    const groups = [['FAIL', '淘汰'], ['UNKNOWN', '未知']];
    const summaries = groups.map(([verdict, label]) => {
      const counts = new Map();
      rejected.filter((item) => item.candidate_verdict === verdict).forEach((item) => {
        const rules = verdict === 'FAIL' ? item.failed_rules : item.unknown_rules;
        (rules || []).forEach((rule) => {
          const key = rule.rule_id || '未命名规则';
          const previous = counts.get(key) || { count: 0, rule };
          previous.count += 1;
          counts.set(key, previous);
        });
      });
      if (!counts.size) return '';
      const rows = [...counts].sort((a, b) => b[1].count - a[1].count).map(([id, item]) =>
        `<li><strong>${esc(id)}</strong>：${item.count} 只<span>示例原因：${esc(item.rule.reason || item.rule.reason_code || '未记录')}</span></li>`).join('');
      return `<div><strong>${label}规则</strong><ul>${rows}</ul></div>`;
    }).filter(Boolean);
    const inputGaps = new Map();
    rejected.forEach((item) => (item.unknown_rules || []).forEach((rule) => {
      if (rule.reason_code !== 'RULE_INPUT_MISSING') return;
      const key = rule.rule_id || '未命名规则';
      inputGaps.set(key, (inputGaps.get(key) || 0) + 1);
    }));
    const gaps = inputGaps.size ? `<div><strong>淘汰与未知记录中的规则输入缺失</strong><ul>${[...inputGaps]
      .sort((a, b) => b[1] - a[1]).map(([id, count]) => `<li><strong>${esc(id)}</strong>：${count} 只</li>`).join('')}</ul></div>` : '';
    const gate = node.status === 'BLOCKED' && (result.gate_results || []).length
      ? `<div class="sel-stage-gate-evidence"><strong>门控依据</strong>${result.gate_results.map(renderRuleEvidence).join('')}</div>` : '';
    root.innerHTML = `<details ${node.rejected_count || node.unknown_count ? 'open' : ''}><summary>筛选依据：淘汰 ${display(node.rejected_count)} 只，未知 ${display(node.unknown_count)} 只</summary>
      ${summaries.length || gaps ? `<p>按逐股规则记录统计；同一只股票可命中多条规则，规则次数不能相加为股票总数。选择“淘汰”或“未知”可查看每只股票的观测值和阈值。</p>${summaries.join('')}${gaps}`
        : '<p>本层没有可统计的逐股淘汰依据。</p>'}${gate}</details>`;
  }
  function renderCandidateEvidence(candidate) {
    if (candidate.verdict === 'PASS' || candidate.verdict === 'FORWARDED') return '—';
    const item = evidenceByCode.get(String(candidate.code));
    const rules = item ? [...(item.failed_rules || []), ...(item.unknown_rules || [])] : [];
    if (rules.length) return `<details class="sel-candidate-evidence"><summary>查看 ${rules.length} 项依据</summary>${rules.map(renderRuleEvidence).join('')}</details>`;
    const ids = [...(candidate.failed_rules || []), ...(candidate.unknown_rules || [])];
    return ids.length ? `<span title="本次运行未保存规则观测值">${esc(ids.join('、'))}（依据未记录）</span>` : '依据未记录';
  }
  function clear() {
    ++generation;
    if (searchTimer) global.clearTimeout(searchTimer);
    searchTimer = null;
    runId = null; stageId = null; nodes = []; offset = 0; total = 0; keyword = ''; runWatermark = '未提供'; evidenceByCode = new Map();
    S().store.set({ activeRunId: null, nodes: [], candidates: [] });
    text('selRunLayerCount', '未运行');
    text('selRunContext', '请选择一次运行');
    text('selResultLayerLabel', '未选择阶段');
    text('selRunCandidateMeta', '');
    if (el('selStageEvidence')) el('selStageEvidence').innerHTML = '';
    text('selResultTotal', '—');
    text('selResultPage', '— / —');
    if (el('selResultSearch')) el('selResultSearch').value = '';
    if (el('selResultVerdict')) el('selResultVerdict').value = '';
    if (el('selRunFunnel')) el('selRunFunnel').innerHTML = '<div class="sel-state sel-state-empty">该模型暂无运行阶段</div>';
    if (el('selResultBody')) el('selResultBody').innerHTML = '<tr><td colspan="8" class="sel-empty-row">请选择一次运行和阶段</td></tr>';
    if (el('selResultPrev')) el('selResultPrev').disabled = true;
    if (el('selResultNext')) el('selResultNext').disabled = true;
  }
  function renderRuns() {
    const st = S().store.get();
    const select = el('selRunSelect');
    if (!select) return;
    const runs = (st.runs || []).filter((run) => run.model_id === st.activeModelId);
    select.innerHTML = runs.length ? runs.map((run) =>
      `<option value="${esc(run.run_id)}">${esc(run.run_id)} · ${esc(run.status)} · ${esc(run.started_at || run.created_at || '时间未提供')}</option>`).join('')
      : '<option value="">暂无运行</option>';
    select.value = runId || '';
  }
  async function syncModel() {
    const st = S().store.get();
    const nextModelId = st.activeModelId;
    if (modelId !== nextModelId) { modelId = nextModelId; clear(); }
    renderRuns();
    if (!nextModelId || st.detailLoading || !st.detail) return;
    const available = (st.runs || []).filter((run) => run.model_id === nextModelId);
    if (!available.length) { clear(); renderRuns(); return; }
    if (!runId || !available.some((run) => run.run_id === runId)) await selectRun(available[0].run_id);
  }
  async function selectRun(id) {
    const st = S().store.get();
    if (!id || !(st.runs || []).some((run) => run.run_id === id && run.model_id === st.activeModelId)) return;
    clear();
    runId = id;
    const selectedModel = st.activeModelId;
    const current = ++generation;
    S().store.set({ activeRunId: id });
    renderRuns();
    text('selRunContext', `运行 ${id} · 加载中`);
    try {
      const [runResp, nodeResp] = await Promise.all([S().api.getRun(id), S().api.getRunNodes(id)]);
      if (current !== generation || selectedModel !== S().store.get().activeModelId) return;
      if (runResp.status !== 'ok' || nodeResp.status !== 'ok') throw new Error(S().stateViews.message(runResp.status !== 'ok' ? runResp : nodeResp));
      const run = runResp.data.run;
      if (run.model_id !== selectedModel || nodeResp.data.run_id !== id) throw new Error('运行归属不匹配');
      runWatermark = (nodeResp.watermark || {}).availability || '未提供';
      nodes = nodeResp.data.nodes || [];
      S().store.set({ nodes });
      text('selRunContext', `运行 ${id} · ${run.status} · 版本 ${run.model_version == null ? '未提供' : 'v' + run.model_version}`);
      text('selRunLayerCount', `共 ${nodes.length} 层`);
      if (!nodes.length) {
        el('selRunFunnel').innerHTML = '<div class="sel-state sel-state-empty">该运行尚无阶段记录</div>';
        return;
      }
      await selectStage(nodes[0].stage_id);
    } catch (error) {
      if (current !== generation) return;
      S().stateViews.error(el('selRunFunnel'), error);
      text('selRunContext', `运行 ${id} · 读取失败`);
    }
  }
  function renderStages() {
    const root = el('selRunFunnel');
    if (!root) return;
    root.innerHTML = nodes.map((node, index) => `<button type="button" class="sel-run-stage ${node.stage_id === stageId ? 'selected' : ''}"
      data-stage-id="${esc(node.stage_id)}" aria-pressed="${node.stage_id === stageId}" aria-label="查看第 ${index + 1} 层 ${esc(node.name || node.stage_id)} 的候选">
      <span class="sel-run-stage-index">${index + 1}</span><span class="sel-run-stage-main"><strong>${esc(node.name || node.stage_id)}</strong><small>${esc(node.status || '状态未提供')} · ${esc(node.completed_at || '完成时刻未提供')}</small>
      <small>输入 ${display(node.input_count)} · 通过 ${display(node.passed_count)} · 淘汰 ${display(node.rejected_count)} · 未知 ${display(node.unknown_count)}${node.forwarded_count == null ? '' : ' · 透传 ' + display(node.forwarded_count)}</small>
      <small>数据水位 ${esc(runWatermark)}</small></span></button>`).join('');
    root.querySelectorAll('[data-stage-id]').forEach((button) => button.addEventListener('click', () => selectStage(button.dataset.stageId)));
  }
  function display(value) { return value == null ? '未提供' : esc(value); }
  async function selectStage(id) {
    if (!runId || !nodes.some((node) => node.stage_id === id)) return;
    stageId = id; offset = 0; keyword = '';
    if (el('selResultSearch')) el('selResultSearch').value = '';
    if (el('selResultVerdict')) el('selResultVerdict').value = '';
    const node = nodes.find((item) => item.stage_id === id);
    text('selResultLayerLabel', node.name || id);
    evidenceByCode = new Map((node.result?.rejected_records || []).map((item) => [String(item.candidate?.code), item]));
    renderStageEvidence(node);
    renderStages();
    await loadCandidates();
  }
  async function loadCandidates() {
    if (!runId || !stageId) return;
    const current = ++generation;
    const requestedRun = runId, requestedStage = stageId, requestedModel = S().store.get().activeModelId;
    const verdict = el('selResultVerdict').value;
    el('selResultBody').innerHTML = '<tr><td colspan="8" class="sel-empty-row">加载候选…</td></tr>';
    try {
      const response = await S().api.getRunCandidates(requestedRun, { stage_id: requestedStage, verdict, keyword, limit: pageSize, offset });
      if (current !== generation || requestedRun !== runId || requestedStage !== stageId || requestedModel !== S().store.get().activeModelId) return;
      if (response.status !== 'ok') throw new Error(S().stateViews.message(response));
      const data = response.data;
      if (data.run_id !== requestedRun || data.stage_id !== requestedStage) throw new Error('候选归属不匹配');
      total = data.total;
      S().store.set({ candidates: data.candidates || [] });
      text('selResultTotal', total);
      text('selResultPage', `${total ? offset + 1 : 0}–${Math.min(offset + pageSize, total)} / ${total}`);
      text('selRunCandidateMeta', `来源 ${data.source || '未提供'} · 数据时点 ${data.as_of || '未提供'} · 快照 ${data.data_snapshot_id || '未提供（运行输入未附快照）'}`);
      el('selResultPrev').disabled = offset === 0;
      el('selResultNext').disabled = offset + pageSize >= total;
      el('selResultBody').innerHTML = data.candidates.length ? data.candidates.map((candidate) => `<tr>
        <td class="sel-mono">${esc(candidate.code)}</td><td>${missing(candidate, 'name')}</td><td>${missing(candidate, 'industry')}</td>
        <td>${missing(candidate, 'price')}</td><td>${missing(candidate, 'change_pct')}</td><td>${esc(candidate.verdict)}</td><td>${renderCandidateEvidence(candidate)}</td>
        <td title="${esc(candidate.source || data.source || '来源未提供')}">${esc(candidate.price_as_of || candidate.as_of || '未提供')}</td></tr>`).join('')
        : '<tr><td colspan="8" class="sel-empty-row">当前筛选无候选</td></tr>';
    } catch (error) {
      if (current === generation) {
        S().stateViews.notifyError(error);
        el('selResultBody').innerHTML = `<tr><td colspan="8" class="sel-empty-row">${esc(S().stateViews.message(error))}</td></tr>`;
      }
    }
  }
  function applyFilters() { offset = 0; loadCandidates(); }
  function search(value) {
    if (searchTimer) global.clearTimeout(searchTimer);
    searchTimer = global.setTimeout(() => { keyword = value.trim(); applyFilters(); }, 250);
  }
  function page(direction) {
    const next = offset + direction * pageSize;
    if (next < 0 || next >= total) return;
    offset = next; loadCandidates();
  }
  async function exportCurrent() {
    if (!runId || !stageId) { global.showToast && global.showToast('请选择运行和阶段'); return; }
    const id = runId, stage = stageId;
    try {
      const blob = await S().api.exportRunCandidates(id, { stage_id: stage, verdict: el('selResultVerdict').value, keyword });
      if (id !== runId || stage !== stageId) return;
      const url = global.URL.createObjectURL(blob);
      const link = global.document.createElement('a');
      link.href = url; link.download = `${id}-${stage}-candidates.csv`; link.click();
      global.setTimeout(() => global.URL.revokeObjectURL(url), 1000);
    } catch (error) { global.showToast && global.showToast(error.message || '导出失败'); }
  }
  S().runWorkspace = { syncModel, selectRun, selectStage, applyFilters, search, page, exportCurrent, clear };
})(window);
