// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · 四态渲染基元（loading / empty / error / success）。
 * 无数据一律如实空态，不伪造任何数值（SPEC-ALGO-ISS-001 §17.2）。
 */
(function (global) {
  'use strict';

  const UNAVAILABLE = '选股模型接口暂不可用';
  const EMPTY = '暂无真实数据';

  function loading(container, label) {
    if (container) container.innerHTML = `<div class="sel-state sel-state-loading">${label || '加载中…'}</div>`;
  }

  function empty(container, label) {
    if (container) container.innerHTML = `<div class="sel-state sel-state-empty">${label || EMPTY}</div>`;
  }

  function error(container, payload) {
    const msg = (payload && (payload.message || payload.error_code)) || UNAVAILABLE;
    if (container) container.innerHTML = `<div class="sel-state sel-state-error">${msg}</div>`;
  }

  /** 统一处理 `{status, data, error_code, watermark}` 包裹：返回 data 或 null（空态/错误已渲染）。 */
  function unwrap(container, resp, opts) {
    const options = opts || {};
    if (!resp || resp.status !== 'ok' || resp.data === null || resp.data === undefined) {
      const code = resp && resp.error_code;
      if (code === 'MODEL_VERSION_NOT_FOUND' || code === 'MODEL_RUN_NOT_FOUND') {
        empty(container, options.emptyLabel);
      } else {
        error(container, resp);
      }
      return null;
    }
    const availability = resp.watermark && resp.watermark.availability;
    if (container && availability && availability !== 'ok' && options.showDegraded) {
      container.setAttribute('data-degraded', availability);
    }
    return resp.data;
  }

  /** 水印是否允许发正式信号（Web 只展示研究结果，不做交易动作）。 */
  function signalEligible(watermark) {
    return !!(watermark && watermark.eligibility !== false && watermark.eligible_for_signal);
  }

  /** 由响应水印 + `error_code` 生成如实的「不可用 / 降级」提示文案（无异常时返回空串）。 */
  function availabilityNotice(watermark, errorCode) {
    const wm = watermark || {};
    if (wm.availability === 'unsupported') {
      return `接口不可用（${errorCode || wm.degraded_reason || 'UNSUPPORTED'}）`;
    }
    if (wm.availability === 'degraded') {
      return `数据已降级：${wm.degraded_reason || errorCode || 'DEGRADED'}（不可发正式信号）`;
    }
    return errorCode ? `错误码：${errorCode}` : '';
  }

  global.SelModels = global.SelModels || {};
  global.SelModels.stateViews = {
    loading, empty, error, unwrap, signalEligible, availabilityNotice, UNAVAILABLE, EMPTY,
  };
})(window);