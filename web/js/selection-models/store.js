// -*- coding: utf-8 -*-
/** 选股模型工作台 · 内存状态与订阅（C5）。不持久化、不缓存业务数据到 localStorage。 */
(function (global) {
  'use strict';

  const state = {
    types: [],
    ruleTypes: [],
    models: [],
    activeModelId: null,
    detail: null,
    versions: [],
    runs: [],
    activeRunId: null,
    nodes: [],
    candidates: [],
    results: [],
    schedule: null,
    dataHealth: null,
    loading: false,
    error: null,
  };

  const listeners = new Set();

  const Store = {
    get: () => state,
    set: (patch) => {
      Object.assign(state, patch);
      listeners.forEach((fn) => { try { fn(state); } catch (_) { /* listener isolated */ } });
    },
    subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); },
    activeModel: () => state.models.find((m) => m.model_id === state.activeModelId) || null,
  };

  global.SelModels = global.SelModels || {};
  global.SelModels.store = Store;
})(window);