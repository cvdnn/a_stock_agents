// -*- coding: utf-8 -*-
/** 选股模型工作台 · 版本管理（列表 / 差异 / 发布 / 激活 / 归档 / 复制到草稿）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;
  const A = () => global.SelModels.api;

  async function open() {
    const modelId = global.SelModels.store.get().activeModelId;
    if (!modelId) { global.showToast && global.showToast('请先选择模型'); return; }
    close();
    const wrap = DOM().createElement('div');
    wrap.className = 'sel-modal-mask';
    wrap.id = 'selectionVersionModal';
    wrap.innerHTML = `
      <div class="sel-modal sel-modal-wide">
        <div class="sel-modal-head"><span>版本管理</span>
          <button type="button" class="sel-close-btn" onclick="SelModels.versionManager.close()">✕</button></div>
        <div class="sel-modal-body" id="selVersionBody">
          <div class="sel-state sel-state-loading">加载中…</div></div>
        <div class="sel-modal-foot">
          <button type="button" class="sel-act-btn" onclick="SelModels.versionManager.close()">关闭</button>
          <button type="button" class="sel-act-btn primary" onclick="SelModels.versionManager.publish()">发布当前草稿</button>
        </div>
      </div>`;
    DOM().body.appendChild(wrap);
    const st = global.SelModels.store.get();
    const publishButton = wrap.querySelector('.sel-modal-foot .primary');
    const canPublish = !!((st.detail || {}).permissions || {}).publish;
    publishButton.disabled = !canPublish || !(st.detail && st.detail.draft);
    publishButton.title = !canPublish ? '当前身份无发布权限' :
      !(st.detail && st.detail.draft) ? '当前没有可发布的草稿' : '';
    await refresh();
  }

  async function refresh() {
    const modelId = global.SelModels.store.get().activeModelId;
    const body = DOM().getElementById('selVersionBody');
    if (!body) return;
    try {
      const resp = await A().listVersions(modelId);
      const data = global.SelModels.stateViews.unwrap(body, resp, { emptyLabel: '暂无发布版本' });
      if (!data) return;
      global.SelModels.store.set({ versions: data.versions });
      if (!data.versions.length) {
        global.SelModels.stateViews.empty(body, '该模型尚未发布任何版本');
        return;
      }
      body.innerHTML = `<table class="sel-version-table"><thead><tr>
          <th>版本</th><th>状态</th><th>plan_hash</th><th>发布时间</th><th>运行引用</th><th>操作</th>
        </tr></thead><tbody>${data.versions.map((v) => row(v, data.active_version)).join('')}</tbody></table>`;
    } catch (err) {
      global.SelModels.stateViews.error(body, { message: err.message });
    }
  }

  function row(v, activeVersion) {
    const isActive = String(v.version) === String(activeVersion);
    const permissions = ((global.SelModels.store.get().detail || {}).permissions || {});
    const activateReason = !permissions.activate ? '仅管理员或模型作者本人可激活' :
      v.status === 'ARCHIVED' ? '归档版本不能激活' : isActive ? '该版本已激活' : '';
    return `<tr>
      <td>v${v.version}${isActive ? '（活动）' : ''}</td>
      <td>${v.status}</td>
      <td class="sel-mono">${String(v.plan_hash || '').slice(0, 18)}…</td>
      <td>${v.published_at || '--'}</td>
      <td>${v.run_reference_count == null ? '--' : v.run_reference_count}</td>
      <td>
        <button type="button" class="sel-mini-btn" onclick="SelModels.versionManager.activate(${v.version})" ${activateReason ? 'disabled' : ''} title="${activateReason || '激活此版本'}">激活</button>
        <button type="button" class="sel-mini-btn" onclick="SelModels.versionManager.copyToDraft(${v.version})">复制到草稿</button>
        ${isActive ? '' : `<button type="button" class="sel-mini-btn" onclick="SelModels.versionManager.archive(${v.version})" ${permissions.publish ? '' : 'disabled'} title="${permissions.publish ? '归档此版本' : '当前身份无发布权限'}">归档</button>`}
      </td></tr>`;
  }

  async function publish() {
    let st = global.SelModels.store.get();
    if (!st.activeModelId) { global.showToast && global.showToast('请先选择模型'); return; }
    if (st.dirty) {
      if (!await global.SelModels.editorHelpers.save()) return;
      st = global.SelModels.store.get();
      if (st.dirty) { global.showToast && global.showToast('编辑内容又有变化，请重新发布'); return; }
    }
    if (!st.detail || !st.detail.draft) { global.showToast && global.showToast('当前没有可发布的草稿'); return; }
    try {
      const valid = await A().validate(st.activeModelId, st.workingDefinition);
      if (valid.status !== 'ok') { global.showToast && global.showToast(global.SelModels.stateViews.message(valid)); return; }
      const resp = await A().publish(st.activeModelId, st.draftBaseVersion, st.draftRevision);
      if (resp.status !== 'ok') { global.showToast && global.showToast(global.SelModels.stateViews.message(resp)); return; }
      global.showToast && global.showToast(`已发布 v${resp.data.version}`);
      await refresh();
      try {
        const models = await A().listModels();
        if (models.status === 'ok') global.SelModels.store.set({ models: models.data.models || [] });
        if (global.SelModels.detailLoader) await global.SelModels.detailLoader.load(st.activeModelId);
      } catch (refreshError) { global.SelModels.stateViews.notifyError(refreshError); }
    } catch (err) { global.showToast && global.showToast(err.message || '发布失败'); }
  }

  async function activate(version) {
    const id = global.SelModels.store.get().activeModelId;
    const resp = await A().activate(id, version);
    global.showToast && global.showToast(resp.status === 'ok' ? `已激活 v${version}` : global.SelModels.stateViews.message(resp));
    if (resp.status === 'ok') {
      const st = global.SelModels.store.get();
      st.detail.active_version = version;
      const model = global.SelModels.store.activeModel();
      if (model) model.active_version = version;
      global.SelModels.store.set({ detail: st.detail });
      global.SelModels.modelCenter.render();
    }
    await refresh();
  }

  async function archive(version) {
    const id = global.SelModels.store.get().activeModelId;
    const resp = await A().archive(id, version);
    global.showToast && global.showToast(resp.status === 'ok' ? `已归档 v${version}` : (resp.message || '归档失败'));
    await refresh();
  }

  async function copyToDraft(version) {
    if (!global.SelModels.store.confirmDiscard()) return;
    const current = global.SelModels.store.get();
    if (current.detail && current.detail.draft && !global.confirm(`复制 v${version} 将覆盖当前已保存草稿。继续吗？`)) return;
    const id = current.activeModelId;
    const resp = await A().copyToDraft(id, version, global.SelModels.store.get().draftRevision);
    if (resp.status !== 'ok') { global.showToast && global.showToast(global.SelModels.stateViews.message(resp)); return; }
    global.showToast && global.showToast(`已复制 v${version} 为草稿`);
    if (global.SelModels.detailLoader) global.SelModels.detailLoader.load(id);
  }

  function close() {
    const modal = DOM().getElementById('selectionVersionModal');
    if (modal) modal.remove();
  }

  global.SelModels.versionManager = { open, close, refresh, publish, activate, archive, copyToDraft };
})(window);
