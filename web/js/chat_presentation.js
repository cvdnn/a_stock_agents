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

  function isMarkdownFileLink(url) {
    var val = String(url || '').trim().toLowerCase();
    if (!val) return false;
    if (val.indexOf('file://') === 0) val = val.slice(7);
    val = val.split('?')[0].split('#')[0];
    return /\.md$/i.test(val) || /\.markdown$/i.test(val);
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
              var rawLabel = text.slice(labelStart, labelEnd);
              if (isMarkdownFileLink(target.url) || isMarkdownFileLink(rawLabel)) {
                var targetPath = isMarkdownFileLink(target.url) ? target.url : rawLabel;
                out += '<a href="javascript:void(0)" class="chat-md-chip" onclick="window.openMarkdownInWorkbench &amp;&amp; window.openMarkdownInWorkbench(\'' + escapeHtml(targetPath) + '\')" title="在工作区打开 Markdown 文档"><span class="chip-icon">📄</span> <span class="chip-title">' + label + '</span> <span class="chip-arrow">↗</span></a>';
              } else {
                var safe = safeUrl(target.url);
                out += safe ? '<a href="' + escapeHtml(safe) + '"' + (target.title == null ? '' : ' title="' + escapeHtml(target.title) + '"') + ' target="_blank" rel="noopener noreferrer">' + label + '</a>' : label;
              }
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

  function cleanMarkdownContent(markdown) {
    if (!markdown) return '';
    var text = String(markdown).replace(/\r\n?/g, '\n');
    // 1. Strip closed <think>...</think> tags
    text = text.replace(/<think>[\s\S]*?<\/think>/gi, '');
    // 2. In streaming mode, strip unclosed <think>... at the tail
    text = text.replace(/<think>[\s\S]*$/gi, '');
    // 3. Strip leading thought preambles before markdown headers
    text = text.replace(/^\s*(?:我将(?:先|再次|按|通过|调度|立即)?|收到，(?:我将|现在)?|正在为您?|现在开始)[^\n]+(?=\n+#{1,6}\s)/, '');
    return text.trim();
  }

  var markedInitialized = false;

  function initMarkedEngine() {
    if (markedInitialized) return;
    var markedLib = (typeof root !== 'undefined' && root.marked) || (typeof window !== 'undefined' && window.marked) || (typeof marked !== 'undefined' ? marked : null);
    if (!markedLib) return;

    var m = markedLib.marked || markedLib;
    var renderer = {
      code: function (token) {
        var text = (typeof token === 'object' && token !== null ? token.text : token) || '';
        var lang = ((typeof token === 'object' && token !== null ? token.lang : arguments[1]) || '').trim();
        var cleanLang = (lang.match(/^([a-zA-Z0-9_\-#+]+)/) || ['', ''])[1].toLowerCase();

        var hljsLib = (typeof root !== 'undefined' && root.hljs) || (typeof window !== 'undefined' && window.hljs) || (typeof hljs !== 'undefined' ? hljs : null);
        var highlighted = '';

        if (hljsLib) {
          try {
            if (cleanLang && hljsLib.getLanguage(cleanLang)) {
              highlighted = hljsLib.highlight(text, { language: cleanLang, ignoreIllegals: true }).value;
            } else if (cleanLang === 'shell' || cleanLang === 'sh' || cleanLang === 'zsh') {
              highlighted = hljsLib.highlight(text, { language: 'bash', ignoreIllegals: true }).value;
            } else {
              var auto = hljsLib.highlightAuto(text);
              highlighted = auto.value;
            }
          } catch (e) {
            highlighted = escapeHtml(text);
          }
        } else {
          highlighted = escapeHtml(text);
        }

        var displayLang = cleanLang ? cleanLang.toUpperCase() : 'CODE';

        return '<div class="code-block-wrapper">' +
          '<div class="code-block-header">' +
            '<span class="code-block-lang">' + escapeHtml(displayLang) + '</span>' +
            '<button type="button" class="code-copy-btn" onclick="ChatPresentation.copyCodeBlock(this)" title="复制代码">' +
              '<span class="copy-icon">📋</span> <span class="copy-text">复制</span>' +
            '</button>' +
          '</div>' +
          '<pre><code class="hljs' + (cleanLang ? ' language-' + escapeHtml(cleanLang) : '') + '">' + highlighted + '</code></pre>' +
        '</div>';
      },
      link: function (token) {
        var href = (typeof token === 'object' && token !== null ? token.href : token) || '';
        var title = (typeof token === 'object' && token !== null ? token.title : arguments[1]) || '';
        var text = (typeof token === 'object' && token !== null ? token.text : arguments[2]) || href;
        if (isMarkdownFileLink(href) || isMarkdownFileLink(text)) {
          var targetPath = isMarkdownFileLink(href) ? href : text;
          return '<a href="javascript:void(0)" class="chat-md-chip" onclick="window.openMarkdownInWorkbench &amp;&amp; window.openMarkdownInWorkbench(\'' + escapeHtml(targetPath) + '\')" title="在工作区打开 Markdown 文档">' +
            '<span class="chip-icon">📄</span> <span class="chip-title">' + text + '</span> <span class="chip-arrow">↗</span>' +
          '</a>';
        }
        var safe = safeUrl(href);
        if (!safe) return escapeHtml(text);
        return '<a href="' + escapeHtml(safe) + '"' + (title ? ' title="' + escapeHtml(title) + '"' : '') + ' target="_blank" rel="noopener noreferrer">' + text + '</a>';
      }
    };

    m.use({
      gfm: true,
      breaks: true,
      renderer: renderer,
      hooks: {
        postprocess: function (html) {
          // 1. Wrap tables in responsive container
          html = html.replace(/<table>/g, '<div class="table-responsive"><table>').replace(/<\/table>/g, '</table></div>');
          // 2. Render GFM Callouts / Alerts (> [!NOTE], > [!TIP], > [!IMPORTANT], > [!WARNING], > [!CAUTION])
          html = html.replace(/<blockquote>\s*<p>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:\s*<br\s*\/?>|\s*\n)?([\s\S]*?)<\/p>\s*<\/blockquote>/gi, function (match, type, content) {
            var lower = type.toLowerCase();
            var titles = { note: '说明', tip: '提示', important: '重要提示', warning: '风控警告', caution: '操作注意' };
            var icons = { note: 'ℹ️', tip: '💡', important: '📌', warning: '⚠️', caution: '🚨' };
            return '<div class="gfm-alert gfm-alert-' + lower + '">' +
              '<div class="gfm-alert-title"><span class="gfm-alert-icon">' + (icons[lower] || 'ℹ️') + '</span> ' + (titles[lower] || type) + '</div>' +
              '<div class="gfm-alert-content">' + content + '</div>' +
              '</div>';
          });
          return html;
        }
      }
    });

    markedInitialized = true;
  }

  function copyCodeBlock(btn) {
    if (!btn) return;
    var wrapper = btn.closest ? btn.closest('.code-block-wrapper') : btn.parentElement.parentElement;
    if (!wrapper) return;
    var codeEl = wrapper.querySelector('pre code');
    var codeText = codeEl ? (codeEl.innerText || codeEl.textContent || '') : '';
    if (!codeText) return;

    function showSuccess() {
      var copyText = btn.querySelector('.copy-text');
      var original = copyText ? copyText.innerText : '复制';
      if (copyText) copyText.innerText = '已复制 ✔';
      btn.classList.add('copied');
      setTimeout(function () {
        if (copyText) copyText.innerText = original;
        btn.classList.remove('copied');
      }, 1500);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(codeText).then(showSuccess).catch(function () {
        fallbackCopyText(codeText, showSuccess);
      });
    } else {
      fallbackCopyText(codeText, showSuccess);
    }
  }

  function fallbackCopyText(text, callback) {
    var textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.top = '0';
    textArea.style.left = '0';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand('copy');
      if (callback) callback();
    } catch (e) {}
    document.body.removeChild(textArea);
  }

  function fallbackRenderMarkdown(cleaned) {
    var lines = cleaned.split('\n');
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
        html.push('<div class="table-responsive"><table><thead><tr>' + heads.map(function (x) { return '<th>' + inline(x) + '</th>'; }).join('') + '</tr></thead><tbody>' + rows.map(function (r) { return '<tr>' + r.map(function (x) { return '<td>' + inline(x) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table></div>'); continue;
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

  function sanitizeHtmlOutput(rawHtml) {
    if (!rawHtml) return '';
    var purifyLib = (typeof root !== 'undefined' && root.DOMPurify) || (typeof window !== 'undefined' && window.DOMPurify) || (typeof DOMPurify !== 'undefined' ? DOMPurify : null);
    if (purifyLib) {
      if (typeof purifyLib === 'function' && typeof purifyLib.sanitize !== 'function' && typeof window !== 'undefined') {
        try { purifyLib = purifyLib(window); } catch (e) {}
      }
      if (purifyLib && typeof purifyLib.sanitize === 'function') {
        return purifyLib.sanitize(rawHtml, {
          ADD_TAGS: ['button'],
          ADD_ATTR: ['target', 'onclick', 'title', 'type', 'class']
        });
      }
    }
    // Fallback security sanitizer if DOMPurify instance is unavailable
    return String(rawHtml)
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/<([^>]+)\s+onerror\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+)/gi, '<$1')
      .replace(/<([^>]+)\s+onload\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+)/gi, '<$1')
      .replace(/href\s*=\s*["']?\s*javascript:[^"'>]*/gi, 'href="#"');
  }

  function renderMarkdown(markdown) {
    var cleaned = cleanMarkdownContent(markdown);
    if (!cleaned) return '';

    var markedLib = (typeof root !== 'undefined' && root.marked) || (typeof window !== 'undefined' && window.marked) || (typeof marked !== 'undefined' ? marked : null);
    if (markedLib) {
      try {
        initMarkedEngine();
        var m = markedLib.marked || markedLib;
        var rawHtml = m.parse(cleaned);
        return sanitizeHtmlOutput(rawHtml);
      } catch (err) {
        console.warn('Marked parse error, fallback to legacy renderer:', err);
      }
    }

    return sanitizeHtmlOutput(fallbackRenderMarkdown(cleaned));
  }

  function stripMarkdown(line) {
    return String(line).replace(/^\s*>\s?/, '').replace(/^\s*(?:[-*+] |\d+[.)] )/, '').replace(/^\s*#{1,6}\s*/, '').replace(/[`*_~]/g, '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/\s+/g, ' ').trim();
  }
  function summarizeMarkdown(markdown, limit) {
    limit = Math.max(1, Number(limit) || 5); var lines = String(markdown || '').split(/\r?\n/), wanted = /^(核心结论|结论|建议|风险|策略)/, active = false, inFence = false, candidates = [], fallback = [];
    lines.forEach(function (line) { if (/^\s*```/.test(line)) { inFence = !inFence; return; } if (inFence) return; var h = line.match(/^\s*#{1,6}\s+(.+)/), clean = stripMarkdown(line); if (h) { active = wanted.test(stripMarkdown(h[1])); return; } if (clean) { if (active) candidates.push(clean); else fallback.push(clean); } });
    var valid = function (x) { return x && !/^[-| ]+$/.test(x); }, preferred = candidates.filter(valid), result = [], seen = new Set(); (preferred.length ? preferred : fallback.filter(valid)).forEach(function (x) { x = x.slice(0, 120); if (!seen.has(x) && result.length < limit) { seen.add(x); result.push(x); } }); return result.slice(0, Math.min(limit, 5));
  }

  // 格式化对话框任务结果摘要：实质性保留核心结论、指标打分与实战三原则，杜绝过度缩减，末尾附完整研报工作区直达卡片
  function formatChatDialogueSummary(markdown, options) {
    options = options || {};
    var rawText = cleanMarkdownContent(markdown || '');
    if (!rawText) return '<span style="color:#86909C;">任务已执行完毕。</span>';

    var deliverableFilename = options.deliverableFilename || '';
    var summaryMarkdown = rawText;

    // 当报告内容较长时，提取包含所有核心结论、量化指标打分、实战交易三原则及重点风控建议的实质性段落
    if (rawText.length > 2000) {
      var lines = rawText.split(/\r?\n/);
      var selectedLines = [];
      var currentSectionWanted = true;
      var inFence = false;
      var hasKeySectionFound = false;

      var keySectionRegex = /(核心结论|结论|诊断|定性|多因子|量化评分|评分|关键指标|指标|实战|原则|保本|止损|动作|风控|建议|策略|复盘|研判|操作)/;
      var verboseSectionRegex = /(原始数据|计算日志|接口抓取明细|完整时序特征表|回溯测试全量清单)/;

      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (/^\s*```/.test(line)) {
          inFence = !inFence;
        }

        var headerMatch = line.match(/^(\s*#{1,4}\s+)(.+)/);
        if (headerMatch && !inFence) {
          var headerText = headerMatch[2].trim();
          if (verboseSectionRegex.test(headerText)) {
            currentSectionWanted = false;
          } else if (keySectionRegex.test(headerText)) {
            currentSectionWanted = true;
            hasKeySectionFound = true;
          } else {
            currentSectionWanted = true;
          }
        }

        if (currentSectionWanted) {
          selectedLines.push(line);
        }
      }

      if (hasKeySectionFound && selectedLines.length >= 10) {
        summaryMarkdown = selectedLines.join('\n').trim();
      }
    }

    var renderedHtml = renderMarkdown(summaryMarkdown);

    // 在对话框摘要底部附带完整报告工作区直达卡片
    if (deliverableFilename) {
      var bannerHtml = '<div class="dialogue-deliverable-banner" style="margin-top: 14px; padding: 10px 14px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; gap: 8px;">' +
        '<div style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: #1E293B;">' +
        '  <span style="font-size: 16px;">📄</span>' +
        '  <span><strong>完整详尽研报：</strong><a href="javascript:void(0)" class="chat-md-chip" onclick="window.openMarkdownInWorkbench &amp;&amp; window.openMarkdownInWorkbench(\'' + escapeHtml(deliverableFilename) + '\')" title="在右侧工作区打开完整报告"><span class="chip-icon">📄</span> <span class="chip-title">' + escapeHtml(deliverableFilename) + '</span> <span class="chip-arrow">↗</span></a></span>' +
        '</div>' +
        '<button type="button" class="btn-workbench-direct" onclick="window.openMarkdownInWorkbench &amp;&amp; window.openMarkdownInWorkbench(\'' + escapeHtml(deliverableFilename) + '\')" style="padding: 4px 10px; font-size: 12px; background: #1677FF; color: #fff; border: none; border-radius: 4px; cursor: pointer; white-space: nowrap;">在工作区查看完整详报 ↗</button>' +
        '</div>';
      renderedHtml += bannerHtml;
    }

    return renderedHtml;
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
    // 智能排序：如果有待执行的 'result' 节点，新执行节点应插入在 'result' 节点之前，确保任务总结与交付物永远收口在最后
    var resultIndex = state.timelineNodes.findIndex(function(n) { return n.type === 'result' && n.status === 'pending'; });
    if (resultIndex !== -1 && (type === 'thought' || type === 'tool' || type === 'stage')) {
      state.timelineNodes.splice(resultIndex, 0, node);
    } else {
      state.timelineNodes.push(node);
    }
    return node;
  }
  function applyEvent(state, type, payload) {
    if (!state || !type) return state;
    payload = payload || {};
    var now = timestamp(eventValue(payload, ['timestamp', 'received_at', 'started_at', 'startedAt'], null));
    if (type === 'thought') {
      var thought = eventValue(payload, ['content', 'text', 'summary'], '');
      var thoughtStr = String(thought || '');
      if (thoughtStr) {
        // 智能检索当前轮次活动的思考节点（即使末尾有预置的 result 节点也能平滑累加）
        var targetThoughtNode = null;
        for (var idx = state.timelineNodes.length - 1; idx >= 0; idx--) {
          var candidate = state.timelineNodes[idx];
          if (candidate.type === 'thought') {
            targetThoughtNode = candidate;
            break;
          }
          // 如果逆序查找时先遇到了活跃或已完成的工具调用（非占位），说明进入了下一轮思考
          if (candidate.type === 'tool' && candidate.nodeId !== 'step-exec' && candidate.status !== 'pending') {
            break;
          }
        }

        if (targetThoughtNode) {
          targetThoughtNode.summary = (targetThoughtNode.summary || '') + thoughtStr;
          targetThoughtNode.completedAt = timestamp(eventValue(payload, ['completed_at', 'completedAt'], now)) || now;
        } else if (thoughtStr.trim()) {
          var tn = timelineNode(state, 'thought', eventValue(payload, ['title'], '模型思考推演'));
          tn.status = 'succeeded';
          tn.summary = thoughtStr;
          tn.startedAt = now;
          tn.completedAt = timestamp(eventValue(payload, ['completed_at', 'completedAt'], now)) || now;
        }
      }
    } else if (type === 'tool_call_start') {
      state.fullMarkdown = '';
      var callId = eventValue(payload, ['call_id', 'callId', 'id'], null), callKey = callId == null ? null : String(callId);
      var tool = callKey != null ? state._toolNodesByCallId[callKey] : null;
      if (!tool) {
        // 如果列表中存在占位的 step-exec 且为 pending，优先复用该槽位
        var placeholderIndex = state.timelineNodes.findIndex(function(n) { return n.nodeId === 'step-exec' && n.status === 'pending'; });
        if (placeholderIndex !== -1) {
          tool = state.timelineNodes[placeholderIndex];
          tool.callId = callKey;
          if (callKey != null) state._toolNodesByCallId[callKey] = tool;
        } else {
          tool = timelineNode(state, 'tool', eventValue(payload, ['title', 'skill_id', 'skillId', 'action'], '工具调用'));
          tool.callId = callKey;
          if (callKey != null) state._toolNodesByCallId[callKey] = tool;
        }
      }
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
      var previousStatus = match.status;
      var terminal = String(eventValue(payload, ['status', 'state', 'outcome', 'type'], '')).toLowerCase();
      var isUnavailable = terminal === 'unavailable' || (payload.data && typeof payload.data === 'object' && payload.data.status === 'unavailable');
      var isTimeout = terminal === 'timeout' || (payload.data && typeof payload.data === 'object' && payload.data.status === 'timeout');
      var hasExplicitError = Boolean(payload.error);
      var isDataError = Boolean(payload.data && typeof payload.data === 'object' && payload.data.status === 'error');
      var isFailed = terminal === 'failed' || terminal === 'error' || isDataError || hasExplicitError;
      var isSuccess = terminal === 'success' || terminal === 'succeeded' || terminal === 'ok';

      if (isUnavailable) {
        match.status = 'degraded';
        match.error = null;
      } else if (isSuccess && !hasExplicitError && !isDataError) {
        match.status = 'succeeded';
        match.error = null;
      } else if (isFailed || isTimeout) {
        var wasFailed = match.status === 'failed';
        var toolError = payload.error || (payload.data && typeof payload.data === 'object' && (payload.data.error || (isDataError && payload.data.message)) ? payload.data : null) || (payload.data && typeof payload.data === 'object' && payload.data.code && !/^\d{6}$/.test(String(payload.data.code)) ? payload.data : null) || payload;
        var errorDetail = toolError && (toolError.detail || toolError.message || (typeof toolError.error === 'string' ? toolError.error : '') || (typeof toolError === 'string' ? toolError : ''));
        var rawCode = toolError && toolError.code;
        if (rawCode && /^\d{6}$/.test(String(rawCode))) {
          rawCode = null;
        }
        if (!rawCode && toolError && typeof toolError.error === 'string' && errors[toolError.error]) {
          rawCode = toolError.error;
        }
        match.status = 'failed';
        if (!hasData && previousStatus !== 'failed') { match.result = null; if (match.callId != null) delete state.toolResultsByCallId[match.callId]; }
        var errorObj = typeof toolError === 'object' && toolError !== null ? Object.assign({}, toolError) : {};
        errorObj.code = rawCode || (isTimeout ? 'LLM_TIMEOUT' : 'CAPABILITY_EXECUTION_FAILED');
        errorObj.detail = errorDetail || payload.detail;
        match.error = presentError(errorObj);
        if (!wasFailed && !state._toolFailureSeen) { match.expanded = true; state.timelineExpanded = true; state._toolFailureSeen = true; }
      } else {
        match.status = 'degraded';
        match.error = null;
      }
      if (!hasData && previousStatus !== match.status) { match.result = null; if (match.callId != null) delete state.toolResultsByCallId[match.callId]; }
      if (explicitElapsed) Object.defineProperty(match, '_elapsedExplicit', { value: true, writable: true, configurable: true, enumerable: false });
    } else if (type === 'content_delta') {
      state.fullMarkdown += String(eventValue(payload, ['text', 'delta', 'content'], ''));
    } else if (type === 'error') {
      var errorInput = payload.error && typeof payload.error === 'object' ? Object.assign({}, payload, payload.error) : payload, presented = presentError(errorInput); state.errors.push(presented); var en = timelineNode(state, 'error', presented.title); en.status = 'failed'; en.error = presented; en.summary = presented.detail || presented.recovery; en.expanded = true; state.status = 'failed'; state._failed = true; state.timelineExpanded = true;
    } else if (type === 'done') {
      state.metrics.elapsedMs = duration(eventValue(payload, ['elapsed_ms', 'elapsedMs'], state.metrics.elapsedMs)); state.metrics.tokens = eventValue(payload, ['total_tokens', 'tokens'], state.metrics.tokens); state.metrics.finishReason = eventValue(payload, ['finish_reason', 'finishReason'], state.metrics.finishReason);
      if (!state._failed) {
        state.status = 'succeeded';
        state.summaryItems = summarizeMarkdown(state.fullMarkdown);
        var resultNode = state.timelineNodes.find(function (n) { return n.type === 'result'; });
        var doneNode = state.timelineNodes.find(function (n) { return n.type === 'done'; });
        var targetNode = resultNode || doneNode || timelineNode(state, 'done', '完成');
        targetNode.status = 'succeeded';
        targetNode.completedAt = timestamp(eventValue(payload, ['completed_at', 'completedAt', 'timestamp'], null));
        targetNode.elapsedMs = state.metrics.elapsedMs;
        targetNode.summary = state.summaryItems.join('；');
      }
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
  var errors = {
    LLM_NOT_CONFIGURED: ['模型尚未配置', '请先完成模型配置后重试'],
    LLM_AUTH_FAILED: ['模型认证失败', '请检查 API 密钥后重试'],
    LLM_MODEL_UNAVAILABLE: ['模型暂不可用', '请稍后重试或选择其他模型'],
    LLM_CAPABILITY_UNSUPPORTED: ['模型不支持此能力', '请更换支持该能力的模型'],
    LLM_TIMEOUT: ['请求超时', '请稍后重试'],
    SSE_HTTP_ERROR: ['服务连接失败', '请稍后重试'],
    SSE_INCOMPLETE: ['响应未完成', '请重试'],
    CAPABILITY_EXECUTION_FAILED: ['能力执行失败', '后端计算或调用异常，请稍后重试'],
    CAPABILITY_NOT_IMPLEMENTED: ['能力暂未接入', '该能力尚未接通生产执行引擎'],
    ACCOUNT_DATA_UNAVAILABLE: ['账户数据不可用', '未找到模拟盘账户或资金数据'],
    DATA_UNAVAILABLE: ['数据暂不可用', '未获取到目标股票的实时数据或该标的不存在'],
    INVALID_STOCK_CODE: ['股票代码无效', '股票代码不存在或已退市，请核对后重试'],
    ANALYSIS_INCOMPLETE: ['分析未完成', '基础数据不足以完成全面诊断'],
    ORDER_RESULT_INVALID: ['订单请求无效', '订单执行失败或参数不合规'],
  };
  function presentError(error) {
    var rawCode = error && (error.code || error.error);
    var code = (rawCode && !/^\d{6}$/.test(String(rawCode))) ? rawCode : null;
    var item = code && Object.prototype.hasOwnProperty.call(errors, code) ? errors[code] : ['请求失败', '请稍后重试'];
    var rawDetail = error && (error.detail != null ? error.detail : (error.message || error.error || ''));
    if (typeof rawDetail === 'object' && rawDetail !== null) {
      rawDetail = rawDetail.detail || rawDetail.message || rawDetail.error || JSON.stringify(rawDetail);
    }
    return { code: code || 'UNKNOWN', title: item[0], recovery: item[1], detail: redactSensitive(rawDetail || '') };
  }

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

    var agentInfo = resolveSkillAgent(targetSkill);

    var steps = [
      {
        nodeId: 'step-intent',
        type: 'intent',
        level: 0,
        title: '判断意图 ' + (stockLabel ? (stockLabel + ' 研判') : (promptText.slice(0, 18) || '任务执行')),
        summary: '用户需求匹配 SOP「' + sopName + '」，提取核心参数与治理策略。',
        status: 'succeeded'
      },
      {
        nodeId: 'step-sop',
        type: 'sop',
        level: 0,
        title: '选择SOP ' + sopName,
        summary: '规划执行路径：前置数据核验 ➔ 调度 ' + targetSkill + ' ➔ 交叉风控审计。',
        status: 'succeeded'
      },
      {
        nodeId: 'step-exec',
        type: 'tool',
        level: 0,
        title: '能力调用 ' + targetSkill,
        skill_id: targetSkill,
        agentName: agentInfo.name,
        agentRole: agentInfo.role,
        agentIcon: agentInfo.icon,
        action: 'execute_pipeline',
        summary: '调度就地量化技能底座，规定执行核心运算与数据检验。',
        status: 'pending',
        deliverable: { filename: deliverableName },
        expanded: true,
        children: [
          {
            stepId: 'sub-1',
            title: '前置数据与参数核验',
            summary: '核对标的 ' + (stockLabel || '自选池') + ' 交易日历与行情基线',
            detail: '已就地校验数据桥接源，优先读取实时行情，保障数据完整。',
            status: 'succeeded'
          },
          {
            stepId: 'sub-2',
            title: '调度核心算子 ' + targetSkill,
            summary: '运行算法流水线与指标矩阵计算',
            detail: '基于量化底座零依赖执行，完成截面因子与策略研判。',
            status: 'pending'
          },
          {
            stepId: 'sub-3',
            title: '交叉风控审计与生成交付物',
            summary: '生成结构化分析文档 ' + deliverableName,
            detail: '遵循实战三原则：最低保本价、三级止损阶梯与三场景反应动作单。',
            status: 'pending'
          }
        ]
      },
      {
        nodeId: 'step-result',
        type: 'result',
        level: 0,
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

  var SKILL_AGENT_MAP = {
    'astock-screener-5a': { name: '5A Screener Agent', role: '五维共振选股智能体', icon: '🤖' },
    'astock-platform-evaluate': { name: 'Evaluation Agent', role: '综合研报与解套智能体', icon: '📊' },
    'astock-action-execution': { name: 'Action Execution Agent', role: '实战反应与保本价风控智能体', icon: '🛡️' },
    'astock-strategy-macd': { name: 'MACD Pattern Agent', role: '形态识别智能体', icon: '📈' },
    'astock-agent-debate': { name: 'Debate Orchestrator', role: '7大分析师多空辩论', icon: '⚖️' },
    'astock-data-feed': { name: 'Data Feed Agent', role: '行情与筹码穿透智能体', icon: '🔍' },
    'astock-strategy-tuige': { name: 'Tuige Shortline Agent', role: '短线接力规则智能体', icon: '⚡' },
    'astock-strategy-mainboard': { name: 'Mainboard Swing Agent', role: '主板波段智能体', icon: '🎯' },
    'astock-trade-paper': { name: 'Paper Trading Agent', role: '模拟撮合交易智能体', icon: '💹' },
    'astock-quant-engine': { name: 'Quant Pipeline Agent', role: '量化因子工程引擎', icon: '⚙️' },
    'astock-pool-audit': { name: 'Pool Audit Agent', role: '股票池审查智能体', icon: '📋' },
    'astock-pool-dashboard': { name: 'Pool Dashboard Agent', role: '股票池全景看板', icon: '💼' }
  };

  function resolveSkillAgent(skillId) {
    if (!skillId) return { name: 'Quant Agent', role: '量化执行智能体', icon: '🤖' };
    var normalized = String(skillId).trim().replace(/_/g, '-');
    if (SKILL_AGENT_MAP[normalized]) return SKILL_AGENT_MAP[normalized];
    for (var key in SKILL_AGENT_MAP) {
      if (normalized.indexOf(key) !== -1 || key.indexOf(normalized) !== -1) {
        return SKILL_AGENT_MAP[key];
      }
    }
    return { name: skillId + ' Agent', role: '专职执行智能体', icon: '🤖' };
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

  function groupContinuousHomogeneousTools(nodes) {
    if (!nodes || nodes.length <= 1) return nodes;
    var grouped = [];
    var i = 0;
    while (i < nodes.length) {
      var n = nodes[i];
      if (n.type === 'tool' && n.nodeId !== 'step-exec') {
        var skillKey = n.skill_id || n.action;
        var run = [n];
        var j = i + 1;
        while (j < nodes.length && nodes[j].type === 'tool' && (nodes[j].skill_id || nodes[j].action) === skillKey && nodes[j].nodeId !== 'step-exec') {
          run.push(nodes[j]);
          j++;
        }
        if (run.length > 1) {
          var hasFailed = run.some(function (x) { return x.status === 'failed'; });
          var hasRunning = run.some(function (x) { return x.status === 'running'; });
          var allDone = run.every(function (x) { return x.status === 'succeeded'; });
          var status = hasFailed ? 'failed' : (hasRunning ? 'running' : (allDone ? 'succeeded' : 'degraded'));

          var groupNode = {
            nodeId: 'group_' + n.nodeId,
            type: 'tool_group',
            skill_id: skillKey,
            action: n.action,
            status: status,
            items: run,
            expanded: n.expanded !== false,
            expandedDrawer: false
          };
          grouped.push(groupNode);
          i = j;
          continue;
        }
      }
      grouped.push(n);
      i++;
    }
    return grouped;
  }

  function calculateExecutionProgress(state) {
    if (!state) return 0;
    if (state.status === 'succeeded') return 100;
    if (state.status === 'failed') return 100;
    if (typeof state.progress === 'number' && Number.isFinite(state.progress)) {
      return Math.max(5, Math.min(100, Math.round(state.progress)));
    }
    var rawNodes = state.timelineNodes || [];
    var totalSteps = Math.max(rawNodes.length, 1);
    var completedCount = 0;
    var runningCount = 0;

    for (var i = 0; i < rawNodes.length; i++) {
      var st = rawNodes[i].status;
      if (st === 'succeeded' || st === 'failed' || st === 'degraded') {
        completedCount++;
      } else if (st === 'running') {
        runningCount++;
      }
    }

    var progress = 18;
    if (state.fullMarkdown && state.fullMarkdown.length > 0) {
      var textFactor = Math.min(15, Math.floor(state.fullMarkdown.length / 20));
      progress = 80 + textFactor;
    } else if (totalSteps > 0) {
      var stepRatio = (completedCount + runningCount * 0.5) / Math.max(totalSteps, 2);
      progress = Math.round(20 + stepRatio * 60);
    }

    progress = Math.max(15, Math.min(96, progress));
    if (state._maxProgress == null) state._maxProgress = progress;
    else state._maxProgress = Math.max(state._maxProgress, progress);
    return state._maxProgress;
  }

  function formatStepTextWithMdLinks(rawText) {
    if (!rawText) return '';
    var textStr = String(rawText);
    if (textStr.indexOf('<a ') !== -1 || textStr.indexOf('class="chat-md-chip"') !== -1) {
      return textStr;
    }
    var escaped = escapeHtml(textStr);
    return escaped.replace(/(`?)([a-zA-Z0-9_\-/\\]+\.(?:md|markdown))\1/gi, function (match, quote, fn) {
      var cleanFn = fn.split('/').pop().split('\\').pop();
      return '<a href="javascript:void(0)" class="chat-md-chip" onclick="window.openMarkdownInWorkbench &amp;&amp; window.openMarkdownInWorkbench(\'' + escapeHtml(fn) + '\')" title="在工作区打开文档"><span class="chip-icon">📄</span> <span class="chip-title">' + escapeHtml(cleanFn) + '</span> <span class="chip-arrow">↗</span></a>';
    });
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

    var rawNodes = state.timelineNodes || [];
    // 执行哪一步显示哪一步任务：当已有正在执行或已完成步骤时，执行过程中不罗列未来未开始(pending)的预置任务
    var hasActiveOrDone = rawNodes.some(function (n) {
      return n.status === 'running' || n.status === 'succeeded' || n.status === 'failed' || n.status === 'degraded';
    });
    if (isStreaming && hasActiveOrDone) {
      rawNodes = rawNodes.filter(function (n) {
        return n.status !== 'pending';
      });
    }
    var nodes = groupContinuousHomogeneousTools(rawNodes);

    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var isNodeFailed = n.status === 'failed';
      var isNodeRunning = n.status === 'running';
      var isNodeDone = n.status === 'succeeded';
      var isNodeDegraded = n.status === 'degraded';
      var itemClass = 'timeline-node-item' + (isNodeFailed ? ' node-failed' : (isNodeRunning ? ' node-running' : (isNodeDegraded ? ' node-degraded' : ' node-done')));

      if (n.type === 'thought') {
        var thoughtText = String(n.summary || '').trim();
        var isThoughtOpen = n.expanded === true;
        var isLong = thoughtText.length > 50 || thoughtText.indexOf('\n') !== -1;
        var previewText = isLong ? (thoughtText.slice(0, 48) + '...') : thoughtText;

        html += '<div class="' + itemClass + ' node-thought-card" id="' + escapeHtml(n.nodeId) + '">';
        html += '  <div class="node-main-row">';
        html += '    <span class="node-icon">🧠</span>';
        html += '    <div class="node-text-col" style="cursor: pointer;" onclick="window.toggleNodeDrawer && window.toggleNodeDrawer(\'' + escapeHtml(state.responseId) + '\', \'' + escapeHtml(n.nodeId) + '\')">';
        html += '      <div class="node-title">' + escapeHtml(n.title || '模型思考推演');
        html += '        <span class="drawer-arrow" style="margin-left: 4px; font-size: 8px; color: #86909C;">' + (isThoughtOpen ? '▼' : '▶') + '</span>';
        html += '      </div>';
        if (!isThoughtOpen && previewText) {
          html += '      <div class="node-subtext" style="color:#64748B;">' + escapeHtml(previewText) + '</div>';
        }
        html += '    </div>';
        html += '  </div>';
        html += '  <div class="node-drawer-body' + (isThoughtOpen ? ' open' : ' closed') + '" id="drawer_' + escapeHtml(n.nodeId) + '" style="margin-top: 3px; margin-left: 19px;">';
        html += '    <div class="thought-full-box">' + escapeHtml(thoughtText) + '</div>';
        html += '  </div>';
        html += '</div>';
        continue;
      }

      var nodeIcon = '•';
      if (n.type === 'intent') nodeIcon = '📝';
      else if (n.type === 'sop') nodeIcon = '⇥';
      else if (n.type === 'thought') nodeIcon = '🧠';
      else if (n.type === 'confirmation') nodeIcon = '🎯';
      else if (n.type === 'tool' || n.type === 'tool_group' || n.type === 'stage') nodeIcon = isNodeFailed ? '❌' : (isNodeDegraded ? '⚠️' : (isNodeRunning ? '⏳' : '🔧'));
      else if (n.type === 'result' || n.type === 'done') nodeIcon = '📄';
      else if (n.type === 'error') nodeIcon = '⚠️';

      var nodeTitle = n.title;
      var isGroup = n.type === 'tool_group';

      if (n.type === 'tool' || isGroup) {
        var skillLabel = n.skill_id || n.action || n.title || '技能调用';
        var prefix = isNodeFailed ? '能力调用失败 ' : (isNodeRunning ? '能力调用中 ' : (isNodeDegraded ? '能力暂未可用 ' : '能力调用完成 '));
        if (isGroup) {
          nodeTitle = '能力调用' + skillLabel + '任务（批量' + n.items.length + '次调用）';
        } else {
          nodeTitle = prefix + skillLabel;
        }
      }

      var subInfo = n.summary || '';
      if (isGroup) {
        var groupItems = n.items || [];
        var failedItems = groupItems.filter(function (x) { return x.status === 'failed'; });
        var succeededItems = groupItems.filter(function (x) { return x.status === 'succeeded' || x.status === 'success'; });
        if (isNodeRunning) {
          subInfo = '正在执行 ' + groupItems.length + ' 次批量调用...';
        } else if (failedItems.length === groupItems.length && groupItems.length > 0) {
          subInfo = '已挂接 ' + groupItems.length + ' 次子任务调用，全部执行失败';
        } else if (failedItems.length > 0) {
          subInfo = '已聚合挂接 ' + groupItems.length + ' 次子任务调用（' + succeededItems.length + ' 项成功，' + failedItems.length + ' 项失败）';
        } else {
          subInfo = '已聚合挂接 ' + groupItems.length + ' 次子任务调用并汇总数据';
        }
      } else if (!subInfo && n.action) {
        subInfo = '第 ' + (i + 1) + ' 个动作 · ' + n.action;
      }
      if (isNodeFailed && n.error) {
        var errTitle = n.error.title || n.error.detail || '执行异常';
        var rawCode = String(n.error.code || '');
        var hidePrefix = ['CAPABILITY_EXECUTION_FAILED', 'UNKNOWN', 'ERROR', 'FAILED', 'DATA_UNAVAILABLE'];
        var codePrefix = (rawCode && hidePrefix.indexOf(rawCode) === -1 && !/^\d{6}$/.test(rawCode)) ? (rawCode + ' · ') : '';
        subInfo = codePrefix ? (codePrefix + errTitle) : errTitle;
      } else if (isNodeDegraded && !subInfo) {
        subInfo = '能力暂未接入生产引擎';
      }

      var isBranchNode = n.type === 'tool' || isGroup || n.type === 'stage' || (n.children && n.children.length > 0);
      var isBranchExpanded = n.expanded !== false;

      html += '<div class="' + itemClass + (isBranchNode ? ' tree-parent-node' : '') + '" id="' + escapeHtml(n.nodeId) + '">';
      html += '  <div class="node-main-row">';
      html += '    <span class="node-icon">' + nodeIcon + '</span>';
      html += '    <div class="node-text-col">';
      html += '      <div class="node-title' + (isNodeFailed ? ' text-failed' : '') + '">' + formatStepTextWithMdLinks(nodeTitle) + '</div>';
      if (subInfo) {
        html += '      <div class="node-subtext' + (isNodeFailed ? ' text-failed-sub' : '') + '">' + formatStepTextWithMdLinks(subInfo) + '</div>';
      }
      html += '    </div>';

      if (isBranchNode) {
        html += '    <button type="button" class="branch-toggle-btn" id="toggle_' + escapeHtml(n.nodeId) + '" onclick="window.toggleBranchCollapse && window.toggleBranchCollapse(\'' + escapeHtml(state.responseId) + '\', \'' + escapeHtml(n.nodeId) + '\')" title="切换子层级展开/收起">';
        html += isBranchExpanded ? '∨' : '>';
        html += '    </button>';
      }
      html += '  </div>';

      // 树形缩进显示框架 (Indented Tree Branch Container with Left Hierarchy Guide Line)
      if (isBranchNode) {
        var agent = resolveSkillAgent(n.skill_id);
        var agentName = n.agentName || agent.name;
        var agentIcon = n.agentIcon || agent.icon;
        var agentStatus = isNodeRunning ? '正在调度执行...' : (isNodeFailed ? '执行遇到异常' : (isNodeDegraded ? '能力暂未接入' : (isGroup ? ('批量执行完成 (' + n.items.length + '项)') : '执行完成')));

        html += '  <div class="timeline-branch-container' + (isBranchExpanded ? '' : ' collapsed') + '" id="branch_' + escapeHtml(n.nodeId) + '">';

        // Level 1: 子智能体卡片
        html += '    <div class="subagent-node-card status-' + (isNodeFailed ? 'failed' : (isNodeRunning ? 'running' : 'done')) + '">';
        html += '      <div class="subagent-header-row">';
        html += '        <span class="subagent-icon">' + agentIcon + '</span>';
        html += '        <span class="subagent-name">' + escapeHtml(agentName) + '</span>';
        html += '        <span class="subagent-divider">|</span>';
        html += '        <span class="subagent-status-text">' + escapeHtml(agentStatus) + '</span>';
        html += '      </div>';
        html += '    </div>';

        // Level 2: 操作步骤与调用子树（二级缩进 + 层级引导线）
        html += '    <div class="timeline-branch-container level-2-branch">';

        if (isGroup) {
          // 批量父任务下的每个原子调用作为挂接子任务展示
          for (var itemIdx = 0; itemIdx < n.items.length; itemIdx++) {
            var itemObj = n.items[itemIdx];
            var subCallId = escapeHtml(itemObj.nodeId || (n.nodeId + '_sub_' + itemIdx));
            var itemIcon = itemObj.status === 'failed' ? '❌' : (itemObj.status === 'running' ? '⏳' : (itemObj.status === 'degraded' ? '⚠️' : '•'));
            var itemSummary = itemObj.summary || (itemObj.action ? (itemObj.action + ' 完成') : '调用成功');
            var itemSkill = itemObj.skill_id || skillLabel;
            var itemTitle = '子任务 ' + (itemIdx + 1) + ': ' + itemSkill + ' · ' + itemSummary;

            html += '      <div class="step-leaf-item" id="' + subCallId + '">';
            html += '        <div class="step-summary-bar">';
            html += '          <span class="step-bullet">' + itemIcon + '</span>';
            html += '          <span class="step-title">' + formatStepTextWithMdLinks(itemTitle) + '</span>';
            html += '        </div>';
            if (itemObj.args && typeof itemObj.args === 'object' && Object.keys(itemObj.args).length > 0) {
              var argsStr = '';
              try { argsStr = JSON.stringify(itemObj.args); } catch(e) { argsStr = String(itemObj.args); }
              html += '        <div class="step-detail-text" style="display:block; margin-top:1px; margin-left:14px; font-size:11px; color:#64748B;">';
              html += '          参数: ' + escapeHtml(argsStr);
              html += '        </div>';
            }
            html += '      </div>';
          }
        } else if (n.children && n.children.length) {
          for (var c = 0; c < n.children.length; c++) {
            var sub = n.children[c];
            var subId = escapeHtml(sub.stepId || (n.nodeId + '_sub_' + c));
            var subTitle = sub.title || ('步骤 ' + (c + 1));
            var hasSubDetail = Boolean(sub.detail);

            html += '      <div class="step-leaf-item">';
            html += '        <div class="step-summary-bar" onclick="window.toggleStepDetail && window.toggleStepDetail(\'' + escapeHtml(state.responseId) + '\', \'' + subId + '\')">';
            html += '          <span class="step-bullet">•</span>';
            html += '          <span class="step-title">' + formatStepTextWithMdLinks(subTitle) + '</span>';
            if (hasSubDetail) {
              html += '          <span class="step-chevron" id="arrow_' + subId + '">></span>';
            }
            html += '        </div>';
            if (hasSubDetail) {
              html += '        <div class="step-detail-text hidden" id="detail_' + subId + '">';
              html += formatStepTextWithMdLinks(sub.detail);
              html += '        </div>';
            }
            html += '      </div>';
          }
        } else {
          // 动态单工具调用降级/默认步骤展示
          html += '      <div class="step-leaf-item">';
          html += '        <div class="step-summary-bar">';
          html += '          <span class="step-bullet">•</span>';
          html += '          <span class="step-title">' + formatStepTextWithMdLinks(subInfo || '执行底层量化引擎计算') + '</span>';
          html += '        </div>';
          html += '      </div>';
        }

        // Collapsible tool result drawer (as in Image 1 and Image 3)
        var drawerObj = isGroup ? { batch_count: n.items.length, results: n.items.map(function(x){ return x.result; }) } : (n.result != null ? n.result : { error: n.error });
        var hasDrawerData = isGroup ? n.items.some(function(x){ return x.result != null; }) : (n.result != null || (n.error && n.error.detail));
        if (hasDrawerData) {
          var isDrawerOpen = n.expandedDrawer === true;
          html += '      <div class="node-drawer-wrap" style="margin-left: 2px;">';
          html += '        <button type="button" class="node-drawer-btn" onclick="window.toggleNodeDrawer && window.toggleNodeDrawer(\'' + escapeHtml(state.responseId) + '\', \'' + escapeHtml(n.nodeId) + '\')">';
          html += '          <span class="drawer-arrow">' + (isDrawerOpen ? '▼' : '▶') + '</span> 查看能力结果';
          html += '        </button>';
          html += '        <div class="node-drawer-body' + (isDrawerOpen ? ' open' : ' closed') + '" id="drawer_' + escapeHtml(n.nodeId) + '">';
          html += '          <pre class="json-code-box"><code>' + escapeHtml(JSON.stringify(drawerObj, null, 2)) + '</code></pre>';
          html += '        </div>';
          html += '      </div>';
        }

        // Deliverable clickable link (Requirement 4 & 6) for branch nodes
        var branchDeliverable = (n.deliverable && n.deliverable.filename) ? n.deliverable.filename : (
          n.result && n.result.data && Array.isArray(n.result.data.deliverables) && n.result.data.deliverables[0] ? n.result.data.deliverables[0] : (
            n.result && Array.isArray(n.result.deliverables) && n.result.deliverables[0] ? n.result.deliverables[0] : (
              n.result && n.result.deliverable_file ? n.result.deliverable_file : (
                n.result && n.result.report_file ? n.result.report_file : null
              )
            )
          )
        );
        if (branchDeliverable) {
          var fn = typeof branchDeliverable === 'string' ? branchDeliverable : (branchDeliverable.filename || branchDeliverable.name);
          html += '      <div class="node-deliverable-wrap" style="margin-left: 2px; margin-top: 4px;">';
          html += '        <span class="deliverable-link-chip" onclick="window.openDeliverableInWorkbench && window.openDeliverableInWorkbench(\'' + escapeHtml(fn) + '\')" title="在右侧工作台打开文件">';
          html += '          📄 ' + escapeHtml(fn) + ' <span class="open-arrow">↗</span>';
          html += '        </span>';
          html += '      </div>';
        }

        html += '    </div>'; // end level-2-branch
        html += '  </div>'; // end timeline-branch-container
      }

      // Deliverable clickable link (Requirement 4 & 6) for non-branch nodes
      var nonBranchDeliverable = (n.deliverable && n.deliverable.filename) ? n.deliverable.filename : (
        n.result && n.result.data && Array.isArray(n.result.data.deliverables) && n.result.data.deliverables[0] ? n.result.data.deliverables[0] : (
          n.result && Array.isArray(n.result.deliverables) && n.result.deliverables[0] ? n.result.deliverables[0] : (
            n.result && n.result.deliverable_file ? n.result.deliverable_file : (
              n.result && n.result.report_file ? n.result.report_file : null
            )
          )
        )
      );
      if (nonBranchDeliverable && !isBranchNode) {
        var nonBranchFn = typeof nonBranchDeliverable === 'string' ? nonBranchDeliverable : (nonBranchDeliverable.filename || nonBranchDeliverable.name);
        html += '  <div class="node-deliverable-wrap" style="margin-top: 4px; margin-left: 19px;">';
        html += '    <span class="deliverable-link-chip" onclick="window.openDeliverableInWorkbench && window.openDeliverableInWorkbench(\'' + escapeHtml(nonBranchFn) + '\')" title="在右侧工作台打开文件">';
        html += '      📄 ' + escapeHtml(nonBranchFn) + ' <span class="open-arrow">↗</span>';
        html += '    </span>';
        html += '  </div>';
      }

      html += '</div>'; // end timeline-node-item
    }

    // Working animation at bottom while active (Requirement 1 & 2)
    if (isStreaming) {
      var progressPercent = calculateExecutionProgress(state);
      var perimeter = 37.7;
      var dashoffset = (perimeter * (1 - progressPercent / 100)).toFixed(1);
      html += '<div class="timeline-working-indicator" data-progress="' + progressPercent + '">';
      html += '  <div class="working-progress-circle working-spinner-ring" title="执行进度: ' + progressPercent + '%" style="--progress:' + progressPercent + ';">';
      html += '    <svg class="working-progress-svg" viewBox="0 0 16 16" width="13" height="13">';
      html += '      <circle class="working-ring-track" cx="8" cy="8" r="6" fill="none" stroke="rgba(22, 119, 255, 0.18)" stroke-width="2.2" />';
      html += '      <circle class="working-ring-fill" cx="8" cy="8" r="6" fill="none" stroke="#1677FF" stroke-width="2.2" stroke-dasharray="37.7" stroke-dashoffset="' + dashoffset + '" stroke-linecap="round" transform="rotate(-90 8 8)" />';
      html += '    </svg>';
      html += '  </div>';
      html += '  <span class="working-text" data-text="working...">working<span class="working-dots"><span class="working-dot dot-1">.</span><span class="working-dot dot-2">.</span><span class="working-dot dot-3">.</span></span></span>';
      html += '</div>';
    }

    html += '</div>'; // end timeline-nodes-list
    html += '</div>'; // end execution-record-box

    return html;
  }

  root.ChatPresentation = {
    escapeHtml: escapeHtml,
    cleanMarkdownContent: cleanMarkdownContent,
    renderMarkdown: renderMarkdown,
    summarizeMarkdown: summarizeMarkdown,
    formatChatDialogueSummary: formatChatDialogueSummary,
    formatStepTextWithMdLinks: formatStepTextWithMdLinks,
    redactSensitive: redactSensitive,
    presentError: presentError,
    createResponseState: createResponseState,
    applyEvent: applyEvent,
    decomposeTask: decomposeTask,
    detectDeliverables: detectDeliverables,
    calculateExecutionProgress: calculateExecutionProgress,
    renderExecutionTimelineHtml: renderExecutionTimelineHtml,
    copyCodeBlock: copyCodeBlock,
    initMarkedEngine: initMarkedEngine
  };
}(typeof window !== 'undefined' ? window : this));
