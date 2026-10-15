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
  function candidateQuery(filters) {
    const params = new URLSearchParams();
    Object.entries(filters || {}).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') params.set(key, value);
    });
    return params.toString() ? `?${params.toString()}` : '';
  }

  async function req(path, options) {
    try {
      const response = await API._fetchJSON(BASE + path, options);
      if (response && response.status === 'error') {
        global.SelModels.stateViews.notifyError(response);
      }
      return response;
    } catch (err) {
      const detail = err && err.detail && err.detail.detail;
      const status = err && err.status;
      const message = detail && typeof detail === 'object' && detail.message
        ? detail.message : (typeof detail === 'string' ? detail : err.message);
      const normalized = new Error(message || '选股模型请求失败');
      normalized.status = status;
      normalized.status_code = status;
      normalized.error_code = (detail && detail.error) || err.code || 'REQUEST_FAILED';
      global.SelModels.stateViews.notifyError(normalized);
      throw normalized;
    }
  }

  const SelectionApi = {
    listTypes: () => req('/types'),
    listRuleTypes: () => req('/rule-types'),
    listModels: (modelType) => req(modelType ? `?model_type=${enc(modelType)}` : ''),
    createModel: (payload) => req('', { method: 'POST', body: JSON.stringify(payload) }),
    fromText: (text, options = {}) => req('/drafts/from-text', {
      method: 'POST', body: JSON.stringify({ text, ...options }),
    }),
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
    debugNode: (id, stageId, options) => req(`/${enc(id)}/debug/node`, {
      method: 'POST',
      body: JSON.stringify({ stage_id: stageId, ...(options || {}) }),
    }),
    createRun: (id, payload) => req(`/${enc(id)}/runs`, { method: 'POST', body: JSON.stringify(payload || {}) }),
    listRecentRuns: (limit = 50) => req(`/runs?limit=${enc(limit)}`),
    listRuns: (id, query) => req(`/${enc(id)}/runs${query || ''}`),
    getRun: (runId) => req(`/runs/${enc(runId)}`),
    getRunNodes: (runId) => req(`/runs/${enc(runId)}/nodes`),
    getRunCandidates: (runId, filters) => req(`/runs/${enc(runId)}/candidates${candidateQuery(filters)}`),
    exportRunCandidates: async (runId, filters) => {
      const url = `${API.baseUrl}${BASE}/runs/${enc(runId)}/candidates/export${candidateQuery(filters)}`;
      const response = await global.fetch(url, { credentials: 'same-origin' });
      if (!response.ok || !String(response.headers.get('content-type') || '').includes('text/csv')) {
        const detail = await response.json();
        throw new Error(detail.message || detail.detail?.message || '导出失败');
      }
      return response.blob();
    },
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
