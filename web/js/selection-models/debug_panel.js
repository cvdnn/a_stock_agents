// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 规则调试面板（正式运行与调试运行严格隔离，发布门禁 10）。
 * 只读取用户粘贴的记录做预演；不落正式运行目录、不发信号、水印标记为调试。
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
    const ruleOptions = collectRules(def).map((r) => `<option value="${r.id}">${r.id} · ${r.type}</option>`).join('');
    const stageOptions = collectStages(def).map((s) => `<option value="${s}">${s}</option>`).join('');
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
            <select id="selDebugRule">${ruleOptions}</select></label>
          <label class="sel-field"><span>输入记录（JSON 数组）</span>
            <textarea id="selDebugRecords" rows="6" placeholder='[{"code":"600001","closes":[...]}]'></textarea></label>
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
    DOM().body.appendChild(wrap);
  }

  function collectRules(def) {
    if (def.model && def.model.model_type === 'condition_tree') {
      return (def.groups || []).flatMap((g) => g.rules || []);
    }
    return (def.stages || []).flatMap((s) => s.rules || []);
  }

  function collectStages(def) {
    return (def.stages || []).map((s) => s.id);
  }

  async function run() {
    const modelId = global.SelModels.store.get().activeModelId;
    const out = DOM().getElementById('selDebugResult');
    let records;
    try {
      records = JSON.parse(DOM().getElementById('selDebugRecords').value || '[]');
      if (!Array.isArray(records)) throw new Error('记录必须是 JSON 数组');
    } catch (err) {
      global.SelModels.stateViews.error(out, { message: '输入记录解析失败：' + err.message });
      return;
    }
    const kind = DOM().getElementById('selDebugKind').value;
    out.innerHTML = '<div class="sel-state sel-state-loading">调试中…</div>';
    try {
      let resp;
      if (kind === 'rule') {
        const ruleId = DOM().getElementById('selDebugRule').value;
        const rule = collectRules(global.SelModels.store.get().workingDefinition || {}).find((r) => r.id === ruleId);
        resp = await A().debugRule(modelId, rule, records);
      } else {
        const stageId = DOM().getElementById('selDebugStage').value;
        resp = await A().debugNode(modelId, stageId, records);
      }
      if (resp.status !== 'ok') { global.SelModels.stateViews.error(out, resp); return; }
      const d = resp.data;
      out.innerHTML = `<div class="sel-debug-note">调试水印：eligible_for_signal=${resp.watermark.eligible_for_signal}</div>
        <div class="sel-debug-summary">输入 ${d.input_count} · 通过 ${d.output_count} · 判定 ${d.verdict}</div>
        <div class="sel-debug-json"><pre>${escapeHtml(JSON.stringify(d, null, 2))}</pre></div>`;
    } catch (err) {
      global.SelModels.stateViews.error(out, { message: err.message });
    }
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  }

  function close() {
    const modal = DOM().getElementById('selectionDebugModal');
    if (modal) modal.remove();
  }

  global.SelModels.debugPanel = { open, close, run };
})(window);