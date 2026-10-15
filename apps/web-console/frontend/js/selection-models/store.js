// -*- coding: utf-8 -*-
/** 选股模型工作台 · 内存状态与订阅（C5）。不持久化、不缓存业务数据到 localStorage。 */
(function (global) {
  'use strict';

  const state = {
    types: [],
    ruleTypes: [],
    models: [],
    listPermissions: {},
    selectionMode: 'runs',
    recentRuns: [],
    activeModelId: null,
    detail: null,
    workingDefinition: null,
    draftBaseVersion: null,
    draftRevision: 0,
    dirty: false,
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
    setDraft: (detail, definition) => {
      const draft = detail && detail.draft;
      Store.set({ workingDefinition: definition || null,
        draftBaseVersion: draft ? draft.base_version : (detail ? detail.active_version : null),
        draftRevision: draft ? draft.draft_revision : 0, dirty: false });
    },
    markDirty: () => Store.set({ dirty: true }),
    confirmDiscard: () => !state.dirty || global.confirm('当前模型有未保存的修改。放弃修改并继续吗？'),
    subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); },
    activeModel: () => state.models.find((m) => m.model_id === state.activeModelId) || null,
  };

  global.SelModels = global.SelModels || {};
  global.SelModels.store = Store;
})(window);
