// ==========================================================================
// A-Stock Agents Web AIChat UI - Main Application Engine
// Three-Column Architecture with Independent Dual-Scroll & Bidirectional Linkage
// ==========================================================================

const AppState = {
  activeRightTab: 'dashboard', // 'dashboard' | 'market' | 'watchlist' | 'returns' | 'projected-action' etc.
  layoutMode: 'chat-center',   // 'chat-center' (投研助手居中) | 'workspace-main' (业务主工作区居中，AI助手在右)
  isCopilotCollapsed: false,
  isWorkbenchCollapsed: false,
  selectedStock: '300750',
  isChatStreaming: false,
  apiBaseUrl: window.location.origin,
  loadedSessionCount: 10,
  riskParams: {
    cost: 320.0,
    shares: 1000,
    t0: -3.0,
    t1: -5.0,
    t2: -8.0,
    stampDuty: 0.05,
    commissionRate: 0.00025,
    minCommission: 5.0,
    transferRate: 0.00002
  },
  strategies: {
    'trend': true,
    'sector': true,
    'alert': true
  },
  providers: [],
  activeProviderId: null,
  modelRoles: {
    chat: { provider_id: '', model_id: '' },
    summary: { provider_id: '', model_id: '' },
    quant: { provider_id: '', model_id: '' },
    debate: { provider_id: '', model_id: '' },
    vision: { provider_id: '', model_id: '' }
  }
};

// --------------------------------------------------------------------------
// 1. Historical Sessions Repository (时间倒序前10条 + 分页加载数据池)
// --------------------------------------------------------------------------
const HistoricalSessions = [
  { id: 's1', title: 'A股大盘反弹持续性与放量研判', time: '刚刚', tab: 'dashboard' },
  { id: 's2', title: '宁德时代300750资金面与底背离诊断', time: '今天 11:20', tab: 'watchlist' },
  { id: 's3', title: '5A多因子量化选股与主线轮动模型', time: '今天 09:45', tab: 'dashboard' },
  { id: 's4', title: '半导体与CPO算力链短线买点筛查', time: '昨天 16:15', tab: 'market' },
  { id: 's5', title: '水下二次金叉战法验证与保本价精算', time: '昨天 14:02', tab: 'projected-action' },
  { id: 's6', title: '中芯国际日K突破与主力控盘分析', time: '09-04 15:30', tab: 'watchlist' },
  { id: 's7', title: '高股息红利板块防御对冲方案', time: '09-04 10:18', tab: 'dashboard' },
  { id: 's8', title: '海光信息均线多头回踩买入策略', time: '09-03 16:50', tab: 'watchlist' },
  { id: 's9', title: '实战三原则止损线执行动作单生成', time: '09-03 13:12', tab: 'projected-action' },
  { id: 's10', title: '宏观降准预期与金融板块异动追踪', time: '09-02 11:05', tab: 'market' },
  // Extra sessions loaded on bottom scroll
  { id: 's11', title: '新能源车出海产业链中报业绩复盘', time: '09-01 14:30', tab: 'watchlist' },
  { id: 's12', title: '低空经济概念超跌反弹动量测试', time: '08-31 16:20', tab: 'market' },
  { id: 's13', title: '银行股破净修复与股息率截面排序', time: '08-30 10:15', tab: 'dashboard' },
  { id: 's14', title: '券商合并传闻与早盘集合竞价异动', time: '08-29 09:28', tab: 'market' },
  { id: 's15', title: '科创50ETF流动性与主力大单跟踪', time: '08-28 15:00', tab: 'dashboard' },
  { id: 's16', title: '中际旭创光模块订单与筹码换手', time: '08-27 11:10', tab: 'watchlist' },
  { id: 's17', title: '量化事件驱动：定增解禁压力测算', time: '08-26 14:40', tab: 'dashboard' },
  { id: 's18', title: '北向资金单日大幅净流入板块挖掘', time: '08-25 17:05', tab: 'market' },
  { id: 's19', title: '退哥龙头首阴战法买卖点回测', time: '08-24 13:50', tab: 'dashboard' },
  { id: 's20', title: '全市场换手率与波动率因子有效性', time: '08-23 16:30', tab: 'returns' }
];

// Initialize and render session list
function renderSessionList() {
  const container = document.getElementById('sessionList');
  if (!container) return;

  const currentCount = AppState.loadedSessionCount;
  const sessionsToRender = HistoricalSessions.slice(0, currentCount);

  container.innerHTML = sessionsToRender.map((s, idx) => `
    <div class="session-item ${idx === 0 ? 'active' : ''}" data-id="${s.id}" onclick="selectSession('${s.id}')">
      <div class="session-item-header">
        <div class="session-item-title" title="${s.title}">${s.title}</div>
      </div>
      <div class="session-item-time">${s.time}</div>
    </div>
  `).join('');

  // Update load more indicator
  const loadMoreElem = document.getElementById('sessionLoadMore');
  if (loadMoreElem) {
    if (currentCount >= HistoricalSessions.length) {
      loadMoreElem.innerHTML = '<span style="color:#B4BCC8;">已加载全部历史会话 (20条)</span>';
    } else {
      loadMoreElem.innerHTML = '<span class="spinner-dot"></span><span>下拉自动加载更早记录...</span>';
    }
  }
}

// Infinite scroll listener for session history
function setupSessionInfiniteScroll() {
  const container = document.getElementById('sessionList');
  if (!container) return;

  let isFetching = false;
  container.addEventListener('scroll', () => {
    if (isFetching) return;
    if (AppState.loadedSessionCount >= HistoricalSessions.length) return;

    // Trigger when user scrolls near the bottom (within 15px)
    if (container.scrollTop + container.clientHeight >= container.scrollHeight - 15) {
      isFetching = true;
      const loadMoreElem = document.getElementById('sessionLoadMore');
      if (loadMoreElem) {
        loadMoreElem.innerHTML = '<span class="spinner-dot"></span><span style="color:#1677FF;">正在从存储中拉取更早的会话...</span>';
      }

      setTimeout(() => {
        AppState.loadedSessionCount = Math.min(HistoricalSessions.length, AppState.loadedSessionCount + 10);
        renderSessionList();
        isFetching = false;
        showToast(`已成功自动加载历史会话（当前展示最近 ${AppState.loadedSessionCount} 条）`);
      }, 500);
    }
  });
}

// Select a session
function selectSession(id) {
  document.querySelectorAll('.session-item').forEach(item => {
    if (item.dataset.id === id) item.classList.add('active');
    else item.classList.remove('active');
  });

  const session = HistoricalSessions.find(s => s.id === id);
  if (session) {
    showToast(`已载入会话：${session.title}`);
    // Switch linked right tab if appropriate
    if (session.tab) {
      switchRightTab(session.tab);
    }
  }
}

// Generate standard Welcome & Quick Actions card HTML
function getWelcomeMessageHtml() {
  return `
    <div class="message-item message-ai">
      <div class="message-bubble-ai welcome-intro-card">
        <div class="welcome-header">
          <div class="welcome-avatar-pill">AI</div>
          <div class="welcome-title-box">
            <h3>您好！我是您的 A股智能投研助手</h3>
            <p>高内聚自包含量化投研中枢 · 多智能体协同对抗研判 · 毫秒级盘面联动</p>
          </div>
        </div>

        <div class="welcome-feature-desc">
          基于全市场 4 级降级实时行情与工业级量化引擎，为您提供<strong>行情全景监测</strong>、<strong>多因子选股诊断</strong>、严格执行<strong>最低保本卖出价精算</strong>与 <strong>T0(-3%)/T1(-5%)/T2(-8%) 三级风控止损</strong>，并支持投资收益多维归因及全天候智能盯盘。
        </div>

        <div class="quick-iron-card">
          <div class="quick-iron-header">⚡ 快捷操作推荐（点击直接发起智能体分析）：</div>
          <div class="quick-iron-grid">
            <div class="quick-pill-box" onclick="executeQuickAction('评估持股策略')" title="诊断持仓健康度，精算保本卖出价与三级止损阶梯动作单">
              <div class="quick-pill-title">🛡️ 评估持股策略</div>
              <div class="quick-pill-val">立即评估 &gt;</div>
            </div>
            <div class="quick-pill-box" onclick="executeQuickAction('分析今日大盘行情')" title="四大指数走势研判、两市放量动能、情绪温度与主线轮动">
              <div class="quick-pill-title">📈 分析今日大盘行情</div>
              <div class="quick-pill-val">一键分析 &gt;</div>
            </div>
            <div class="quick-pill-box" onclick="executeQuickAction('收益分析')" title="复盘资产净值走势、夏普比率、最大回撤与多因子收益归因">
              <div class="quick-pill-title">💰 收益分析</div>
              <div class="quick-pill-val">查看分析 &gt;</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

// Start a new chat session
function startNewChat() {
  const newSession = {
    id: 's_' + Date.now(),
    title: '新建投研对话 ' + new Date().toLocaleTimeString().slice(0, 5),
    time: '刚刚',
    tab: 'dashboard'
  };
  HistoricalSessions.unshift(newSession);
  AppState.loadedSessionCount++;
  renderSessionList();

  const chatMessages = document.getElementById('chatMessages');
  if (chatMessages) {
    chatMessages.innerHTML = getWelcomeMessageHtml();
  }
  
  // 确保处于投研助手模式及默认板块
  if (AppState.activeRightTab !== 'dashboard') {
    switchRightTab('dashboard');
  } else {
    switchLayoutMode('chat-center');
  }

  showToast('已创建新投研会话！欢迎查阅功能介绍与快捷操作');
}

// 快捷操作响应调度器（评估持股策略、分析今日大盘行情、收益分析）
function executeQuickAction(actionType) {
  if (AppState.isChatStreaming) {
    showToast('AI 智能体正在研判中，请稍候...');
    return;
  }

  // 确保工作台处于展示状态且为投研助手居中模式
  if (AppState.activeRightTab === 'dashboard') {
    switchLayoutMode('chat-center');
  }

  if (actionType === '评估持股策略') {
    const prompt = '请评估我的持股策略，对当前持仓标的进行量化健康度诊断，并根据实战三原则计算最低保本卖出价与三级风控止损阶梯。';
    appendChatMessage('user', prompt);
    const tpl = PromptTemplates['评估持股策略'] || PromptTemplates['行情分析'];
    streamAIResponse(tpl, '持股策略与实战三原则量化诊断报告', '持仓综合评分88分，精算税费保本卖出价与三级止损阶梯');
    const sec = document.getElementById('section-portfolio-overview');
    if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast('已发起【评估持股策略】量化诊断！');
  } else if (actionType === '分析今日大盘行情') {
    const prompt = '请深度分析今日A股大盘行情走势、两市成交量能、四大指数强弱分化与核心板块轮动主线。';
    appendChatMessage('user', prompt);
    if (typeof UIEngine !== 'undefined') {
      executeA2UITask('分析今日大盘行情');
    } else {
      const tpl = PromptTemplates['行情分析'];
      streamAIResponse(tpl, '今日A股大盘行情与主线轮动深度研判', '两市放量成交破1.28万亿，科技成长主线共振领涨，短期延续反弹');
    }
    const sec = document.getElementById('section-market-indices');
    if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast('已发起【分析今日大盘行情】深度研判！');
  } else if (actionType === '收益分析') {
    const prompt = '请对当前投资组合进行全景收益分析，评估资产净值曲线、夏普比率、最大回撤以及多因子收益归因。';
    appendChatMessage('user', prompt);
    const tpl = PromptTemplates['收益分析'] || PromptTemplates['行情分析'];
    streamAIResponse(tpl, '投资组合全景收益与多因子归因报告', '累计总收益 +36.78%，夏普比率 1.84，个股Alpha与行业配置贡献核心超额');
    const sec = document.getElementById('section-investment-analysis');
    if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast('已发起【收益分析】多维量化研判！');
  }
}

// --------------------------------------------------------------------------
// 2. Left Menu Bar Navigation
// --------------------------------------------------------------------------
function handleMenuClick(tabId) {
  // Update Left Sidebar Active Nav
  document.querySelectorAll('.sidebar-nav-section .nav-item').forEach(item => {
    if (item.dataset.tab === tabId) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // 1. 当选择【投研助手】时：【AIChatUI】在中间
  // 2. 当点击其他功能（市场行情、自选个股、收益分析...）：【AIChatUI】定位为AI助手，布局变到右侧，中间区域为主工作区
  if (tabId === 'dashboard') {
    switchLayoutMode('chat-center');
  } else {
    switchLayoutMode('workspace-main');
  }

  // Switch right/middle business pane
  switchRightTab(tabId);
}

// Switch between Chat-Centric mode and Workspace-Centric Copilot mode
function switchLayoutMode(mode) {
  const container = document.getElementById('appContainer') || document.querySelector('.app-container');
  const chatTitle = document.getElementById('chatHeaderTitle');
  const chatStatus = document.getElementById('chatHeaderStatus');
  const collapseIcon = document.getElementById('collapseIcon');
  const collapseText = document.getElementById('collapseText');
  const btnCollapse = document.getElementById('btnCollapseChat');

  if (!container) return;
  AppState.layoutMode = mode;

  if (mode === 'chat-center') {
    container.classList.remove('layout-workspace-main');
    container.classList.add('layout-chat-center');

    // 铁律：投研助手模式下 AIChatUI 始终展示，杜绝收起自身
    container.classList.remove('chat-collapsed');
    const chatCol = document.getElementById('appMiddleChat');
    if (chatCol) chatCol.classList.remove('collapsed');

    if (chatTitle) chatTitle.innerText = '投研助手';
    if (chatStatus) {
      chatStatus.innerText = '● 在线';
      chatStatus.style.color = '#52C41A';
    }
  } else {
    container.classList.remove('layout-chat-center');
    container.classList.add('layout-workspace-main');

    if (chatTitle) chatTitle.innerText = 'AI助手';
    if (chatStatus) {
      chatStatus.innerText = '● 协同中';
      chatStatus.style.color = '#1677FF';
    }
    if (collapseIcon) collapseIcon.innerText = '▶';
    if (collapseText) collapseText.innerText = '收起';
    if (btnCollapse) btnCollapse.title = '收起AI助手';
  }

  // Trigger resize event for canvas charts
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 320);
}

// --------------------------------------------------------------------------
// 3. Right Workbench & Multi-Tab Management
// --------------------------------------------------------------------------
const ViewDescriptions = {
  'dashboard': '整体投研盘面 (大盘/自选/持仓监控/策略开关)',
  'market': '市场行情全景 (四大指数/情绪仪表盘/日K线/板块流向)',
  'watchlist': '自选个股深度研判 (宁德时代多周期K线/主力控盘)',
  'returns': '投资收益全景分析 (资产净值曲线/胜率/盈亏归因)',
  'projected-action': '实战交易三原则指令单 (保本价试算器/三级止损)'
};

const ViewHeaderInfo = {
  'dashboard': { title: '工作台', icon: '📊' },
  'market': { title: '市场行情全景', icon: '📈' },
  'watchlist': { title: '自选个股深度研判', icon: '⭐' },
  'returns': { title: '投资收益全景分析', icon: '💰' },
  'projected-action': { title: '工作台 · 实战动作单', icon: '🛡️' }
};

function switchRightTab(tabId) {
  AppState.activeRightTab = tabId;

  // 1. 同步布局模式：投研盘面居中，其他功能主工作区居中+AI助手在右
  if (tabId === 'dashboard') {
    switchLayoutMode('chat-center');
  } else {
    switchLayoutMode('workspace-main');
  }

  // 2. Update Left Menu Active state if matching
  document.querySelectorAll('.sidebar-nav-section .nav-item').forEach(item => {
    if (item.dataset.tab === tabId) item.classList.add('active');
    else item.classList.remove('active');
  });

  // 3. Update Panes
  document.querySelectorAll('.right-pane').forEach(pane => {
    pane.classList.remove('active');
  });
  const targetPane = document.getElementById(`pane-${tabId}`);
  if (targetPane) {
    targetPane.classList.add('active');
  }

  // 4. Update Header Title and Icon
  const info = ViewHeaderInfo[tabId] || { title: `工作台 [${tabId}]`, icon: '📊' };
  const headerTitleElem = document.getElementById('workbenchHeaderTitle');
  if (headerTitleElem) headerTitleElem.innerText = info.title;
  const headerIconElem = document.getElementById('workbenchIconBadge');
  if (headerIconElem) headerIconElem.innerText = info.icon;

  const linkedContextElem = document.getElementById('linkedContextText');
  if (linkedContextElem) linkedContextElem.innerText = info.title;

  // 5. Re-render Canvas Charts for this tab
  setTimeout(() => {
    renderTabCharts(tabId);
  }, 40);
}

// Dynamically open a new tab on the right
function openRightTab(tabId, title, icon = '📑', isClosable = true) {
  ViewHeaderInfo[tabId] = { title: title, icon: icon };
  const headerTitleElem = document.getElementById('workbenchHeaderTitle');
  if (headerTitleElem) headerTitleElem.innerText = title;
  const headerIconElem = document.getElementById('workbenchIconBadge');
  if (headerIconElem) headerIconElem.innerText = icon;

  switchRightTab(tabId);
}

// Close a tab and fallback safely to dashboard
function closeRightTab(tabId, event) {
  if (event) event.stopPropagation();

  if (AppState.activeRightTab === tabId) {
    switchRightTab('dashboard');
    showToast('已关闭投射视窗，平滑返回【工作台】');
  }
}

// --------------------------------------------------------------------------
// 4. 【重要交互 1】：AIChat 针对右侧信息提问与修改
// --------------------------------------------------------------------------
function askAboutRightContent() {
  // 若当前处于业务主工作区且右侧 AI 助手已收起，自动展开呼出
  if (AppState.layoutMode === 'workspace-main' && AppState.isCopilotCollapsed) {
    toggleCopilot(false);
  }

  const tab = AppState.activeRightTab;
  const input = document.getElementById('chatInput');
  if (!input) return;

  let prompt = '';
  if (tab === 'dashboard') {
    prompt = '请结合整体投研盘面数据（两市放量1.28万亿，科技领涨），分析明天的核心主线与防守标的。';
  } else if (tab === 'market') {
    prompt = '请结合市场行情全景看板与北向资金流向，深度研判大盘短期突破 3,450 点的动能与风险。';
  } else if (tab === 'watchlist') {
    prompt = '请针对自选标的【宁德时代 300750】的主力控盘仪表盘与资金流向，制定下周一的买入与防守策略。';
  } else if (tab === 'returns') {
    prompt = '请评估投资收益全景看板中的最大回撤(-8.24%)与夏普比率(1.84)，并给出仓位与多因子优化建议。';
  } else if (tab === 'projected-action') {
    const cost = AppState.riskParams.cost;
    prompt = `请针对实战动作单中的买入成本 ¥${cost}、最低保本卖出价与三级止损阶梯给出盘中突发跳水的执行动作细节。`;
  } else {
    prompt = `请根据当前展示的【${tab}】数据，出具深度的量化投研报告。`;
  }

  input.value = prompt;
  input.focus();

  // Highlight effect
  const inputBar = document.querySelector('.chat-input-bar');
  if (inputBar) {
    inputBar.style.boxShadow = '0 0 0 3px rgba(22, 119, 255, 0.25)';
    setTimeout(() => { inputBar.style.boxShadow = ''; }, 1200);
  }

  showToast(`已提取数据并载入 AI 助手输入框，直接回车即可发送！`);
}

// Injects prompt for specific stock row
function askStockPrompt(name, code, price) {
  // 若当前处于业务主工作区且右侧 AI 助手已收起，自动展开呼出
  if (AppState.layoutMode === 'workspace-main' && AppState.isCopilotCollapsed) {
    toggleCopilot(false);
  }

  const input = document.getElementById('chatInput');
  if (!input) return;

  input.value = `请针对标的【${name} (${code})】（现价 ¥${price}）进行量化深度诊断，并计算最低保本卖出价与三场景反应动作单。`;
  input.focus();
  showToast(`已引用【${name}】数据至提问框！按回车即可执行诊断`);
}

// Unlink context
function unlinkRightContent() {
  const linkedContextElem = document.getElementById('linkedContextText');
  if (linkedContextElem) linkedContextElem.innerText = '未关联 (自由对话模式)';
  showToast('已解除右侧上下文强绑定');
}

// Open / Close Modify Parameter Modal
function openModifyRightParam() {
  const modal = document.getElementById('modifyParamModal');
  if (!modal) return;

  document.getElementById('modCost').value = AppState.riskParams.cost;
  document.getElementById('modShares').value = AppState.riskParams.shares;
  document.getElementById('modT1').value = AppState.riskParams.t1;
  document.getElementById('modT2').value = AppState.riskParams.t2;

  modal.classList.add('active');
}

function closeModifyParamModal() {
  const modal = document.getElementById('modifyParamModal');
  if (modal) modal.classList.remove('active');
}

// Apply form modifications to right panel
function applyRightParamForm() {
  const cost = parseFloat(document.getElementById('modCost').value) || 320.0;
  const shares = parseInt(document.getElementById('modShares').value) || 1000;
  const t1 = parseFloat(document.getElementById('modT1').value) || -5.0;
  const t2 = parseFloat(document.getElementById('modT2').value) || -8.0;

  AppState.riskParams.cost = cost;
  AppState.riskParams.shares = shares;
  AppState.riskParams.t1 = t1;
  AppState.riskParams.t2 = t2;

  // Sync with projected sliders
  const sliderCost = document.getElementById('sliderCost');
  if (sliderCost) sliderCost.value = cost;
  const sliderShares = document.getElementById('sliderShares');
  if (sliderShares) sliderShares.value = shares;

  updateProjectedCalculator();
  closeModifyParamModal();
  showToast('已成功更新右侧风控参数！保本价与三级止损线已完成精确重算');
}

// --------------------------------------------------------------------------
// 5. 【重要交互 2】：AIChat 卡片/连接放大投射到右侧（保留当前右侧内容）
// --------------------------------------------------------------------------
function projectToRight(cardType, payload = {}) {
  let tabId = 'projected-action';
  let title = '🛡️ 实战动作单·宁德时代';

  if (cardType === 'action') {
    tabId = 'projected-action';
    title = `🛡️ 实战动作单·${payload.name || '宁德时代'}`;
    if (payload.cost) AppState.riskParams.cost = payload.cost;
    if (payload.shares) AppState.riskParams.shares = payload.shares;
  } else if (cardType === 'report') {
    tabId = 'projected-action';
    title = `📑 行情研报·深度版`;
  }

  // 若处于投研助手模式且工作台已收起，自动展开工作台以展示投射内容
  if (AppState.layoutMode === 'chat-center' && AppState.isWorkbenchCollapsed) {
    toggleWorkbenchCollapse(false);
  }

  // Open the tab preserving previous tabs
  openRightTab(tabId, title, '⛶', true);

  // Update calculator values in the projected pane
  updateProjectedCalculator();

  // Trigger from-left-to-right pop-in animation (从左到右弹出展示)
  const pane = document.getElementById('pane-projected');
  if (pane) {
    pane.classList.remove('popup-slide-from-left');
    void pane.offsetWidth; // force DOM reflow
    pane.classList.add('popup-slide-from-left');
  }

  showToast(`已将【${title}】放大投射至右侧窗口（从左至右动画弹出，原有内容完整保留）`);
}

// Master Collapse Button Handler in Chat Header
function handleChatCollapseBtn() {
  if (AppState.layoutMode === 'workspace-main') {
    // Mode 2: 收起右侧 AI 助手
    toggleCopilot();
  }
  // Mode 1: 铁律 — AIChatUI 在投研助手模式下始终展示，不执行收起自身
}

// Toggle Workbench collapse / expand (Mode 1: 投研助手模式下工作台的收起 / 展开)
function toggleWorkbenchCollapse(forceState) {
  const container = document.getElementById('appContainer') || document.querySelector('.app-container');
  if (!container) return;

  const willCollapse = typeof forceState === 'boolean'
    ? forceState
    : !container.classList.contains('workbench-collapsed');

  if (willCollapse) {
    container.classList.add('workbench-collapsed');
    AppState.isWorkbenchCollapsed = true;
    showToast('已收起工作台，投研助手全屏沉浸展现');
  } else {
    container.classList.remove('workbench-collapsed');
    AppState.isWorkbenchCollapsed = false;
    showToast('已展开工作台 (占比 60%)');
  }

  // Trigger resize event so Canvas charts smoothly re-render
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 320);
}

// Toggle AI Copilot on the right (Mode 2: 业务主工作区模式下的收起 / 展开)
function toggleCopilot(forceState) {
  const container = document.getElementById('appContainer') || document.querySelector('.app-container');
  if (!container) return;

  const willCollapse = typeof forceState === 'boolean'
    ? forceState
    : !container.classList.contains('copilot-collapsed');

  if (willCollapse) {
    container.classList.add('copilot-collapsed');
    AppState.isCopilotCollapsed = true;
    showToast('已收起 AI 助手，中间主工作区已全宽大屏展现');
  } else {
    container.classList.remove('copilot-collapsed');
    AppState.isCopilotCollapsed = false;
    showToast('已展开 AI 助手伴随协同视窗');
  }

  // Trigger resize event so Canvas charts smoothly re-render
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 320);
}

// Toggle ChatUI collapse / expand (兼容性方法，Mode 1 强制保持 AIChatUI 常驻)
function toggleChatCollapse() {
  if (AppState.layoutMode === 'chat-center') {
    // Mode 1 铁律：AIChatUI 始终展示
    return;
  }
  toggleCopilot();
}

// Interactive Dynamic Calculator inside Projected View (math.ceil rule)
function updateProjectedCalculator() {
  const sliderCost = document.getElementById('sliderCost');
  const sliderShares = document.getElementById('sliderShares');
  if (!sliderCost || !sliderShares) return;

  const cost = parseFloat(sliderCost.value);
  const shares = parseInt(sliderShares.value);

  document.getElementById('sliderCostVal').innerText = `¥${cost.toFixed(2)}`;
  document.getElementById('sliderSharesVal').innerText = `${shares.toLocaleString()} 股`;

  AppState.riskParams.cost = cost;
  AppState.riskParams.shares = shares;

  const buyAmount = cost * shares;
  const buyComm = Math.max(AppState.riskParams.minCommission, buyAmount * AppState.riskParams.commissionRate);
  const buyTransfer = buyAmount * AppState.riskParams.transferRate;

  const sellStamp = buyAmount * (AppState.riskParams.stampDuty / 100);
  const sellComm = Math.max(AppState.riskParams.minCommission, buyAmount * AppState.riskParams.commissionRate);
  const sellTransfer = buyAmount * AppState.riskParams.transferRate;

  const totalFee = buyComm + buyTransfer + sellStamp + sellComm + sellTransfer;
  
  // Mandatory math.ceil to the nearest cent (0.01)
  const breakeven = Math.ceil(((buyAmount + totalFee) / shares) * 100) / 100;

  const t0Price = Math.round(cost * (1 + AppState.riskParams.t0 / 100) * 100) / 100;
  const t1Price = Math.round(cost * (1 + AppState.riskParams.t1 / 100) * 100) / 100;
  const t2Price = Math.round(cost * (1 + AppState.riskParams.t2 / 100) * 100) / 100;

  document.getElementById('resBreakeven').innerText = `¥${breakeven.toFixed(2)}`;
  document.getElementById('resT0').innerText = `¥${t0Price.toFixed(2)}`;
  document.getElementById('resT1').innerText = `¥${t1Price.toFixed(2)}`;
  document.getElementById('resT2').innerText = `¥${t2Price.toFixed(2)}`;

  document.getElementById('feeAmount').innerText = `¥${buyAmount.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
  document.getElementById('feeBuyComm').innerText = `¥${buyComm.toFixed(2)}`;
  document.getElementById('feeStamp').innerText = `¥${sellStamp.toFixed(2)}`;
  document.getElementById('feeTransfer').innerText = `¥${(buyTransfer + sellTransfer).toFixed(2)}`;
  document.getElementById('feeTotal').innerText = `¥${totalFee.toFixed(2)}`;
}

function askAboutProjectedAction() {
  const cost = AppState.riskParams.cost;
  const shares = AppState.riskParams.shares;
  const breakeven = document.getElementById('resBreakeven').innerText;

  const input = document.getElementById('chatInput');
  if (!input) return;

  input.value = `针对右侧放大投射的实战动作单（买入成本 ${cost} 元，${shares} 股，最低保本卖出价 ${breakeven}），若盘中跳水跌破 T1 减仓线，请给出分批对冲与减仓的具体委单策略。`;
  input.focus();
  showToast('已带入动作单最新保本参数至提问框！按回车即可提问');
}

// --------------------------------------------------------------------------
// 6. Canvas Charts Rendering
// --------------------------------------------------------------------------
function renderTabCharts(tabId) {
  if (tabId === 'dashboard') {
    // 1. 投资概要: 资产配置环形图
    FinancialCharts.drawDonutChart('portfolioDonut', [
      { name: '股票持仓', value: 328.56, color: '#1677FF' },
      { name: '现金储备', value: 125.68, color: '#4096FF' }
    ], { centerTitle: '总市值', centerValue: '328.56万' });

    // 2-1. 大盘指数: 四大指数 Sparklines
    FinancialCharts.drawSparkline('sparklineSh', [3390, 3405, 3400, 3415, 3422, 3418, 3426.56], true);
    FinancialCharts.drawSparkline('sparklineSz', [10750, 10780, 10820, 10800, 10860, 10892.14], true);
    FinancialCharts.drawSparkline('sparklineCy', [2250, 2265, 2260, 2278, 2282, 2289.76], true);
    FinancialCharts.drawSparkline('sparklineKc', [980, 992, 988, 1005, 1012.35], true);

    // 2-2. 行情分析: 市场情绪仪表盘 (78分 亢温)
    FinancialCharts.drawGauge('dashboardSentimentGauge', 78, { colorType: 'sentiment' });

    // 3-1. 自选指数: 自选主题分时线
    FinancialCharts.drawSparkline('sparklineCustomIdx1', [1220, 1228, 1235, 1230, 1242, 1248.60], true);
    FinancialCharts.drawSparkline('sparklineCustomIdx2', [3010, 3045, 3080, 3065, 3105, 3120.45], true);

    // 3-2. 投资分析: 策略净值 vs 沪深300 基准对比微曲线
    FinancialCharts.drawEquityCurve('dashboardInvestCurve', 
      [1.00, 1.05, 1.08, 1.15, 1.25, 1.34], 
      [1.00, 1.01, 1.03, 1.05, 1.07, 1.09], 
      ['3月', '5月', '7月', '9月']
    );
  } 
  else if (tabId === 'market') {
    FinancialCharts.drawSparkline('marketSparkSh', [3395, 3408, 3402, 3418, 3426.56], true);
    FinancialCharts.drawSparkline('marketSparkSz', [10760, 10795, 10830, 10892.14], true);
    FinancialCharts.drawSparkline('marketSparkCy', [2260, 2272, 2265, 2280, 2289.76], true);
    FinancialCharts.drawSparkline('marketSparkKc', [980, 992, 988, 1005, 1012.35], true);

    FinancialCharts.drawSentimentGauge('marketSentimentGauge', 78);

    const klines = generateKlines(3400, 28, 0.006);
    FinancialCharts.drawCandlestickChart('marketMainCandle', klines, { showVolume: true });
  }
  else if (tabId === 'watchlist') {
    const klines = generateKlines(315, 28, 0.009);
    FinancialCharts.drawCandlestickChart('stockDetailCandle', klines, { showVolume: true });

    FinancialCharts.drawDonutChart('capitalFlowDonut', [
      { name: '超大单', value: 45, color: '#F5222D' },
      { name: '大单', value: 25, color: '#FF7875' },
      { name: '中单', value: 18, color: '#52C41A' },
      { name: '小单', value: 12, color: '#86909C' }
    ], { centerTitle: '主力流入', centerValue: '+12.36亿' });

    FinancialCharts.drawTrendLine('flowTrendLine', [2.5, 4.8, -1.2, 8.6, 12.36], ['08-21', '08-22', '08-25', '08-26', '08-27']);
    FinancialCharts.drawSentimentGauge('mainForceGauge', 85);
  }
  else if (tabId === 'returns') {
    // Strategy equity curve vs Benchmark 沪深300
    const strategyEquity = [1.00, 1.02, 1.01, 1.05, 1.08, 1.06, 1.12, 1.15, 1.18, 1.16, 1.22, 1.25, 1.28, 1.30, 1.34];
    const benchmarkEquity = [1.00, 1.01, 0.99, 1.02, 1.03, 1.01, 1.04, 1.05, 1.04, 1.02, 1.05, 1.06, 1.07, 1.08, 1.09];
    const labels = ['3月', '4月', '5月', '6月', '7月', '8月', '9月'];
    FinancialCharts.drawEquityCurve('equityCurveCanvas', strategyEquity, benchmarkEquity, labels);

    // Monthly PnL
    const monthlyPnL = [
      { month: '1月', pnl: 4.8 },
      { month: '2月', pnl: 6.2 },
      { month: '3月', pnl: -1.5 },
      { month: '4月', pnl: 5.4 },
      { month: '5月', pnl: 3.1 },
      { month: '6月', pnl: 7.8 },
      { month: '7月', pnl: -2.1 },
      { month: '8月', pnl: 8.6 }
    ];
    FinancialCharts.drawMonthlyPnLChart('monthlyPnLCanvas', monthlyPnL);
  }
}

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

// --------------------------------------------------------------------------
// 7. Chat Engine & Typewriter Streaming
// --------------------------------------------------------------------------
const PromptTemplates = {
  '评估持股策略': {
    title: '持股策略与实战三原则量化诊断报告',
    summary: '持仓组合综合健康度 88分，精算税费保本卖出价与三级止损阶梯',
    body: `
      <div class="ai-report-section">
        <div class="ai-report-section-title">1. 持仓组合结构画像</div>
        <p>当前总资产规模 <strong>¥454.24万</strong>，持仓总市值 <strong>¥328.56万</strong>（仓位占比 72.3%），可用现金 <strong>¥125.68万</strong>（占比 27.7%）。持仓聚焦科技成长与新能源双主线：<strong>宁德时代(35%)、中芯国际(25%)、海光信息(20%)</strong>，仓位适度偏多，流动性充裕。</p>
      </div>
      <div class="ai-report-section">
        <div class="ai-report-section-title">2. 持仓标的健康度诊断</div>
        <ul>
          <li><strong>宁德时代 (300750)</strong>：量化评分 92分。完成 60分钟水下二次金叉验底，主力超大单密集流入，处于安全边际支撑位上方。</li>
          <li><strong>中芯国际 (688981)</strong>：量化评分 94分。放量突破前期颈线高位平台，量价共振显著，多头排列稳固。</li>
          <li><strong>海光信息 (688041)</strong>：量化评分 89分。回踩 MA20 均线确认支撑，筹码集中度持续提升至 82%。</li>
        </ul>
      </div>
      <div class="summary-highlight-card">
        <span class="summary-icon">🛡️</span>
        <div class="summary-text"><strong>策略诊断结论</strong>：持仓组合整体健康度优秀，处于安全垫区间（平均缓冲距离 +11.8%），建议保持底仓，待盘中拉升逐步止盈。</div>
      </div>
      <div class="risk-iron-card">
        <div class="risk-iron-header">
          <span class="risk-iron-title">🛡️ 实战交易三原则（合规风控指令单）</span>
          <button class="risk-iron-action-btn" title="投射到右侧工作台" onclick="projectToRight('action', {code:'300750', name:'宁德时代', cost:320, shares:1000})">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
            </svg>
          </button>
        </div>
        <div class="risk-iron-grid">
          <div class="risk-pill-box">
            <div class="risk-pill-title">最低保本卖出价</div>
            <div class="risk-pill-val">¥320.69</div>
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
  '收益分析': {
    title: '投资组合全景收益与多因子归因报告',
    summary: '累计总收益 +36.78%，夏普比率 1.84，个股Alpha与行业配置贡献核心超额',
    body: `
      <div class="ai-report-section">
        <div class="ai-report-section-title">1. 净值走势与超额收益</div>
        <p>自建仓以来组合累计实现净值 <strong>1.368</strong>，总收益率 <strong class="text-up">+36.78%</strong>，年化收益率 <strong class="text-up">+18.24%</strong>，较沪深300基准累计超额收益达 <strong>+25.4%</strong>。</p>
      </div>
      <div class="ai-report-section">
        <div class="ai-report-section-title">2. 风险与胜率核心量化指标</div>
        <ul>
          <li><strong>夏普比率 (Sharpe Ratio)</strong>：<strong>1.84</strong>（优于全市场 88% 的量化公募基准）。</li>
          <li><strong>交易胜率 (Win Rate)</strong>：<strong>68.5%</strong>，平均盈亏比 <strong>2.41</strong>。</li>
          <li><strong>最大回撤 (Max Drawdown)</strong>：<strong>-8.24%</strong>（发生在前期震荡验底期，现已完全修复创新高）。</li>
          <li><strong>贝塔系数 (Beta)</strong>：<strong>0.82</strong>，防御性与回撤控制表现良好。</li>
        </ul>
      </div>
      <div class="ai-report-section">
        <div class="ai-report-section-title">3. Brinson 多因子收益归因</div>
        <ul>
          <li><strong>行业配置效应</strong>：贡献 <strong>+14.2%</strong>，核心超额来自超配半导体与人工智能算力链。</li>
          <li><strong>个股选股 Alpha</strong>：贡献 <strong>+18.6%</strong>，核心重仓标的涨幅跑赢所属申万一级行业。</li>
          <li><strong>择时与对冲收益</strong>：贡献 <strong>+3.98%</strong>，早盘分级止盈与水下二次金叉验底加仓成效显著。</li>
        </ul>
      </div>
      <div class="summary-highlight-card">
        <span class="summary-icon">💰</span>
        <div class="summary-text"><strong>收益优化建议</strong>：多因子驱动健康，建议对涨幅超过30%的重仓个股适度兑现浮盈至现金储备，维持总仓位在 65%~75% 动态中性区间。</div>
      </div>
    `
  },
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
      <div class="summary-highlight-card">
        <span class="summary-icon">📈</span>
        <div class="summary-text"><strong>一句总结线</strong>：市场短期延续震荡向上趋势，科技成长仍是核心主线，建议逢低布局，合理控制仓位。</div>
      </div>
      <div class="risk-iron-card">
        <div class="risk-iron-header">
          <span class="risk-iron-title">🛡️ 实战交易三原则（合规风控指令单）</span>
          <button class="risk-iron-action-btn" title="投射到右侧工作台" onclick="projectToRight('action', {code:'300750', name:'宁德时代', cost:320, shares:1000})">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
            </svg>
          </button>
        </div>
        <div class="risk-iron-grid">
          <div class="risk-pill-box">
            <div class="risk-pill-title">最低保本卖出价</div>
            <div class="risk-pill-val">¥320.69</div>
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
        <div class="summary-text"><strong>量化提示</strong>：技术指标反弹动能充沛，需严格遵守分级风控止损原则，防范虚假突破。</div>
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

function appendChatMessage(role, content, meta = {}) {
  const container = document.getElementById('chatMessages');
  if (!container) return;

  const item = document.createElement('div');
  item.className = `message-item message-${role}`;
  const nowStr = new Date().toLocaleTimeString().slice(0, 5);

  if (role === 'user') {
    item.innerHTML = `
      <div class="message-bubble-user">
        ${content}
        <div class="message-timestamp">${nowStr}</div>
      </div>
    `;
    container.appendChild(item);
  } else {
    const msgId = meta.msgId || 'msg_' + Date.now();
    const title = meta.title || '量化投研综合研报';
    const summary = meta.summary || '模型结合盘面数据与风控铁律输出';

    item.innerHTML = `
      <div class="message-bubble-ai" id="${msgId}">
        <div class="ai-msg-header">
          <div class="ai-avatar-pill">AI</div>
          <div class="ai-msg-header-text">
            <h3 class="ai-msg-title">${title}</h3>
            <p class="ai-msg-summary">${summary}</p>
          </div>
        </div>
        ${meta.toolRunning ? `
          <div class="tool-status-bubble" id="toolStatus">
            <span class="tool-badge-running"></span>
            <span>正在调用智能量化引擎 [astock-action-execution / astock-data-feed]...</span>
          </div>
        ` : ''}
        <div class="ai-content-body">${content}</div>
        <div class="message-actions">
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

function streamAIResponse(contentOrTpl, titleParam, summaryParam) {
  let fullText = contentOrTpl;
  let title = titleParam || '当前A股市场行情分析';
  let summary = summaryParam || '两市成交放量破1.28万亿，科技成长主线共振领涨，短期延续震荡向上反弹格局';

  if (contentOrTpl && typeof contentOrTpl === 'object') {
    fullText = contentOrTpl.body || '';
    if (contentOrTpl.title) title = contentOrTpl.title;
    if (contentOrTpl.summary) summary = contentOrTpl.summary;
  }

  AppState.isChatStreaming = true;
  const msgId = 'aiMsg_' + Date.now();

  appendChatMessage('ai', '<span style="color:#86909C;">AI正在综合大盘、资金流、筹码与技术指标进行深度研判...</span>', {
    msgId: msgId,
    title: title,
    summary: summary,
    toolRunning: true
  });

  setTimeout(() => {
    const container = document.getElementById(msgId);
    if (!container) return;

    const toolStatus = container.querySelector('#toolStatus');
    if (toolStatus) {
      toolStatus.innerHTML = `
        <span style="color:#52C41A; font-weight:700;">✓</span>
        <span>已完成数据调取与实战三原则保本价精算（含全部税费保本测算）</span>
      `;
    }

    const contentBody = container.querySelector('.ai-content-body');
    contentBody.innerHTML = '';

    let idx = 0;
    const speed = 12;
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
  }, 500);
}

// --------------------------------------------------------------------------
// 7.1 Agent2UI (A2UI) Task Pipeline Execution
// --------------------------------------------------------------------------
function executeA2UITask(promptText = '分析市场行情') {
  AppState.isChatStreaming = true;
  const taskId = 'a2ui_' + Date.now();

  const isStock = promptText.includes('宁德') || promptText.includes('中芯') || promptText.includes('海光');
  const stockName = isStock ? '宁德时代 (300750)' : 'A股市场大盘全景';
  const title = `${stockName} 深度量化研报`;

  // Stage 0: 骨架屏预占位 (约50ms, 零CLS)
  const layoutMeta = {
    title: title,
    icon: isStock ? '⚡' : '📊',
    workbench_tab: {
      tab_id: 'tab_' + taskId,
      tab_title: isStock ? '🛡️ 宁德时代研报' : '📊 市场行情全景',
      closable: true
    }
  };

  const skeletonTree = [
    { slot_id: 'radar', component: 'MarketRadar', height: 52 },
    { slot_id: 'candle', component: 'CandleMatrix', height: 260 },
    { slot_id: 'risk', component: 'RiskBreakevenCalc', height: 110 }
  ];

  UIEngine.mountSkeleton(taskId, 'both_linked', layoutMeta, skeletonTree);

  // Stage 1: 快数据水合 (180ms)
  setTimeout(() => {
    UIEngine.hydrateFast(taskId, 'radar', {
      indices: [
        { name: '上证指数', price: 3426.56, change_pct: 0.72 },
        { name: '深证成指', price: 10892.14, change_pct: 1.08 },
        { name: '创业板指', price: 2289.76, change_pct: 1.31 }
      ],
      sentiment: { score: 78, text: '78分 贪婪 / 亢温' },
      total_volume: '1.28万亿元'
    });
  }, 180);

  // Stage 2: 打字机流式输出文本 (350ms - 850ms)
  const reportNarrative = `【A2UI 渐进式研报】基于多因子量化模型与盘面数据深度研判：今日两市成交突破 1.28 万亿，科技成长主线共振领涨。均线呈多头排列，零轴下方二次金叉验底形态确认。实战交易严格执行保本价精算与三级止损阶梯防守。`;
  let idx = 0;
  setTimeout(() => {
    const timer = setInterval(() => {
      if (idx < reportNarrative.length) {
        UIEngine.streamTextDelta(taskId, reportNarrative.slice(idx, idx + 4));
        idx += 4;
      } else {
        clearInterval(timer);
      }
    }, 15);
  }, 350);

  // Stage 3: 重型图表水合 (1000ms)
  setTimeout(() => {
    UIEngine.hydrateHeavy(taskId, 'radar');
    UIEngine.hydrateHeavy(taskId, 'candle', {
      benchmark: isStock ? '宁德时代 (300750)' : '上证指数 (000001)'
    });
  }, 1000);

  // Stage 4: 实战动作单与保本算价器水合 (1250ms)
  setTimeout(() => {
    const cost = isStock ? 320.0 : 3400.0;
    const shares = 1000;
    UIEngine.hydrateFast(taskId, 'risk', { cost, shares });
    UIEngine.hydrateHeavy(taskId, 'risk', { cost, shares });

    UIEngine.hydrateActionSheet(taskId, [
      { type: 'project', label: '⛶ 放大投射到工作台', target_tab: 'tab_' + taskId },
      { type: 'prompt', label: '💬 追问主力资金流向', secondary: true, prompt: `请深度拆解【${stockName}】的主力超大单净流入与筹码集中度分布。` }
    ]);

    AppState.isChatStreaming = false;
  }, 1250);
}

function handleSendChat() {
  if (AppState.isChatStreaming) return;

  const input = document.getElementById('chatInput');
  const text = input ? input.value.trim() : '';
  if (!text) return;

  appendChatMessage('user', text);
  input.value = '';

  // Route to A2UI Engine if recognized
  if (typeof UIEngine !== 'undefined' && (
      text.includes('行情') || text.includes('大盘') || text.includes('分析') ||
      text.includes('市场') || text.includes('诊断') || text.includes('5A') ||
      text.includes('选股') || text.includes('宁德') || text.includes('指标')
  )) {
    executeA2UITask(text);
    return;
  }

  let tpl = PromptTemplates['行情分析'];
  if (text.includes('持股') || text.includes('持仓') || text.includes('保本')) {
    tpl = PromptTemplates['评估持股策略'];
  } else if (text.includes('收益') || text.includes('盈亏') || text.includes('净值') || text.includes('归因')) {
    tpl = PromptTemplates['收益分析'];
  } else if (text.includes('指标') || text.includes('技术') || text.includes('金叉')) {
    tpl = PromptTemplates['技术指标'];
  } else if (text.includes('选股') || text.includes('模型') || text.includes('因子')) {
    tpl = PromptTemplates['选股模型'];
  }

  streamAIResponse(tpl.body, tpl.title, tpl.summary);
}

function copyMessageText(btn) {
  const card = btn.closest('.message-bubble-ai');
  if (!card) return;
  const text = card.innerText.replace(/📋 复制|🔄 重新生成/g, '').trim();
  navigator.clipboard.writeText(text).then(() => {
    showToast('内容已复制到剪贴板！');
  }).catch(() => {
    showToast('已选中内容，可直接复制');
  });
}

function regenerateLastMessage() {
  showToast('正在重新调用 AI 模型与风控规则...');
  streamAIResponse(PromptTemplates['行情分析'], '重算行情研报');
}

// --------------------------------------------------------------------------
// 8. Modals Management (模型接入、模型分配、系统设置 & 风控参数)
// --------------------------------------------------------------------------

function openSettingsModal() {
  const modal = document.getElementById('settingsModal');
  if (modal) {
    modal.classList.add('active');
    initProvidersSettings();
  }
}

function closeSettingsModal() {
  const modal = document.getElementById('settingsModal');
  if (modal) modal.classList.remove('active');
}

function switchSettingsSec(secId) {
  document.querySelectorAll('.settings-tab').forEach(tab => {
    if (tab.dataset.sec === secId) tab.classList.add('active');
    else tab.classList.remove('active');
  });

  document.querySelectorAll('.settings-sec').forEach(sec => {
    sec.classList.remove('active');
  });
  const target = document.getElementById(`sec-${secId}`);
  if (target) target.classList.add('active');

  // If switched to model roles tab, refresh dropdown options from active providers
  if (secId === 'roles') {
    renderModelRolesDropdowns();
  }
}

// --------------------------------------------------------------------------
// 8.1 Providers & Model Roles Core Controller
// --------------------------------------------------------------------------

async function initProvidersSettings() {
  try {
    // 1. Fetch providers from backend
    const provResp = await fetch('/api/models/providers');
    if (provResp.ok) {
      const data = await provResp.json();
      AppState.providers = data.providers || [];
    } else {
      loadProvidersFromLocalStorage();
    }
  } catch (err) {
    loadProvidersFromLocalStorage();
  }

  try {
    // 2. Fetch roles from backend
    const rolesResp = await fetch('/api/models/roles');
    if (rolesResp.ok) {
      const data = await rolesResp.json();
      AppState.modelRoles = Object.assign({
        chat: { provider_id: '', model_id: '' },
        summary: { provider_id: '', model_id: '' },
        quant: { provider_id: '', model_id: '' },
        debate: { provider_id: '', model_id: '' },
        vision: { provider_id: '', model_id: '' }
      }, data.roles || {});
    } else {
      loadRolesFromLocalStorage();
    }
  } catch (err) {
    loadRolesFromLocalStorage();
  }

  // Set active provider (first one if available and none selected)
  if (AppState.providers.length > 0) {
    if (!AppState.activeProviderId || !AppState.providers.find(p => p.provider_id === AppState.activeProviderId)) {
      AppState.activeProviderId = AppState.providers[0].provider_id;
    }
  } else {
    AppState.activeProviderId = null;
  }

  renderProvidersList();
  renderActiveProviderDetail();
  renderModelRolesDropdowns();
}

function loadProvidersFromLocalStorage() {
  try {
    const raw = localStorage.getItem('astock_llm_providers');
    AppState.providers = raw ? JSON.parse(raw) : [];
  } catch (e) {
    AppState.providers = [];
  }
}

function loadRolesFromLocalStorage() {
  try {
    const raw = localStorage.getItem('astock_model_roles');
    AppState.modelRoles = raw ? JSON.parse(raw) : {
      chat: { provider_id: '', model_id: '' },
      summary: { provider_id: '', model_id: '' },
      quant: { provider_id: '', model_id: '' },
      debate: { provider_id: '', model_id: '' },
      vision: { provider_id: '', model_id: '' }
    };
  } catch (e) {
    // fallback
  }
}

function renderProvidersList(filterText = '') {
  const container = document.getElementById('providersListContainer');
  if (!container) return;

  const keyword = filterText.trim().toLowerCase();
  const list = AppState.providers.filter(p => {
    if (!keyword) return true;
    return (p.name && p.name.toLowerCase().includes(keyword)) ||
           (p.base_url && p.base_url.toLowerCase().includes(keyword));
  });

  if (list.length === 0) {
    container.innerHTML = `
      <div style="padding: 24px 10px; text-align: center; color: var(--text-muted); font-size: 11.5px;">
        ${keyword ? '未匹配到供应商' : '暂无供应商，点击下方添加'}
      </div>
    `;
    return;
  }

  container.innerHTML = list.map(p => {
    const isActive = p.provider_id === AppState.activeProviderId;
    const initial = (p.name || 'P').trim().charAt(0).toUpperCase();
    const isEnabled = !!p.enabled;
    return `
      <div class="provider-list-item ${isActive ? 'active' : ''}" onclick="selectProvider('${p.provider_id}')">
        <div class="provider-item-left">
          <div class="provider-avatar">${initial}</div>
          <span class="provider-item-name" title="${p.name}">${p.name}</span>
        </div>
        ${isEnabled ? '<span class="provider-badge-on">ON</span>' : ''}
      </div>
    `;
  }).join('');
}

function filterProvidersList(val) {
  renderProvidersList(val);
}

function selectProvider(id) {
  // Save any unsaved edits of current provider before switching
  syncCurrentProviderFormToState();
  AppState.activeProviderId = id;
  renderProvidersList(document.getElementById('providerSearchInput')?.value || '');
  renderActiveProviderDetail();
}

function addNewProvider() {
  syncCurrentProviderFormToState();
  const newId = 'prov_' + Date.now().toString(36);
  const newProv = {
    provider_id: newId,
    name: '新供应商 ' + (AppState.providers.length + 1),
    base_url: 'https://api.deepseek.com/v1',
    api_key: '',
    enabled: true,
    models: [
      { id: 'deepseek-chat', name: 'deepseek-chat', selected: true, capabilities: ['chat', 'tools'] },
      { id: 'deepseek-reasoner', name: 'deepseek-reasoner', selected: true, capabilities: ['chat', 'reasoning'] }
    ],
    custom_headers: {},
    timeout_seconds: 60
  };

  AppState.providers.push(newProv);
  AppState.activeProviderId = newId;

  renderProvidersList();
  renderActiveProviderDetail();
  renderModelRolesDropdowns();

  const nameInput = document.getElementById('currProviderName');
  if (nameInput) {
    nameInput.focus();
    nameInput.select();
  }
  showToast('已新增模型供应商，请完善 API 地址与密钥');
}

function deleteCurrentProvider() {
  if (!AppState.activeProviderId) return;
  const curr = AppState.providers.find(p => p.provider_id === AppState.activeProviderId);
  const name = curr ? curr.name : '此供应商';

  if (!confirm(`确定要删除模型供应商【${name}】吗？`)) return;

  const targetId = AppState.activeProviderId;
  AppState.providers = AppState.providers.filter(p => p.provider_id !== targetId);

  // Clear from backend
  fetch(`/api/models/providers/${targetId}`, { method: 'DELETE' }).catch(() => {});

  // Clear any roles assigned to this provider
  for (const roleKey in AppState.modelRoles) {
    if (AppState.modelRoles[roleKey]?.provider_id === targetId) {
      AppState.modelRoles[roleKey] = { provider_id: '', model_id: '' };
    }
  }

  AppState.activeProviderId = AppState.providers.length > 0 ? AppState.providers[0].provider_id : null;

  renderProvidersList();
  renderActiveProviderDetail();
  renderModelRolesDropdowns();
  showToast(`已删除供应商【${name}】`);
}

function syncCurrentProviderFormToState() {
  if (!AppState.activeProviderId) return;
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (!p) return;

  const nameInput = document.getElementById('currProviderName');
  if (nameInput) p.name = nameInput.value.trim() || p.name;

  const enabledInput = document.getElementById('currProviderEnabled');
  if (enabledInput) p.enabled = enabledInput.checked;

  const keyInput = document.getElementById('currProviderKey');
  if (keyInput) p.api_key = keyInput.value.trim();

  const urlInput = document.getElementById('currProviderUrl');
  if (urlInput) p.base_url = urlInput.value.trim();

  const timeoutInput = document.getElementById('currProviderTimeout');
  if (timeoutInput) p.timeout_seconds = parseInt(timeoutInput.value, 10) || 60;

  const headersInput = document.getElementById('currProviderHeaders');
  if (headersInput && headersInput.value.trim()) {
    try {
      p.custom_headers = JSON.parse(headersInput.value.trim());
    } catch (e) {
      // ignore invalid json
    }
  }
}

function renderActiveProviderDetail() {
  const emptyState = document.getElementById('providerEmptyState');
  const editForm = document.getElementById('providerEditForm');

  if (!AppState.activeProviderId || AppState.providers.length === 0) {
    if (emptyState) emptyState.style.display = 'block';
    if (editForm) editForm.style.display = 'none';
    return;
  }

  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (!p) {
    if (emptyState) emptyState.style.display = 'block';
    if (editForm) editForm.style.display = 'none';
    return;
  }

  if (emptyState) emptyState.style.display = 'none';
  if (editForm) editForm.style.display = 'flex';

  const nameInput = document.getElementById('currProviderName');
  if (nameInput) nameInput.value = p.name || '';

  const idBadge = document.getElementById('currProviderIdBadge');
  if (idBadge) idBadge.innerText = p.provider_id ? `(${p.provider_id})` : '';

  const enabledInput = document.getElementById('currProviderEnabled');
  if (enabledInput) enabledInput.checked = !!p.enabled;

  const keyInput = document.getElementById('currProviderKey');
  if (keyInput) keyInput.value = p.api_key || '';

  const urlInput = document.getElementById('currProviderUrl');
  if (urlInput) urlInput.value = p.base_url || '';

  updateUrlPreview(p.base_url || '');

  const timeoutInput = document.getElementById('currProviderTimeout');
  if (timeoutInput) timeoutInput.value = p.timeout_seconds || 60;

  const headersInput = document.getElementById('currProviderHeaders');
  if (headersInput) {
    headersInput.value = (p.custom_headers && Object.keys(p.custom_headers).length > 0)
      ? JSON.stringify(p.custom_headers, null, 2)
      : '';
  }

  renderCurrentProviderModels();
}

function updateUrlPreview(url) {
  const preview = document.getElementById('currUrlPreview');
  if (!preview) return;
  const clean = (url || '').trim().replace(/\/+$/, '');
  preview.innerText = clean ? `预览: ${clean}/chat/completions` : '预览: (请输入有效的 API 地址)';
}

function handleProviderNameChange(val) {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (p) {
    p.name = val.trim() || '未命名供应商';
    renderProvidersList(document.getElementById('providerSearchInput')?.value || '');
    renderModelRolesDropdowns();
  }
}

function toggleCurrentProviderEnabled(checked) {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (p) {
    p.enabled = checked;
    renderProvidersList(document.getElementById('providerSearchInput')?.value || '');
    renderModelRolesDropdowns();
    showToast(checked ? `已启用供应商【${p.name}】` : `已停用供应商【${p.name}】`);
  }
}

function handleProviderKeyChange(val) {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (p) p.api_key = val.trim();
}

function handleProviderUrlChange(val) {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (p) p.base_url = val.trim();
  updateUrlPreview(val);
}

function handleProviderTimeoutChange(val) {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (p) p.timeout_seconds = parseInt(val, 10) || 60;
}

function handleProviderHeadersChange(val) {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (!p) return;
  try {
    p.custom_headers = val.trim() ? JSON.parse(val.trim()) : {};
  } catch (e) {
    // wait for valid JSON
  }
}

function toggleKeyVisibility() {
  const keyInput = document.getElementById('currProviderKey');
  if (!keyInput) return;
  keyInput.type = keyInput.type === 'password' ? 'text' : 'password';
}

async function testCurrentProviderConn() {
  const btn = document.getElementById('btnTestConn');
  const urlInput = document.getElementById('currProviderUrl');
  const keyInput = document.getElementById('currProviderKey');

  const base_url = urlInput ? urlInput.value.trim() : '';
  const api_key = keyInput ? keyInput.value.trim() : '';

  if (!base_url) {
    showToast('请先输入 API 地址 (Base URL)');
    if (urlInput) urlInput.focus();
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerText = '检测中...';
  }

  try {
    const resp = await fetch('/api/models/test-connection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url, api_key, timeout_seconds: 8 })
    });
    const res = await resp.json();
    if (res.status === 'ok') {
      showToast(`✅ ${res.message || '连接测试成功！'}`);
    } else if (res.status === 'warning') {
      showToast(`⚠️ ${res.message || '服务已响应，但状态非 200'}`);
    } else {
      showToast(`❌ ${res.message || '连接失败，请检查网络或密钥'}`);
    }
  } catch (err) {
    showToast(`❌ 网络异常: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = '检测';
    }
  }
}

async function fetchCurrentProviderModels() {
  const btn = document.getElementById('btnFetchModels');
  const urlInput = document.getElementById('currProviderUrl');
  const keyInput = document.getElementById('currProviderKey');

  const base_url = urlInput ? urlInput.value.trim() : '';
  const api_key = keyInput ? keyInput.value.trim() : '';

  if (!base_url) {
    showToast('请先填写有效的 API 地址');
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> 获取中...';
  }

  try {
    const resp = await fetch('/api/models/fetch-remote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url, api_key, timeout_seconds: 15 })
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    const fetchedModels = data.models || [];

    if (fetchedModels.length === 0) {
      showToast('上游接口返回空模型列表，您可点击【＋ 手动添加】');
      return;
    }

    const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
    if (p) {
      // Merge with existing selections if any
      const existingMap = {};
      (p.models || []).forEach(m => { existingMap[m.id] = m.selected; });

      p.models = fetchedModels.map(m => ({
        id: m.id,
        name: m.name || m.id,
        selected: existingMap[m.id] !== undefined ? existingMap[m.id] : true,
        capabilities: m.capabilities || ['chat']
      }));

      renderCurrentProviderModels();
      renderModelRolesDropdowns();
      showToast(`🎉 成功获取 ${p.models.length} 个可用模型！已自动保留复选`);
    }
  } catch (err) {
    showToast(`❌ 获取模型失败: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span class="btn-icon">🔄</span> 获取模型列表';
    }
  }
}

function promptAddCustomModel() {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (!p) return;

  const modelId = prompt('请输入要添加的模型 ID (如 deepseek-chat、gpt-4o、qwen2.5:7b):');
  if (!modelId || !modelId.trim()) return;

  const cleanId = modelId.trim();
  if (!p.models) p.models = [];

  const existing = p.models.find(m => m.id === cleanId);
  if (existing) {
    existing.selected = true;
    showToast(`模型【${cleanId}】已存在，已为您勾选`);
  } else {
    // Infer capabilities
    const caps = ['chat'];
    const lower = cleanId.toLowerCase();
    if (lower.includes('vision') || lower.includes('vl') || lower.includes('4o')) caps.push('vision');
    if (lower.includes('reasoner') || lower.includes('r1') || lower.includes('thinking')) caps.push('reasoning');
    if (lower.includes('coder') || lower.includes('code') || lower.includes('deepseek')) caps.push('tools');

    p.models.unshift({
      id: cleanId,
      name: cleanId,
      selected: true,
      capabilities: caps
    });
    showToast(`已成功添加模型【${cleanId}】`);
  }

  renderCurrentProviderModels();
  renderModelRolesDropdowns();
}

function renderCurrentProviderModels(filterText = '') {
  const container = document.getElementById('currModelListContainer');
  const countBadge = document.getElementById('currModelCount');
  if (!container) return;

  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (!p || !p.models) {
    container.innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 11.5px;">暂无模型，点击【获取模型列表】或【＋ 手动添加】</div>';
    if (countBadge) countBadge.innerText = '0';
    return;
  }

  const keyword = filterText.trim().toLowerCase();
  const filtered = p.models.filter(m => {
    if (!keyword) return true;
    return m.id.toLowerCase().includes(keyword) || (m.name && m.name.toLowerCase().includes(keyword));
  });

  const selectedCount = p.models.filter(m => m.selected !== false).length;
  if (countBadge) countBadge.innerText = `${selectedCount}/${p.models.length}`;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="padding: 16px; text-align: center; color: var(--text-muted); font-size: 11.5px;">
        ${keyword ? '未找到匹配模型' : '暂无模型，点击【获取模型列表】拉取'}
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(m => {
    const isChecked = m.selected !== false;
    const caps = m.capabilities || ['chat'];

    const capIcons = [];
    if (caps.includes('chat')) capIcons.push('<span class="cap-badge" title="支持对话">💬</span>');
    if (caps.includes('vision')) capIcons.push('<span class="cap-badge" title="支持视觉多模态">👁️</span>');
    if (caps.includes('reasoning')) capIcons.push('<span class="cap-badge" title="支持深度思考推理">🧠</span>');
    if (caps.includes('tools')) capIcons.push('<span class="cap-badge" title="支持工具调用与代码">🔧</span>');
    if (caps.includes('fast')) capIcons.push('<span class="cap-badge" title="低延迟快速模型">⚡</span>');

    return `
      <div class="model-item-card">
        <div class="model-item-left">
          <input type="checkbox" class="model-item-checkbox" ${isChecked ? 'checked' : ''} onchange="toggleModelSelection('${m.id}', this.checked)">
          <span class="model-item-id" title="${m.id}">${m.name || m.id}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div class="model-caps">${capIcons.join('')}</div>
          <button type="button" class="btn-del-model" onclick="deleteModelFromProvider('${m.id}')" title="从列表移除">✕</button>
        </div>
      </div>
    `;
  }).join('');
}

function filterCurrentProviderModels(val) {
  renderCurrentProviderModels(val);
}

function toggleModelSelection(modelId, checked) {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (!p || !p.models) return;
  const m = p.models.find(item => item.id === modelId);
  if (m) {
    m.selected = checked;
    const countBadge = document.getElementById('currModelCount');
    const selectedCount = p.models.filter(x => x.selected !== false).length;
    if (countBadge) countBadge.innerText = `${selectedCount}/${p.models.length}`;
    renderModelRolesDropdowns();
  }
}

function deleteModelFromProvider(modelId) {
  const p = AppState.providers.find(item => item.provider_id === AppState.activeProviderId);
  if (!p || !p.models) return;
  p.models = p.models.filter(m => m.id !== modelId);
  renderCurrentProviderModels();
  renderModelRolesDropdowns();
}

// --------------------------------------------------------------------------
// 8.2 Section 2: Model Roles Dynamic Dropdown Generator (对齐图2)
// --------------------------------------------------------------------------

function renderModelRolesDropdowns() {
  const roleKeys = ['chat', 'summary', 'quant', 'debate', 'vision'];

  // Collect all active models across all enabled providers
  const availableOptions = [
    { value: '', label: '-- 请选择模型 (未指定) --' }
  ];

  AppState.providers.forEach(p => {
    if (!p.enabled) return;
    (p.models || []).forEach(m => {
      if (m.selected !== false) {
        availableOptions.push({
          value: `${m.id}|${p.provider_id}`,
          label: `${m.name || m.id} | ${p.name}`,
          provider_id: p.provider_id,
          model_id: m.id
        });
      }
    });
  });

  roleKeys.forEach(role => {
    const select = document.getElementById(`roleSelect_${role}`);
    if (!select) return;

    select.innerHTML = availableOptions.map(opt => `
      <option value="${opt.value}">${opt.label}</option>
    `).join('');

    // Restore configured value
    const currentAssignment = AppState.modelRoles[role];
    if (currentAssignment && currentAssignment.model_id && currentAssignment.provider_id) {
      const targetVal = `${currentAssignment.model_id}|${currentAssignment.provider_id}`;
      if (availableOptions.some(o => o.value === targetVal)) {
        select.value = targetVal;
        return;
      }
    }

    // Smart default selection if unset and options available
    if (availableOptions.length > 1 && !select.value) {
      if (role === 'summary') {
        const flashOpt = availableOptions.find(o => o.label.toLowerCase().includes('flash') || o.label.toLowerCase().includes('mini'));
        if (flashOpt) select.value = flashOpt.value;
      } else if (role === 'debate') {
        const reasonOpt = availableOptions.find(o => o.label.toLowerCase().includes('reasoner') || o.label.toLowerCase().includes('r1') || o.label.toLowerCase().includes('o1'));
        if (reasonOpt) select.value = reasonOpt.value;
      } else if (role === 'vision') {
        const visOpt = availableOptions.find(o => o.label.toLowerCase().includes('vision') || o.label.toLowerCase().includes('vl') || o.label.toLowerCase().includes('4o'));
        if (visOpt) select.value = visOpt.value;
      }
      if (!select.value && availableOptions[1]) {
        select.value = availableOptions[1].value;
      }
    }
  });
}

function handleRoleChange(roleKey, compositeValue) {
  if (!compositeValue) {
    AppState.modelRoles[roleKey] = { provider_id: '', model_id: '' };
    return;
  }
  const parts = compositeValue.split('|');
  AppState.modelRoles[roleKey] = {
    model_id: parts[0] || '',
    provider_id: parts[1] || ''
  };
}

async function saveSettings() {
  syncCurrentProviderFormToState();

  // 1. Save providers to backend and localStorage
  try {
    for (const p of AppState.providers) {
      await fetch('/api/models/providers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(p)
      });
    }
    localStorage.setItem('astock_llm_providers', JSON.stringify(AppState.providers));
  } catch (err) {
    localStorage.setItem('astock_llm_providers', JSON.stringify(AppState.providers));
  }

  // 2. Save model roles to backend and localStorage
  try {
    await fetch('/api/models/roles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roles: AppState.modelRoles })
    });
    localStorage.setItem('astock_model_roles', JSON.stringify(AppState.modelRoles));
  } catch (err) {
    localStorage.setItem('astock_model_roles', JSON.stringify(AppState.modelRoles));
  }

  // 3. Save risk parameters if modified
  const stampInput = document.getElementById('cfgStampDuty');
  if (stampInput) AppState.riskParams.stampDuty = parseFloat(stampInput.value) || 0.05;
  const commInput = document.getElementById('cfgCommission');
  if (commInput) AppState.riskParams.commissionRate = (parseFloat(commInput.value) || 2.5) / 10000;
  const minCommInput = document.getElementById('cfgMinComm');
  if (minCommInput) AppState.riskParams.minCommission = parseFloat(minCommInput.value) || 5.0;

  closeSettingsModal();
  showToast('✅ 系统设置已成功保存！模型接入与角色分配已热重载生效');
}

// --------------------------------------------------------------------------
// 9. Toast Notification Helper
// --------------------------------------------------------------------------
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
  }, 2600);
}

// --------------------------------------------------------------------------
// 10. Initial DOM Ready Hook
// --------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  // 1. Render Session History & Infinite Scroll
  renderSessionList();
  setupSessionInfiniteScroll();

  // 2. Setup Chat Input Enter Key
  const chatInput = document.getElementById('chatInput');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendChat();
      }
    });
  }

  // 3. Setup Prompt Pills
  document.querySelectorAll('.prompt-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const key = pill.innerText.replace(/\[|\]/g, '').trim();
      appendChatMessage('user', `请帮我执行【${key}】并出具研报`);
      if (typeof UIEngine !== 'undefined') {
        executeA2UITask(key);
      } else {
        const content = PromptTemplates[key] || PromptTemplates['行情分析'];
        streamAIResponse(content, `${key} 深度诊断`);
      }
    });
  });

  // 4. Initial Tab & View Activation
  switchRightTab('dashboard');
  updateProjectedCalculator();

  // 5. Initialize Model Providers and Roles settings
  initProvidersSettings();
});

// Resize listener
window.addEventListener('resize', () => {
  renderTabCharts(AppState.activeRightTab);
});
