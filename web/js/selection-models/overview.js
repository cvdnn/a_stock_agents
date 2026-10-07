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
    setText('selDetailModelName', model ? model.name : '--');
    const status = DOM().getElementById('selDetailStatus');
    if (status) {
      if (!model) {
        status.className = 'sel-status-badge status-pending';
        status.innerText = '○ 未选择模型';
      } else {
        const active = model.active_version != null;
        status.className = 'sel-status-badge ' + (active ? 'status-active' : 'status-pending');
        status.innerText = active ? `已激活 v${model.active_version}` : '未激活';
      }
    }
    const sched = st.schedule || {};
    setText('selNextRunAt', sched.next_run_at || '--');
    const wm = (st.dataHealth && st.dataHealth.watermark) || null;
    setText('selDataWatermark', wm ? wm.availability : '--');
  }

  global.SelModels.overview = { render };
})(window);