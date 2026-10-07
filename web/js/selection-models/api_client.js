// -*- coding: utf-8 -*-
/**
 * 选股模型工作台 · API 客户端（C5 / SPEC-ALGO-ISS-001 §15）
 *
 * 严格浏览器传输：所有数据只来自后端 `/api/selection-models/*` 响应，不含任何本地兜底。
 * 复用 api.js 的 AStockAPI._fetchJSON（自动携带会话 Cookie）。
 */
(function (global) {
  'use strict';

  const API = global.AStockAPI;
  const BASE = '/api/selection-models';
  const enc = encodeURIComponent;

  function req(path, options) {
    return API._fetchJSON(BASE + path, options);
  }

  const SelectionApi = {
    listTypes: () => req('/types'),
    listRuleTypes: () => req('/rule-types'),
    listModels: (modelType) => req(modelType ? `?model_type=${enc(modelType)}` : ''),
    createModel: (payload) => req('', { method: 'POST', body: JSON.stringify(payload) }),
    fromText: (text) => req('/drafts/from-text', { method: 'POST', body: JSON.stringify({ text }) }),
    getModel: (id) => req(`/${enc(id)}`),
    saveDraft: (id, definition, baseVersion, draftRevision) => req(`/${enc(id)}/draft`, {
      method: 'PATCH',
      body: JSON.stringify({ definition, base_version: baseVersion, draft_revision: draftRevision }),
    }),
    validate: (id, definition) => req(`/${enc(id)}/validate`, {
      method: 'POST',
      body: JSON.stringify(definition ? { definition } : {}),
    }),
    listVersions: (id) => req(`/${enc(id)}/versions`),
    versionDiff: (id, from, to) => req(`/${enc(id)}/version-diff?from=${enc(from)}&to=${enc(to)}`),
    getVersion: (id, version) => req(`/${enc(id)}/versions/${enc(version)}`),
    publish: (id, baseVersion, draftRevision) => req(`/${enc(id)}/versions`, {
      method: 'POST',
      body: JSON.stringify({ base_version: baseVersion, draft_revision: draftRevision }),
    }),
    copyToDraft: (id, version, draftRevision) => req(`/${enc(id)}/versions/${enc(version)}/copy-to-draft`, {
      method: 'POST',
      body: JSON.stringify({ draft_revision: draftRevision }),
    }),
    archive: (id, version) => req(`/${enc(id)}/versions/${enc(version)}/archive`, { method: 'POST' }),
    activate: (id, version) => req(`/${enc(id)}/activate/${enc(version)}`, { method: 'POST' }),
    debugRule: (id, rule, records) => req(`/${enc(id)}/debug/rule`, {
      method: 'POST',
      body: JSON.stringify({ rule, records }),
    }),
    debugNode: (id, stageId, records) => req(`/${enc(id)}/debug/node`, {
      method: 'POST',
      body: JSON.stringify({ stage_id: stageId, records }),
    }),
    createRun: (id, payload) => req(`/${enc(id)}/runs`, { method: 'POST', body: JSON.stringify(payload || {}) }),
    listRuns: (id, query) => req(`/${enc(id)}/runs${query || ''}`),
    getRun: (runId) => req(`/runs/${enc(runId)}`),
    getRunNodes: (runId) => req(`/runs/${enc(runId)}/nodes`),
    getRunCandidates: (runId) => req(`/runs/${enc(runId)}/candidates`),
    cancelRun: (runId) => req(`/runs/${enc(runId)}/cancel`, { method: 'POST' }),
    eventsUrl: (runId) => `${BASE}/runs/${enc(runId)}/events`,
    getSchedule: (id) => req(`/${enc(id)}/schedule`),
    updateSchedule: (id, payload) => req(`/${enc(id)}/schedule`, { method: 'PUT', body: JSON.stringify(payload) }),
    pause: (id) => req(`/${enc(id)}/pause`, { method: 'POST' }),
    resume: (id) => req(`/${enc(id)}/resume`, { method: 'POST' }),
    results: (modelId, signalDate) => {
      const q = [];
      if (modelId) q.push(`model_id=${enc(modelId)}`);
      if (signalDate) q.push(`signal_date=${enc(signalDate)}`);
      return req(`/results${q.length ? '?' + q.join('&') : ''}`);
    },
    dataHealth: () => req('/data-health'),
    // 阶段 E：结果研究（E1） / 持续跟踪（E3） / 评价与调优（E4·E5）
    getAssessments: (runId) => req(`/runs/${enc(runId)}/assessments`),
    createAssessment: (runId, payload) => req(`/runs/${enc(runId)}/assessments`, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    }),
    createTrackingPlan: (payload) => req('/tracking-plans', {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    }),
    getTrackingPlan: (trackingId) => req(`/tracking-plans/${enc(trackingId)}`),
    getTrackingObservations: (trackingId) => req(`/tracking-plans/${enc(trackingId)}/observations`),
    createEvaluation: (modelId, payload) => req(`/${enc(modelId)}/evaluations`, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    }),
    getEvaluation: (modelId, evaluationId) => req(`/${enc(modelId)}/evaluations/${enc(evaluationId)}`),
    createTuningSuggestions: (modelId, payload) => req(`/${enc(modelId)}/tuning-suggestions`, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    }),
    listTuningSuggestions: (modelId) => req(`/${enc(modelId)}/tuning-suggestions`),
    markTuningStatus: (modelId, suggestionId, status) => req(
      `/${enc(modelId)}/tuning-suggestions/${enc(suggestionId)}/status`,
      { method: 'POST', body: JSON.stringify({ status }) },
    ),
  };

  global.SelModels = global.SelModels || {};
  global.SelModels.api = SelectionApi;
})(window);