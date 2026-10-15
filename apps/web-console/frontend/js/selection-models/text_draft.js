// -*- coding: utf-8 -*-
/** 选股模型工作台 · 文案草稿解析（§15.1 drafts/from-text）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  let parsedDraft = null;
  let parseSequence = 0;
  const escapeHtml = (value) => String(value == null ? '' : value)
    .replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

  function open() {
    parsedDraft = null;
    ++parseSequence;
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
          <label class="sel-field"><span>解析方式</span><select id="selTextDraftMode">
            <option value="llm">大语言模型</option><option value="local">本地基础解析</option>
          </select></label>
          <label class="sel-field"><span>LLM 模型标识（可选，留空使用量化角色）</span>
            <input id="selTextDraftModel" type="text" maxlength="150" placeholder="例如已配置的 DeepSeek 或 GLM 模型标识" /></label>
          <div id="selTextDraftResult" class="sel-text-draft-result"></div>
        </div>
        <div class="sel-modal-foot">
          <button type="button" class="sel-act-btn" onclick="SelModels.textDraft.close()">关闭</button>
          <button type="button" id="selTextDraftSave" class="sel-act-btn" disabled onclick="SelModels.textDraft.save()">创建草稿</button>
          <button type="button" class="sel-act-btn primary" onclick="SelModels.textDraft.parse()">解析</button>
        </div>
      </div>`;
    DOM().body.appendChild(wrap);
    const invalidate = () => {
      ++parseSequence;
      parsedDraft = null;
      wrap.querySelector('#selTextDraftSave').disabled = true;
      wrap.querySelector('#selTextDraftResult').textContent = '';
    };
    wrap.querySelector('#selTextDraftInput').addEventListener('input', invalidate);
    wrap.querySelector('#selTextDraftMode').addEventListener('change', invalidate);
    wrap.querySelector('#selTextDraftModel').addEventListener('input', invalidate);
  }

  async function parse() {
    const input = DOM().getElementById('selTextDraftInput');
    const out = DOM().getElementById('selTextDraftResult');
    if (!input || !out) return;
    parsedDraft = null;
    const sequence = ++parseSequence;
    const saveButton = DOM().getElementById('selTextDraftSave');
    if (saveButton) saveButton.disabled = true;
    const text = input.value.trim();
    if (!text) { out.innerHTML = '<div class="sel-state sel-state-empty">请输入选股文案</div>'; return; }
    out.innerHTML = '<div class="sel-state sel-state-loading">解析中…</div>';
    try {
      const mode = DOM().getElementById('selTextDraftMode').value;
      const model = DOM().getElementById('selTextDraftModel').value.trim();
      const resp = await global.SelModels.api.fromText(text, { mode, ...(mode === 'llm' && model ? { model } : {}) });
      if (sequence !== parseSequence || !DOM().getElementById('selectionTextDraftModal')) return;
      if (resp.status !== 'ok') {
        global.SelModels.stateViews.error(out, resp);
        return;
      }
      const data = resp.data;
      const matched = (data.matched_rules || []).map((item) => {
        const rule = item.rule || item;
        return `<li>${escapeHtml(item.text || '')} → ${escapeHtml(rule.type)} · ${escapeHtml(rule.id)}</li>`;
      }).join('');
      const amb = (data.ambiguities || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
      const complete = data.complete === true && !data.ambiguities?.length;
      if (mode === 'llm' && complete && data.definition && matched) {
        parsedDraft = data;
        if (saveButton) saveButton.disabled = false;
      }
      out.innerHTML = `
        <div class="sel-text-draft-note">解析方式：${escapeHtml(data.parser_mode || mode)}${data.model_name ? ` · ${escapeHtml(data.model_name)}` : ''}</div>
        <div class="sel-text-draft-block"><strong>已识别规则</strong>
          <ul>${matched || '<li>无</li>'}</ul></div>
        <div class="sel-text-draft-block"><strong>待人工确认（歧义）</strong>
          <ul>${amb || '<li>无</li>'}</ul></div>
        <div class="sel-text-draft-note">${complete ? '已完成解析，可创建未激活草稿。' : '条件尚未完整解析，请修改文案后重试或进入编辑器手工配置。'}</div>`;
    } catch (err) {
      if (sequence !== parseSequence || !DOM().getElementById('selectionTextDraftModal')) return;
      global.SelModels.stateViews.error(out, { message: err.message });
    }
  }

  async function save() {
    if (!parsedDraft || parsedDraft.parser_mode !== 'llm' || parsedDraft.complete !== true) return;
    if (!global.SelModels.store.confirmDiscard()) return;
    const button = DOM().getElementById('selTextDraftSave');
    if (button) button.disabled = true;
    try {
      const definition = JSON.parse(JSON.stringify(parsedDraft.definition));
      const name = definition.model.name || 'LLM 选股草稿';
      const created = await global.SelModels.api.createModel({ model_type: 'funnel', name, template: 'blank' });
      if (created.status !== 'ok') throw new Error(created.message || '创建模型失败');
      const model = created.data;
      definition.model.id = model.model_id;
      definition.model.name = name;
      const saved = await global.SelModels.api.saveDraft(
        model.model_id, definition, model.base_version, model.draft_revision,
      );
      if (saved.status !== 'ok') throw new Error(`模型 ${model.model_id} 已创建，但保存规则失败：${saved.message || saved.error_code}`);
      parsedDraft = null;
      close();
      global.SelModels.store.set({ selectionMode: 'models' });
      await global.SelModels.bootstrap();
      global.SelModels.modelCenter.select(model.model_id);
    } catch (err) {
      const out = DOM().getElementById('selTextDraftResult');
      if (out) global.SelModels.stateViews.error(out, { message: err.message });
      if (button) button.disabled = false;
    }
  }

  function close() {
    ++parseSequence;
    parsedDraft = null;
    const modal = DOM().getElementById('selectionTextDraftModal');
    if (modal) modal.remove();
  }

  global.SelModels.textDraft = { open, close, parse, save };
})(window);
