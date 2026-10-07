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
    return `<tr>
      <td>v${v.version}${isActive ? '（活动）' : ''}</td>
      <td>${v.status}</td>
      <td class="sel-mono">${String(v.plan_hash || '').slice(0, 18)}…</td>
      <td>${v.published_at || '--'}</td>
      <td>${v.run_reference_count == null ? '--' : v.run_reference_count}</td>
      <td>
        <button type="button" class="sel-mini-btn" onclick="SelModels.versionManager.activate(${v.version})">激活</button>
        <button type="button" class="sel-mini-btn" onclick="SelModels.versionManager.copyToDraft(${v.version})">复制到草稿</button>
        ${isActive ? '' : `<button type="button" class="sel-mini-btn" onclick="SelModels.versionManager.archive(${v.version})">归档</button>`}
      </td></tr>`;
  }

  async function publish() {
    const st = global.SelModels.store.get();
    const model = global.SelModels.store.activeModel();
    try {
      const resp = await A().publish(st.activeModelId, model && model.active_version != null ? model.active_version : null, st.draftRevision || 0);
      if (resp.status !== 'ok') { global.showToast && global.showToast(resp.message || '发布失败'); return; }
      global.showToast && global.showToast(`已发布 v${resp.data.version}`);
      await refresh();
    } catch (err) { global.showToast && global.showToast(err.message || '发布失败'); }
  }

  async function activate(version) {
    const id = global.SelModels.store.get().activeModelId;
    const resp = await A().activate(id, version);
    global.showToast && global.showToast(resp.status === 'ok' ? `已激活 v${version}` : (resp.message || '激活失败'));
    await refresh();
  }

  async function archive(version) {
    const id = global.SelModels.store.get().activeModelId;
    const resp = await A().archive(id, version);
    global.showToast && global.showToast(resp.status === 'ok' ? `已归档 v${version}` : (resp.message || '归档失败'));
    await refresh();
  }

  async function copyToDraft(version) {
    const id = global.SelModels.store.get().activeModelId;
    const resp = await A().copyToDraft(id, version, global.SelModels.store.get().draftRevision || 0);
    if (resp.status !== 'ok') { global.showToast && global.showToast(resp.message || '复制失败'); return; }
    global.showToast && global.showToast(`已复制 v${version} 为草稿`);
    if (global.SelModels.detailLoader) global.SelModels.detailLoader.load(id);
  }

  function close() {
    const modal = DOM().getElementById('selectionVersionModal');
    if (modal) modal.remove();
  }

  global.SelModels.versionManager = { open, close, refresh, publish, activate, archive, copyToDraft };
})(window);