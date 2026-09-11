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

  function inline(text) {
    var placeholders = [];
    function hold(value) { placeholders.push(value); return '\u0000' + (placeholders.length - 1) + '\u0000'; }
    var out = escapeHtml(text);
    out = out.replace(/`([^`\n]+)`/g, function (_, x) { return hold('<code>' + x + '</code>'); });
    out = out.replace(/!\[([^\]]*)\]\([^)]*\)/g, function (_, alt) { return alt; });
    out = out.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, function (_, label, url) {
      var safe = safeUrl(url.replace(/&amp;/g, '&')); return safe ? hold('<a href="' + escapeHtml(safe) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>') : label;
    });
    out = out.replace(/\*\*([^*\n]+)\*\*|__([^_\n]+)__/g, function (_, a, b) { return '<strong>' + (a || b) + '</strong>'; });
    out = out.replace(/\*([^*\n]+)\*|_([^_\n]+)_/g, function (_, a, b) { return '<em>' + (a || b) + '</em>'; });
    return out.replace(/\u0000(\d+)\u0000/g, function (_, i) { return placeholders[Number(i)]; });
  }

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
      if (/^\s*\|?.+\|.+\|?\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$/.test(lines[i + 1])) {
        function cells(s) { return s.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (x) { return x.trim(); }); }
        var heads = cells(line), rows = []; i += 2;
        while (i < lines.length && /^\s*\|?.+\|.+\|?\s*$/.test(lines[i]) && lines[i].trim() !== '') { rows.push(cells(lines[i++])); }
        html.push('<table><thead><tr>' + heads.map(function (x) { return '<th>' + inline(x) + '</th>'; }).join('') + '</tr></thead><tbody>' + rows.map(function (r) { return '<tr>' + r.map(function (x) { return '<td>' + inline(x) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table>'); continue;
      }
      var heading = line.match(/^\s*(#{1,6})\s+(.+?)\s*#*\s*$/);
      if (heading) { html.push('<h' + heading[1].length + '>' + inline(heading[2]) + '</h' + heading[1].length + '>'); i++; continue; }
      if (/^\s*>/.test(line)) { var quote = []; while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, '')); html.push('<blockquote>' + inline(quote.join('\n')) + '</blockquote>'); continue; }
      var list = line.match(/^\s*([-*+])\s+(.+)/), ordered = line.match(/^\s*\d+[.)]\s+(.+)/);
      if (list || ordered) { var tag = ordered ? 'ol' : 'ul', items = []; while (i < lines.length) { var m = lines[i].match(ordered ? /^\s*\d+[.)]\s+(.+)/ : /^\s*[-*+]\s+(.+)/); if (!m) break; items.push('<li>' + inline(m[1]) + '</li>'); i++; } html.push('<' + tag + '>' + items.join('') + '</' + tag + '>'); continue; }
      if (!line.trim()) { i++; continue; }
      var para = [line]; i++; while (i < lines.length && lines[i].trim() && !/^\s*(#{1,6})\s+|^\s*[-*+]\s+|^\s*\d+[.)]\s+|^\s*>|^\s*```/.test(lines[i])) para.push(lines[i++]); html.push('<p>' + inline(para.join('\n')).replace(/\n/g, '<br>') + '</p>');
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
  function redactSensitive(value) {
    return String(value == null ? '' : value).replace(/(Authorization\s*:\s*(?:Bearer\s+)?)[^\s,;"'}]+/gi, '$1[REDACTED]').replace(/(["']Authorization["']\s*:\s*["'])([^"']*)(["'])/gi, '$1[REDACTED]$3').replace(/(Cookie\s*:\s*)[^\r\n]+/gi, '$1[REDACTED]').replace(/(["'](?:api[_-]?key|token|cookie|secret)["']\s*:\s*["'])([^"']*)(["'])/gi, '$1[REDACTED]$3').replace(/((?:api[_-]?key|token|cookie|secret)\s*[:=]\s*)["']?[^\s,;"'}]+["']?/gi, '$1[REDACTED]');
  }
  var errors = { LLM_NOT_CONFIGURED: ['模型尚未配置', '请先完成模型配置后重试'], LLM_AUTH_FAILED: ['模型认证失败', '请检查 API 密钥后重试'], LLM_MODEL_UNAVAILABLE: ['模型暂不可用', '请稍后重试或选择其他模型'], LLM_CAPABILITY_UNSUPPORTED: ['模型不支持此能力', '请更换支持该能力的模型'], LLM_TIMEOUT: ['请求超时', '请稍后重试'], SSE_HTTP_ERROR: ['服务连接失败', '请稍后重试'], SSE_INCOMPLETE: ['响应未完成', '请重试'] };
  function presentError(error) { var code = error && error.code, item = Object.prototype.hasOwnProperty.call(errors, code) ? errors[code] : ['请求失败', '请稍后重试']; return { code: code || 'UNKNOWN', title: item[0], recovery: item[1], detail: redactSensitive(error && (error.detail || error.message || '')) }; }
  root.ChatPresentation = { escapeHtml: escapeHtml, renderMarkdown: renderMarkdown, summarizeMarkdown: summarizeMarkdown, redactSensitive: redactSensitive, presentError: presentError };
}(typeof window !== 'undefined' ? window : this));
