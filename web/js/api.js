// -*- coding: utf-8 -*-
/** Strict browser transport. Production data comes only from backend responses. */

const AStockAPI = {
  baseUrl: '',

  async _fetchJSON(endpoint, options = {}) {
    const resp = await fetch(this.baseUrl + endpoint, {
      ...options,
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...(options.headers || {})
      }
    });
    if (!resp.ok) {
      let detail = null;
      try { detail = await resp.json(); } catch (_) { /* response had no JSON body */ }
      const error = new Error(
        (detail && (detail.detail || detail.error)) || `HTTP ${resp.status}: ${resp.statusText}`
      );
      error.code = (detail && detail.error) || 'HTTP_ERROR';
      error.status = resp.status;
      error.detail = detail;
      throw error;
    }
    try {
      return await resp.json();
    } catch (_) {
      const error = new Error('Server returned malformed JSON');
      error.code = 'MALFORMED_RESPONSE';
      throw error;
    }
  },

  getMarketIndices() { return this._fetchJSON('/api/market/indices'); },
  getMarketSentiment() { return this._fetchJSON('/api/market/sentiment'); },
  getMarketKline(code = '000001', period = 'day') {
    return this._fetchJSON(`/api/market/kline?code=${encodeURIComponent(code)}&period=${encodeURIComponent(period)}`);
  },
  getMarketRanks() { return this._fetchJSON('/api/market/ranks'); },
  getPortfolioOverview() { return this._fetchJSON('/api/portfolio/overview'); },
  getPortfolioAnalysis() { return this._fetchJSON('/api/portfolio/analysis'); },
  getWatchlist(activeCode = '') {
    return this._fetchJSON(`/api/watchlist?active_code=${encodeURIComponent(activeCode)}`);
  },
  getMonitorStream() { return this._fetchJSON('/api/monitor/stream'); },

  async listSessions(limit = 30, offset = 0) {
    const data = await this._fetchJSON(`/api/chat/sessions?limit=${limit}&offset=${offset}`);
    return Array.isArray(data.sessions) ? data.sessions : [];
  },

  createSession(title = '新投研对话', model = null, meta = {}) {
    const payload = { title, meta };
    if (model) payload.model = model;
    return this._fetchJSON('/api/chat/sessions', { method: 'POST', body: JSON.stringify(payload) });
  },

  deleteSession(sessionId) {
    return this._fetchJSON(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  },

  async streamChatCompletions(message, sessionId, model = null, callbacks = {}) {
    const {
      onStart = () => {}, onThought = () => {}, onToolStart = () => {},
      onToolComplete = () => {}, onDelta = () => {}, onRiskCard = () => {},
      onDone = () => {}, onError = () => {}
    } = callbacks;
    let terminal = false;
    const fail = (error) => {
      if (terminal) return false;
      terminal = true;
      onError(error);
      return false;
    };
    const complete = (data) => {
      if (terminal) return;
      terminal = true;
      onDone(data);
    };

    try {
      const payload = { message, session_id: sessionId, tools_enabled: true };
      if (model) payload.model = model;
      const resp = await fetch(this.baseUrl + '/api/chat/completions/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        const error = new Error(`SSE connection failed with HTTP ${resp.status}`);
        error.code = 'SSE_HTTP_ERROR';
        error.status = resp.status;
        return fail(error);
      }
      if (!resp.body || typeof resp.body.getReader !== 'function') {
        const error = new Error('SSE response body is unavailable');
        error.code = 'SSE_BODY_UNAVAILABLE';
        return fail(error);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      const processBlock = (block) => {
        if (!block.trim() || terminal) return;
        let eventName = 'message';
        const dataLines = [];
        for (const line of block.split(/\r?\n/)) {
          if (line.startsWith('event:')) eventName = line.slice(6).trim();
          if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
        }
        if (!dataLines.length) return;
        let data;
        try { data = JSON.parse(dataLines.join('\n')); }
        catch (_) {
          const error = new Error('Malformed SSE JSON payload');
          error.code = 'MALFORMED_SSE';
          fail(error);
          return;
        }
        if (eventName === 'conversation_start') onStart(data);
        else if (eventName === 'thought') onThought(data.thought || data.content || '');
        else if (eventName === 'tool_call_start') onToolStart(data);
        else if (eventName === 'tool_call_complete') onToolComplete(data);
        else if (eventName === 'content_delta') onDelta(data.delta || data.content || data.text || '');
        else if (eventName === 'risk_card') onRiskCard(data);
        else if (eventName === 'error') {
          const error = new Error(data.error || 'Agent execution failed');
          error.code = data.code || 'AGENT_ERROR';
          error.detail = data;
          fail(error);
        } else if (eventName === 'done') complete(data);
      };

      while (!terminal) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || '';
        blocks.forEach(processBlock);
      }
      if (!terminal && buffer.trim()) processBlock(buffer);
      if (!terminal) {
        const error = new Error('SSE stream ended before a done event');
        error.code = 'SSE_INCOMPLETE';
        return fail(error);
      }
      return true;
    } catch (error) {
      return fail(error);
    }
  }
};

window.AStockAPI = AStockAPI;
