(function (root) {
  'use strict';

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function safeUrl(url) {
    var value = String(url || '').trim();
    return /^(https?:|mailto:)/i.test(value) ? value : null;
  }

  function isMarkdownPunctuation(value) {
    var code = String(value || '').charCodeAt(0);
    return (code >= 33 && code <= 47) || (code >= 58 && code <= 64) || (code >= 91 && code <= 96) || (code >= 123 && code <= 126);
  }

  function findLabelEnd(text, start) {
    for (var i = start; i < text.length; i++) {
      if (text[i] === '\\' && i + 1 < text.length && isMarkdownPunctuation(text[i + 1])) { i++; continue; }
      if (text[i] === '`') {
        var codeEnd = text.indexOf('`', i + 1);
        if (codeEnd !== -1 && text.slice(i + 1, codeEnd).indexOf('\n') === -1) { i = codeEnd; continue; }
      }
      if (text[i] === ']') return i;
      if (text[i] === '\n') return -1;
    }
    return -1;
  }

  function parseLinkTarget(text, start) {
    var i = start, url = '', title = null, quote, closed = false;
    while (i < text.length && /[ \t]/.test(text[i])) i++;
    if (text[i] === '<') {
      i++;
      while (i < text.length && text[i] !== '>' && text[i] !== '\n') {
        if (text[i] === '\\' && i + 1 < text.length && isMarkdownPunctuation(text[i + 1])) { url += text[i + 1]; i += 2; }
        else url += text[i++];
      }
      if (text[i] !== '>') return null;
      i++;
    } else {
      while (i < text.length && !/[\s)]/.test(text[i])) {
        if (text[i] === '\\' && i + 1 < text.length && isMarkdownPunctuation(text[i + 1])) { url += text[i + 1]; i += 2; }
        else url += text[i++];
      }
    }
    if (!url) return null;
    while (i < text.length && /[ \t]/.test(text[i])) i++;
    if (text[i] === ')') return { end: i + 1, url: url, title: null };
    quote = text[i];
    if (quote !== '"' && quote !== "'") return null;
    i++;
    title = '';
    while (i < text.length && text[i] !== '\n') {
      if (text[i] === '\\' && i + 1 < text.length && isMarkdownPunctuation(text[i + 1])) { title += text[i + 1]; i += 2; continue; }
      if (text[i] === quote) { closed = true; i++; break; }
      title += text[i++];
    }
    if (!closed) return null;
    while (i < text.length && /[ \t]/.test(text[i])) i++;
    return text[i] === ')' ? { end: i + 1, url: url, title: title } : null;
  }

  function findInlineEnd(text, start, delimiter) {
    for (var i = start; i <= text.length - delimiter.length; i++) {
      if (text[i] === '\n') return -1;
      if (text[i] === '\\' && i + 1 < text.length && isMarkdownPunctuation(text[i + 1])) { i++; continue; }
      if (text.slice(i, i + delimiter.length) === delimiter) return i;
    }
    return -1;
  }

  function inline(text, depth) {
    text = String(text == null ? '' : text).replace(/\u0000/g, '');
    depth = depth || 0;
    if (depth >= 32) return escapeHtml(text);
    var out = '', i = 0;
    while (i < text.length) {
      if (text[i] === '\\' && i + 1 < text.length && isMarkdownPunctuation(text[i + 1])) {
        out += escapeHtml(text[i + 1]); i += 2; continue;
      }
      if (text[i] === '`') {
        var codeEnd = text.indexOf('`', i + 1);
        if (codeEnd > i + 1 && text.slice(i + 1, codeEnd).indexOf('\n') === -1) {
          out += '<code>' + escapeHtml(text.slice(i + 1, codeEnd)) + '</code>';
          i = codeEnd + 1; continue;
        }
      }
      var image = text[i] === '!' && text[i + 1] === '[', link = text[i] === '[';
      if (image || link) {
        var labelStart = i + (image ? 2 : 1), labelEnd = findLabelEnd(text, labelStart);
        if (labelEnd !== -1 && text[labelEnd + 1] === '(') {
          var target = parseLinkTarget(text, labelEnd + 2);
          if (target) {
            var label = inline(text.slice(labelStart, labelEnd), depth + 1);
            if (image) out += label;
            else {
              var safe = safeUrl(target.url);
              out += safe ? '<a href="' + escapeHtml(safe) + '"' + (target.title == null ? '' : ' title="' + escapeHtml(target.title) + '"') + ' target="_blank" rel="noopener noreferrer">' + label + '</a>' : label;
            }
            i = target.end; continue;
          }
        }
      }
      var delimiter = text.slice(i, i + 2) === '**' || text.slice(i, i + 2) === '__' ? text.slice(i, i + 2) : (text[i] === '*' || text[i] === '_' ? text[i] : null);
      if (delimiter) {
        var emphasisEnd = findInlineEnd(text, i + delimiter.length, delimiter);
        if (emphasisEnd > i + delimiter.length) {
          out += (delimiter.length === 2 ? '<strong>' : '<em>') + inline(text.slice(i + delimiter.length, emphasisEnd), depth + 1) + (delimiter.length === 2 ? '</strong>' : '</em>');
          i = emphasisEnd + delimiter.length; continue;
        }
      }
      out += escapeHtml(text[i]); i++;
    }
    return out;
  }

  function isTableRow(line) { return /^\s*\|?.+\|.+\|?\s*$/.test(line); }
  function isTableDelimiter(line) { return /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$/.test(line); }
  function isTableStart(lines, index) { return index + 1 < lines.length && isTableRow(lines[index]) && isTableDelimiter(lines[index + 1]); }

  function renderMarkdown(markdown) {
    var lines = String(markdown == null ? '' : markdown).replace(/\r\n?/g, '\n').split('\n');
    var html = [], i = 0;
    while (i < lines.length) {
      var line = lines[i];
      if (/^\s*```/.test(line)) {
        var lang = line.replace(/^\s*```\s*/, '').trim(), body = [], fence = ++i;
        while (i < lines.length && !/^\s*```/.test(lines[i])) body.push(lines[i++]);
        if (i < lines.length) i++;
        html.push('<pre><code' + (lang ? ' class="language-' + escapeHtml(lang) + '"' : '') + '>' + escapeHtml(body.join('\n')) + '</code></pre>'); continue;
      }
      if (isTableStart(lines, i)) {
        function cells(s) { return s.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (x) { return x.trim(); }); }
        var heads = cells(line), rows = []; i += 2;
        while (i < lines.length && isTableRow(lines[i]) && lines[i].trim() !== '') { rows.push(cells(lines[i++])); }
        html.push('<table><thead><tr>' + heads.map(function (x) { return '<th>' + inline(x) + '</th>'; }).join('') + '</tr></thead><tbody>' + rows.map(function (r) { return '<tr>' + r.map(function (x) { return '<td>' + inline(x) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table>'); continue;
      }
      var heading = line.match(/^\s*(#{1,6})\s+(.+?)\s*#*\s*$/);
      if (heading) { html.push('<h' + heading[1].length + '>' + inline(heading[2]) + '</h' + heading[1].length + '>'); i++; continue; }
      if (/^\s*>/.test(line)) { var quote = []; while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, '')); html.push('<blockquote>' + inline(quote.join('\n')) + '</blockquote>'); continue; }
      var list = line.match(/^\s*([-*+])\s+(.+)/), ordered = line.match(/^\s*\d+[.)]\s+(.+)/);
      if (list || ordered) { var tag = ordered ? 'ol' : 'ul', items = []; while (i < lines.length) { var m = lines[i].match(ordered ? /^\s*\d+[.)]\s+(.+)/ : /^\s*[-*+]\s+(.+)/); if (!m) break; items.push('<li>' + inline(m[1]) + '</li>'); i++; } html.push('<' + tag + '>' + items.join('') + '</' + tag + '>'); continue; }
      if (!line.trim()) { i++; continue; }
      var para = [line]; i++; while (i < lines.length && lines[i].trim() && !/^\s*(#{1,6})\s+|^\s*[-*+]\s+|^\s*\d+[.)]\s+|^\s*>|^\s*```/.test(lines[i]) && !isTableStart(lines, i)) para.push(lines[i++]); html.push('<p>' + inline(para.join('\n')).replace(/\n/g, '<br>') + '</p>');
    }
    return html.join('\n');
  }

  function stripMarkdown(line) {
    return String(line).replace(/^\s*>\s?/, '').replace(/^\s*(?:[-*+] |\d+[.)] )/, '').replace(/^\s*#{1,6}\s*/, '').replace(/[`*_~]/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/\s+/g, ' ').trim();
  }
  function summarizeMarkdown(markdown, limit) {
    limit = Math.max(1, Number(limit) || 5); var lines = String(markdown || '').split(/\r?\n/), wanted = /^(核心结论|结论|建议|风险|策略)/, active = false, inFence = false, candidates = [], fallback = [];
    lines.forEach(function (line) { if (/^\s*```/.test(line)) { inFence = !inFence; return; } if (inFence) return; var h = line.match(/^\s*#{1,6}\s+(.+)/), clean = stripMarkdown(line); if (h) { active = wanted.test(stripMarkdown(h[1])); return; } if (clean) { if (active) candidates.push(clean); else fallback.push(clean); } });
    var valid = function (x) { return x && !/^[-| ]+$/.test(x); }, preferred = candidates.filter(valid), result = [], seen = new Set(); (preferred.length ? preferred : fallback.filter(valid)).forEach(function (x) { x = x.slice(0, 120); if (!seen.has(x) && result.length < limit) { seen.add(x); result.push(x); } }); return result.slice(0, Math.min(limit, 5));
  }
  function createResponseState(responseId) {
    var state = {
      responseId: String(responseId == null ? '' : responseId), status: 'streaming', fullMarkdown: '', summaryItems: [], timelineNodes: [],
      toolResultsByCallId: Object.create(null), errors: [], detailTabId: 'chat-response-' + String(responseId == null ? '' : responseId), timelineExpanded: false,
      metrics: { elapsedMs: null, tokens: null, finishReason: null }
    };
    Object.defineProperty(state, '_nextNode', { value: 1, writable: true, enumerable: false });
    Object.defineProperty(state, '_failed', { value: false, writable: true, enumerable: false });
    Object.defineProperty(state, '_toolNodesByCallId', { value: Object.create(null), writable: true, enumerable: false });
    return state;
  }
  function snapshot(value) { if (value == null) return value; try { return JSON.parse(JSON.stringify(value)); } catch (e) { return String(value); } }
  function timestamp(value) { if (value == null) return null; var n = typeof value === 'number' ? value : Date.parse(value); return Number.isFinite(n) ? n : null; }
  function duration(value) { var n = Number(value); return Number.isFinite(n) && n >= 0 ? n : null; }
  function eventValue(payload, names, fallback) {
    for (var i = 0; i < names.length; i++) if (payload && payload[names[i]] != null) return payload[names[i]];
    return fallback;
  }
  function timelineNode(state, type, title) {
    var node = { nodeId: 'node-' + state._nextNode++, type: type, title: String(title || ''), status: 'pending', startedAt: null, completedAt: null, elapsedMs: null, summary: '', result: null, error: null, expanded: false };
    state.timelineNodes.push(node); return node;
  }
  function applyEvent(state, type, payload) {
    if (!state || !type) return state;
    payload = payload || {};
    var now = timestamp(eventValue(payload, ['timestamp', 'received_at', 'started_at', 'startedAt'], null));
    if (type === 'thought') {
      var thought = eventValue(payload, ['content', 'text', 'summary'], '');
      if (String(thought || '').trim()) { var tn = timelineNode(state, 'thought', eventValue(payload, ['title'], '思考')); tn.status = 'succeeded'; tn.summary = String(thought); tn.startedAt = now; tn.completedAt = timestamp(eventValue(payload, ['completed_at', 'completedAt'], now)); }
    } else if (type === 'tool_call_start') {
      var callId = eventValue(payload, ['call_id', 'callId', 'id'], null), callKey = callId == null ? null : String(callId);
      var tool = callKey != null ? state._toolNodesByCallId[callKey] : null;
      if (!tool) { tool = timelineNode(state, 'tool', eventValue(payload, ['title', 'skill_id', 'skillId', 'action'], '工具调用')); tool.callId = callKey; if (callKey != null) state._toolNodesByCallId[callKey] = tool; }
      if (tool.status === 'pending' || tool.status === 'running') tool.status = 'running';
      tool.startedAt = now == null ? tool.startedAt : now; tool.skill_id = snapshot(payload.skill_id); tool.action = snapshot(payload.action); tool.args = snapshot(payload.args);
    } else if (type === 'tool_call_complete') {
      var completedId = eventValue(payload, ['call_id', 'callId', 'id'], null), completedKey = completedId == null ? null : String(completedId), match = completedKey != null ? state._toolNodesByCallId[completedKey] : state.timelineNodes.find(function (n) { return n.type === 'tool' && n.callId == null && n.status === 'running'; });
      if (!match) { match = timelineNode(state, 'tool', '未匹配工具调用'); match.callId = completedKey; if (completedKey != null) state._toolNodesByCallId[completedKey] = match; match.startedAt = now; }
      match.completedAt = timestamp(eventValue(payload, ['completed_at', 'completedAt', 'timestamp'], now)); var explicitElapsed = Object.prototype.hasOwnProperty.call(payload, 'elapsed_ms') || Object.prototype.hasOwnProperty.call(payload, 'elapsedMs'); match.elapsedMs = explicitElapsed ? duration(eventValue(payload, ['elapsed_ms', 'elapsedMs'], null)) : (match.startedAt != null && match.completedAt != null && match.completedAt >= match.startedAt ? match.completedAt - match.startedAt : null);
      var hasData = Object.prototype.hasOwnProperty.call(payload, 'data') || Object.prototype.hasOwnProperty.call(payload, 'result'), result = eventValue(payload, ['data', 'result'], null); if (hasData) { match.result = snapshot(result); if (match.callId != null) state.toolResultsByCallId[match.callId] = snapshot(result); }
      if (Object.prototype.hasOwnProperty.call(payload, 'summary')) match.summary = String(payload.summary || '');
      var terminal = String(eventValue(payload, ['status', 'state', 'outcome', 'type'], '')).toLowerCase(), toolError = payload.error || (terminal === 'error' || terminal === 'timeout' ? payload : null);
      if (toolError || terminal === 'failed') { var errorDetail = toolError && (toolError.detail || toolError.message || (typeof toolError === 'string' ? toolError : '')); match.status = 'failed'; match.error = presentError(toolError && toolError.code ? toolError : { code: terminal === 'timeout' ? 'LLM_TIMEOUT' : 'UNKNOWN', detail: errorDetail || payload.detail }); if (terminal === 'timeout' || terminal === 'error' || toolError) { match.expanded = true; state.timelineExpanded = true; } }
      else match.status = terminal === 'success' || terminal === 'succeeded' || terminal === 'ok' ? 'succeeded' : 'degraded';
    } else if (type === 'content_delta') {
      state.fullMarkdown += String(eventValue(payload, ['text', 'delta', 'content'], ''));
    } else if (type === 'error') {
      var errorInput = payload.error && typeof payload.error === 'object' ? Object.assign({}, payload, payload.error) : payload, presented = presentError(errorInput); state.errors.push(presented); var en = timelineNode(state, 'error', presented.title); en.status = 'failed'; en.error = presented; en.summary = presented.detail || presented.recovery; en.expanded = true; state.status = 'failed'; state._failed = true; state.timelineExpanded = true;
    } else if (type === 'done') {
      state.metrics.elapsedMs = duration(eventValue(payload, ['elapsed_ms', 'elapsedMs'], state.metrics.elapsedMs)); state.metrics.tokens = eventValue(payload, ['total_tokens', 'tokens'], state.metrics.tokens); state.metrics.finishReason = eventValue(payload, ['finish_reason', 'finishReason'], state.metrics.finishReason);
      if (!state._failed) { state.status = 'succeeded'; state.summaryItems = summarizeMarkdown(state.fullMarkdown); var done = state.timelineNodes.find(function (n) { return n.type === 'done'; }) || timelineNode(state, 'done', '完成'); done.status = 'succeeded'; done.completedAt = eventValue(payload, ['completed_at', 'completedAt', 'timestamp'], null); done.elapsedMs = state.metrics.elapsedMs; done.summary = state.summaryItems.join('；'); }
    }
    return state;
  }
  function redactSensitive(value) {
    var input = String(value == null ? '' : value), output = '', cursor = 0, i = 0;
    var names = /^(authorization|x-api-key|api[_-]?key|access_token|token|cookie|secret)$/i;
    function quotedEnd(start, quote) {
      for (var p = start + 1; p < input.length; p++) {
        if (input[p] === '\\' && p + 1 < input.length) { p++; continue; }
        if (input[p] === quote) return p;
        if (input[p] === '\r' || input[p] === '\n') return -1;
      }
      return -1;
    }
    function lineEnd(start) {
      var cr = input.indexOf('\r', start), lf = input.indexOf('\n', start);
      if (cr === -1) return lf === -1 ? input.length : lf;
      return lf === -1 ? cr : Math.min(cr, lf);
    }
    function matchAt(start) {
      var quoted = input[start] === '"' || input[start] === "'", keyEnd, key, p, separator;
      if (quoted) {
        keyEnd = quotedEnd(start, input[start]);
        if (keyEnd === -1) return null;
        key = input.slice(start + 1, keyEnd);
        p = keyEnd + 1;
      } else {
        if (start > 0 && /[A-Za-z0-9_-]/.test(input[start - 1])) return null;
        var found = input.slice(start).match(/^(authorization|x-api-key|api[_-]?key|access_token|token|cookie|secret)/i);
        if (!found || /[A-Za-z0-9_-]/.test(input[start + found[0].length] || '')) return null;
        key = found[0]; keyEnd = start + found[0].length; p = keyEnd;
      }
      if (!names.test(key)) return null;
      while (p < input.length && /[ \t]/.test(input[p])) p++;
      separator = input[p];
      if (separator !== ':' && separator !== '=') return null;
      p++;
      while (p < input.length && /[ \t]/.test(input[p])) p++;
      return { key: key.toLowerCase(), quoted: quoted, separator: separator, valueStart: p };
    }
    while (i < input.length) {
      var match = matchAt(i);
      if (!match) { i++; continue; }
      output += input.slice(cursor, match.valueStart);
      if (!match.quoted && match.separator === ':' && (match.key === 'authorization' || match.key === 'cookie')) {
        i = lineEnd(match.valueStart);
        output += '[REDACTED]'; cursor = i; continue;
      }
      var valueStart = match.valueStart, end;
      if (input[valueStart] === '"' || input[valueStart] === "'") {
        var valueQuote = input[valueStart], close = quotedEnd(valueStart, valueQuote);
        if (close === -1) {
          end = lineEnd(valueStart);
          output += valueQuote + '[REDACTED]';
        } else {
          end = close + 1;
          output += valueQuote + '[REDACTED]' + valueQuote;
        }
      } else {
        end = valueStart;
        while (end < input.length && !/[\s,;}\]]/.test(input[end])) end++;
        output += '[REDACTED]';
      }
      i = end; cursor = end;
    }
    return output + input.slice(cursor);
  }
  var errors = { LLM_NOT_CONFIGURED: ['模型尚未配置', '请先完成模型配置后重试'], LLM_AUTH_FAILED: ['模型认证失败', '请检查 API 密钥后重试'], LLM_MODEL_UNAVAILABLE: ['模型暂不可用', '请稍后重试或选择其他模型'], LLM_CAPABILITY_UNSUPPORTED: ['模型不支持此能力', '请更换支持该能力的模型'], LLM_TIMEOUT: ['请求超时', '请稍后重试'], SSE_HTTP_ERROR: ['服务连接失败', '请稍后重试'], SSE_INCOMPLETE: ['响应未完成', '请重试'] };
  function presentError(error) { var code = error && error.code, item = Object.prototype.hasOwnProperty.call(errors, code) ? errors[code] : ['请求失败', '请稍后重试']; return { code: code || 'UNKNOWN', title: item[0], recovery: item[1], detail: redactSensitive(error && (error.detail || error.message || error.error || '')) }; }
  root.ChatPresentation = { escapeHtml: escapeHtml, renderMarkdown: renderMarkdown, summarizeMarkdown: summarizeMarkdown, redactSensitive: redactSensitive, presentError: presentError, createResponseState: createResponseState, applyEvent: applyEvent };
}(typeof window !== 'undefined' ? window : this));
