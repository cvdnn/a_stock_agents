// ==========================================================================
// A-Stock Agents Web AIChat UI - Main Application Logic
// Supports View Routing, Interactive Charts, SSE Streaming Chat, Mock Data
// ==========================================================================

const AppState = {
  activeView: 'chat', // 'chat' | 'market' | 'watchlist'
  selectedStock: '300750',
  isChatStreaming: false,
  apiBaseUrl: window.location.origin,
  strategies: {
    'trend': true,
    'sector': true,
    'alert': true
  }
};

// 1. Synthetic K-line Generator (28 trading bars)
function generateKlines(basePrice = 320, count = 28, trend = 0.008) {
  const list = [];
  let curr = basePrice;
  const now = new Date('2026-08-27');

  for (let i = 0; i < count; i++) {
    const d = new Date(now.getTime() - (count - 1 - i) * 86400000);
    const dateStr = d.toISOString().slice(5, 10);
    const change = (Math.random() - 0.44 + trend) * (curr * 0.03);
    const open = curr;
    const close = Math.round((curr + change) * 100) / 100;
    const high = Math.round((Math.max(open, close) + Math.random() * (curr * 0.015)) * 100) / 100;
    const low = Math.round((Math.min(open, close) - Math.random() * (curr * 0.015)) * 100) / 100;
    const vol = Math.round(20000 + Math.random() * 45000);
    list.push([dateStr, open, close, high, low, vol]);
    curr = close;
  }
  return list;
}

// 2. View Routing
function switchView(viewName) {
  AppState.activeView = viewName;

  // Update Left Sidebar Active Nav
  document.querySelectorAll('.nav-item').forEach(item => {
    if (item.dataset.view === viewName) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // Update Top Sub-Nav Active Item if present
  document.querySelectorAll('.top-subnav-item').forEach(item => {
    if (item.dataset.view === viewName) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // Toggle View Panels
  document.querySelectorAll('.view-panel').forEach(panel => {
    panel.classList.remove('active');
  });

  const targetPanel = document.getElementById(`view-${viewName}`);
  if (targetPanel) {
    targetPanel.classList.add('active');
  }

  // Toggle floating bottom bar (only in watchlist view)
  const floatingBar = document.getElementById('aiFloatingBar');
  if (floatingBar) {
    floatingBar.style.display = (viewName === 'watchlist') ? 'flex' : 'none';
  }

  // Re-render corresponding charts
  setTimeout(() => {
    renderViewCharts(viewName);
  }, 50);
}

// 3. Render Charts according to active view
function renderViewCharts(viewName) {
  if (viewName === 'chat') {
    // 整体盘面 Sparklines
    FinancialCharts.drawSparkline('sparklineSh', [3390, 3405, 3400, 3415, 3422, 3418, 3426.56], true);
    FinancialCharts.drawSparkline('sparklineSz', [10750, 10780, 10820, 10800, 10860, 10892.14], true);
    FinancialCharts.drawSparkline('sparklineCy', [2250, 2265, 2260, 2278, 2282, 2289.76], true);

    // 持股/投资统计 Donut
    FinancialCharts.drawDonutChart('portfolioDonut', [
      { name: '持仓市值', value: 328.56, color: '#1677FF' },
      { name: '现金', value: 125.68, color: '#4096FF' }
    ], { centerTitle: '总市值', centerValue: '328.56万' });
  } 
  else if (viewName === 'market') {
    // 4 大指数 Sparklines
    FinancialCharts.drawSparkline('marketSparkSh', [3395, 3408, 3402, 3418, 3426.56], true);
    FinancialCharts.drawSparkline('marketSparkSz', [10760, 10795, 10830, 10892.14], true);
    FinancialCharts.drawSparkline('marketSparkCy', [2255, 2270, 2265, 2289.76], true);
    FinancialCharts.drawSparkline('marketSparkKc', [952, 958, 963, 969.43], true);

    // 市场情绪仪表盘
    FinancialCharts.drawGauge('sentimentGauge', 78, {
      statusText: '较强',
      statusColor: '#F5222D',
      fontSize: 24
    });

    // 大盘走势主 K 线图 (上证日K)
    const shKlines = generateKlines(3380, 35, 0.006);
    FinancialCharts.drawCandlestickChart('marketKlineCanvas', shKlines, { showVolume: true });
  } 
  else if (viewName === 'watchlist') {
    // 宁德时代个股 K 线
    const catlKlines = generateKlines(300, 35, 0.012);
    FinancialCharts.drawCandlestickChart('stockKlineCanvas', catlKlines, { showVolume: true });

    // 资金流向分布 Donut
    FinancialCharts.drawDonutChart('fundFlowDonut', [
      { name: '主力净流入', value: 12.36, color: '#F5222D' },
      { name: '中单小单净流出', value: 12.36, color: '#52C41A' }
    ], { centerTitle: '主力净流入', centerValue: '+12.36亿' });

    // 近5日资金流向趋势折线图 (主力 vs 散户)
    FinancialCharts.drawMultiLine('fundFlowTrendLine', 
      ['08-21', '08-22', '08-25', '08-26', '08-27'],
      [
        { name: '主力', color: '#F5222D', data: [-2, 3, 5, 8, 12.36] },
        { name: '散户', color: '#52C41A', data: [2, -1, -3, -6, -8.15] }
      ]
    );

    // 北向资金占比 Donut
    FinancialCharts.drawDonutChart('northboundDonut', [
      { name: '沪股通', value: 3.12, color: '#1677FF' },
      { name: '深股通', value: 2.11, color: '#52C41A' }
    ], { centerTitle: '北向合计', centerValue: '5.23亿' });

    // 近5日北向净买入柱状图
    FinancialCharts.drawBarChart('northboundBar',
      ['08-21', '08-22', '08-25', '08-26', '08-27'],
      [-3.2, 4.1, -1.8, 6.5, 5.23]
    );

    // 主力控盘度仪表盘
    FinancialCharts.drawGauge('mainControlGauge', 68.32, {
      suffix: '%',
      statusText: '高控盘',
      statusColor: '#1677FF',
      colorType: 'control',
      fontSize: 22
    });

    // 主力持仓变化柱状图 (近5日)
    FinancialCharts.drawBarChart('mainHoldingsBar',
      ['08-21', '08-22', '08-25', '08-26', '08-27'],
      [4.2, 6.8, 7.5, 11.2, 14.6]
    );
  }
}

// 4. Chat Typing Stream Simulation / Real SSE Bridge
function appendChatMessage(role, content, options = {}) {
  const container = document.getElementById('chatMessages');
  if (!container) return null;

  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

  const item = document.createElement('div');
  item.className = `message-item ${role === 'user' ? 'message-user' : 'message-ai'}`;

  if (role === 'user') {
    item.innerHTML = `
      <div class="message-bubble-user">
        ${content}
        <div class="message-timestamp">${timeStr}</div>
      </div>
    `;
    container.appendChild(item);
  } else {
    const title = options.title || '当前A股市场行情分析';
    const summary = options.summary || '两市成交放量破1.28万亿，科技成长主线共振领涨，短期延续震荡向上反弹格局';

    // AI Structured Response Card with integrated header (仿照第2张图布局: 头像 + 标题 + 摘要)
    item.innerHTML = `
      <div class="message-bubble-ai" id="${options.msgId || 'aiMsg_' + Date.now()}">
        <!-- 头像 + 标题 + 摘要 -->
        <div class="ai-msg-header">
          <div class="ai-avatar-pill">AI</div>
          <div class="ai-msg-header-text">
            <h3 class="ai-msg-title">${title}</h3>
            <p class="ai-msg-summary">${summary}</p>
          </div>
        </div>

        ${options.toolRunning ? `
          <div class="tool-status-bubble" id="toolStatus">
            <span class="tool-badge-running"></span>
            <span>正在调用智能量化引擎 [astock-action-execution / astock-data-feed]...</span>
          </div>
        ` : ''}

        <!-- 详细内容【在头像+标题+摘要】下方 -->
        <div class="ai-content-body">${content}</div>

        <div class="message-actions">
          <span class="action-chip" onclick="showToast('感谢您的反馈：标记为有用！')">👍 有用</span>
          <span class="action-chip" onclick="showToast('感谢反馈，我们将持续优化')">👎 没用</span>
          <span class="action-chip" onclick="copyMessageText(this)">📋 复制</span>
          <span class="action-chip" onclick="regenerateLastMessage()">🔄 重新生成</span>
        </div>
      </div>
    `;
    container.appendChild(item);
  }

  container.scrollTop = container.scrollHeight;
  return item;
}

// Typewriter Streaming
function streamAIResponse(contentOrTpl, titleParam, summaryParam) {
  let fullText = contentOrTpl;
  let title = titleParam || '当前A股市场行情分析';
  let summary = summaryParam || '两市成交放量破1.28万亿，科技成长主线共振领涨，短期延续震荡向上反弹格局';

  if (contentOrTpl && typeof contentOrTpl === 'object') {
    fullText = contentOrTpl.body || '';
    if (contentOrTpl.title) title = contentOrTpl.title;
    if (contentOrTpl.summary) summary = contentOrTpl.summary;
  }
  if (titleParam && typeof contentOrTpl !== 'object') {
    title = titleParam;
  }
  if (summaryParam) {
    summary = summaryParam;
  }

  AppState.isChatStreaming = true;
  const msgId = 'aiMsg_' + Date.now();
  
  // Initial placeholder with tool animation
  const msgElem = appendChatMessage('ai', '<span style="color:#86909C;">AI正在综合大盘、资金流、筹码与技术指标进行深度研判...</span>', {
    msgId: msgId,
    title: title,
    summary: summary,
    toolRunning: true
  });

  setTimeout(() => {
    const container = document.getElementById(msgId);
    if (!container) return;

    // Remove tool status or mark completed
    const toolStatus = container.querySelector('#toolStatus');
    if (toolStatus) {
      toolStatus.innerHTML = `
        <span style="color:#52C41A; font-weight:700;">✓</span>
        <span>已完成数据调取与实战三原则保本价精算（税费最低卖出价向上进位至分）</span>
      `;
    }

    const contentBody = container.querySelector('.ai-content-body');
    contentBody.innerHTML = '';

    // Stream characters
    let idx = 0;
    const speed = 12; // ms per char
    const interval = setInterval(() => {
      idx += 3;
      if (idx >= fullText.length) {
        clearInterval(interval);
        contentBody.innerHTML = fullText;
        AppState.isChatStreaming = false;
      } else {
        contentBody.innerHTML = fullText.slice(0, idx) + '<span style="color:#1677FF; font-weight:bold;">▌</span>';
      }
      const scrollBox = document.getElementById('chatMessages');
      if (scrollBox) scrollBox.scrollTop = scrollBox.scrollHeight;
    }, speed);
  }, 600);
}

// Quick Prompts Pre-set Content
const PromptTemplates = {
  '行情分析': {
    title: '当前A股市场行情分析',
    summary: '两市成交放量破1.28万亿，科技成长主线共振领涨，短期延续震荡向上反弹格局',
    body: `
      <div class="ai-report-section">
        <div class="ai-report-section-title">1. 整体走势</div>
        <p>今日上证指数收于 <strong>3,426.56</strong> 点，涨幅 <strong>+0.72%</strong>；深证成指收于 <strong>10,892.14</strong> 点，涨幅 <strong>+1.08%</strong>；创业板指收于 <strong>2,289.76</strong> 点，涨幅 <strong>+1.31%</strong>。两市成交额约 <strong>1.28万亿元</strong>，较昨日放量 12%，市场情绪回暖，资金呈现持续净流入。</p>
      </div>
      <div class="ai-report-section">
        <div class="ai-report-section-title">2. 主要板块表现</div>
        <ul>
          <li><strong>TMT 板块</strong>：表现强势，AI、半导体、算力硬件与软件开发领涨。</li>
          <li><strong>金融板块</strong>：小幅上涨，券商、保险稳健护盘。</li>
          <li><strong>周期板块</strong>：有色金属、特种钢材涨幅居前。</li>
          <li><strong>消费板块</strong>：整体偏弱，食品饮料与家电呈现结构性分化。</li>
        </ul>
      </div>
      <div class="ai-report-section">
        <div class="ai-report-section-title">3. 技术面分析</div>
        <p>上证指数站上 5日/10日均线，MACD 水上金叉发散；创业板指放量突破前期压力位，需关注 2,300 点强压力区筹码消化。</p>
      </div>
      <div class="summary-highlight-card">
        <span class="summary-icon">📈</span>
        <div class="summary-text"><strong>一句总结线</strong>：市场短期延续震荡向上趋势，科技成长仍是核心主线，建议逢低布局，合理控制仓位，警惕高位股获利回吐。</div>
      </div>
      <div class="risk-iron-card">
        <div class="risk-iron-header">🛡️ 实战交易三原则（合规风控指令单）</div>
        <div class="risk-iron-grid">
          <div class="risk-pill-box">
            <div class="risk-pill-title">最低保本卖出价</div>
            <div class="risk-pill-val">¥320.69 (ceil进位)</div>
          </div>
          <div class="risk-pill-box">
            <div class="risk-pill-title">T1减仓线 (-5%)</div>
            <div class="risk-pill-val">¥304.16 (减仓50%)</div>
          </div>
          <div class="risk-pill-box">
            <div class="risk-pill-title">T2绝杀线 (-8%)</div>
            <div class="risk-pill-val">¥294.55 (坚决止损)</div>
          </div>
        </div>
      </div>
    `
  },
  '技术指标': {
    title: '全市场技术形态与指标共振扫描',
    summary: '865只标的多头排列，科技主线占比超40%，重点留意水下二次金叉战法信号',
    body: `
      <div class="ai-report-section">
        <div class="ai-report-section-title">1. MACD 与均线多头排列</div>
        <p>全市场共 <strong>865</strong> 只标的出现 5日/10日/20日 均线多头排列，其中科技主线（半导体/CPO）占比超 40%。</p>
      </div>
      <div class="ai-report-section">
        <div class="ai-report-section-title">2. 水下二次金叉战法雷达</div>
        <p>雷达检测到 <strong>宁德时代 (300750)</strong> 与 <strong>海光信息 (688041)</strong> 在零轴下方完成二次金叉验底，筹码换手充分，第一脚与第二脚支撑扎实。</p>
      </div>
      <div class="summary-highlight-card">
        <span class="summary-icon">🎯</span>
        <div class="summary-text"><strong>量化提示</strong>：技术指标反弹动能充沛，但需严格遵守分级风控止损原则，防范虚假突破。</div>
      </div>
    `
  },
  '选股模型': {
    title: '5A五维共振旋转选股输出',
    summary: '多因子综合评分前三候选标的，重点关注量价共振与主力大单流向',
    body: `
      <div class="ai-report-section">
        <ul>
          <li><strong>中芯国际 (688981)</strong>：量价评分 94，资金面评分 91，主线轮动匹配度 A+，现价 98.60 元。</li>
          <li><strong>宁德时代 (300750)</strong>：量价评分 92，基本面评分 95，主力净流入 +12.36亿，现价 328.56 元。</li>
          <li><strong>海光信息 (688041)</strong>：量价评分 89，算力主线共振，突破前高筹码密集区，现价 145.20 元。</li>
        </ul>
      </div>
      <div class="summary-highlight-card">
        <span class="summary-icon">💡</span>
        <div class="summary-text"><strong>操作指引</strong>：建议以 3成底仓介入，并在开盘冲高 +3% 时分批减持，若盘中跌破 5日线立即触发 T0 对冲。</div>
      </div>
    `
  }
};

// 5. Chat Input Handler
function handleSendChat() {
  if (AppState.isChatStreaming) return;

  const input = document.getElementById('chatInput');
  const text = input ? input.value.trim() : '';
  if (!text) return;

  appendChatMessage('user', text);
  input.value = '';

  // Check matching template or fallback
  let tpl = PromptTemplates['行情分析'];
  if (text.includes('指标') || text.includes('技术')) {
    tpl = PromptTemplates['技术指标'];
  } else if (text.includes('选股') || text.includes('模型') || text.includes('股票')) {
    tpl = PromptTemplates['选股模型'];
  }

  streamAIResponse(tpl.body, tpl.title, tpl.summary);
}

// 6. Watchlist stock selection
function selectWatchStock(code) {
  AppState.selectedStock = code;
  document.querySelectorAll('.watchlist-item-card').forEach(card => {
    if (card.dataset.code === code) {
      card.classList.add('active');
    } else {
      card.classList.remove('active');
    }
  });

  showToast(`已切换至个股：${code}`);
  if (AppState.activeView !== 'watchlist') {
    switchView('watchlist');
  } else {
    renderViewCharts('watchlist');
  }
}

// 7. Strategy switch toggler
function toggleStrategy(key, el) {
  AppState.strategies[key] = el.checked;
  const status = el.checked ? '已开启' : '已暂停';
  showToast(`策略 [${key}] ${status}！盯盘后台已同步更新`);
}

// 8. Toast Helper
function showToast(msg) {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<span>🔔</span> <span>${msg}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-10px)';
    setTimeout(() => toast.remove(), 300);
  }, 2400);
}

// 9. Copy message helper
function copyMessageText(btn) {
  const card = btn.closest('.message-bubble-ai');
  if (!card) return;
  const text = card.innerText.replace(/👍 有用|👎 没用|📋 复制|🔄 重新生成/g, '').trim();
  navigator.clipboard.writeText(text).then(() => {
    showToast('内容已复制到剪贴板！');
  }).catch(() => {
    showToast('已选中内容，可直接复制');
  });
}

// 10. Regenerate message helper
function regenerateLastMessage() {
  showToast('正在重新调用 AI 模型与风控规则...');
  streamAIResponse(PromptTemplates['行情分析'], '重算行情研报');
}

// 11. Initial DOM Ready Hook
document.addEventListener('DOMContentLoaded', () => {
  // Setup Global Nav clicks
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const view = item.dataset.view;
      if (view) switchView(view);
    });
  });

  // Setup Top Sub-Nav clicks
  document.querySelectorAll('.top-subnav-item').forEach(item => {
    item.addEventListener('click', () => {
      const view = item.dataset.view;
      if (view) switchView(view);
    });
  });

  // Setup Prompt Pills click
  document.querySelectorAll('.prompt-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const key = pill.innerText.replace(/\[|\]/g, '').trim();
      const content = PromptTemplates[key] || PromptTemplates['行情分析'];
      appendChatMessage('user', `请帮我执行【${key}】并出具研报`);
      streamAIResponse(content, `${key} 深度诊断`);
    });
  });

  // Setup Card Tabs Switcher
  document.querySelectorAll('.card-tabs').forEach(tabBar => {
    tabBar.querySelectorAll('.card-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        tabBar.querySelectorAll('.card-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        showToast(`已切换至标签：${tab.innerText}`);
      });
    });
  });

  // Setup Chat Input Enter Key
  const chatInput = document.getElementById('chatInput');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendChat();
      }
    });
  }

  // Setup Floating bottom bar input
  const floatingInput = document.getElementById('aiFloatingInput');
  if (floatingInput) {
    floatingInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const text = floatingInput.value.trim();
        if (text) {
          switchView('chat');
          appendChatMessage('user', text);
          floatingInput.value = '';
          streamAIResponse(PromptTemplates['行情分析'], '针对个股即时诊断');
        }
      }
    });
  }

  // Initial View Rendering
  switchView('chat');
});

// Window resize re-renders charts
window.addEventListener('resize', () => {
  renderViewCharts(AppState.activeView);
});
