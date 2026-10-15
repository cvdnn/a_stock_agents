// -*- coding: utf-8 -*-
/** 选股模型工作台 · 总览头（模型名 / 状态 / 活动版本 / 下一执行 / 数据水印）。 */
(function (global) {
  'use strict';

  const DOM = () => global.document;

  function setText(id, value) {
    const el = DOM().getElementById(id);
    if (el) el.innerText = value == null ? '--' : String(value);
  }

  function render() {
    const st = global.SelModels.store.get();
    const model = global.SelModels.store.activeModel();
    const isRunMode = st.selectionMode === 'runs';
    const selectedRun = isRunMode ? (st.recentRuns || []).find((run) => run.run_id === st.activeRunId) : null;
    setText('selDetailModelName', isRunMode && !selectedRun ? '尚未新建选股' : (model ? model.name : '--'));
    const status = DOM().getElementById('selDetailStatus');
    if (status) {
      if (isRunMode && selectedRun) {
        status.className = 'sel-status-badge ' + (selectedRun.status === 'COMPLETED' ? 'status-done' : 'status-pending');
        status.innerText = `v${selectedRun.model_version} · ${selectedRun.status}`;
      } else if (!model || isRunMode) {
        status.className = 'sel-status-badge status-pending';
        status.innerText = '○ 未选择模型';
      } else {
        const active = model.active_version != null;
        status.className = 'sel-status-badge ' + (active ? 'status-active' : 'status-pending');
        status.innerText = active ? `已激活 v${model.active_version}` : '未激活';
      }
    }
    const sched = st.schedule || {};
    setText('selDraftState', model ? (st.detail && st.detail.has_draft ? '有草稿' : '无草稿') : '--');
    setText('selPlanState', model ? (sched.paused ? '已暂停' : '未暂停') : '--');
    setText('selDaemonState', model ? ((sched.daemon || {}).online ? '在线' : '离线或未启动') : '--');
    const latestRun = (st.runs || [])[0];
    setText('selRunState', model ? (latestRun ? `${latestRun.status} · ${latestRun.run_id}` : '尚无运行') : '--');
    setText('selNextRunAt', sched.next_run_at || '--');
    const wm = (st.dataHealth && st.dataHealth.watermark) || null;
    setText('selDataWatermark', wm ? wm.availability : '--');
    setText('selSelectionHint', selectedRun
      ? `${selectedRun.started_at || selectedRun.created_at || '时间未提供'} · 使用已发布版本 v${selectedRun.model_version}`
      : '点击左侧“新建选股”，选择已发布模型即可直接运行');
    DOM().querySelectorAll('[data-sel-action]').forEach((button) => {
      const action = button.getAttribute('data-sel-action');
      const permissions = (st.detail && st.detail.permissions) || {};
      let reason = !st.detail ? '请先选择模型并等待加载完成' :
        !permissions[action === 'rerun' ? 'run' : action] ? `当前身份无 ${action} 权限` : '';
      if (!reason && action === 'rerun' && !selectedRun) reason = '请先选择一条选股记录';
      if (!reason && action === 'publish' && !st.detail.draft) reason = '当前没有可发布的草稿';
      if (!button.hasAttribute('data-enabled-title')) button.setAttribute('data-enabled-title', button.title);
      button.disabled = !!reason;
      button.title = reason || button.getAttribute('data-enabled-title');
    });
  }

  global.SelModels.overview = { render };
})(window);
