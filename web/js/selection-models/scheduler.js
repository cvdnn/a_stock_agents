// -*- coding: utf-8 -*-
/** 选股模型工作台 · 调度中心（时间窗 / 下一执行 / 暂停恢复 / 时间窗覆盖）。 */
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
    wrap.id = 'selectionScheduleModal';
    wrap.innerHTML = `
      <div class="sel-modal sel-modal-wide">
        <div class="sel-modal-head"><span>调度中心</span>
          <button type="button" class="sel-close-btn" onclick="SelModels.scheduler.close()">✕</button></div>
        <div class="sel-modal-body" id="selScheduleBody">
          <div class="sel-state sel-state-loading">加载中…</div></div>
        <div class="sel-modal-foot">
          <button type="button" class="sel-act-btn" onclick="SelModels.scheduler.togglePause()">暂停 / 恢复</button>
          <button type="button" class="sel-act-btn primary" onclick="SelModels.scheduler.save()">保存时间窗</button>
        </div>
      </div>`;
    DOM().body.appendChild(wrap);
    await refresh();
  }

  async function refresh() {
    const modelId = global.SelModels.store.get().activeModelId;
    const body = DOM().getElementById('selScheduleBody');
    if (!body) return;
    try {
      const resp = await A().getSchedule(modelId);
      const data = global.SelModels.stateViews.unwrap(body, resp, { emptyLabel: '无调度定义' });
      if (!data) return;
      global.SelModels.store.set({ schedule: data });
      const wm = resp.watermark;
      body.innerHTML = `
        <div class="sel-schedule-head">
          <span class="sel-status-badge ${data.paused ? 'status-pending' : 'status-active'}">${data.paused ? '已暂停' : '运行中'}</span>
          <span>下一执行：${data.next_run_at || '今日无更多窗口'}</span>
          <span class="sel-schedule-wm">水印：${wm ? wm.availability : '--'}</span>
        </div>
        <table class="sel-version-table"><thead><tr><th>阶段</th><th>时间窗</th><th>启停</th></tr></thead>
          <tbody>${(data.windows || []).map((w) => `<tr>
            <td>${w.stage_id}</td>
            <td><input type="text" class="sel-inline-input" data-window-stage="${w.stage_id}"
              value="${(data.overrides && data.overrides[w.stage_id]) || (w.start + '-' + w.end)}" /></td>
            <td>${w.enabled ? '启用' : '停用'}</td></tr>`).join('') || '<tr><td colspan="3">无时间窗</td></tr>'}</tbody></table>`;
      if (global.SelModels.overview) global.SelModels.overview.render();
    } catch (err) {
      global.SelModels.stateViews.error(body, { message: err.message });
    }
  }

  async function save() {
    const modelId = global.SelModels.store.get().activeModelId;
    const stages = {};
    DOM().querySelectorAll('[data-window-stage]').forEach((el) => {
      stages[el.getAttribute('data-window-stage')] = el.value.trim();
    });
    const resp = await A().updateSchedule(modelId, { stages });
    global.showToast && global.showToast(resp.status === 'ok' ? '时间窗已保存' : (resp.message || '保存失败'));
    await refresh();
  }

  async function togglePause() {
    const modelId = global.SelModels.store.get().activeModelId;
    const paused = !!(global.SelModels.store.get().schedule || {}).paused;
    const resp = paused ? await A().resume(modelId) : await A().pause(modelId);
    global.showToast && global.showToast(resp.status === 'ok' ? (paused ? '已恢复' : '已暂停') : (resp.message || '操作失败'));
    await refresh();
  }

  function close() {
    const modal = DOM().getElementById('selectionScheduleModal');
    if (modal) modal.remove();
  }

  global.SelModels.scheduler = { open, close, refresh, save, togglePause };
})(window);