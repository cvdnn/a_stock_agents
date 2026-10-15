// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 结果研究（阶段 E1 / SSOT §12.1）。
 *
 * 只呈现后端 `/runs/{run_id}/assessments` 的真实响应：个股信息、入选证据、风险画像与
 * 建仓持股策略均标注为「研究方案，非交易指令」；缺行情切片即失败关闭，本模块不补写任何数值。
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
    return DOM().getElementById('selResearchBody');
  }

  /** 用 store.runs 填充运行下拉框（数据来自后端运行记录，无记录时不预置任何示例）。 */
  function render() {
    const select = DOM().getElementById('selResearchRunSelect');
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
    if (currentRunId) load();
    else SV().empty(body(), '请选择一次运行后读取或生成结果研究评估');
  }

  async function load() {
    const box = body();
    if (!box) return;
    if (!currentRunId) { SV().empty(box, '请先选择一次运行'); return; }
    SV().loading(box, '读取结果研究评估…');
    try {
      const resp = await A().getAssessments(currentRunId);
      if (resp.status !== 'ok') { renderUnavailable(box, resp); return; }
      const data = resp.data || {};
      if (!data.generated || !data.assessment) {
        const wm = resp.watermark || {};
        SV().empty(box, wm.degraded_reason === 'ASSESSMENT_NOT_GENERATED'
          ? '该运行尚未生成结果研究评估，请点击「生成评估」'
          : '暂无真实结果研究评估');
        return;
      }
      renderAssessment(box, data.assessment);
    } catch (err) {
      SV().error(box, { message: err.message });
    }
  }

  /** 生成评估：候选行情切片由数据侧提供，前端未持有即由后端失败关闭，绝不伪造数值。 */
  async function generate() {
    const box = body();
    if (!box) return;
    if (!currentRunId) { global.showToast && global.showToast('请先选择一次运行'); return; }
    SV().loading(box, '提交结果研究评估请求…');
    try {
      const resp = await A().createAssessment(currentRunId, {});
      if (resp.status !== 'ok') { renderUnavailable(box, resp); return; }
      renderAssessment(box, resp.data.assessment);
    } catch (err) {
      SV().error(box, { message: err.message });
    }
  }

  /** 业务性不可用（HTTP 200 + error_code）与传输异常一律按水印如实提示。 */
  function renderUnavailable(box, resp) {
    const notice = SV().availabilityNotice(resp.watermark, resp.error_code);
    SV().error(box, { message: `${resp.message || '结果研究评估不可用'}${notice ? ' · ' + notice : ''}` });
  }

  function renderAssessment(box, payload) {
    const items = (payload && payload.assessments) || [];
    if (!items.length) {
      SV().empty(box, '本次运行没有锁存正式信号，无可研究的最终候选');
      return;
    }
    const notice = `${esc(payload.research_only_notice || '研究方案，非交易指令')}<br>${esc(payload.interpretation || '')}`;
    const rows = items.map((item, index) => {
      const sec = item.security || {};
      const ev = item.selection_evidence || {};
      const stages = (ev.hit_stages || []).join(' → ') || '--';
      return `<tr>
        <td class="tabular-nums">${index + 1}</td>
        <td class="sel-code-cell sel-mono">${esc(item.code)}</td>
        <td class="sel-name-cell">${esc(sec.name)}</td>
        <td>${esc(sec.board)}</td>
        <td>${esc(sec.trade_status)}</td>
        <td class="num tabular-nums">${fmt(sec.last_close)}</td>
        <td>${esc(stages)}</td>
        <td>${item.data_available ? '含行情切片' : '缺行情切片'}</td></tr>`;
    }).join('');
    const details = items.map((item) => renderDetail(item)).join('');
    box.innerHTML = `<div class="sel-stage-notice">${notice}</div>
      <div class="sel-stage-meta">评估时点：${esc(payload.assessment_as_of)} · 数据快照：${esc(payload.data_snapshot_id)} · 价格口径：${esc(payload.price_caliber)}</div>
      <table class="sel-version-table"><thead><tr>
        <th>排名</th><th>代码</th><th>名称</th><th>上市板</th><th>交易状态</th>
        <th class="num">最新收盘</th><th>命中层级</th><th>数据</th></tr></thead>
        <tbody>${rows}</tbody></table>
      <div class="sel-research-details">${details}</div>`;
  }

  function renderDetail(item) {
    const sec = item.security || {};
    const ev = item.selection_evidence || {};
    const profile = item.technical_risk_profile || {};
    const policy = item.position_policy || {};
    const markout = item.markout_analysis || {};
    const trading = item.trading_backtest || {};
    const history = item.history_behavior || {};
    const riskTags = (sec.risk_tags || []).join('、') || '--';
    const events = (sec.key_events || []);
    const eventText = events.length
      ? events.map((e) => esc(typeof e === 'string' ? e : (e.title || JSON.stringify(e)))).join('；')
      : '--';
    const trend = profile.trend || {};
    const profileBody = profile.available
      ? `趋势：MA20 ${fmt(trend.ma20)} · MA60 ${fmt(trend.ma60)} · 年化波动 ${fmt(profile.volatility_annualized_pct)}% · 动量 ${fmt(profile.momentum_20d_pct)}%`
      : `不可用（${esc(profile.reason_code || 'NO_DATA')}）`;
    const policyEntry = policy.entry || {};
    return `<details class="sel-research-detail">
      <summary>${esc(item.code)} · ${esc(sec.name)} 研究明细</summary>
      <div class="sel-research-detail-body">
        <div class="sel-research-block"><h4>个股信息</h4>
          <div>行业：${esc(sec.industry)} · 流通市值：${fmt(sec.circulating_market_cap)} · 数据时点：${esc(sec.as_of)}</div>
          <div>风险标签：${esc(riskTags)}</div>
          <div>关键事件：${eventText}</div></div>
        <div class="sel-research-block"><h4>入选证据（研究，非交易指令）</h4>
          <div>同批排名：${fmt(ev.rank_in_batch)} · 命中层级：${(ev.hit_stages || []).join(' → ') || '--'}</div>
          <div>通过规则数：${fmt((ev.passed_rules || []).length)}</div></div>
        <div class="sel-research-block"><h4>技术与风险画像</h4>
          <div>${profileBody}</div>
          <div>风险标记：${(profile.risk_flags || []).join('、') || '--'}</div></div>
        <div class="sel-research-block"><h4>历史行为 / 相对表现 / 跟踪可用性</h4>
          <div>相似信号：${fmt(history.similar_signal_count)} · 历史均值收益：${fmt(history.mean_return_pct)}%</div>
          <div>相对基准：${(item.relative_performance || {}).available ? '可用' : '不可用（' + esc((item.relative_performance || {}).reason_code || '') + '）'}</div>
          <div>markout：${markout.available ? '可用' : '不可用（' + esc(markout.reason_code || '') + '）'} · 事件回测：${trading.available ? '可用' : '不可用（' + esc(trading.reason_code || '') + '）'}</div></div>
        <div class="sel-research-block"><h4>建仓与持股策略（研究方案，非交易指令）</h4>
          <div>research_only：${policy.research_only === true ? '是' : '否'} · 计划入场价：${fmt(policyEntry.planned_entry_price)} · 保本价：${fmt(policy.breakeven_price)}</div>
          <div>待补充输入：${(policy.missing_inputs || []).join('、') || '无'}</div>
          <pre>${esc(JSON.stringify(policy, null, 2))}</pre></div>
      </div></details>`;
  }

  global.SelModels.resultAssessment = { render, selectRun, load, generate };
})(window);