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
    Object.defineProperty(state, '_toolFailureSeen', { value: false, writable: true, enumerable: false });
    return state;
  }
  function snapshot(value) { if (value == null) return value; try { return JSON.parse(JSON.stringify(value)); } catch (e) { return String(value); } }
  function timestamp(value) { if (value == null) return null; var n = typeof value === 'number' ? value : Date.parse(value); return Number.isFinite(n) ? n : null; }
  function duration(value) { if (value == null || value === '') return null; var n = Number(value); return Number.isFinite(n) && n >= 0 ? n : null; }
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
      tool.startedAt = now == null ? tool.startedAt : now; if (!tool._elapsedExplicit && tool.elapsedMs == null && tool.completedAt != null && tool.startedAt != null) tool.elapsedMs = tool.completedAt >= tool.startedAt ? tool.completedAt - tool.startedAt : null;
      if (eventValue(payload, ['title', 'skill_id', 'skillId', 'action'], null) != null) tool.title = String(eventValue(payload, ['title', 'skill_id', 'skillId', 'action'], '工具调用'));
      if (payload.skill_id != null || payload.skillId != null) tool.skill_id = snapshot(payload.skill_id != null ? payload.skill_id : payload.skillId);
      if (payload.action != null) tool.action = snapshot(payload.action);
      if (Object.prototype.hasOwnProperty.call(payload, 'args') && payload.args != null) tool.args = snapshot(payload.args);
    } else if (type === 'tool_call_complete') {
      var completedId = eventValue(payload, ['call_id', 'callId', 'id'], null), completedKey = completedId == null ? null : String(completedId), match = completedKey != null ? state._toolNodesByCallId[completedKey] : state.timelineNodes.find(function (n) { return n.type === 'tool' && n.callId == null && n.status === 'running'; });
      if (!match) { match = timelineNode(state, 'tool', eventValue(payload, ['title', 'skill_id', 'skillId', 'action'], '未匹配工具调用')); match.callId = completedKey; if (completedKey != null) state._toolNodesByCallId[completedKey] = match; match.startedAt = now; match.skill_id = snapshot(payload.skill_id); match.action = snapshot(payload.action); match.args = snapshot(payload.args); }
      var suppliedCompleted = eventValue(payload, ['completed_at', 'completedAt', 'timestamp', 'received_at'], null); if (suppliedCompleted != null) match.completedAt = timestamp(suppliedCompleted); var rawElapsed = eventValue(payload, ['elapsed_ms', 'elapsedMs'], null), explicitElapsed = (Object.prototype.hasOwnProperty.call(payload, 'elapsed_ms') || Object.prototype.hasOwnProperty.call(payload, 'elapsedMs')) && duration(rawElapsed) != null; if (explicitElapsed) match.elapsedMs = duration(rawElapsed); else if (match.elapsedMs == null && match.startedAt != null && match.completedAt != null && match.completedAt >= match.startedAt) match.elapsedMs = match.completedAt - match.startedAt;
      var hasData = Object.prototype.hasOwnProperty.call(payload, 'data') || Object.prototype.hasOwnProperty.call(payload, 'result'), result = eventValue(payload, ['data', 'result'], null); if (hasData) { match.result = snapshot(result); if (match.callId != null) state.toolResultsByCallId[match.callId] = snapshot(result); }
      if (Object.prototype.hasOwnProperty.call(payload, 'summary')) match.summary = String(payload.summary || '');
      var previousStatus = match.status, terminal = String(eventValue(payload, ['status', 'state', 'outcome', 'type'], '')).toLowerCase(), toolError = payload.error || (payload.data && typeof payload.data === 'object' && (payload.data.code || payload.data.error || payload.data.message) ? payload.data : null) || (terminal === 'error' || terminal === 'timeout' ? payload : null);
      if (toolError || terminal === 'failed') { var wasFailed = match.status === 'failed', errorDetail = toolError && (toolError.detail || toolError.message || (typeof toolError === 'string' ? toolError : '')); match.status = 'failed'; if (!hasData && previousStatus !== 'failed') { match.result = null; if (match.callId != null) delete state.toolResultsByCallId[match.callId]; } match.error = presentError(toolError && toolError.code ? toolError : { code: terminal === 'timeout' ? 'LLM_TIMEOUT' : 'UNKNOWN', detail: errorDetail || payload.detail }); if (!wasFailed && !state._toolFailureSeen) { match.expanded = true; state.timelineExpanded = true; state._toolFailureSeen = true; } }
      else { match.status = terminal === 'success' || terminal === 'succeeded' || terminal === 'ok' ? 'succeeded' : 'degraded'; match.error = null; }
      if (!hasData && previousStatus !== match.status) { match.result = null; if (match.callId != null) delete state.toolResultsByCallId[match.callId]; }
      if (explicitElapsed) Object.defineProperty(match, '_elapsedExplicit', { value: true, writable: true, configurable: true, enumerable: false });
    } else if (type === 'content_delta') {
      state.fullMarkdown += String(eventValue(payload, ['text', 'delta', 'content'], ''));
    } else if (type === 'error') {
      var errorInput = payload.error && typeof payload.error === 'object' ? Object.assign({}, payload, payload.error) : payload, presented = presentError(errorInput); state.errors.push(presented); var en = timelineNode(state, 'error', presented.title); en.status = 'failed'; en.error = presented; en.summary = presented.detail || presented.recovery; en.expanded = true; state.status = 'failed'; state._failed = true; state.timelineExpanded = true;
    } else if (type === 'done') {
      state.metrics.elapsedMs = duration(eventValue(payload, ['elapsed_ms', 'elapsedMs'], state.metrics.elapsedMs)); state.metrics.tokens = eventValue(payload, ['total_tokens', 'tokens'], state.metrics.tokens); state.metrics.finishReason = eventValue(payload, ['finish_reason', 'finishReason'], state.metrics.finishReason);
      if (!state._failed) { state.status = 'succeeded'; state.summaryItems = summarizeMarkdown(state.fullMarkdown); var done = state.timelineNodes.find(function (n) { return n.type === 'done'; }) || timelineNode(state, 'done', '完成'); done.status = 'succeeded'; done.completedAt = timestamp(eventValue(payload, ['completed_at', 'completedAt', 'timestamp'], null)); done.elapsedMs = state.metrics.elapsedMs; done.summary = state.summaryItems.join('；'); }
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

  function decomposeTask(promptText, meta) {
    promptText = String(promptText || '').trim();
    meta = meta || {};
    var operators = meta.operators || {};
    var stock = (operators.stocks && operators.stocks[0]) || null;
    var stockLabel = stock ? (stock.name + ' (' + stock.code + ')') : (promptText.match(/(\d{6})/g) ? promptText.match(/(\d{6})/g)[0] : '');

    var isBreakeven = /保本|止损|成本|风控|挂单|卖出价/.test(promptText);
    var is5A = /5A|选股|多因子|筛选|共振/.test(promptText);
    var isMACD = /MACD|金叉|背离|形态|波谷/.test(promptText);
    var isPaper = /模拟盘|买入|卖出|交易|仓位|下单/.test(promptText);
    var isDebate = /辩论|多空|研报|深度研判/.test(promptText);
    var isReturns = /收益|盈亏|净值|归因/.test(promptText);

    var targetSkill = 'astock-platform-evaluate';
    var sopName = 'A股全流程综合研报';
    var deliverableName = 'report_market_overview.md';

    if (isBreakeven) {
      targetSkill = 'astock-action-execution';
      sopName = '实战反应动作与精确保本价精算';
      deliverableName = stock ? ('action_plan_' + stock.code + '.md') : 'action_plan.md';
    } else if (is5A) {
      targetSkill = 'astock-screener-5a';
      sopName = '五维共振旋转选股与龙头池初筛';
      deliverableName = '5a_screening_pool.md';
    } else if (isMACD) {
      targetSkill = 'astock-strategy-macd';
      sopName = 'MACD水下二次金叉与底背离形态识别';
      deliverableName = stock ? ('macd_pattern_' + stock.code + '.md') : 'macd_analysis.md';
    } else if (isPaper) {
      targetSkill = 'astock-trade-paper';
      sopName = '真实滑点模拟撮合与持仓风控';
      deliverableName = 'paper_trade_execution.md';
    } else if (isDebate) {
      targetSkill = 'astock-agent-debate';
      sopName = '7大分析师多空辩论研判';
      deliverableName = stock ? ('debate_' + stock.code + '.md') : 'debate_report.md';
    } else if (isReturns) {
      targetSkill = 'astock-quant-engine';
      sopName = '多因子量化收益全景归因';
      deliverableName = 'portfolio_attribution.md';
    } else if (stock) {
      targetSkill = 'astock-data-feed';
      sopName = '个股量价走势与筹码穿透诊断';
      deliverableName = 'report_' + stock.code + '.md';
    }

    var steps = [
      {
        type: 'intent',
        title: '判断意图 ' + (stockLabel ? (stockLabel + ' 研判') : (promptText.slice(0, 18) || '任务执行')),
        summary: '用户需求匹配 SOP「' + sopName + '」，提取核心参数与治理策略。',
        status: 'succeeded'
      },
      {
        type: 'sop',
        title: '选择SOP ' + sopName,
        summary: '规划执行路径：前置数据核验 ➔ 调度 ' + targetSkill + ' ➔ 交叉风控审计。',
        status: 'succeeded'
      },
      {
        type: 'tool',
        title: '能力调用 ' + targetSkill,
        skill_id: targetSkill,
        action: 'execute_pipeline',
        summary: '调度就地量化技能底座，规定执行核心运算与数据检验。',
        status: 'pending',
        deliverable: { filename: deliverableName }
      },
      {
        type: 'result',
        title: '整理任务结果',
        summary: '汇总结构化数据与生成交付物 ' + deliverableName + '。',
        status: 'pending'
      }
    ];

    return {
      sopName: sopName,
      targetSkill: targetSkill,
      deliverableName: deliverableName,
      stockLabel: stockLabel,
      steps: steps
    };
  }

  function detectDeliverables(markdown, toolData) {
    var files = [];
    var seen = new Set();
    var addFile = function (fn, desc) {
      if (fn && !seen.has(fn)) {
        seen.add(fn);
        files.push({ filename: fn, desc: desc || fn });
      }
    };

    if (markdown) {
      var matches = String(markdown).matchAll(/`?([a-zA-Z0-9_\-]+\.(?:md|json|csv|html))`?/g);
      for (var m of matches) {
        var fn = m[1];
        if (fn.endsWith('.md') || fn.endsWith('.json')) {
          addFile(fn, '研报交付物文档');
        }
      }
    }

    if (toolData) {
      if (Array.isArray(toolData.deliverables)) {
        toolData.deliverables.forEach(function (d) {
          if (typeof d === 'string') addFile(d);
          else if (d && d.name) addFile(d.name, d.desc);
        });
      }
      if (toolData.deliverable_file) addFile(toolData.deliverable_file);
      if (toolData.report_file) addFile(toolData.report_file);
    }
    return files;
  }

  function renderExecutionTimelineHtml(state, options) {
    if (!state) return '';
    options = options || {};
    var hasFailed = state.status === 'failed' || (state.timelineNodes && state.timelineNodes.some(function (n) { return n.status === 'failed'; }));
    var isStreaming = state.status === 'streaming';
    var isDone = state.status === 'succeeded' || (!isStreaming && !hasFailed);
    var expanded = state.timelineExpanded !== false;
    var durationText = state.metrics && state.metrics.elapsedMs != null ? ((state.metrics.elapsedMs / 1000).toFixed(1) + 's') : '';

    var headerClass = 'timeline-toggle-bar' + (hasFailed ? ' has-error' : (isStreaming ? ' is-running' : ' is-done'));
    var headerTitle = hasFailed ? '执行遇到问题' : (isStreaming ? '任务执行中...' : '执行记录');
    var headerIcon = hasFailed ? '⚠️' : (isStreaming ? '<span class="header-spin-ring"></span>' : '📋');

    var html = '<div class="execution-record-box' + (hasFailed ? ' error-mode' : '') + '" id="recordBox_' + escapeHtml(state.responseId) + '">';
    html += '<button type="button" class="' + headerClass + '" onclick="window.toggleTimelineRecord && window.toggleTimelineRecord(\'' + escapeHtml(state.responseId) + '\')" aria-expanded="' + (expanded ? 'true' : 'false') + '">';
    html += '  <div class="toggle-bar-left">';
    html += '    <span class="record-icon">' + headerIcon + '</span>';
    html += '    <span class="record-title">' + headerTitle + '</span>';
    if (durationText) {
      html += '    <span class="record-duration">耗时 ' + durationText + '</span>';
    }
    html += '  </div>';
    html += '  <span class="record-chevron">' + (expanded ? '∨' : '>') + '</span>';
    html += '</button>';

    html += '<div class="timeline-nodes-list' + (expanded ? '' : ' hidden') + '" id="nodesList_' + escapeHtml(state.responseId) + '">';

    var nodes = state.timelineNodes || [];
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var isNodeFailed = n.status === 'failed';
      var isNodeRunning = n.status === 'running';
      var isNodeDone = n.status === 'succeeded';
      var itemClass = 'timeline-node-item' + (isNodeFailed ? ' node-failed' : (isNodeRunning ? ' node-running' : ' node-done'));

      var nodeIcon = '•';
      if (n.type === 'intent') nodeIcon = '📝';
      else if (n.type === 'sop') nodeIcon = '⇥';
      else if (n.type === 'thought') nodeIcon = '💭';
      else if (n.type === 'confirmation') nodeIcon = '🎯';
      else if (n.type === 'tool') nodeIcon = isNodeFailed ? '❌' : (isNodeRunning ? '⏳' : '🔧');
      else if (n.type === 'result' || n.type === 'done') nodeIcon = '📄';
      else if (n.type === 'error') nodeIcon = '⚠️';

      var nodeTitle = n.title;
      if (n.type === 'tool') {
        var skillLabel = n.skill_id || n.action || n.title || '技能调用';
        if (isNodeFailed) nodeTitle = '能力调用失败 ' + skillLabel;
        else if (isNodeRunning) nodeTitle = '能力调用中 ' + skillLabel;
        else nodeTitle = '能力调用完成 ' + skillLabel;
      }

      html += '<div class="' + itemClass + '" id="' + escapeHtml(n.nodeId) + '">';
      html += '  <div class="node-main-row">';
      html += '    <span class="node-icon">' + nodeIcon + '</span>';
      html += '    <div class="node-text-col">';
      html += '      <div class="node-title' + (isNodeFailed ? ' text-failed' : '') + '">' + escapeHtml(nodeTitle) + '</div>';

      var subInfo = n.summary || '';
      if (!subInfo && n.action) subInfo = '第 ' + (i + 1) + ' 个动作 · ' + n.action;
      if (isNodeFailed && n.error) {
        subInfo = (n.error.code ? (n.error.code + ' · ') : '') + (n.error.detail || n.error.title || '执行异常');
      }
      if (subInfo) {
        html += '      <div class="node-subtext' + (isNodeFailed ? ' text-failed-sub' : '') + '">' + escapeHtml(subInfo) + '</div>';
      }
      html += '    </div>';
      html += '  </div>';

      // Collapsible tool result drawer (as in Image 1 and Image 3)
      if (n.result != null || (n.error && n.error.detail)) {
        var isDrawerOpen = n.expanded === true;
        var drawerData = n.result != null ? n.result : { error: n.error };
        html += '  <div class="node-drawer-wrap">';
        html += '    <button type="button" class="node-drawer-btn" onclick="window.toggleNodeDrawer && window.toggleNodeDrawer(\'' + escapeHtml(state.responseId) + '\', \'' + escapeHtml(n.nodeId) + '\')">';
        html += '      <span class="drawer-arrow">' + (isDrawerOpen ? '▼' : '▶') + '</span> 查看能力结果';
        html += '    </button>';
        html += '    <div class="node-drawer-body' + (isDrawerOpen ? ' open' : ' closed') + '" id="drawer_' + escapeHtml(n.nodeId) + '">';
        html += '      <pre class="json-code-box"><code>' + escapeHtml(JSON.stringify(drawerData, null, 2)) + '</code></pre>';
        html += '    </div>';
        html += '  </div>';
      }

      // Deliverable clickable link (Requirement 6)
      if (n.deliverable && n.deliverable.filename) {
        var fn = n.deliverable.filename;
        html += '  <div class="node-deliverable-wrap">';
        html += '    <span class="deliverable-link-chip" onclick="window.openDeliverableInWorkbench && window.openDeliverableInWorkbench(\'' + escapeHtml(fn) + '\')" title="在右侧工作台打开文件">';
        html += '      📄 ' + escapeHtml(fn) + ' <span class="open-arrow">↗</span>';
        html += '    </span>';
        html += '  </div>';
      }

      html += '</div>';
    }

    // Working animation at bottom while active (Requirement 2)
    if (isStreaming) {
      html += '<div class="timeline-working-indicator">';
      html += '  <span class="working-spinner-ring"></span>';
      html += '  <span class="working-text">working...</span>';
      html += '</div>';
    }

    html += '</div>'; // end timeline-nodes-list
    html += '</div>'; // end execution-record-box

    return html;
  }

  root.ChatPresentation = {
    escapeHtml: escapeHtml,
    renderMarkdown: renderMarkdown,
    summarizeMarkdown: summarizeMarkdown,
    redactSensitive: redactSensitive,
    presentError: presentError,
    createResponseState: createResponseState,
    applyEvent: applyEvent,
    decomposeTask: decomposeTask,
    detectDeliverables: detectDeliverables,
    renderExecutionTimelineHtml: renderExecutionTimelineHtml
  };
}(typeof window !== 'undefined' ? window : this));
