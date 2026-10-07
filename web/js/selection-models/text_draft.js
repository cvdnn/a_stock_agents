// -*- coding: utf-8 -*-
/** 选股模型工作台 · 文案草稿解析（§15.1 drafts/from-text）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;

  function open() {
    const existing = DOM().getElementById('selectionTextDraftModal');
    if (existing) existing.remove();
    const wrap = DOM().createElement('div');
    wrap.className = 'sel-modal-mask';
    wrap.id = 'selectionTextDraftModal';
    wrap.innerHTML = `
      <div class="sel-modal">
        <div class="sel-modal-head"><span>文案解析为草稿</span>
          <button type="button" class="sel-close-btn" onclick="SelModels.textDraft.close()">✕</button></div>
        <div class="sel-modal-body">
          <textarea id="selTextDraftInput" rows="5" placeholder="例如：20日新高，高于60日均线，排除ST"></textarea>
          <div id="selTextDraftResult" class="sel-text-draft-result"></div>
        </div>
        <div class="sel-modal-foot">
          <button type="button" class="sel-act-btn" onclick="SelModels.textDraft.close()">关闭</button>
          <button type="button" class="sel-act-btn primary" onclick="SelModels.textDraft.parse()">解析</button>
        </div>
      </div>`;
    DOM().body.appendChild(wrap);
  }

  async function parse() {
    const input = DOM().getElementById('selTextDraftInput');
    const out = DOM().getElementById('selTextDraftResult');
    if (!input || !out) return;
    const text = input.value.trim();
    if (!text) { out.innerHTML = '<div class="sel-state sel-state-empty">请输入选股文案</div>'; return; }
    out.innerHTML = '<div class="sel-state sel-state-loading">解析中…</div>';
    try {
      const resp = await global.SelModels.api.fromText(text);
      if (resp.status !== 'ok') {
        global.SelModels.stateViews.error(out, resp);
        return;
      }
      const data = resp.data;
      const matched = (data.matched_rules || []).map((r) => `<li>${r.type} · ${r.id}</li>`).join('');
      const amb = (data.ambiguities || []).map((a) => `<li>${a}</li>`).join('');
      out.innerHTML = `
        <div class="sel-text-draft-block"><strong>已识别规则</strong>
          <ul>${matched || '<li>无</li>'}</ul></div>
        <div class="sel-text-draft-block"><strong>待人工确认（歧义）</strong>
          <ul>${amb || '<li>无</li>'}</ul></div>
        <div class="sel-text-draft-note">草稿未激活；需进入编辑器补充后保存并发布。</div>`;
    } catch (err) {
      global.SelModels.stateViews.error(out, { message: err.message });
    }
  }

  function close() {
    const modal = DOM().getElementById('selectionTextDraftModal');
    if (modal) modal.remove();
  }

  global.SelModels.textDraft = { open, close, parse };
})(window);