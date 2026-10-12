// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 规则调试面板（正式运行与调试运行严格隔离，发布门禁 10）。
 * 首层使用本地同步的市场股票，后续层使用上游通过候选；不落正式运行目录或发信号。
 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const A = () => global.SelModels.api;

  function open() {
    const modelId = global.SelModels.store.get().activeModelId;
    if (!modelId) { global.showToast && global.showToast('请先选择模型'); return; }
    close();
    const def = global.SelModels.store.get().workingDefinition || {};
    const stageOptions = collectStages(def).map((stage) => {
      const name = stage.name || stage.id;
      const label = name === stage.id ? name : `${name}（${stage.id}）`;
      return `<option value="${escapeHtml(stage.id)}">${escapeHtml(label)}</option>`;
    }).join('');
    const wrap = DOM().createElement('div');
    wrap.className = 'sel-modal-mask';
    wrap.id = 'selectionDebugModal';
    wrap.innerHTML = `
      <div class="sel-modal sel-modal-wide">
        <div class="sel-modal-head"><span>调试运行（不产生正式信号）</span>
          <button type="button" class="sel-close-btn" onclick="SelModels.debugPanel.close()">✕</button></div>
        <div class="sel-modal-body">
          <label class="sel-field"><span>调试对象</span>
            <select id="selDebugKind">
              <option value="node">阶段/节点</option>
              <option value="rule">单规则</option>
            </select></label>
          <label class="sel-field" id="selDebugNodeField"><span>阶段</span>
            <select id="selDebugStage">${stageOptions}</select></label>
          <label class="sel-field" id="selDebugRuleField" style="display:none"><span>规则</span>
            <select id="selDebugRule"></select></label>
          <div class="sel-debug-note">首层读取本地已同步的市场股票；后续层读取前一层通过的候选。数据未就绪时会显示水位原因。</div>
          <div id="selDebugResult" class="sel-debug-result"></div>
        </div>
        <div class="sel-modal-foot">
          <button type="button" class="sel-act-btn" onclick="SelModels.debugPanel.close()">关闭</button>
          <button type="button" class="sel-act-btn primary" onclick="SelModels.debugPanel.run()">执行调试</button>
        </div>
      </div>`;
    wrap.querySelector('#selDebugKind').addEventListener('change', (e) => {
      const isRule = e.target.value === 'rule';
      wrap.querySelector('#selDebugRuleField').style.display = isRule ? '' : 'none';
      wrap.querySelector('#selDebugNodeField').style.display = isRule ? 'none' : '';
    });
    wrap.querySelector('#selDebugStage').addEventListener('change', () => updateRules(wrap, def));
    updateRules(wrap, def);
    DOM().body.appendChild(wrap);
  }

  function collectRules(def, stageId) {
    if (def.model && def.model.model_type === 'condition_tree') {
      return (def.groups || []).flatMap((g) => g.rules || []).filter((rule) => rule.enabled !== false);
    }
    const stage = (def.stages || []).find((item) => item.id === stageId);
    return (stage ? stage.rules || [] : []).filter((rule) => rule.enabled !== false);
  }

  function collectStages(def) {
    if (def.model && def.model.model_type === 'condition_tree') {
      return [{ id: 'condition_filter', name: '条件筛选' }];
    }
    return def.stages || [];
  }

  function updateRules(wrap, def) {
    const stageId = wrap.querySelector('#selDebugStage').value;
    wrap.querySelector('#selDebugRule').innerHTML = collectRules(def, stageId).map((rule) => {
      const name = global.SelModels.ruleLibrary.displayName(rule);
      return `<option value="${escapeHtml(rule.id)}">${escapeHtml(name)}（${escapeHtml(rule.id)}）</option>`;
    }).join('');
  }

  async function run() {
    const modelId = global.SelModels.store.get().activeModelId;
    const out = DOM().getElementById('selDebugResult');
    const kind = DOM().getElementById('selDebugKind').value;
    const stageId = DOM().getElementById('selDebugStage').value;
    const ruleId = kind === 'rule' ? DOM().getElementById('selDebugRule').value : null;
    if (!stageId || (kind === 'rule' && !ruleId)) {
      global.SelModels.stateViews.error(out, { message: '请先选择可调试的阶段或规则' });
      return;
    }
    out.innerHTML = '<div class="sel-state sel-state-loading">正在读取同步数据并按层级预演…</div>';
    try {
      const definition = global.SelModels.store.get().workingDefinition;
      const resp = await A().debugNode(modelId, stageId, { definition, rule_id: ruleId });
      if (resp.status !== 'ok') {
        global.SelModels.stateViews.error(out, resp);
        if (resp.data) out.innerHTML += `<div class="sel-debug-json"><pre>${escapeHtml(JSON.stringify(resp.data, null, 2))}</pre></div>`;
        return;
      }
      const d = resp.data;
      const snapshot = d.snapshot || {};
      const current = d.result || {};
      const stages = (d.stages || []).map((item) =>
        `${item.name || item.stage_id}：输入 ${item.input_count}，通过 ${item.output_count}，${item.status}`).join(' → ');
      out.innerHTML = `<div class="sel-debug-note">本地同步快照 ${escapeHtml(snapshot.trade_date || '日期未提供')} · 市场股票 ${escapeHtml(snapshot.input_count == null ? '未提供' : snapshot.input_count)} 条 · 水位 ${escapeHtml(snapshot.gate_state || '未提供')} · 覆盖率门禁 ${escapeHtml(snapshot.coverage_passed == null ? '未提供' : snapshot.coverage_passed ? '通过' : '未通过')} · 仅调试，不发正式信号</div>
        <div class="sel-debug-summary">${escapeHtml(stages || '无已执行阶段')}</div>
        <div class="sel-debug-summary">${d.status === 'NOT_REACHED' ? `所选层未执行：上游 ${escapeHtml(d.blocked_by || '未知')} 已停止` : `所选层输入 ${escapeHtml(current.input_count)} · 通过 ${escapeHtml(current.output_count)} · 判定 ${escapeHtml(current.verdict)}`}</div>
        <div class="sel-debug-json"><pre>${escapeHtml(JSON.stringify(current.status ? current : d, null, 2))}</pre></div>`;
    } catch (err) {
      global.SelModels.stateViews.error(out, { message: err.message });
    }
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function close() {
    const modal = DOM().getElementById('selectionDebugModal');
    if (modal) modal.remove();
  }

  global.SelModels.debugPanel = { open, close, run };
})(window);
