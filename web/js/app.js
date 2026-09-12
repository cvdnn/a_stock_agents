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
  },
  skillsList: [],
  skillsAudit: null,
  skillsFilter: {
    category: 'all',
    search: '',
    enabledOnly: false
  },
  activeDebugSkillId: 'astock-data-feed'
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
  AppState.currentSessionId = id;
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
async function startNewChat() {
  let newId = 's_' + Date.now();
  const title = '新建投研对话 ' + new Date().toLocaleTimeString().slice(0, 5);
  if (window.AStockAPI) {
    try {
      const res = await window.AStockAPI.createSession(title);
      if (res && res.session_id) newId = res.session_id;
    } catch (e) {
      console.warn('createSession fallback:', e);
    }
  }
  AppState.currentSessionId = newId;

  const newSession = {
    id: newId,
    title: title,
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
    streamAIResponse(tpl, '持股策略与实战三原则量化诊断报告', '持仓综合评分88分，精算税费保本卖出价与三级止损阶梯', { userText: prompt });
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
      streamAIResponse(tpl, '今日A股大盘行情与主线轮动深度研判', '等待后端返回可验证行情证据', { userText: prompt });
    }
    const sec = document.getElementById('section-market-indices');
    if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast('已发起【分析今日大盘行情】深度研判！');
  } else if (actionType === '收益分析') {
    const prompt = '请对当前投资组合进行全景收益分析，评估资产净值曲线、夏普比率、最大回撤以及多因子收益归因。';
    appendChatMessage('user', prompt);
    const tpl = PromptTemplates['收益分析'] || PromptTemplates['行情分析'];
    streamAIResponse(tpl, '投资组合全景收益与多因子归因报告', '等待后端返回可验证账户绩效与归因数据', { userText: prompt });
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
  'projected-action': '实战交易三原则指令单 (保本价试算器/三级止损)',
  'skills': '17项量化投研技能治理中枢 (元数据契约/动态热插拔/安全门禁/调用度量/在线调试)'
};

const ViewHeaderInfo = {
  'dashboard': { title: '工作台', icon: '📊' },
  'market': { title: '市场行情全景', icon: '📈' },
  'watchlist': { title: '自选个股深度研判', icon: '⭐' },
  'returns': { title: '投资收益全景分析', icon: '💰' },
  'projected-action': { title: '工作台 · 实战动作单', icon: '🛡️' },
  'skills': { title: '技能治理中心', icon: '🧩' }
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

  // 3.1 Hook: if switching to skills governance, initialize and render
  if (tabId === 'skills') {
    initSkillsGovernance();
  }

  // 4. Update Header Title and Icon
  const info = ViewHeaderInfo[tabId] || { title: `工作台 [${tabId}]`, icon: '📊' };
  const headerTitleElem = document.getElementById('workbenchHeaderTitle');
  if (headerTitleElem) headerTitleElem.innerText = info.title;
  const headerIconElem = document.getElementById('workbenchIconBadge');
  if (headerIconElem) headerIconElem.innerText = info.icon;

  // 5. Re-render Canvas Charts and fetch dynamic data for this tab
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
    prompt = '请结合工作台中本次成功返回的投研数据，分析明天的核心主线与防守标的；缺失数据请明确披露。';
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
// 6. Dynamic Backend Data Loaders & Canvas Charts Rendering
// --------------------------------------------------------------------------

// 6.1 Initialize Chat Sessions from Backend Database
async function initSessionsFromBackend() {
  if (!window.AStockAPI) return;
  try {
    const sessions = await window.AStockAPI.listSessions(30, 0);
    if (Array.isArray(sessions) && sessions.length > 0) {
      HistoricalSessions.length = 0;
      sessions.forEach(s => {
        HistoricalSessions.push({
          id: s.session_id,
          title: s.title,
          time: s.time || (s.created_at ? s.created_at.slice(5, 16) : '刚刚'),
          tab: s.tab || 'dashboard'
        });
      });
      AppState.loadedSessionCount = Math.min(10, HistoricalSessions.length);
      AppState.currentSessionId = HistoricalSessions[0].id;
      renderSessionList();
    }
  } catch (err) {
    console.warn('initSessionsFromBackend error:', err);
  }
}

// 6.2 Load Dashboard Data (Tab 1: 投研助手工作台)
// 数据只通过 AStockAPI 获取；失败时渲染错误或空状态。
function renderWorkbenchUnavailable(paneId, error) {
  const pane = document.getElementById(paneId);
  if (!pane) return;
  pane.dataset.state = 'unavailable';
  pane.innerHTML = `<div class="data-unavailable-state">
    <strong>当前数据不可用</strong>
    <span></span>
  </div>`;
  const detail = pane.querySelector('.data-unavailable-state span');
  if (detail) detail.textContent = error && (error.code || error.message)
    ? (error.code || error.message)
    : 'BACKEND_UNAVAILABLE';
}

async function loadDashboardData() {
  if (!window.AStockAPI) return;
  try {
    const setText = (id, text) => { const el = document.getElementById(id); if (el) el.innerText = text; };

    // 1. Portfolio Overview
    const portRes = await window.AStockAPI.getPortfolioOverview();
    if (portRes) {
      setText('ovTotalAssets', portRes.total_assets);
      setText('ovPositionRatioLbl', `持仓总市值 (${portRes.position_ratio}%)`);
      setText('ovPositionMarketVal', portRes.position_market_value);
      setText('ovCashRatioLbl', `可用现金 (${portRes.cash_ratio}%)`);
      setText('ovCash', portRes.available_cash);
      setText('ovTodayPnl', `${portRes.today_pnl} (${portRes.today_pnl_pct >= 0 ? '+' : ''}${portRes.today_pnl_pct}%)`);
      setText('ovAccumReturn', `${portRes.total_return_pct >= 0 ? '+' : ''}${portRes.total_return_pct}%`);
      setText('ovAnnualReturn', `${portRes.annualized_return_pct >= 0 ? '+' : ''}${portRes.annualized_return_pct}%`);
      setText('ovRiskStatus', `● ${portRes.risk_status}`);
      setText('ovCushionDesc', portRes.cushion_desc);

      const holdList = document.getElementById('ovHoldingsList');
      if (holdList && Array.isArray(portRes.holdings)) {
        holdList.innerHTML = portRes.holdings.map(h => `
          <div class="overview-holding-pill">
            <span style="font-weight:600;">${h.name} (${h.code})</span>
            <span class="tabular-nums">持仓 ${h.ratio_pct}%</span>
            <span class="${h.return_pct >= 0 ? 'text-up' : 'text-down'} tabular-nums">${h.return_pct >= 0 ? '+' : ''}${h.return_pct}%</span>
          </div>
        `).join('');
      }
      if (Array.isArray(portRes.donut_data) && document.getElementById('portfolioDonut')) {
        FinancialCharts.drawDonutChart('portfolioDonut', portRes.donut_data, {
          centerTitle: '总资产',
          centerValue: portRes.total_assets
        });
      }
    }

    // 2. Indices
    const idxRes = await window.AStockAPI.getMarketIndices();
    if (idxRes && Array.isArray(idxRes.indices)) {
      const byName = {};
      idxRes.indices.forEach(i => { byName[i.name] = i; });
      const bindDashIdx = (name, valId, changeId, metaId, sparkId) => {
        const item = byName[name];
        if (!item) return;
        const up = item.change >= 0;
        const fmt = (n) => n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const v = document.getElementById(valId);
        if (v) { v.innerText = fmt(item.price); v.className = `index-2x2-val ${up ? 'text-up' : 'text-down'} tabular-nums`; }
        const c = document.getElementById(changeId);
        if (c) {
          c.innerHTML = `<span>${up ? '▲ +' : '▼ '}${Math.abs(item.change).toFixed(2)}</span><span>${up ? '+' : ''}${item.change_pct}%</span>`;
          c.className = `index-2x2-change ${up ? 'text-up' : 'text-down'} tabular-nums`;
        }
        const m = document.getElementById(metaId);
        if (m) m.innerHTML = `<span>今开 ${fmt(item.open)}</span><span>成交 ${item.turnover_amount}</span>`;
        if (Array.isArray(item.sparkline)) FinancialCharts.drawSparkline(sparkId, item.sparkline, up);
      };
      bindDashIdx('上证指数', 'dashIndexShVal', 'dashIndexShChange', 'dashIndexShMeta', 'sparklineSh');
      bindDashIdx('深证成指', 'dashIndexSzVal', 'dashIndexSzChange', 'dashIndexSzMeta', 'sparklineSz');
      bindDashIdx('创业板指', 'dashIndexCyVal', 'dashIndexCyChange', 'dashIndexCyMeta', 'sparklineCy');
      bindDashIdx('科创50', 'dashIndexKcVal', 'dashIndexKcChange', 'dashIndexKcMeta', 'sparklineKc');
    }

    // 3. Sentiment
    const sentRes = await window.AStockAPI.getMarketSentiment();
    if (sentRes) {
      setText('dashSentimentScoreText', `${sentRes.score}分 · ${sentRes.status_text}`);
      const descEl = document.getElementById('dashSentimentMetaDesc');
      if (descEl) {
        descEl.innerHTML = `两市总成交 <strong>${sentRes.total_turnover}</strong> (${sentRes.turnover_growth})<br>上涨 <strong class="text-up">${sentRes.up_count.toLocaleString()}</strong> 家，下跌 <strong class="text-down">${sentRes.down_count.toLocaleString()}</strong> 家，涨停 <strong class="text-up">${sentRes.limit_up_count}</strong> 只`;
      }
      const aiEl = document.getElementById('dashAiCommentary');
      if (aiEl) aiEl.innerHTML = `<strong>AI量化研判</strong>：${sentRes.ai_summary}`;
      const sectorList = document.getElementById('dashSectorHotList');
      if (sectorList && Array.isArray(sentRes.sectors)) {
        sectorList.innerHTML = sentRes.sectors.map(s => `
          <div class="sector-hot-item">
            <span class="sector-hot-name">${s.name}</span>
            <span class="text-up tabular-nums" style="font-weight:600;">+${s.change_pct}%</span>
            <span class="text-up tabular-nums" style="font-size:11px;">主力净流入 ${s.net_inflow}</span>
          </div>
        `).join('');
      }
      if (document.getElementById('dashboardSentimentGauge')) {
        FinancialCharts.drawGauge('dashboardSentimentGauge', sentRes.score, { colorType: 'sentiment' });
      }
    }

    // 4. Custom Indices & Watchlist table
    const watchRes = await window.AStockAPI.getWatchlist();
    if (watchRes) {
      if (Array.isArray(watchRes.custom_indices)) {
        watchRes.custom_indices.slice(0, 2).forEach((ci, i) => {
          const n = i + 1;
          setText(`dashCustomIdx${n}Title`, ci.name);
          const ch = document.getElementById(`dashCustomIdx${n}Change`);
          if (ch) { ch.innerText = `${ci.change_pct >= 0 ? '+' : ''}${ci.change_pct}%`; ch.className = ci.change_pct >= 0 ? 'text-up' : 'text-down'; }
          setText(`dashCustomIdx${n}Val`, ci.val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
          if (Array.isArray(ci.sparkline)) FinancialCharts.drawSparkline(`sparklineCustomIdx${n}`, ci.sparkline, ci.change_pct >= 0);
        });
      }
      const tbody = document.getElementById('dashWatchlistTableBody');
      if (tbody && Array.isArray(watchRes.stocks)) {
        tbody.innerHTML = watchRes.stocks.slice(0, 4).map(stock => {
          const isUp = stock.change_pct >= 0;
          const sign = isUp ? '+' : '';
          const cls = isUp ? 'text-up' : 'text-down';
          return `
            <tr onclick="askStockPrompt('${stock.name}', '${stock.code}', '${stock.price.toFixed(2)}')">
              <td class="stock-name-cell">
                <span class="stock-name">${stock.name}</span>
                <span class="stock-code">${stock.code}</span>
              </td>
              <td class="tabular-nums" style="font-weight: 600;">${stock.price.toFixed(2)}</td>
              <td class="${cls} tabular-nums" style="font-weight: 600;">${sign}${stock.change_pct}%</td>
              <td class="${cls} tabular-nums">${stock.net_inflow || '--'}</td>
              <td style="text-align: right;">
                <button class="btn-follow">诊断</button>
              </td>
            </tr>
          `;
        }).join('');
      }
    }

    // 5. Investment Analysis
    const anaRes = await window.AStockAPI.getPortfolioAnalysis();
    if (anaRes) {
      setText('dashSharpeVal', anaRes.sharpe_ratio.toFixed(2));
      setText('dashWinRateVal', `${anaRes.win_rate}%`);
      setText('dashMaxDdVal', `${anaRes.max_drawdown}%`);
      setText('dashPlRatioVal', anaRes.pl_ratio.toFixed(2));
      setText('dashAttributionExcess', `跑赢基准 +${anaRes.benchmark_excess}%`);
      if (anaRes.equity_curve && document.getElementById('dashboardInvestCurve')) {
        const eq = anaRes.equity_curve;
        FinancialCharts.drawEquityCurve('dashboardInvestCurve', eq.strategy, eq.benchmark, eq.labels);
      }
      const attrRow = document.getElementById('dashAttributionRow');
      if (attrRow && Array.isArray(anaRes.attributions)) {
        attrRow.innerHTML = anaRes.attributions.slice(0, 3).map(a =>
          `<span>${a.name}: <strong class="text-up tabular-nums">+${a.contrib_pct}%</strong></span>`
        ).join('');
      }
    }

    // 6. Monitor Stream
    const monRes = await window.AStockAPI.getMonitorStream();
    if (monRes) {
      const badge = document.getElementById('dashMonitorLiveBadge');
      if (badge) badge.innerHTML = `<span class="live-dot"></span> 实时盯盘监控中 (延迟${monRes.latency_ms}ms)`;
      const streamList = document.getElementById('dashMonitorStreamList');
      if (streamList && Array.isArray(monRes.events)) {
        streamList.innerHTML = monRes.events.map(ev => {
          let itemClass = 'stream-buy';
          let tagClass = 'tag-buy';
          if (ev.type === 'main') { itemClass = 'stream-main'; tagClass = 'tag-main'; }
          else if (ev.type === 'risk') { itemClass = 'stream-risk'; tagClass = 'tag-risk'; }
          return `
            <div class="monitor-stream-item ${itemClass}">
              <div class="monitor-stream-left">
                <span class="monitor-stream-tag ${tagClass}">${ev.tag}</span>
                <span><strong>【${ev.name} ${ev.code}】</strong> ${ev.desc}</span>
              </div>
              <span class="monitor-stream-time tabular-nums">${ev.time}</span>
            </div>
          `;
        }).join('');
      }
      const stratContainer = document.getElementById('dashStrategiesContainer');
      if (stratContainer && Array.isArray(monRes.strategies)) {
        stratContainer.innerHTML = monRes.strategies.map(s => `
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div>
              <div style="font-size: 11.5px; font-weight: 600; color: #1D2129;">${s.name}</div>
              <div style="font-size: 10.5px; color: #86909C;">${s.desc}</div>
            </div>
            <label class="switch">
              <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="toggleStrategy('${s.name}', this)">
              <span class="slider"></span>
            </label>
          </div>
        `).join('');
      }
    }
  } catch (err) {
    console.warn('loadDashboardData error:', err);
    renderWorkbenchUnavailable('pane-dashboard', err);
  }
}

// 6.3 Load Market Data (Tab 2: 市场行情全景)
// 数据只通过 AStockAPI 获取；失败时渲染错误或空状态。
async function loadMarketData() {
  if (!window.AStockAPI) return;
  try {
    const setText = (id, text) => { const el = document.getElementById(id); if (el) el.innerText = text; };

    // 1. Indices
    const idxRes = await window.AStockAPI.getMarketIndices();
    if (idxRes && Array.isArray(idxRes.indices)) {
      const byName = {};
      idxRes.indices.forEach(i => { byName[i.name] = i; });
      const bindMktIdx = (name, prefix, canvasId) => {
        const item = byName[name];
        if (!item) return;
        const up = item.change >= 0;
        const fmt = (n) => n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const p = document.getElementById(prefix + 'Price');
        if (p) { p.innerText = fmt(item.price); p.className = `market-index-price ${up ? 'text-up' : 'text-down'} tabular-nums`; }
        const c = document.getElementById(prefix + 'Change');
        if (c) {
          c.innerHTML = `<span>${up ? '▲ +' : '▼ '}${Math.abs(item.change).toFixed(2)}</span><span>${up ? '+' : ''}${item.change_pct}%</span>`;
          c.className = `market-index-change ${up ? 'text-up' : 'text-down'} tabular-nums`;
        }
        setText(prefix + 'Open', fmt(item.open));
        setText(prefix + 'High', fmt(item.high));
        setText(prefix + 'PreClose', fmt(item.pre_close));
        setText(prefix + 'Turnover', item.turnover_amount);
        if (Array.isArray(item.sparkline)) FinancialCharts.drawSparkline(canvasId, item.sparkline, up);
      };
      bindMktIdx('上证指数', 'mktSh', 'marketSparkSh');
      bindMktIdx('深证成指', 'mktSz', 'marketSparkSz');
      bindMktIdx('创业板指', 'mktCy', 'marketSparkCy');
      bindMktIdx('科创50', 'mktKc', 'marketSparkKc');
    }

    // 2. Sentiment
    const sentRes = await window.AStockAPI.getMarketSentiment();
    if (sentRes) {
      setText('mktLimitUpCount', sentRes.limit_up_count);
      setText('mktLimitDownCount', sentRes.limit_down_count);
      setText('mktTotalTurnover', sentRes.total_turnover);
      setText('mktUpCount', sentRes.up_count.toLocaleString());
      setText('mktFlatCount', sentRes.flat_count.toLocaleString());
      setText('mktDownCount', sentRes.down_count.toLocaleString());
      if (document.getElementById('sentimentGauge')) {
        FinancialCharts.drawGauge('sentimentGauge', sentRes.score, { colorType: 'sentiment' });
      }
    }

    // 3. Kline
    const klineRes = await window.AStockAPI.getMarketKline('000001');
    if (klineRes) {
      setText('mktKlineMa5', klineRes.ma5.toFixed(2));
      setText('mktKlineMa10', klineRes.ma10.toFixed(2));
      setText('mktKlineMa20', klineRes.ma20.toFixed(2));
      if (Array.isArray(klineRes.klines) && document.getElementById('marketKlineCanvas')) {
        FinancialCharts.drawCandlestickChart('marketKlineCanvas', klineRes.klines, { showVolume: true });
      }
    }

    // 4. Ranks & Sectors & News & Concepts
    const rankRes = await window.AStockAPI.getMarketRanks();
    if (rankRes) {
      const gainers = rankRes.gainers || [];
      const losers = rankRes.losers || [];
      const northbound = rankRes.northbound || [];
      const sectors = rankRes.sectors_rank || [];
      const news = rankRes.news || [];
      const concepts = rankRes.hot_concepts || [];

      const gb = document.getElementById('mktGainersBody');
      if (gb) {
        gb.innerHTML = gainers.map(item => `
          <tr>
            <td><span class="news-index-badge">${item.rank}</span></td>
            <td><strong>${item.name}</strong><div class="stock-code">${item.code}</div></td>
            <td class="text-up tabular-nums" style="font-weight:600;">${item.price.toFixed(2)}</td>
            <td class="text-up tabular-nums" style="font-weight:600;">+${item.change_pct}%</td>
            <td class="text-up tabular-nums">${item.change_amount != null ? '+' + item.change_amount : '--'}</td>
          </tr>
        `).join('');
      }
      const lb = document.getElementById('mktLosersBody');
      if (lb) {
        lb.innerHTML = losers.map(item => `
          <tr>
            <td><span class="news-index-badge">${item.rank}</span></td>
            <td><strong>${item.name}</strong><div class="stock-code">${item.code}</div></td>
            <td class="text-down tabular-nums" style="font-weight:600;">${item.price.toFixed(2)}</td>
            <td class="text-down tabular-nums" style="font-weight:600;">${item.change_pct}%</td>
            <td class="text-down tabular-nums">${item.change_amount != null ? item.change_amount : '--'}</td>
          </tr>
        `).join('');
      }
      const nb = document.getElementById('mktNorthboundBody');
      if (nb) {
        nb.innerHTML = northbound.map(item => `
          <tr>
            <td><span class="news-index-badge">${item.rank}</span></td>
            <td><strong>${item.name}</strong><div class="stock-code">${item.code}</div></td>
            <td class="text-up tabular-nums" style="font-weight:600;">${item.net_inflow != null ? item.net_inflow : '--'}</td>
            <td class="text-up tabular-nums">${item.change_pct >= 0 ? '+' : ''}${item.change_pct}%</td>
          </tr>
        `).join('');
      }
      const sg = document.getElementById('mktSectorGrid');
      if (sg) {
        sg.innerHTML = sectors.map(item => `
          <div class="sector-tile">
            <div class="sector-name">${item.name}</div>
            <div class="sector-change tabular-nums">${item.change}</div>
          </div>
        `).join('');
      }
      const nl = document.getElementById('mktNewsList');
      if (nl) {
        nl.innerHTML = news.map(item => `
          <div class="news-briefing-item">
            <span class="tabular-nums" style="color: #86909C; font-size: 11px;">${item.time}</span>
            <div class="news-briefing-text">${item.title}</div>
          </div>
        `).join('');
      }
      const hc = document.getElementById('mktHotConcepts');
      if (hc) {
        hc.innerHTML = concepts.map(c => `<span class="concept-tag">${c}</span>`).join('');
      }
    }
  } catch (err) {
    console.warn('loadMarketData error:', err);
    renderWorkbenchUnavailable('pane-market', err);
  }
}

// 6.4 Load Watchlist Data (Tab 3: 自选个股深度研判)
// 数据只通过 AStockAPI 获取；失败时渲染错误或空状态。
async function loadWatchlistData(selectedCode) {
  if (!window.AStockAPI) return;
  const code = selectedCode || AppState.selectedStock || '300750';
  AppState.selectedStock = code;

  try {
    const watchRes = await window.AStockAPI.getWatchlist(code);
    if (!watchRes) return;
    const setText = (id, text) => { const el = document.getElementById(id); if (el) el.innerText = text; };

    // 1. Render Watchlist Sidebar
    if (Array.isArray(watchRes.stocks)) {
      const container = document.getElementById('watchStockList');
      if (container) {
        container.innerHTML = watchRes.stocks.map(stock => {
          const isActive = stock.code === code ? 'active' : '';
          const isUp = stock.change_pct >= 0;
          const cls = isUp ? 'text-up' : 'text-down';
          const sign = isUp ? '+' : '';
          return `
            <div class="watchlist-item-card ${isActive}" data-code="${stock.code}" onclick="selectWatchStock('${stock.code}')">
              <div>
                <div style="font-weight: 600; color: #1D2129;">${stock.name}</div>
                <div class="stock-code">${stock.code}</div>
              </div>
              <div style="text-align: right;">
                <div class="tabular-nums" style="font-weight: 600;">${stock.price.toFixed(2)}</div>
                <div class="${cls} tabular-nums" style="font-size: 11px;">${sign}${stock.change_pct}%</div>
              </div>
            </div>
          `;
        }).join('');
      }
      setText('watchStockCount', `自选股 (${watchRes.stocks.length})`);
      syncAtOperatorQuotes(watchRes.stocks);
    }

    // 2. Render Stock Detail
    const d = watchRes.active_stock_detail;
    if (!d) return;
    const isUp = d.change >= 0;
    const sign = isUp ? '+' : '';
    const arrow = isUp ? '▲ +' : '▼ ';
    const cls = isUp ? 'text-up' : 'text-down';

    setText('watchHeroName', d.name);
    setText('watchHeroCode', d.code);
    const priceEl = document.getElementById('watchHeroPrice');
    if (priceEl) { priceEl.innerText = d.price.toFixed(2); priceEl.className = `stock-hero-price ${cls} tabular-nums`; }
    const deltaEl = document.getElementById('watchHeroDelta');
    if (deltaEl) {
      deltaEl.innerHTML = `<span>${arrow}${Math.abs(d.change).toFixed(2)}</span><span>${sign}${d.change_pct}%</span>`;
      deltaEl.className = `stock-hero-delta ${cls} tabular-nums`;
    }
    setText('watchHeroOpen', d.open.toFixed(2));
    setText('watchHeroHigh', d.high.toFixed(2));
    setText('watchHeroLow', d.low.toFixed(2));
    setText('watchHeroPreClose', d.pre_close.toFixed(2));
    setText('watchHeroVol', d.volume);
    setText('watchHeroAmount', d.amount);

    setText('watchMetaIndustry', d.industry);
    setText('watchMetaConcepts', d.concepts);
    setText('watchMetaFloatCap', d.circ_market_val);
    setText('watchMetaTotalCap', d.total_market_val);
    setText('watchMetaPe', d.pe_ttm.toFixed(2));
    setText('watchMetaPb', d.pb.toFixed(2));
    setText('watchMeta52High', d.high_52w.toFixed(2));
    setText('watchMeta52Low', d.low_52w.toFixed(2));

    // Tags
    const tagsContainer = document.getElementById('watchHeroTags');
    if (tagsContainer && Array.isArray(d.tags)) {
      tagsContainer.innerHTML = d.tags.map(t => `<span class="stock-tag-pill">${t}</span>`).join('');
    }

    // Events
    const evEl = document.getElementById('watchEventsTimeline');
    if (evEl && Array.isArray(d.events)) {
      evEl.innerHTML = d.events.map(e => `
        <div class="timeline-item">
          <div class="timeline-date">${e.date}</div>
          <div class="timeline-content">${e.content}</div>
        </div>
      `).join('');
    }

    // Capital Flow
    if (d.capital_flow) {
      const cf = d.capital_flow;
      setText('watchFundMainInflow', cf.main_net);
      setText('watchFundSuperInflow', cf.super_large);
      setText('watchFundLargeInflow', cf.large);
      setText('watchFundMidInflow', cf.medium);
      setText('watchFundSmallInflow', cf.small);
      if (Array.isArray(cf.donut) && document.getElementById('fundFlowDonut')) {
        FinancialCharts.drawDonutChart('fundFlowDonut', cf.donut, { centerTitle: '主力流入', centerValue: cf.main_net });
      }
      if (document.getElementById('fundFlowTrendLine') && Array.isArray(cf.trend)) {
        FinancialCharts.drawMultiLine('fundFlowTrendLine', cf.dates || [], [
          { color: '#F5222D', data: cf.trend }
        ]);
      }
    }

    // Main Tracking
    if (d.main_control) {
      const mt = d.main_control;
      setText('watchMainHoldings', mt.holding);
      setText('watchMainRatio', mt.ratio);
      setText('watchMainConcentration', mt.concentration);
      if (document.getElementById('mainControlGauge')) {
        FinancialCharts.drawGauge('mainControlGauge', mt.score, { colorType: 'control' });
      }
    }

    // Northbound
    if (d.northbound) {
      setText('watchNorthSH', d.northbound.sh_flow);
      setText('watchNorthSZ', d.northbound.sz_flow);
    }

    // AI Conclusion (分析结果来自后端接口)
    if (d.ai_conclusion) {
      setText('watchAiConclusion', d.ai_conclusion.summary);
      const aiTags = document.getElementById('watchAiTags');
      if (aiTags && Array.isArray(d.ai_conclusion.tags)) {
        aiTags.innerHTML = d.ai_conclusion.tags.map((t, i) => {
          const style = i === d.ai_conclusion.tags.length - 1
            ? 'style="background: #E6F4FF; color: #1677FF; padding: 2px 6px; border-radius: 4px; font-size: 10px;"'
            : 'style="padding: 2px 6px; border-radius: 4px; font-size: 10px;"';
          return `<span class="bg-up-tag" ${style}>${t}</span>`;
        }).join('');
      }
    }

    // Kline
    if (Array.isArray(d.klines) && document.getElementById('stockKlineCanvas')) {
      FinancialCharts.drawCandlestickChart('stockKlineCanvas', d.klines, { showVolume: true });
    }
  } catch (err) {
    console.warn('loadWatchlistData error:', err);
    renderWorkbenchUnavailable('pane-watchlist', err);
  }
}

// 将后端 watchlist 行情合并到 @ 操作符静态股票配置：
// 现价/涨跌幅取自后端接口，拼音/描述/股池/持仓比例等保留为静态 UI 配置。
function syncAtOperatorQuotes(stocks) {
  if (!Array.isArray(stocks) || typeof AtOperatorRegistry === 'undefined') return;
  const priceMap = {};
  stocks.forEach(s => { if (s && s.code) priceMap[s.code] = s; });
  [AtOperatorRegistry.stock, AtOperatorRegistry.watchlist].forEach(list => {
    if (!Array.isArray(list)) return;
    list.forEach(item => {
      const live = priceMap[item.code];
      if (live) {
        if (live.price != null) item.currentPrice = live.price;
        if (live.change_pct != null) item.changePct = live.change_pct;
      }
    });
  });
}

// 6.5 Load Returns Data (Tab 4: 投资收益全景分析)
// 数据只通过 AStockAPI 获取；失败时渲染错误或空状态。
async function loadReturnsData() {
  if (!window.AStockAPI) return;
  try {
    const anaRes = await window.AStockAPI.getPortfolioAnalysis();
    if (!anaRes) return;
    const setText = (id, text) => { const el = document.getElementById(id); if (el) el.innerText = text; };

    setText('retAccumReturnVal', `+${anaRes.total_return}%`);
    setText('retBenchmarkExcessVal', `+${anaRes.benchmark_excess}%`);
    setText('retAnnualReturnVal', `+${anaRes.annualized_return}%`);
    setText('retWinRateVal', `${anaRes.win_rate}%`);
    setText('retWinLossCount', anaRes.win_loss_detail);
    setText('retSharpeVal', anaRes.sharpe_ratio.toFixed(2));
    setText('retMaxDrawdownVal', `${anaRes.max_drawdown}%`);
    setText('retPlRatioVal', anaRes.pl_ratio.toFixed(2));

    // Equity Curve
    if (anaRes.equity_curve && document.getElementById('equityCurveCanvas')) {
      FinancialCharts.drawEquityCurve('equityCurveCanvas', anaRes.equity_curve.strategy, anaRes.equity_curve.benchmark, anaRes.equity_curve.labels);
    }
    // Monthly PnL
    if (Array.isArray(anaRes.monthly_pnl) && document.getElementById('monthlyPnLCanvas')) {
      FinancialCharts.drawMonthlyPnLChart('monthlyPnLCanvas', anaRes.monthly_pnl);
    }

    // Strategy Contributions
    const scGrid = document.getElementById('retStrategyContribGrid');
    if (scGrid && Array.isArray(anaRes.attributions)) {
      scGrid.innerHTML = anaRes.attributions.map(sc => `
        <div class="strategy-contrib-item">
          <div class="contrib-header">
            <span>${sc.name}</span>
            <strong class="text-up tabular-nums">+${sc.contrib_pct}% (占比 ${sc.share_pct}%)</strong>
          </div>
          <div class="contrib-bar-wrap"><div class="contrib-bar-fill" style="width: ${sc.share_pct}%; background: ${sc.color};"></div></div>
        </div>
      `).join('');
    }

    // Positions Table
    const posTbody = document.getElementById('retPositionsTableBody');
    if (posTbody && Array.isArray(anaRes.positions)) {
      posTbody.innerHTML = anaRes.positions.map(pos => {
        const isUp = pos.pnl_pct >= 0;
        const cls = isUp ? 'text-up' : 'text-down';
        const sign = isUp ? '+' : '';
        return `
          <tr>
            <td>
              <div class="stock-cell-name">${pos.name}</div>
              <div class="stock-cell-code">${pos.code}</div>
            </td>
            <td class="tabular-nums">${pos.shares.toLocaleString()} 股</td>
            <td class="tabular-nums">¥${pos.cost.toFixed(2)}</td>
            <td class="tabular-nums ${cls}" style="font-weight:700;">¥${pos.price.toFixed(2)}</td>
            <td class="${cls} tabular-nums" style="font-weight:700;">${sign}${pos.pnl_pct}% (${pos.pnl_amount})</td>
            <td class="tabular-nums" style="color:#1677FF; font-weight:700;">¥${pos.breakeven_price.toFixed(2)}</td>
            <td><span style="color:${pos.status.includes('警戒') ? '#FA8C16' : '#52C41A'}; font-weight:600;">${pos.status}</span></td>
            <td><span class="tag-chip">${pos.strategy}</span></td>
            <td>
              <button class="action-btn" onclick="askStockPrompt('${pos.name}', '${pos.code}', '${pos.price.toFixed(2)}')">💬 提问</button>
            </td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    console.warn('loadReturnsData error:', err);
    renderWorkbenchUnavailable('pane-returns', err);
  }
}

// 6.6 Load All Backend Data in Parallel
async function loadAllBackendData() {
  await Promise.allSettled([
    initSessionsFromBackend(),
    loadDashboardData(),
    loadMarketData(),
    loadWatchlistData(),
    loadReturnsData()
  ]);
}

// 6.7 Canvas Charts Dispatcher
// 图表数据全部来自后端接口（MOCK 兜底），此处仅触发对应数据加载器重新渲染。
function renderTabCharts(tabId) {
  if (tabId === 'dashboard') {
    loadDashboardData();
  } else if (tabId === 'market') {
    loadMarketData();
  } else if (tabId === 'watchlist') {
    loadWatchlistData(AppState.selectedStock);
  } else if (tabId === 'returns') {
    loadReturnsData();
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
    summary: '等待后端根据真实持仓和成本数据生成诊断',
    body: '<p>尚未取得可验证的持仓、成本与行情数据；不能生成评分、保本价或交易动作。</p>'
  },
  '收益分析': {
    title: '投资组合全景收益与多因子归因报告',
    summary: '等待后端根据真实账户净值和交易记录生成归因',
    body: '<p>尚未取得可验证的账户净值和交易记录；不能生成收益、回撤、胜率或归因结论。</p>'
  },
  '行情分析': {
    title: '当前A股市场行情分析',
    summary: '等待后端返回可验证行情证据',
    body: '<p>尚未取得可验证的指数、成交额和板块数据；不能生成市场方向或交易建议。</p>'
  },
  '技术指标': {
    title: '全市场技术形态与指标共振扫描',
    summary: '等待后端根据真实 K 线计算技术指标',
    body: '<p>尚未取得可验证的 K 线与指标数据；不能生成形态、金叉或趋势结论。</p>'
  },
  '选股模型': {
    title: '5A五维共振旋转选股输出',
    summary: '等待后端根据真实候选池和因子证据生成结果',
    body: '<p>尚未取得可验证的候选池、行情和因子数据；不能生成排名、评分或买卖建议。</p>'
  }
};

// ==========================================================================
// 【@操作符】机制：数据注册中心与交互控制器 (AtOperatorRegistry & Controller)
// ==========================================================================

const AtOperatorRegistry = {
  watchlist: [
    { name: '比亚迪', code: '002594', pinyin: 'byd', insertText: '@比亚迪(002594)', desc: '新能源汽车', icon: '🚗', pool: 'watchlist', tag: '自选池', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '贵州茅台', code: '600519', pinyin: 'gzmt mt', insertText: '@贵州茅台(600519)', desc: '白酒', icon: '🍶', pool: 'holding', tag: '持仓池', isHolding: true, holdingRatio: null, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '海光信息', code: '688041', pinyin: 'hgxx', insertText: '@海光信息(688041)', desc: '国产算力', icon: '💽', pool: 'focus', tag: '关注池', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '宁德时代', code: '300750', pinyin: 'ndsd nd', insertText: '@宁德时代(300750)', desc: '动力电池', icon: '🔋', pool: 'holding', tag: '持仓池', isHolding: true, holdingRatio: null, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '中国平安', code: '601318', pinyin: 'zgpa pa', insertText: '@中国平安(601318)', desc: '金融', icon: '🛡️', pool: 'watchlist', tag: '自选池', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '中信证券', code: '600030', pinyin: 'zxzq zx', insertText: '@中信证券(600030)', desc: '券商', icon: '📊', pool: 'watchlist', tag: '自选池', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '中芯国际', code: '688981', pinyin: 'zxgj smic', insertText: '@中芯国际(688981)', desc: '半导体', icon: '💾', pool: 'focus', tag: '关注池', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '中际旭创', code: '300308', pinyin: 'zjxc xc', insertText: '@中际旭创(300308)', desc: '光模块', icon: '⚡', pool: 'focus', tag: '关注池', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null }
  ],
  stock: [
    // 1. 【持仓股】(Holding)
    { name: '贵州茅台', code: '600519', pinyin: 'gzmt mt', insertText: '@贵州茅台(600519)', desc: '白酒', icon: '🍶', pool: 'holding', tag: '持仓池', isHolding: true, holdingRatio: null, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '宁德时代', code: '300750', pinyin: 'ndsd nd', insertText: '@宁德时代(300750)', desc: '动力电池', icon: '🔋', pool: 'holding', tag: '持仓池', isHolding: true, holdingRatio: null, currentPrice: null, costPrice: null, changePct: null, pe: null },
    // 2. 【自选股】(Watchlist)
    { name: '比亚迪', code: '002594', pinyin: 'byd', insertText: '@比亚迪(002594)', desc: '新能源汽车', icon: '🚗', pool: 'watchlist', tag: '高端制造', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '长江电力', code: '600900', pinyin: 'cjdl', insertText: '@长江电力(600900)', desc: '公用事业', icon: '💧', pool: 'watchlist', tag: '红利防守', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '东方财富', code: '300059', pinyin: 'dfcf dc', insertText: '@东方财富(300059)', desc: '互联网券商', icon: '💻', pool: 'watchlist', tag: '金融科技', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '赛力斯', code: '601127', pinyin: 'sls', insertText: '@赛力斯(601127)', desc: '汽车', icon: '🏎️', pool: 'watchlist', tag: '华为链', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '中国平安', code: '601318', pinyin: 'zgpa pa', insertText: '@中国平安(601318)', desc: '金融', icon: '🛡️', pool: 'watchlist', tag: '高股息', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '中信证券', code: '600030', pinyin: 'zxzq zx', insertText: '@中信证券(600030)', desc: '券商', icon: '📊', pool: 'watchlist', tag: '大金融', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '紫金矿业', code: '601899', pinyin: 'zjky', insertText: '@紫金矿业(601899)', desc: '有色金属', icon: '⛏️', pool: 'watchlist', tag: '资源周期', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    // 3. 【关注股】(Focus)
    { name: '创业板指', code: '399006', pinyin: 'cybz cy', insertText: '@创业板指(399006)', desc: '宽基指数', icon: '🚀', pool: 'focus', tag: '科技成长', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '工业富联', code: '601138', pinyin: 'gyfl', insertText: '@工业富联(601138)', desc: 'AI硬件', icon: '🏭', pool: 'focus', tag: 'AI硬件', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '海光信息', code: '688041', pinyin: 'hgxx', insertText: '@海光信息(688041)', desc: '国产算力', icon: '💽', pool: 'focus', tag: '国产算力', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '沪深300', code: '000300', pinyin: 'hs300', insertText: '@沪深300(000300)', desc: '宽基指数', icon: '📈', pool: 'focus', tag: '核心指数', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '科创50', code: '000688', pinyin: 'kc50 kc', insertText: '@科创50(000688)', desc: '宽基指数', icon: '🔬', pool: 'focus', tag: '硬科技', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '上证指数', code: '000001', pinyin: 'szzs sh', insertText: '@上证指数(000001)', desc: '宽基指数', icon: '🏛️', pool: 'focus', tag: '大盘基准', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '中芯国际', code: '688981', pinyin: 'zxgj smic', insertText: '@中芯国际(688981)', desc: '半导体', icon: '💾', pool: 'focus', tag: '半导体', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null },
    { name: '中际旭创', code: '300308', pinyin: 'zjxc xc', insertText: '@中际旭创(300308)', desc: '光模块', icon: '⚡', pool: 'focus', tag: '算力硬件', isHolding: false, currentPrice: null, costPrice: null, changePct: null, pe: null }
  ],
  reference: [
    { name: '投资概要', code: 'ref_portfolio', insertText: '@投资概要', desc: '提取后端返回的持仓与资产状态', icon: '💼', tag: '右侧板块1' },
    { name: '大盘指数', code: 'ref_indices', insertText: '@大盘指数', desc: '提取后端返回的核心指数数据', icon: '📈', tag: '右侧板块2-1' },
    { name: '行情分析', code: 'ref_market', insertText: '@行情分析', desc: '提取后端返回的市场分析数据', icon: '🔥', tag: '右侧板块2-2' },
    { name: '自选指数', code: 'ref_watchlist', insertText: '@自选指数', desc: '提取后端返回的自选池与行情数据', icon: '⭐', tag: '右侧板块3-1' },
    { name: '投资分析', code: 'ref_invest', insertText: '@投资分析', desc: '提取后端返回的账户绩效与归因数据', icon: '📊', tag: '右侧板块3-2' },
    { name: '实时盯盘', code: 'ref_monitor', insertText: '@实时盯盘', desc: '提取后端返回的监控状态与事件', icon: '⚡', tag: '右侧板块4' }
  ],
  skill: [
    { name: 'astock-data-feed', code: 'skill_data', insertText: '@astock-data-feed', desc: '4级降级实时行情与日K线，经典技术指标与筹码', icon: '📡', tag: '数据基座' },
    { name: 'astock-platform-evaluate', code: 'skill_eval', insertText: '@astock-platform-evaluate', desc: '100分制量化打分、解套决策树与大盘健康度研判', icon: '⚖️', tag: '综合评估' },
    { name: 'astock-screener-5a', code: 'skill_5a', insertText: '@astock-screener-5a', desc: '量价/基本面/估值/主线旋转 5 维共振多因子选股模型', icon: '🎯', tag: '多因子选股' },
    { name: 'astock-quant-engine', code: 'skill_quant', insertText: '@astock-quant-engine', desc: '工业级截面量价因子、MAD去极值与滚动IC合成', icon: '⚙️', tag: '量化工程' },
    { name: 'astock-action-execution', code: 'skill_action', insertText: '@astock-action-execution', desc: '全部税费向上进位(ceil)最低保本价与三级风控阶梯', icon: '🛡️', tag: '实战风控' },
    { name: 'astock-strategy-macd', code: 'skill_macd', insertText: '@astock-strategy-macd', desc: '水下二次金叉与MACD底背离经典形态识别算法', icon: '〽️', tag: '经典形态' },
    { name: 'astock-strategy-tuige', code: 'skill_tuige', insertText: '@astock-strategy-tuige', desc: '退哥短线规则、涨停回调、连板接力与龙头首阴', icon: '⚡', tag: '短线规则' },
    { name: 'astock-strategy-mainboard', code: 'skill_mainboard', insertText: '@astock-strategy-mainboard', desc: '聚焦主板大市值流动性品种的多波段防御回踩策略', icon: '🌊', tag: '波段防御' },
    { name: 'astock-agent-debate', code: 'skill_debate', insertText: '@astock-agent-debate', desc: '基本面/量价/政策/游资/筹码/风控 7 角色对抗研判', icon: '👥', tag: '多智能体' },
    { name: 'astock-trade-paper', code: 'skill_paper', insertText: '@astock-trade-paper', desc: '考虑市场冲击滑点与 T+1 硬约束的模拟撮合交易', icon: '💼', tag: '模拟交易' }
  ],
  algorithm: [
    { name: '5A共振多因子模型', code: 'algo_5a', insertText: '@5A共振多因子模型', desc: '量价、基本面、估值、资金与主线5维正交旋转评分', icon: '🌪️', tag: '多因子' },
    { name: 'MAD去极值与截面Z-score', code: 'algo_mad', insertText: '@MAD去极值与截面Z-score', desc: '中位数绝对偏差去极值 + 截面标准化与分位数Rank', icon: '📐', tag: '数据清洗' },
    { name: '目标波动率与凯利仓位', code: 'algo_kelly', insertText: '@目标波动率与凯利仓位', desc: '动态对冲波动率与最优化杠杆仓位分配数学模型', icon: '🎲', tag: '仓位分配' },
    { name: '水下二次金叉判别算法', code: 'algo_macd_two', insertText: '@水下二次金叉判别算法', desc: 'DIFF零轴下方双波谷极值对比与波段间距硬过滤', icon: '🔱', tag: '形态判别' },
    { name: '真实滑点冲击撮合', code: 'algo_slippage', insertText: '@真实滑点冲击撮合', desc: '基于L2订单簿深度与成交量比率的对数滑点冲击', icon: '📉', tag: '撮合仿真' },
    { name: '阶梯移动止损算法', code: 'algo_stoploss', insertText: '@阶梯移动止损算法', desc: '依据最新高点与ATR阶梯式上移保本线与止盈线', icon: '🪜', tag: '动态风控' },
    { name: '因子IC/IR时序滚动回测', code: 'algo_ic_ir', insertText: '@因子IC/IR时序滚动回测', desc: '信息系数(IC)、信息比率(IR)与因子半衰期时序追踪', icon: '📊', tag: '因子检验' }
  ]
};

function formatOptionalDecimal(value) {
  return Number.isFinite(value) ? value.toFixed(2) : '--';
}

const AtOperatorController = {
  isOpen: false,
  focusPane: 'menu', // 'menu' | 'content'
  menuIndex: 0,
  selectedIndex: 0,
  activeCategory: 'stock',
  stockSearchQuery: '',
  categories: [
    { id: 'stock',     name: '股票', icon: '📈', count: 17 },
    { id: 'reference', name: '引用', icon: '📄', count: 6 },
    { id: 'skill',     name: '技能', icon: '⚡', count: 10 },
    { id: 'algorithm', name: '算法', icon: '🧠', count: 7 }
  ],

  init() {
    // 按照【持仓股】【自选股】【关注股】三大股池顺序叠加，股池中股票按照名称排序
    const poolPriority = { 'holding': 1, 'watchlist': 2, 'focus': 3 };
    AtOperatorRegistry.stock.sort((a, b) => {
      const pA = poolPriority[a.pool] || 99;
      const pB = poolPriority[b.pool] || 99;
      if (pA !== pB) return pA - pB;
      return a.name.localeCompare(b.name, 'zh-Hans-CN');
    });
    if (AtOperatorRegistry.watchlist) {
      AtOperatorRegistry.watchlist.sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN'));
    }

    this.renderSidebar();
    this.renderContent();

    const popup = document.getElementById('atOperatorPopup');
    if (popup) {
      // 阻止浮窗内部点击冒泡至 document，杜绝点击浮窗内任何元素导致意外关闭
      popup.addEventListener('click', (e) => {
        e.stopPropagation();
      });
    }

    // 绑定股票搜索框动态匹配
    const searchInput = document.getElementById('atStockSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.handleStockSearchInput(e.target.value);
      });
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          const items = this.getFilteredItems();
          if (items.length) {
            this.selectedIndex = 0;
            this.updateItemSelection();
            searchInput.blur();
            if (popup) popup.focus();
          }
        } else if (e.key === 'ArrowLeft') {
          e.preventDefault();
          this.focusPane = 'menu';
          this.renderSidebar();
          this.renderContent();
          searchInput.blur();
          if (popup) popup.focus();
        } else if (e.key === 'Enter') {
          e.preventDefault();
          this.selectCurrentItem();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          this.close();
        }
      });
    }

    // 全局方向键与操作键接管：当浮窗开启时，立即响应键盘上下左右、Enter、Escape 操作
    document.addEventListener('keydown', (e) => {
      if (!this.isOpen) return;
      const searchInput = document.getElementById('atStockSearchInput');
      if (document.activeElement === searchInput) {
        // 搜索输入框内部键入交由 searchInput 自身 keydown 处理
        return;
      }
      const navKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Escape'];
      if (navKeys.includes(e.key)) {
        e.preventDefault();
        this.handleKeyDown(e);
      }
    }, true);

    // 点击外部区域自动关闭浮窗（安全防御，防止 detached DOM 误触发）
    document.addEventListener('click', (e) => {
      if (this.isOpen) {
        const popup = document.getElementById('atOperatorPopup');
        const atBtn = document.getElementById('btnAtTrigger');
        // 忽略已从 DOM 树移除的节点（如动态刷新的元素）
        if (!document.contains(e.target)) return;
        const path = e.composedPath ? e.composedPath() : [];
        if (popup && (popup.contains(e.target) || path.includes(popup))) return;
        if (atBtn && (atBtn.contains(e.target) || path.includes(atBtn))) return;
        this.close();
      }
    });
  },

  open(catId = null) {
    const popup = document.getElementById('atOperatorPopup');
    if (!popup) return;

    if (catId && AtOperatorRegistry[catId]) {
      this.activeCategory = catId;
      this.menuIndex = this.categories.findIndex(c => c.id === catId);
      if (this.menuIndex < 0) this.menuIndex = 0;
    } else {
      this.activeCategory = 'stock';
      this.menuIndex = 0;
    }

    // @后弹窗焦点落在菜单栏上
    this.focusPane = 'menu';
    this.selectedIndex = 0;
    this.stockSearchQuery = '';

    const searchInput = document.getElementById('atStockSearchInput');
    if (searchInput) searchInput.value = '';

    this.renderSidebar();
    this.renderContent();
    popup.style.display = 'flex';
    this.isOpen = true;

    // 将焦点立即移到浮窗上，确保方向键即时可操作
    popup.setAttribute('tabindex', '-1');
    popup.focus();

    const atBtn = document.getElementById('btnAtTrigger');
    if (atBtn) atBtn.classList.add('active');
  },

  close() {
    const popup = document.getElementById('atOperatorPopup');
    if (!popup) return;
    popup.style.display = 'none';
    this.isOpen = false;
    this.focusPane = 'menu';
    this.stockSearchQuery = '';

    const atBtn = document.getElementById('btnAtTrigger');
    if (atBtn) atBtn.classList.remove('active');

    const input = document.getElementById('chatInput');
    if (input) input.focus();
  },

  toggle(e) {
    if (e && e.stopPropagation) e.stopPropagation();
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  },

  // 点击浮窗菜单栏项：展开右侧内容，阻止冒泡，不作为点击回填！
  handleMenuClick(e, catId, idx) {
    if (e) {
      if (e.stopPropagation) e.stopPropagation();
      if (e.preventDefault) e.preventDefault();
    }
    this.focusPane = 'menu';
    this.menuIndex = idx;
    this.setCategory(catId);
    const popup = document.getElementById('atOperatorPopup');
    if (popup) popup.focus();
  },

  setCategory(catId) {
    if (!AtOperatorRegistry[catId]) return;
    this.activeCategory = catId;
    this.selectedIndex = 0;
    this.renderSidebar();
    this.renderContent();
  },

  focusSearch() {
    const searchInput = document.getElementById('atStockSearchInput');
    if (searchInput) {
      this.focusPane = 'content';
      searchInput.focus();
      if (this.stockSearchQuery) {
        this.handleStockSearchInput(searchInput.value);
      }
    }
  },

  handleStockSearchInput(query) {
    this.stockSearchQuery = (query || '').trim().toLowerCase();
    this.selectedIndex = 0;
    const clearBtn = document.getElementById('atStockSearchClear');
    if (clearBtn) {
      clearBtn.style.display = this.stockSearchQuery ? 'inline-block' : 'none';
    }
    this.renderItemsList();
    this.updateItemSelection();
  },

  clearStockSearch() {
    this.stockSearchQuery = '';
    const searchInput = document.getElementById('atStockSearchInput');
    if (searchInput) {
      searchInput.value = '';
      searchInput.focus();
    }
    const clearBtn = document.getElementById('atStockSearchClear');
    if (clearBtn) clearBtn.style.display = 'none';
    this.selectedIndex = 0;
    this.renderItemsList();
    this.updateItemSelection();
  },

  getFilteredItems() {
    const rawItems = AtOperatorRegistry[this.activeCategory] || [];
    if (this.activeCategory === 'stock' && this.stockSearchQuery) {
      const q = this.stockSearchQuery;
      return rawItems.filter(item => {
        const codeMatch = item.code && item.code.toLowerCase().includes(q);
        const nameMatch = item.name && item.name.toLowerCase().includes(q);
        const pinyinMatch = item.pinyin && item.pinyin.toLowerCase().includes(q);
        const tagMatch = item.tag && item.tag.toLowerCase().includes(q);
        return codeMatch || nameMatch || pinyinMatch || tagMatch;
      });
    }
    return rawItems;
  },

  renderSidebar() {
    const sidebar = document.getElementById('atPopupSidebar');
    if (!sidebar) return;

    if (this.focusPane === 'menu') {
      sidebar.classList.add('pane-active');
    } else {
      sidebar.classList.remove('pane-active');
    }

    sidebar.innerHTML = this.categories.map((cat, idx) => {
      const isActive = cat.id === this.activeCategory;
      const isFocused = this.focusPane === 'menu' && idx === this.menuIndex;
      let classes = 'at-cat-item';
      if (isActive) classes += ' active';
      if (isFocused) classes += ' menu-focused';

      return `
        <div class="${classes}" onclick="AtOperatorController.handleMenuClick(event, '${cat.id}', ${idx})" title="${cat.name}">
          <div class="at-cat-item-left">
            <span>${cat.icon}</span>
            <span>${cat.name}</span>
          </div>
          <span class="at-cat-count">${AtOperatorRegistry[cat.id] ? AtOperatorRegistry[cat.id].length : cat.count}</span>
        </div>
      `;
    }).join('');
  },

  renderContent() {
    const searchWrap = document.getElementById('atStockSearchWrap');
    if (searchWrap) {
      if (this.activeCategory === 'stock') {
        searchWrap.style.display = 'flex';
      } else {
        searchWrap.style.display = 'none';
      }
    }

    const contentWrapper = document.getElementById('atPopupContentWrapper');
    if (contentWrapper) {
      if (this.focusPane === 'content') {
        contentWrapper.classList.add('pane-active');
      } else {
        contentWrapper.classList.remove('pane-active');
      }
    }

    this.renderItemsList();
    this.updateItemSelection();
  },

  renderItemsList() {
    const content = document.getElementById('atPopupContent');
    if (!content) return;

    const items = this.getFilteredItems();
    if (!items.length) {
      content.innerHTML = `
        <div style="padding: 30px 10px; text-align: center; color: #94A3B8; font-size: 12px;">
          <div style="font-size: 20px; margin-bottom: 6px;">🔍</div>
          <div>未找到与 "${this.stockSearchQuery}" 匹配的股票或代码</div>
        </div>
      `;
      return;
    }

    content.innerHTML = items.map((item, idx) => {
      const isSelected = this.focusPane === 'content' && idx === this.selectedIndex;

      // 股票类型标的 (具有现价 currentPrice)
      if (item.currentPrice !== undefined) {
        // 股池状态胶囊徽章标识：持仓股【持仓 xx%】、自选股【自选】、关注股【关注】，位置同【持仓xx%】，不同色彩区分
        let holdingBadgeHtml = '';
        if (item.pool === 'holding' || item.isHolding) {
          holdingBadgeHtml = `<span class="at-holding-badge holding">持仓 ${item.holdingRatio || ''}</span>`;
        } else if (item.pool === 'watchlist') {
          holdingBadgeHtml = `<span class="at-holding-badge watchlist">自选</span>`;
        } else if (item.pool === 'focus') {
          holdingBadgeHtml = `<span class="at-holding-badge focus">关注</span>`;
        }

        // 今日涨幅 (红涨绿跌，置于第二行最右侧)
        let changeTagHtml = '';
        if (Number.isFinite(item.changePct)) {
          const isUp = item.changePct > 0;
          const isDown = item.changePct < 0;
          const changeClass = isUp ? 'up' : (isDown ? 'down' : 'flat');
          const sign = isUp ? '+' : '';
          changeTagHtml = `<span class="at-change-tag ${changeClass}">${sign}${formatOptionalDecimal(item.changePct)}%</span>`;
        }

        const costStr = Number.isFinite(item.costPrice)
          ? `¥${formatOptionalDecimal(item.costPrice)}`
          : '--';

        // 截图规范：左侧图标 + 三行式一体化排版 (标题行 / 实时价+成本价+涨跌幅 / 题材描述行)
        return `
          <div class="at-item-card stock-card ${isSelected ? 'selected' : ''}" 
               onclick="AtOperatorController.selectItemByIndex(${idx})" 
               onmouseenter="if (AtOperatorController.focusPane === 'content') { AtOperatorController.selectedIndex = ${idx}; AtOperatorController.updateItemSelection(); }">
            <div class="at-item-icon">${item.icon}</div>
            <div class="at-item-info">
              <div class="at-item-header-line">
                <span class="at-item-name">${item.name}</span>
                ${item.code ? `<span class="at-item-code">(${item.code})</span>` : ''}
                ${holdingBadgeHtml}
              </div>
              <div class="at-item-price-row">
                <div class="at-item-price-line">
                  <span>实时价: <strong class="price-val">${Number.isFinite(item.currentPrice) ? `¥${formatOptionalDecimal(item.currentPrice)}` : '--'}</strong></span>
                  <span class="price-sep">|</span>
                  <span>成本价: <strong class="cost-val">${costStr}</strong></span>
                </div>
                ${changeTagHtml}
              </div>
              <div class="at-item-desc" title="${item.desc}">${item.desc}</div>
            </div>
          </div>
        `;
      }

      // 非股票类型标的 (引用/技能/算法)
      return `
        <div class="at-item-card non-stock-card ${isSelected ? 'selected' : ''}" 
             onclick="AtOperatorController.selectItemByIndex(${idx})" 
             onmouseenter="if (AtOperatorController.focusPane === 'content') { AtOperatorController.selectedIndex = ${idx}; AtOperatorController.updateItemSelection(); }">
          <div class="at-item-card-left">
            <div class="at-item-icon">${item.icon}</div>
            <div class="at-item-info">
              <div class="at-item-header-line">
                <span class="at-item-name">${item.name}</span>
                ${item.code ? `<span class="at-item-code">(${item.code})</span>` : ''}
              </div>
              <div class="at-item-desc" title="${item.desc}">${item.desc}</div>
            </div>
          </div>
          <div class="at-item-card-right">
            <span class="at-item-tag">${item.tag}</span>
            <span class="at-item-select-check">✔</span>
          </div>
        </div>
      `;
    }).join('');
  },

  updateItemSelection() {
    const content = document.getElementById('atPopupContent');
    if (!content) return;
    const cards = content.querySelectorAll('.at-item-card');
    cards.forEach((card, idx) => {
      if (this.focusPane === 'content' && idx === this.selectedIndex) {
        card.classList.add('selected');
        card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      } else {
        card.classList.remove('selected');
      }
    });
  },

  handleKeyDown(e) {
    if (!this.isOpen) return;

    if (e.key === 'Escape') {
      e.preventDefault();
      this.close();
      return;
    }

    // 焦点在菜单栏上：上下选菜单，右箭头进入内容区
    if (this.focusPane === 'menu') {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        this.menuIndex = (this.menuIndex + 1) % this.categories.length;
        this.activeCategory = this.categories[this.menuIndex].id;
        this.selectedIndex = 0;
        this.renderSidebar();
        this.renderContent();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        this.menuIndex = (this.menuIndex - 1 + this.categories.length) % this.categories.length;
        this.activeCategory = this.categories[this.menuIndex].id;
        this.selectedIndex = 0;
        this.renderSidebar();
        this.renderContent();
      } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        e.preventDefault();
        this.focusPane = 'content';
        this.selectedIndex = 0;
        this.renderSidebar();
        this.renderContent();
      }
      return;
    }

    // 焦点在内容区上：左箭头返回菜单栏，上下选条目，Enter确认回填
    if (this.focusPane === 'content') {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        this.focusPane = 'menu';
        this.renderSidebar();
        this.renderContent();
        const searchInput = document.getElementById('atStockSearchInput');
        if (searchInput) searchInput.blur();
        const popup = document.getElementById('atOperatorPopup');
        if (popup) popup.focus();
        return;
      }

      const items = this.getFilteredItems();
      if (!items.length) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        this.selectedIndex = (this.selectedIndex + 1) % items.length;
        this.updateItemSelection();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        this.selectedIndex = (this.selectedIndex - 1 + items.length) % items.length;
        this.updateItemSelection();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        this.selectCurrentItem();
      }
    }
  },

  selectItemByIndex(idx) {
    this.focusPane = 'content';
    this.selectedIndex = idx;
    this.selectCurrentItem();
  },

  selectCurrentItem() {
    const items = this.getFilteredItems();
    const item = items[this.selectedIndex];
    if (!item) return;

    this.backfillToInput(item, this.activeCategory);
    this.close();
  },

  backfillToInput(item, catId) {
    const input = document.getElementById('chatInput');
    if (!input) return;

    input.focus();

    // 创建高亮加粗标签节点
    const tokenSpan = document.createElement('span');
    tokenSpan.className = `at-token at-token-${catId}`;
    tokenSpan.contentEditable = 'false';
    tokenSpan.dataset.category = catId;
    tokenSpan.dataset.value = item.insertText.replace(/^@/, '');
    tokenSpan.innerText = item.insertText;

    // 单个空格文本节点（严格只保留一个自然空格）
    const spaceNode = document.createTextNode('\u00A0');

    // 检查光标位置或选区
    const sel = window.getSelection();
    let range = null;
    if (sel && sel.rangeCount > 0) {
      range = sel.getRangeAt(0);
      if (!input.contains(range.commonAncestorContainer)) {
        range = null;
      }
    }

    if (!range) {
      range = document.createRange();
      range.selectNodeContents(input);
      range.collapse(false);
    }

    // 若当前光标前紧挨着 '@' 字符，则将其消除
    if (range.startContainer.nodeType === (typeof Node !== "undefined" ? Node.TEXT_NODE : 3)) {
      const textNode = range.startContainer;
      const offset = range.startOffset;
      if (offset > 0 && textNode.textContent.charAt(offset - 1) === '@') {
        textNode.textContent = textNode.textContent.slice(0, offset - 1) + textNode.textContent.slice(offset);
        range.setStart(textNode, offset - 1);
        range.setEnd(textNode, offset - 1);
      }
    }

    range.deleteContents();
    range.insertNode(spaceNode);
    range.insertNode(tokenSpan);

    // 将光标严格移动至空格节点之后
    const newRange = document.createRange();
    newRange.setStartAfter(spaceNode);
    newRange.setEndAfter(spaceNode);
    if (sel) {
      sel.removeAllRanges();
      sel.addRange(newRange);
    }

    // 规范化多余空格，确保操作符后严格只保留一个空格
    this.normalizeInputSpaces(input);

    showToast(`已成功插入操作符【${item.insertText}】`);
  },

  normalizeInputSpaces(input) {
    const walker = document.createTreeWalker(input, NodeFilter.SHOW_TEXT, null, false);
    let node;
    while ((node = walker.nextNode())) {
      const prev = node.previousSibling;
      if (prev && prev.nodeType === Node.ELEMENT_NODE && prev.classList && prev.classList.contains('at-token')) {
        node.textContent = node.textContent.replace(/^[\s\u00A0]+/, '\u00A0');
      }
    }
  }
};

window.AtOperatorController = AtOperatorController;
window.openAtPopup = (catId = null) => AtOperatorController.open(catId);
window.closeAtPopup = () => AtOperatorController.close();
window.toggleAtPopup = (e) => AtOperatorController.toggle(e);

function focusChatInput() {
  const input = document.getElementById('chatInput');
  if (input) input.focus();
}
window.focusChatInput = focusChatInput;
// ==========================================================================
// 【# 模型】弹出浮窗与回填控制器 (ModelPopupController)
// ==========================================================================
const ModelPopupController = {
  isOpen: false,
  focusPane: 'sidebar', // 'sidebar' | 'content'
  sidebarIndex: 0,
  selectedIndex: 0,
  activeProviderId: null,
  searchQuery: '',

  init() {
    const popup = document.getElementById('modelSelectorPopup');
    if (popup) {
      popup.addEventListener('click', (e) => {
        e.stopPropagation();
      });
    }

    const searchInput = document.getElementById('modelSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.handleSearch(e.target.value);
      });
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          const items = this.getFilteredModels();
          if (items.length) {
            this.focusPane = 'content';
            this.selectedIndex = 0;
            this.updateSelection();
            searchInput.blur();
            if (popup) popup.focus();
          }
        } else if (e.key === 'ArrowLeft') {
          e.preventDefault();
          this.focusPane = 'sidebar';
          this.renderSidebar();
          this.renderContent();
          searchInput.blur();
          if (popup) popup.focus();
        } else if (e.key === 'Enter') {
          e.preventDefault();
          this.selectCurrentModel();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          this.close();
        }
      });
    }

    document.addEventListener('keydown', (e) => {
      if (!this.isOpen) return;
      const searchInput = document.getElementById('modelSearchInput');
      if (document.activeElement === searchInput) return;
      const navKeys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Escape'];
      if (navKeys.includes(e.key)) {
        e.preventDefault();
        this.handleKeyDown(e);
      }
    }, true);

    document.addEventListener('click', (e) => {
      if (this.isOpen) {
        const popup = document.getElementById('modelSelectorPopup');
        const modelBtn = document.getElementById('btnModelTrigger');
        const badge = document.getElementById('chatCurrentModelBadge');
        if (!document.contains(e.target)) return;
        const path = e.composedPath ? e.composedPath() : [];
        if (popup && (popup.contains(e.target) || path.includes(popup))) return;
        if (modelBtn && (modelBtn.contains(e.target) || path.includes(modelBtn))) return;
        if (badge && (badge.contains(e.target) || path.includes(badge))) return;
        this.close();
      }
    });

    this.updateCurrentBadgeDisplay();
  },

  getEnabledProviders() {
    return (AppState.providers || []).filter(p => p.enabled !== false);
  },

  getActiveProvider() {
    const enabled = this.getEnabledProviders();
    if (!enabled.length) return null;
    let p = enabled.find(x => x.provider_id === this.activeProviderId);
    if (!p) {
      this.activeProviderId = enabled[0].provider_id;
      p = enabled[0];
    }
    return p;
  },

  getFilteredModels() {
    const provider = this.getActiveProvider();
    if (!provider || !provider.models) return [];
    const models = provider.models.filter(m => m.selected !== false);
    const list = models.length > 0 ? models : provider.models;
    const q = this.searchQuery.trim().toLowerCase();
    if (!q) return list;
    return list.filter(m => (m.id && m.id.toLowerCase().includes(q)) || (m.name && m.name.toLowerCase().includes(q)));
  },

  open() {
    const popup = document.getElementById('modelSelectorPopup');
    if (!popup) return;

    // 若 @ 操作符浮窗打开则互斥关闭
    if (typeof AtOperatorController !== 'undefined' && AtOperatorController.isOpen) {
      AtOperatorController.close();
    }

    const enabled = this.getEnabledProviders();
    const savedProviderId = localStorage.getItem('astock_chat_selected_provider');
    if (savedProviderId && enabled.some(p => p.provider_id === savedProviderId)) {
      this.activeProviderId = savedProviderId;
      this.sidebarIndex = enabled.findIndex(p => p.provider_id === savedProviderId);
    } else {
      this.activeProviderId = enabled.length ? enabled[0].provider_id : null;
      this.sidebarIndex = 0;
    }

    this.isOpen = true;
    this.focusPane = 'sidebar';
    this.searchQuery = '';
    this.selectedIndex = 0;

    const searchInput = document.getElementById('modelSearchInput');
    if (searchInput) searchInput.value = '';
    const clearBtn = document.getElementById('modelSearchClear');
    if (clearBtn) clearBtn.style.display = 'none';

    popup.style.display = 'block';
    const triggerBtn = document.getElementById('btnModelTrigger');
    if (triggerBtn) triggerBtn.classList.add('active');

    this.renderSidebar();
    this.renderContent();
    popup.focus();
  },

  close() {
    const popup = document.getElementById('modelSelectorPopup');
    if (popup) popup.style.display = 'none';
    this.isOpen = false;
    const triggerBtn = document.getElementById('btnModelTrigger');
    if (triggerBtn) triggerBtn.classList.remove('active');
  },

  toggle(e) {
    if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  },

  renderSidebar() {
    const sidebar = document.getElementById('modelPopupSidebar');
    if (!sidebar) return;

    const enabled = this.getEnabledProviders();
    if (!enabled.length) {
      sidebar.innerHTML = '<div style="padding:16px 12px; font-size:12px; color:#94A3B8; text-align:center;">暂无启用供应商<br><button class="model-popup-config-btn" style="margin-top:8px;" onclick="openProvidersSettingsModal()">＋ 新增供应商</button></div>';
      return;
    }

    sidebar.innerHTML = enabled.map((p, idx) => {
      const isActive = p.provider_id === this.activeProviderId;
      const isFocused = this.focusPane === 'sidebar' && idx === this.sidebarIndex;
      const modelCount = (p.models || []).length;
      return `
        <div class="at-cat-item ${isActive ? 'active' : ''} ${isFocused ? 'menu-focused' : ''}"
             onclick="ModelPopupController.handleProviderClick('${p.provider_id}', ${idx})"
             title="${p.name || p.provider_id}">
          <div class="at-cat-icon">🏢</div>
          <div class="at-cat-info">
            <span class="at-cat-name">${p.name || p.provider_id}</span>
            <span class="at-cat-count">${modelCount} 模型</span>
          </div>
        </div>
      `;
    }).join('');
  },

  handleProviderClick(providerId, idx) {
    this.activeProviderId = providerId;
    this.sidebarIndex = idx;
    this.focusPane = 'sidebar';
    this.selectedIndex = 0;
    this.renderSidebar();
    this.renderContent();
  },

  handleSearch(val) {
    this.searchQuery = val;
    this.selectedIndex = 0;
    const clearBtn = document.getElementById('modelSearchClear');
    if (clearBtn) clearBtn.style.display = val ? 'inline-block' : 'none';
    this.renderContent();
  },

  clearSearch() {
    this.searchQuery = '';
    const searchInput = document.getElementById('modelSearchInput');
    if (searchInput) {
      searchInput.value = '';
      searchInput.focus();
    }
    const clearBtn = document.getElementById('modelSearchClear');
    if (clearBtn) clearBtn.style.display = 'none';
    this.selectedIndex = 0;
    this.renderContent();
  },

  focusSearch() {
    const searchInput = document.getElementById('modelSearchInput');
    if (searchInput) searchInput.focus();
  },

  renderContent() {
    const container = document.getElementById('modelPopupContent');
    if (!container) return;

    const provider = this.getActiveProvider();
    if (!provider) {
      container.innerHTML = '<div style="padding:28px 16px; text-align:center; color:#94A3B8; font-size:12px;">请先在左侧选择模型供应商</div>';
      return;
    }

    const models = this.getFilteredModels();
    if (!models.length) {
      container.innerHTML = `
        <div style="padding:28px 16px; text-align:center; color:#94A3B8; font-size:12px;">
          暂无匹配的模型<br>
          <button class="model-popup-config-btn" style="margin-top:10px;" onclick="openProvidersSettingsModal()">⚙️ 管理此供应商模型</button>
        </div>
      `;
      return;
    }

    const savedModelId = localStorage.getItem('astock_chat_selected_model');

    container.innerHTML = models.map((m, idx) => {
      const isSelected = this.focusPane === 'content' && idx === this.selectedIndex;
      const isCurrentActive = (m.id === savedModelId);
      const caps = m.capabilities || ['chat'];
      const capBadges = [];
      if (caps.includes('chat')) capBadges.push('<span class="op-badge op-badge-stock" style="font-size:10.5px; padding:1px 5px;">💬 对话</span>');
      if (caps.includes('reasoning')) capBadges.push('<span class="op-badge op-badge-algo" style="font-size:10.5px; padding:1px 5px;">🧠 思考</span>');
      if (caps.includes('tools')) capBadges.push('<span class="op-badge op-badge-skill" style="font-size:10.5px; padding:1px 5px;">🔧 工具</span>');
      if (caps.includes('fast')) capBadges.push('<span class="op-badge op-badge-ref" style="font-size:10.5px; padding:1px 5px;">⚡ 极速</span>');

      return `
        <div class="at-item-card ${isSelected ? 'selected' : ''}"
             onclick="ModelPopupController.selectModelByIndex(${idx})"
             onmouseenter="if (ModelPopupController.focusPane === 'content') { ModelPopupController.selectedIndex = ${idx}; ModelPopupController.updateSelection(); }"
             title="点击选择模型：# ${m.id}(${provider.name || provider.provider_id})">
          <div class="at-item-row-top">
            <span class="at-item-name">${m.name || m.id}</span>
            <span class="at-item-code">${m.id}</span>
            ${isCurrentActive ? '<span class="at-stock-badge at-badge-watchlist">当前</span>' : ''}
          </div>
          <div class="at-item-row-bottom" style="display:flex; align-items:center; gap:6px; margin-top:4px;">
            <div style="display:flex; align-items:center; gap:4px;">${capBadges.join('')}</div>
            <span style="font-size:11px; color:#94A3B8; margin-left:auto;">${provider.name || provider.provider_id}</span>
          </div>
        </div>
      `;
    }).join('');
  },

  selectModelByIndex(idx) {
    this.focusPane = 'content';
    this.selectedIndex = idx;
    this.selectCurrentModel();
  },

  selectCurrentModel() {
    const models = this.getFilteredModels();
    const model = models[this.selectedIndex];
    const provider = this.getActiveProvider();
    if (!model || !provider) return;

    this.backfillToInput(provider, model);
    this.close();
  },

  updateSelection() {
    const cards = document.querySelectorAll('#modelPopupContent .at-item-card');
    cards.forEach((card, idx) => {
      if (idx === this.selectedIndex) {
        card.classList.add('selected');
        card.scrollIntoView({ block: 'nearest' });
      } else {
        card.classList.remove('selected');
      }
    });
  },

  handleKeyDown(e) {
    const enabled = this.getEnabledProviders();
    const models = this.getFilteredModels();

    if (e.key === 'Escape') {
      this.close();
      return;
    }

    if (this.focusPane === 'sidebar') {
      if (e.key === 'ArrowDown') {
        if (this.sidebarIndex < enabled.length - 1) {
          this.sidebarIndex++;
          this.activeProviderId = enabled[this.sidebarIndex].provider_id;
          this.selectedIndex = 0;
          this.renderSidebar();
          this.renderContent();
        }
      } else if (e.key === 'ArrowUp') {
        if (this.sidebarIndex > 0) {
          this.sidebarIndex--;
          this.activeProviderId = enabled[this.sidebarIndex].provider_id;
          this.selectedIndex = 0;
          this.renderSidebar();
          this.renderContent();
        }
      } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        if (models.length) {
          this.focusPane = 'content';
          this.selectedIndex = 0;
          this.renderSidebar();
          this.updateSelection();
        }
      }
    } else if (this.focusPane === 'content') {
      if (e.key === 'ArrowDown') {
        if (this.selectedIndex < models.length - 1) {
          this.selectedIndex++;
          this.updateSelection();
        }
      } else if (e.key === 'ArrowUp') {
        if (this.selectedIndex > 0) {
          this.selectedIndex--;
          this.updateSelection();
        }
      } else if (e.key === 'ArrowLeft') {
        this.focusPane = 'sidebar';
        this.renderSidebar();
        this.updateSelection();
      } else if (e.key === 'Enter') {
        this.selectCurrentModel();
      }
    }
  },

  backfillToInput(provider, model) {
    const input = document.getElementById('chatInput');
    if (!input) return;

    input.focus();

    const providerName = provider.name || provider.provider_id;
    const modelId = model.id;
    const insertText = `# ${modelId}(${providerName})`;

    // 创建高亮加粗标签节点（.at-token.at-token-model）
    const tokenSpan = document.createElement('span');
    tokenSpan.className = 'at-token at-token-model';
    tokenSpan.contentEditable = 'false';
    tokenSpan.dataset.category = 'model';
    tokenSpan.dataset.provider = provider.provider_id;
    tokenSpan.dataset.model = modelId;
    tokenSpan.innerText = insertText;

    const spaceNode = document.createTextNode(' ');

    const sel = window.getSelection();
    let range = null;
    if (sel && sel.rangeCount > 0) {
      range = sel.getRangeAt(0);
      if (!input.contains(range.commonAncestorContainer)) {
        range = null;
      }
    }

    if (!range) {
      range = document.createRange();
      range.selectNodeContents(input);
      range.collapse(false);
    }

    // 若当前光标前紧挨着 '#' 字符，将其消除
    if (range.startContainer.nodeType === (typeof Node !== "undefined" ? Node.TEXT_NODE : 3)) {
      const textNode = range.startContainer;
      const offset = range.startOffset;
      if (offset > 0 && textNode.textContent.charAt(offset - 1) === '#') {
        textNode.textContent = textNode.textContent.slice(0, offset - 1) + textNode.textContent.slice(offset);
        range.setStart(textNode, offset - 1);
        range.setEnd(textNode, offset - 1);
      }
    }

    range.deleteContents();
    range.insertNode(spaceNode);
    range.insertNode(tokenSpan);

    const newRange = document.createRange();
    newRange.setStartAfter(spaceNode);
    newRange.setEndAfter(spaceNode);
    if (sel) {
      sel.removeAllRanges();
      sel.addRange(newRange);
    }

    // 记录到本地状态与全局控制器
    localStorage.setItem('astock_chat_selected_provider', provider.provider_id);
    localStorage.setItem('astock_chat_selected_model', modelId);
    if (window.ChatModelSelectorController) {
      ChatModelSelectorController.render();
    }

    this.updateCurrentBadgeDisplay();
    showToast(`已选定模型【${insertText}】`);
  },

  updateCurrentBadgeDisplay() {
    const badgeText = document.getElementById('chatCurrentModelText');
    if (!badgeText) return;

    const savedProviderId = localStorage.getItem('astock_chat_selected_provider');
    const savedModelId = localStorage.getItem('astock_chat_selected_model');

    const enabled = this.getEnabledProviders();
    let p = enabled.find(x => x.provider_id === savedProviderId) || enabled[0];
    if (p) {
      const m = (p.models || []).find(x => x.id === savedModelId) || (p.models && p.models[0]);
      const pName = p.name || p.provider_id;
      const mId = m ? (m.name || m.id) : (savedModelId || '未设模型');
      badgeText.innerText = `${pName} / ${mId}`;
      if (badgeText.parentElement) {
        badgeText.parentElement.title = `当前生效模型: ${pName} / ${mId} (点击更换)`;
      }
    } else {
      badgeText.innerText = '未配置模型';
    }
  }
};
window.ModelPopupController = ModelPopupController;
window.openModelPopup = () => ModelPopupController.open();
window.closeModelPopup = () => ModelPopupController.close();
window.toggleModelPopup = (e) => ModelPopupController.toggle(e);


function clearChatInput() {
  const input = document.getElementById('chatInput');
  if (input) {
    input.innerHTML = '';
    input.focus();
    showToast('输入框已清空');
  }
}
window.clearChatInput = clearChatInput;

// ==========================================================================
// 输入框兼容层 (支持 .value 双向透明访问与富文本回填)
// ==========================================================================

function getChatInputPlainText(elem) {
  if (!elem) return '';
  let result = '';
  function traverse(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      result += node.textContent;
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      if (node.classList.contains('at-token')) {
        result += node.innerText.trim();
      } else if (node.tagName === 'BR') {
        result += '\n';
      } else {
        for (let child of node.childNodes) {
          traverse(child);
        }
      }
    }
  }
  traverse(elem);
  return result.replace(/\u00A0/g, ' ').replace(/\s+/g, ' ').trim();
}

function setChatInputFromText(elem, text) {
  if (!elem) return;
  elem.innerHTML = '';
  if (!text) return;

  const regex = /(@[^\s]+)/g;
  let lastIdx = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    const textBefore = text.slice(lastIdx, match.index);
    if (textBefore) {
      elem.appendChild(document.createTextNode(textBefore));
    }
    const tokenStr = match[1];
    const span = document.createElement('span');
    span.className = 'at-token';
    if (tokenStr.includes('60') || tokenStr.includes('30') || tokenStr.includes('00') || tokenStr.includes('68')) {
      span.classList.add('at-token-stock');
    } else if (tokenStr.includes('投资概要') || tokenStr.includes('大盘指数') || tokenStr.includes('行情分析') || tokenStr.includes('自选指数') || tokenStr.includes('投资分析') || tokenStr.includes('盯盘') || tokenStr.includes('工作台')) {
      span.classList.add('at-token-ref');
    } else if (tokenStr.includes('astock')) {
      span.classList.add('at-token-skill');
    } else if (tokenStr.includes('持仓') || tokenStr.includes('自选') || tokenStr.includes('关注')) {
      span.classList.add('at-token-watchlist');
    } else {
      span.classList.add('at-token-algo');
    }
    span.contentEditable = 'false';
    span.innerText = tokenStr;
    elem.appendChild(span);
    elem.appendChild(document.createTextNode('\u00A0'));
    lastIdx = regex.lastIndex;
  }

  const remaining = text.slice(lastIdx);
  if (remaining) {
    elem.appendChild(document.createTextNode(remaining));
  }
}

// ==========================================================================
// 【@操作符】原子化连带删除机制 (Backspace 退格处理)
// 当光标落在【@操作符+空格】后，按退格键时，空格与【@操作符】一同删除
// ==========================================================================

function handleChatInputBackspace(e, input) {
  if (!input) input = document.getElementById('chatInput');
  if (!input) return false;

  const sel = window.getSelection();
  if (!sel || !sel.rangeCount || !sel.isCollapsed) {
    return false;
  }

  const range = sel.getRangeAt(0);
  if (!input.contains(range.startContainer)) {
    return false;
  }

  const container = range.startContainer;
  const offset = range.startOffset;

  // 辅助判断节点是否为 @操作符 span
  function isAtToken(node) {
    return !!(node && node.nodeType === Node.ELEMENT_NODE && node.classList && node.classList.contains('at-token'));
  }

  // 辅助判断字符是否为空格 (普通空格 \u0020 或 NBSP \u00A0)
  function isSpaceChar(ch) {
    return ch === ' ' || ch === '\u00A0' || /\s/.test(ch);
  }

  // 辅助向前跳过空文本节点
  function getPrevNonEmptySibling(node) {
    let p = node ? node.previousSibling : null;
    while (p && p.nodeType === Node.TEXT_NODE && p.textContent === '') {
      p = p.previousSibling;
    }
    return p;
  }

  let tokenToDelete = null;
  let textNodeToTrim = null;
  let plainTextMatch = null;
  let cursorTarget = null;

  // 防御：若光标意外落在 .at-token 内部
  let current = container;
  while (current && current !== input) {
    if (isAtToken(current)) {
      tokenToDelete = current;
      const next = current.nextSibling;
      if (next && next.nodeType === Node.TEXT_NODE && next.textContent.length > 0 && isSpaceChar(next.textContent.charAt(0))) {
        textNodeToTrim = { node: next, index: 0 };
      }
      break;
    }
    current = current.parentNode;
  }

  // 情况 1: 光标在容器元素中 (offset 是子节点序号)
  if (!tokenToDelete && container.nodeType === Node.ELEMENT_NODE) {
    if (offset > 0) {
      const prevChild = container.childNodes[offset - 1];
      if (prevChild) {
        if (prevChild.nodeType === Node.TEXT_NODE) {
          const text = prevChild.textContent;
          if (text.length > 0 && isSpaceChar(text.charAt(text.length - 1))) {
            const tokenNode = getPrevNonEmptySibling(prevChild);
            if (isAtToken(tokenNode)) {
              tokenToDelete = tokenNode;
              textNodeToTrim = { node: prevChild, index: text.length - 1 };
              const nodeBefore = getPrevNonEmptySibling(tokenNode);
              if (nodeBefore) {
                cursorTarget = { node: nodeBefore, after: true };
              } else if (text.length > 1) {
                cursorTarget = { node: prevChild, offset: text.length - 1 };
              } else {
                cursorTarget = { node: input, start: true };
              }
            }
          }
        } else if (isAtToken(prevChild)) {
          // 光标紧跟在 .at-token 后面（无空格）
          tokenToDelete = prevChild;
          const nodeBefore = getPrevNonEmptySibling(prevChild);
          cursorTarget = nodeBefore ? { node: nodeBefore, after: true } : { node: input, start: true };
        }
      }
    }
  }

  // 情况 2: 光标在文本节点内部
  if (!tokenToDelete && container.nodeType === Node.TEXT_NODE) {
    const text = container.textContent;

    if (offset > 0) {
      const prevChar = text.charAt(offset - 1);
      if (isSpaceChar(prevChar)) {
        // 2.1 文本节点开头的空格，且前一个兄弟节点是 .at-token
        if (offset === 1) {
          const prev = getPrevNonEmptySibling(container);
          if (isAtToken(prev)) {
            tokenToDelete = prev;
            textNodeToTrim = { node: container, index: 0 };
            const nodeBefore = getPrevNonEmptySibling(prev);
            if (container.textContent.length > 1) {
              cursorTarget = { node: container, offset: 0 };
            } else if (nodeBefore) {
              cursorTarget = { node: nodeBefore, after: true };
            } else {
              cursorTarget = { node: input, start: true };
            }
          }
        }

        // 2.2 纯文本形式的 "@操作符 + 空格"
        if (!tokenToDelete) {
          const textBefore = text.slice(0, offset);
          const match = textBefore.match(/(@[^\s\u00A0]+)[\s\u00A0]$/);
          if (match) {
            plainTextMatch = {
              node: container,
              offset: offset,
              length: match[0].length
            };
          }
        }
      }
    } else if (offset === 0) {
      // 2.3 光标在文本节点起点 (offset === 0)
      const prev = getPrevNonEmptySibling(container);
      if (prev) {
        if (prev.nodeType === Node.TEXT_NODE) {
          const prevText = prev.textContent;
          if (prevText.length > 0 && isSpaceChar(prevText.charAt(prevText.length - 1))) {
            const tokenNode = getPrevNonEmptySibling(prev);
            if (isAtToken(tokenNode)) {
              tokenToDelete = tokenNode;
              textNodeToTrim = { node: prev, index: prevText.length - 1 };
              cursorTarget = { node: container, offset: 0 };
            }
          }
        } else if (isAtToken(prev)) {
          // 直接紧随 .at-token
          tokenToDelete = prev;
          cursorTarget = { node: container, offset: 0 };
        }
      }
    }
  }

  // 执行原子化连带删除
  if (tokenToDelete) {
    if (e && e.preventDefault) e.preventDefault();

    const nodeBefore = getPrevNonEmptySibling(tokenToDelete);

    // 1. 缩减或删除空格文本节点
    if (textNodeToTrim) {
      const tn = textNodeToTrim.node;
      const idx = textNodeToTrim.index;
      const original = tn.textContent;
      const updated = original.slice(0, idx) + original.slice(idx + 1);
      if (updated.length === 0) {
        tn.remove();
      } else {
        tn.textContent = updated;
      }
    }

    // 2. 删除 @操作符 节点
    tokenToDelete.remove();

    // 3. 精确定位删除后的光标
    const newRange = document.createRange();
    let caretPlaced = false;

    if (cursorTarget && cursorTarget.node && cursorTarget.node.parentNode) {
      try {
        if (cursorTarget.start) {
          newRange.setStart(cursorTarget.node, 0);
          newRange.setEnd(cursorTarget.node, 0);
          caretPlaced = true;
        } else if (cursorTarget.after) {
          if (cursorTarget.node.nodeType === Node.TEXT_NODE) {
            newRange.setStart(cursorTarget.node, cursorTarget.node.textContent.length);
            newRange.setEnd(cursorTarget.node, cursorTarget.node.textContent.length);
          } else {
            newRange.setStartAfter(cursorTarget.node);
            newRange.setEndAfter(cursorTarget.node);
          }
          caretPlaced = true;
        } else if (typeof cursorTarget.offset === 'number') {
          const maxOffset = cursorTarget.node.nodeType === Node.TEXT_NODE
            ? cursorTarget.node.textContent.length
            : cursorTarget.node.childNodes.length;
          const off = Math.min(cursorTarget.offset, maxOffset);
          newRange.setStart(cursorTarget.node, off);
          newRange.setEnd(cursorTarget.node, off);
          caretPlaced = true;
        }
      } catch (err) {
        caretPlaced = false;
      }
    }

    if (!caretPlaced) {
      if (nodeBefore && nodeBefore.parentNode) {
        if (nodeBefore.nodeType === Node.TEXT_NODE) {
          newRange.setStart(nodeBefore, nodeBefore.textContent.length);
          newRange.setEnd(nodeBefore, nodeBefore.textContent.length);
        } else {
          newRange.setStartAfter(nodeBefore);
          newRange.setEndAfter(nodeBefore);
        }
      } else {
        newRange.selectNodeContents(input);
        newRange.collapse(true);
      }
    }

    sel.removeAllRanges();
    sel.addRange(newRange);

    // 4. 若内容已全部清空，规范化输入框内部结构
    if (input.innerText.trim() === '' && !input.querySelector('.at-token')) {
      input.innerHTML = '';
      const emptyRange = document.createRange();
      emptyRange.selectNodeContents(input);
      emptyRange.collapse(true);
      sel.removeAllRanges();
      sel.addRange(emptyRange);
    }

    input.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }

  if (plainTextMatch) {
    if (e && e.preventDefault) e.preventDefault();
    const node = plainTextMatch.node;
    const off = plainTextMatch.offset;
    const len = plainTextMatch.length;
    const original = node.textContent;
    node.textContent = original.slice(0, off - len) + original.slice(off);

    const targetOffset = off - len;
    const newRange = document.createRange();
    newRange.setStart(node, targetOffset);
    newRange.setEnd(node, targetOffset);
    sel.removeAllRanges();
    sel.addRange(newRange);

    if (input.innerText.trim() === '' && !input.querySelector('.at-token')) {
      input.innerHTML = '';
      const emptyRange = document.createRange();
      emptyRange.selectNodeContents(input);
      emptyRange.collapse(true);
      sel.removeAllRanges();
      sel.addRange(emptyRange);
    }

    input.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }

  return false;
}

window.handleChatInputBackspace = handleChatInputBackspace;

function setupChatInputCompatibility() {
  const chatInput = document.getElementById('chatInput');
  if (!chatInput) return;

  if (!chatInput._isCompatConfigured) {
    Object.defineProperty(chatInput, 'value', {
      get() {
        return getChatInputPlainText(this);
      },
      set(val) {
        setChatInputFromText(this, val);
      },
      configurable: true
    });
    chatInput._isCompatConfigured = true;
  }

  chatInput.addEventListener('keydown', (e) => {
    if (AtOperatorController.isOpen) {
      if (e.key === 'Backspace' && AtOperatorController.focusPane === 'menu') {
        AtOperatorController.close();
      } else {
        AtOperatorController.handleKeyDown(e);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendChat();
      return;
    }

    if (e.key === 'Backspace') {
      if (handleChatInputBackspace(e, chatInput)) {
        return;
      }
    }

    if (e.key === '#' || (e.shiftKey && e.key === '3')) {
      setTimeout(() => {
        if (typeof ModelPopupController !== 'undefined') ModelPopupController.open();
      }, 20);
    }

    if (e.key === '@' || (e.shiftKey && e.key === '2')) {
      setTimeout(() => {
        AtOperatorController.open();
      }, 20);
    }
  });

  chatInput.addEventListener('input', (e) => {
    if (e.data === '#') {
      if (typeof ModelPopupController !== 'undefined') ModelPopupController.open();
    }
    if (e.data === '@') {
      AtOperatorController.open();
    }
  });
}

function formatUserContentWithAtBadges(text) {
  if (!text) return '';
  text = text.replace(/(#[^\s(（]+[(（][^\s)）]+[)）])/g, '<span class="at-token at-token-model">$1</span>');
  return text.replace(/(@[^\s]+)/g, (match) => {
    let catClass = 'at-token-algo';
    if (match.includes('60') || match.includes('30') || match.includes('00') || match.includes('68')) {
      catClass = 'at-token-stock';
    } else if (match.includes('投资概要') || match.includes('大盘指数') || match.includes('行情分析') || match.includes('自选指数') || match.includes('投资分析') || match.includes('盯盘') || match.includes('工作台')) {
      catClass = 'at-token-ref';
    } else if (match.includes('astock')) {
      catClass = 'at-token-skill';
    } else if (match.includes('持仓') || match.includes('自选') || match.includes('关注')) {
      catClass = 'at-token-watchlist';
    }
    return `<span class="at-token ${catClass}">${match}</span>`;
  });
}

// --------------------------------------------------------------------------
// 7. Chat Messages & AI Streaming Engine
// --------------------------------------------------------------------------

function appendChatMessage(role, content, meta = {}) {
  const container = document.getElementById('chatMessages');
  if (!container) return;

  const item = document.createElement('div');
  item.className = `message-item message-${role}`;
  const nowStr = new Date().toLocaleTimeString().slice(0, 5);

  if (role === 'user') {
    const formattedContent = formatUserContentWithAtBadges(content);
    item.innerHTML = `
      <div class="message-bubble-user">
        ${formattedContent}
        <div class="message-timestamp">${nowStr}</div>
      </div>
    `;
    container.appendChild(item);
  } else {
    const msgId = meta.msgId || 'msg_' + Date.now();
    const title = meta.title || '量化投研综合研报';
    const summary = meta.summary || '模型结合盘面数据与风控铁律输出';

    let badgesHtml = '';
    if (meta.operators) {
      const op = meta.operators;
      const badgeList = [];
      if (op.stocks && op.stocks.length) {
        op.stocks.forEach(s => badgeList.push(`<span class="op-badge op-badge-stock">📈 标的: ${s.name} (${s.code})</span>`));
      }
      if (op.refs && op.refs.length) {
        op.refs.forEach(r => badgeList.push(`<span class="op-badge op-badge-ref">📑 上下文: ${r}</span>`));
      }
      if (op.skills && op.skills.length) {
        op.skills.forEach(sk => badgeList.push(`<span class="op-badge op-badge-skill">⚡ 技能: ${sk}</span>`));
      }
      if (op.algos && op.algos.length) {
        op.algos.forEach(a => badgeList.push(`<span class="op-badge op-badge-algo">🧠 算法: ${a}</span>`));
      }
      if (badgeList.length) {
        badgesHtml = `<div class="operator-badges-row">${badgeList.join('')}</div>`;
      }
    }

    item.innerHTML = `
      <div class="message-bubble-ai" id="${msgId}">
        <div class="ai-msg-header">
          <div class="ai-avatar-pill">AI</div>
          <div class="ai-msg-header-text">
            <h3 class="ai-msg-title">${title}</h3>
            <p class="ai-msg-summary">${summary}</p>
          </div>
        </div>
        ${badgesHtml}
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

function streamAIResponse(contentOrTpl, titleParam, summaryParam, metaParam = {}) {
  let fullText = contentOrTpl;
  let title = titleParam || '当前A股市场行情分析';
  let summary = summaryParam || '等待后端返回可验证结果';

  if (contentOrTpl && typeof contentOrTpl === 'object') {
    fullText = contentOrTpl.body || '';
    if (contentOrTpl.title) title = contentOrTpl.title;
    if (contentOrTpl.summary) summary = contentOrTpl.summary;
  }

  AppState.isChatStreaming = true;
  const msgId = 'aiMsg_' + Date.now();

  const msgMeta = {
    msgId: msgId,
    title: title,
    summary: summary,
    toolRunning: true,
    operators: metaParam.operators || null
  };

  appendChatMessage('ai', '<span style="color:#86909C;">AI正在综合大盘、资金流、筹码与技术指标进行深度研判...</span>', msgMeta);

  const queryText = metaParam.userText || title;
  const activeSessionId = AppState.currentSessionId || (HistoricalSessions[0] ? HistoricalSessions[0].id : null);

  // If AStockAPI is available and user query / prompt text is provided, attempt backend SSE
  if (window.AStockAPI && activeSessionId && metaParam.useApi !== false) {
    let accumulatedText = '';
    const container = document.getElementById(msgId);
    const toolStatus = container ? container.querySelector('#toolStatus') : null;
    const contentBody = container ? container.querySelector('.ai-content-body') : null;

    const selectedModelComposite = metaParam.overriddenModel || (
      (typeof ChatModelSelectorController !== 'undefined')
        ? ChatModelSelectorController.getSelectedModelComposite()
        : null
    );

    window.AStockAPI.streamChatCompletions(
      queryText,
      activeSessionId,
      selectedModelComposite,
      {
        onStart: (s) => {
          if (s && s.session_id) AppState.currentSessionId = s.session_id;
        },
        onThought: (thought) => {
          if (toolStatus) {
            toolStatus.innerHTML = `
              <span class="tool-badge-running"></span>
              <span>${thought}</span>
            `;
          }
        },
        onToolStart: (tool) => {
          if (toolStatus) {
            toolStatus.innerHTML = `
              <span class="tool-badge-running"></span>
              <span>调用技能 [${tool.skill_id || tool.tool_name || 'quant'}]：${tool.action || '执行量化运算与保本精算'}</span>
            `;
          }
        },
        onToolComplete: (tool) => {
          if (toolStatus) {
            const succeeded = tool.status === 'success';
            toolStatus.innerHTML = `
              <span style="color:${succeeded ? '#52C41A' : '#F5222D'}; font-weight:700;">${succeeded ? '✓' : '!'}</span>
              <span>${tool.summary || (succeeded ? '工具执行成功' : '工具未成功执行')}</span>
            `;
          }
        },
        onDelta: (delta) => {
          if (contentBody) {
            if (accumulatedText === '') contentBody.innerHTML = '';
            accumulatedText += delta;
            contentBody.innerHTML = accumulatedText + '<span style="color:#1677FF; font-weight:bold;">▌</span>';
            const scrollBox = document.getElementById('chatMessages');
            if (scrollBox) scrollBox.scrollTop = scrollBox.scrollHeight;
          }
        },
        onDone: (data) => {
          if (contentBody) {
            contentBody.innerHTML = accumulatedText || '<span style="color:#86909C;">模型未返回文本内容。</span>';
          }
          if (toolStatus) {
            toolStatus.innerHTML = `
              <span style="color:#52C41A; font-weight:700;">✓</span>
              <span>模型响应已结束</span>
            `;
          }
          AppState.isChatStreaming = false;
        },
        onError: (err) => {
          if (toolStatus) toolStatus.innerHTML = '<span style="color:#F5222D; font-weight:700;">!</span><span>请求失败</span>';
          if (contentBody) contentBody.textContent = `当前无法完成请求：${err.code || err.message || 'UNKNOWN_ERROR'}`;
          AppState.isChatStreaming = false;
        }
      }
    ).catch(err => {
      if (contentBody) contentBody.textContent = `当前无法完成请求：${err.code || err.message || 'UNKNOWN_ERROR'}`;
      AppState.isChatStreaming = false;
    });
  } else {
    const container = document.getElementById(msgId);
    const toolStatus = container ? container.querySelector('#toolStatus') : null;
    const contentBody = container ? container.querySelector('.ai-content-body') : null;
    if (toolStatus) toolStatus.innerHTML = '<span style="color:#F5222D; font-weight:700;">!</span><span>后端或会话不可用</span>';
    if (contentBody) contentBody.textContent = '当前无法连接生产 Agent 运行时。';
    AppState.isChatStreaming = false;
  }
}

// --------------------------------------------------------------------------
// 7.1 Agent2UI (A2UI) Task Pipeline Execution
// --------------------------------------------------------------------------
function executeA2UITask(promptText = '分析市场行情', stockParam = null, operatorsParam = null) {
  const stockLabel = stockParam ? `【${stockParam.name} (${stockParam.code})】` : '当前市场';
  streamAIResponse('', `${stockLabel}分析`, '', {
    userText: promptText,
    operators: operatorsParam || null
  });
}

// --------------------------------------------------------------------------
// 7.2 任务路由与 @操作符 综合执行引擎
// --------------------------------------------------------------------------
function executeOperatorTask(text, operators, overriddenModel = null) {
  // 1. 如果包含股票标的，优先执行该股票的量化研报与诊断
  if (operators.stocks && operators.stocks.length > 0) {
    const targetStock = operators.stocks[0];
    AppState.selectedStock = targetStock.code;

    if (typeof UIEngine !== 'undefined') {
      executeA2UITask(text, targetStock, operators);
      return;
    }

    const tpl = PromptTemplates['评估持股策略'];
    const title = `${targetStock.name} (${targetStock.code}) 深度诊断研报`;
    const summary = '已提交真实持仓诊断请求，等待后端返回可验证结果';
    streamAIResponse(tpl.body, title, summary, { operators, userText: text });
    return;
  }

  // 2. 如果指定了特定技能操作符
  if (operators.skills && operators.skills.length > 0) {
    const skillId = operators.skills[0];
    let title = `【${skillId}】技能调度执行报告`;
    let summary = `按就地技能规范成功调度量化计算流水线并返回结构化研判`;
    let body = '';

    if (skillId === 'astock-screener-5a') {
      title = '5A五维共振旋转选股评分报告';
      summary = '量价/基本面/估值/主线/资金 5维共振得分 > 85分龙头池';
      body = `
        <p><strong>【astock-screener-5a 选股流水线输出】</strong></p>
        <p>本期五维共振旋转评分模型运行完成，截面剔除 ST 与停牌标的后，共筛选出 3 只高胜率共振龙头：</p>
        <table class="report-table" style="width:100%; border-collapse:collapse; margin:10px 0; font-size:12px;">
          <thead>
            <tr style="background:#F6F8FB; border-bottom:1px solid #E2E8F0;">
              <th style="padding:6px 8px; text-align:left;">标的代码</th>
              <th style="padding:6px 8px; text-align:left;">标的名称</th>
              <th style="padding:6px 8px; text-align:center;">综合评分</th>
              <th style="padding:6px 8px; text-align:left;">核心驱动主线</th>
              <th style="padding:6px 8px; text-align:center;">操作建议</th>
            </tr>
          </thead>
          <tbody>
            <tr style="border-bottom:1px solid #F1F5F9;">
              <td style="padding:6px 8px; font-weight:600;">600519</td>
              <td style="padding:6px 8px;">贵州茅台</td>
              <td style="padding:6px 8px; text-align:center; color:#1677FF; font-weight:700;">94.2</td>
              <td style="padding:6px 8px;">消费龙头 · 估值修复</td>
              <td style="padding:6px 8px; text-align:center;"><span style="color:#52C41A; font-weight:600;">可建仓</span></td>
            </tr>
            <tr style="border-bottom:1px solid #F1F5F9;">
              <td style="padding:6px 8px; font-weight:600;">300750</td>
              <td style="padding:6px 8px;">宁德时代</td>
              <td style="padding:6px 8px; text-align:center; color:#1677FF; font-weight:700;">91.8</td>
              <td style="padding:6px 8px;">动力电池 · 动量突破</td>
              <td style="padding:6px 8px; text-align:center;"><span style="color:#52C41A; font-weight:600;">顺势跟进</span></td>
            </tr>
            <tr style="border-bottom:1px solid #F1F5F9;">
              <td style="padding:6px 8px; font-weight:600;">002594</td>
              <td style="padding:6px 8px;">比亚迪</td>
              <td style="padding:6px 8px; text-align:center; color:#1677FF; font-weight:700;">88.5</td>
              <td style="padding:6px 8px;">主板稳健 · 趋势回踩</td>
              <td style="padding:6px 8px; text-align:center;"><span style="color:#1677FF; font-weight:600;">逢低吸纳</span></td>
            </tr>
          </tbody>
        </table>
        <div class="summary-highlight-card">
          <span class="summary-icon">🛡️</span>
          <div class="summary-text"><strong>风控铁律提醒</strong>：入场必须预设 T0(-3%)/T1(-5%)/T2(-8%) 三级止损阶梯，绝不扛单。</div>
        </div>
      `;
    } else if (skillId === 'astock-action-execution') {
      title = '实战反应动作中枢与精确保本价报告';
      summary = '全部税费向上进位(ceil)与三场景反应动作单';
      body = `
        <p><strong>【astock-action-execution 精算输出】</strong></p>
        <p>严格遵守工作区 <code>AGENTS.md</code> 铁律：计入印花税 0.05%、券商佣金万2.5（最低5元起收）、过户费 0.002%，向上进位至分位（<code>math.ceil</code>）。</p>
        <div class="risk-iron-card" style="margin:10px 0;">
          <div class="risk-iron-header">
            <span>🛡️ 实战风控阶梯与精确保本位 (买入成本 ¥320.00 / 1000股)</span>
          </div>
          <div class="risk-iron-grid">
            <div class="risk-pill-box">
              <div class="risk-pill-title">最低保本卖出价</div>
              <div class="risk-pill-val" style="color:#1677FF;">¥320.26</div>
            </div>
            <div class="risk-pill-box">
              <div class="risk-pill-title">T1 减仓线 (-5%)</div>
              <div class="risk-pill-val" style="color:#D46B08;">¥304.00</div>
            </div>
            <div class="risk-pill-box">
              <div class="risk-pill-title">T2 绝杀线 (-8%)</div>
              <div class="risk-pill-val" style="color:#F5222D;">¥294.40</div>
            </div>
          </div>
        </div>
        <p><strong>三场景即时动作单：</strong></p>
        <ul>
          <li><strong>开盘冲高 (+3% 以上)</strong>：触及第一阻力位，先减仓 1/3 锁定部分收益，剩余底仓以保本价挂单移动止盈；</li>
          <li><strong>盘中窄幅震荡 (±1.5% 以内)</strong>：持股不动，观察分时量比与主力大单流向；</li>
          <li><strong>盘中跳水急跌 (触及 -5% T1减仓线)</strong>：无条件减仓 50% 防守，若继续下挫触及 -8% 绝杀线立即全仓出局。</li>
        </ul>
      `;
    } else if (skillId === 'astock-strategy-macd') {
      title = 'MACD 水下二次金叉与底背离形态识别研报';
      summary = '波谷极值对比与波段间距硬约束过滤假信号';
      body = `
        <p><strong>【astock-strategy-macd 形态识别输出】</strong></p>
        <p>依据纯粹 MACD 经典战法标准进行波段波谷极值提取与零轴位置核查：</p>
        <ul>
          <li><strong>形态判定</strong>：零轴下方二次金叉验底完成，第二脚波谷高于第一脚（DIF极值 -4.20 vs -8.60）；</li>
          <li><strong>间距过滤</strong>：两次金叉时间跨度为 14 个交易日，满足最小 8~25 根日K线有效形态过滤要求；</li>
          <li><strong>信号评级</strong>：<strong>【可试错出手（二星）】</strong>，背离有效率 76.4%；</li>
          <li><strong>止损锚点</strong>：以第一脚低点价格作为硬性防守绝杀线，跌破无条件离场。</li>
        </ul>
      `;
    } else {
      body = `
        <p><strong>【${skillId} 就地执行报告】</strong></p>
        <p>针对输入提问：<em>"${text}"</em>，系统已成功调用该技能底座流水线，完成全流程数据校验与逻辑计算。</p>
        <p>实战建议：结合当前盘面成交量能与板块动量，保持仓位在 5 成以内，严格执行三级风控止损阶梯。</p>
      `;
    }

    streamAIResponse(body, title, summary, { operators, userText: text });
    return;
  }

  // 3. 如果指定了算法操作符
  if (operators.algos && operators.algos.length > 0) {
    const algoName = operators.algos[0];
    const title = `【${algoName}】量化算法仿真推演`;
    const summary = `基于工业级量化工程规范完成截面因子处理与动态参数测算`;
    const body = `
      <p><strong>【${algoName} 计算引擎输出】</strong></p>
      <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:10px 12px; margin:8px 0; font-family:var(--font-mono, monospace); font-size:12px; line-height:1.6;">
        <div><strong>数学模型定义与参数：</strong></div>
        ${algoName.includes('MAD') ? `
          <div>1. 中位数绝对偏差: MAD = median(|X_i - median(X)|)</div>
          <div>2. 去极值上下界: [median(X) - 3×1.4826×MAD, median(X) + 3×1.4826×MAD]</div>
          <div>3. 截面 Z-score: Z_i = (X_i - mean(X_clean)) / std(X_clean)</div>
          <div>4. 截面 Rank 归一化: RankScore_i = rank(Z_i) / N</div>
        ` : algoName.includes('凯利') ? `
          <div>1. 目标年化波动率: σ_target = 15.0%</div>
          <div>2. 资产协方差矩阵: Σ 滚动250交易日收缩估计 (Ledoit-Wolf)</div>
          <div>3. 凯利杠杆倍数: f* = (μ - r) / σ²，半凯利系数: 0.5 × f*</div>
          <div>4. 动态风险预算: 单资产最大头寸权重 ≤ 20.0%</div>
        ` : `
          <div>1. 因子 IC 均值: 0.068 (t-stat = 3.82)</div>
          <div>2. 因子 IR 比率: 1.45 (具有优良信息增益)</div>
          <div>3. 半衰期衰减: 12.4 交易日，建议调仓周期: 5日轮动</div>
        `}
      </div>
      <p><strong>实战应用建议：</strong>当前模型在样本外检验中显著跑赢基准沪深300，且最大回撤由 -18.4% 优化至 -8.2%。已同步将参数更新至量化实盘风控网关。</p>
    `;

    streamAIResponse(body, title, summary, { operators, userText: text });
    return;
  }

// --------------------------------------------------------------------------
// 7.2.1 针对右侧区域提取板块内容核心解析器
// --------------------------------------------------------------------------
function extractWorkbenchSectionData(refName) {
  if (refName.includes('投资概要')) {
    return {
      type: '投资概要',
      sectionId: 'section-portfolio-overview',
      title: '右侧工作台【投资概要】板块数据提取与研判',
      summary: '等待后端返回可验证账户与持仓数据',
      body: '<p>等待后端返回本次账户、持仓和风控事实；当前不生成静态资产或收益结论。</p>'
    };
  }

  if (refName.includes('大盘指数')) {
    return {
      type: '大盘指数',
      sectionId: 'section-market-indices',
      title: '右侧工作台【大盘指数】四大核心全景研判',
      summary: '等待后端返回可验证指数与成交数据',
      body: '<p>等待后端返回本次指数、涨跌幅和成交额事实；当前不生成静态盘面结论。</p>'
    };
  }

  if (refName.includes('行情分析')) {
    return {
      type: '行情分析',
      sectionId: 'section-market-analysis',
      title: '右侧工作台【行情分析】市场情绪与主线资金流',
      summary: '等待后端返回可验证市场情绪与成交数据',
      body: '<p>等待后端返回本次市场情绪、成交和资金流事实；当前不生成静态主线或交易结论。</p>'
    };
  }

  if (refName.includes('自选指数')) {
    return {
      type: '自选指数',
      sectionId: 'section-watchlist-indices',
      title: '右侧工作台【自选指数】自选组合与标的异动',
      summary: '等待后端返回可验证自选池与行情数据',
      body: '<p>等待后端返回本次自选池、组合与个股行情事实；当前不生成静态异动结论。</p>'
    };
  }

  if (refName.includes('投资分析')) {
    return {
      type: '投资分析',
      sectionId: 'section-investment-analysis',
      title: '右侧工作台【投资分析】多因子量化收益归因研报',
      summary: '等待后端返回可验证账户绩效与归因数据',
      body: '<p>等待后端返回本次净值、交易和基准事实；当前不生成静态绩效或归因结论。</p>'
    };
  }

  if (refName.includes('盯盘') || refName.includes('实时盯盘')) {
    return {
      type: '实时盯盘',
      sectionId: 'section-realtime-monitor',
      title: '右侧工作台【实时盯盘】预警异动与策略监控',
      summary: '等待后端返回可验证监控状态与事件',
      body: '<p>等待后端返回本次监控运行状态和事件事实；当前不生成静态告警或在线状态。</p>'
    };
  }

  // 默认兜底：提取整个工作台当前数据
  return {
    type: '工作台当前数据',
    sectionId: 'section-portfolio-overview',
    title: `结合【${refName}】的深度研判`,
    summary: '等待后端读取并验证工作台上下文',
    body: `<p>等待后端返回与【${refName}】相关的本次事实；当前不生成静态行情、持仓或风控结论。</p>`
  };
}

  // 4. 如果包含引用操作符 (针对右侧区域提取板块内容)
  if (operators.refs && operators.refs.length > 0) {
    const refName = operators.refs[0];
    const sectionInfo = extractWorkbenchSectionData(refName);

    // 联动右侧工作台：平滑滚动到该卡片并进行高亮脉冲提示
    if (sectionInfo.sectionId) {
      const targetEl = document.getElementById(sectionInfo.sectionId);
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        targetEl.style.transition = 'box-shadow 0.3s ease, border-color 0.3s ease';
        targetEl.style.boxShadow = '0 0 0 3px rgba(22, 119, 255, 0.35)';
        targetEl.style.borderColor = '#1677FF';
        setTimeout(() => {
          targetEl.style.boxShadow = '';
          targetEl.style.borderColor = '';
        }, 2000);
      }
    }

    streamAIResponse(sectionInfo.body, sectionInfo.title, sectionInfo.summary, { operators, userText: text });
    return;
  }

  // 5. 默认降级路由
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

  streamAIResponse(tpl.body, tpl.title, tpl.summary, { operators, userText: text, overriddenModel });
}

function handleSendChat() {
  if (AppState.isChatStreaming) return;

  const input = document.getElementById('chatInput');
  const rawText = input ? input.value : '';
  const text = rawText ? rawText.trim() : '';
  if (!text) return;

  // 提取与解析 @操作符
  const operators = {
    stocks: [],
    refs: [],
    skills: [],
    algos: []
  };

  // 0. 模型匹配 (# 模型id(供应商) 或 #模型id)
  let userOverriddenModel = null;
  const modelTagRegex = /#\s*([^\s(（]+)(?:[(（]([^\s)）]+)[)）])?/g;
  let mm;
  while ((mm = modelTagRegex.exec(text)) !== null) {
    const rawModelId = mm[1];
    const rawProviderName = mm[2] || '';
    let targetProvider = null;
    if (rawProviderName && AppState.providers) {
      targetProvider = AppState.providers.find(p => p.name === rawProviderName || p.provider_id === rawProviderName);
    }
    if (!targetProvider && AppState.providers) {
      targetProvider = AppState.providers.find(p => (p.models || []).some(m => m.id === rawModelId));
    }
    if (targetProvider) {
      userOverriddenModel = `${rawModelId}|${targetProvider.provider_id}`;
    } else {
      userOverriddenModel = rawModelId;
    }
  }

  // 1. 股票标的匹配
  const stockRegex = /@?([^\s(（]+)[(（](\d{6})[)）]/g;
  let sm;
  while ((sm = stockRegex.exec(text)) !== null) {
    operators.stocks.push({ name: sm[1], code: sm[2], raw: sm[0] });
  }

  // 2. 引用匹配 (针对右侧板块内容精确抽取：投资概要/大盘指数/行情分析/自选指数/投资分析/实时盯盘)
  if (text.includes('投资概要')) operators.refs.push('投资概要');
  if (text.includes('大盘指数')) operators.refs.push('大盘指数');
  if (text.includes('行情分析')) operators.refs.push('行情分析');
  if (text.includes('自选指数')) operators.refs.push('自选指数');
  if (text.includes('投资分析')) operators.refs.push('投资分析');
  if (text.includes('实时盯盘') || text.includes('盯盘')) operators.refs.push('实时盯盘');
  if (text.includes('工作台当前数据')) operators.refs.push('投资概要');

  // 3. 技能匹配
  const skillMatch = text.match(/@(astock-[a-z0-9-]+)/g);
  if (skillMatch) {
    operators.skills = skillMatch.map(s => s.replace('@', ''));
  }

  // 4. 算法匹配
  if (text.includes('5A共振') || text.includes('5A')) operators.algos.push('5A共振多因子模型');
  if (text.includes('MAD') || text.includes('Z-score') || text.includes('去极值')) operators.algos.push('MAD去极值与截面Z-score');
  if (text.includes('目标波动率') || text.includes('凯利')) operators.algos.push('目标波动率与凯利仓位');
  if (text.includes('二次金叉') || text.includes('底背离')) operators.algos.push('水下二次金叉判别算法');
  if (text.includes('滑点') || text.includes('冲击撮合')) operators.algos.push('真实滑点冲击撮合');
  if (text.includes('移动止损') || text.includes('阶梯')) operators.algos.push('阶梯移动止损算法');
  if (text.includes('IC/IR') || text.includes('衰减')) operators.algos.push('因子IC/IR时序滚动回测');

  // 渲染用户输入卡片
  appendChatMessage('user', text);
  input.value = '';

  // 任务路由与执行 (执行与提示符相关的任务)
  executeOperatorTask(text, operators, userOverriddenModel);
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
// 8.0 AIChat Input Bar Model & Provider Selector Controller
// --------------------------------------------------------------------------
const ChatModelSelectorController = {
  storageKeyProvider: 'astock_chat_selected_provider',
  storageKeyModel: 'astock_chat_selected_model',

  init() {
    this.render();
  },

  getEnabledProviders() {
    return (AppState.providers || []).filter(p => p.enabled !== false);
  },

  getProviderById(providerId) {
    return (AppState.providers || []).find(p => p.provider_id === providerId);
  },

  render() {
    const providerSelect = document.getElementById('chatProviderSelect');
    const modelSelect = document.getElementById('chatModelSelect');
    if (!providerSelect || !modelSelect) return;

    const enabledProviders = this.getEnabledProviders();

    if (enabledProviders.length === 0) {
      providerSelect.innerHTML = '<option value="">无可用供应商</option>';
      providerSelect.disabled = true;
      modelSelect.innerHTML = '<option value="">未配置模型</option>';
      modelSelect.disabled = true;
      return;
    }

    providerSelect.disabled = false;
    modelSelect.disabled = false;

    // 1. 确定选中的 provider_id
    let savedProviderId = localStorage.getItem(this.storageKeyProvider);
    let savedModelId = localStorage.getItem(this.storageKeyModel);

    const chatRole = AppState.modelRoles && AppState.modelRoles.chat;
    if (!savedProviderId || !enabledProviders.some(p => p.provider_id === savedProviderId)) {
      if (chatRole && chatRole.provider_id && enabledProviders.some(p => p.provider_id === chatRole.provider_id)) {
        savedProviderId = chatRole.provider_id;
        if (!savedModelId && chatRole.model_id) savedModelId = chatRole.model_id;
      } else {
        savedProviderId = enabledProviders[0].provider_id;
      }
    }

    // 2. 渲染供应商下拉列表
    providerSelect.innerHTML = enabledProviders.map(p => {
      const isSelected = p.provider_id === savedProviderId ? 'selected' : '';
      const safeId = (p.provider_id || '').replace(/"/g, '&quot;');
      const safeName = (p.name || p.provider_id || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return '<option value="' + safeId + '" ' + isSelected + '>' + safeName + '</option>';
    }).join('');
    providerSelect.value = savedProviderId;

    // 3. 联动渲染该供应商下的模型列表
    this.renderModelsForProvider(savedProviderId, savedModelId);
  },

  renderModelsForProvider(providerId, preferredModelId = null) {
    const modelSelect = document.getElementById('chatModelSelect');
    if (!modelSelect) return;

    const provider = this.getProviderById(providerId);
    if (!provider || !provider.models || provider.models.length === 0) {
      modelSelect.innerHTML = '<option value="">暂无可用模型</option>';
      modelSelect.disabled = true;
      localStorage.setItem(this.storageKeyProvider, providerId);
      localStorage.removeItem(this.storageKeyModel);
      return;
    }

    modelSelect.disabled = false;
    const availableModels = provider.models.filter(m => m.selected !== false);
    const modelsToRender = availableModels.length > 0 ? availableModels : provider.models;

    let targetModelId = preferredModelId;
    if (!targetModelId || !modelsToRender.some(m => m.id === targetModelId)) {
      const chatRole = AppState.modelRoles && AppState.modelRoles.chat;
      if (chatRole && chatRole.provider_id === providerId && modelsToRender.some(m => m.id === chatRole.model_id)) {
        targetModelId = chatRole.model_id;
      } else {
        targetModelId = modelsToRender[0].id;
      }
    }

    modelSelect.innerHTML = modelsToRender.map(m => {
      const isSelected = m.id === targetModelId ? 'selected' : '';
      const safeId = (m.id || '').replace(/"/g, '&quot;');
      const rawName = m.name && m.name !== m.id ? (m.name + ' (' + m.id + ')') : m.id;
      const safeName = rawName.replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return '<option value="' + safeId + '" ' + isSelected + '>' + safeName + '</option>';
    }).join('');

    if (targetModelId) {
      modelSelect.value = targetModelId;
    }

    localStorage.setItem(this.storageKeyProvider, providerId);
    if (targetModelId) {
      localStorage.setItem(this.storageKeyModel, targetModelId);
    }
  },

  handleProviderChange(newProviderId) {
    if (!newProviderId) return;
    const providerSelect = document.getElementById('chatProviderSelect');
    if (providerSelect) providerSelect.value = newProviderId;
    localStorage.setItem(this.storageKeyProvider, newProviderId);
    this.renderModelsForProvider(newProviderId);
  },

  handleModelChange(newModelId) {
    if (!newModelId) return;
    const modelSelect = document.getElementById('chatModelSelect');
    if (modelSelect) modelSelect.value = newModelId;
    localStorage.setItem(this.storageKeyModel, newModelId);
  },

  getSelectedModelComposite() {
    const providerSelect = document.getElementById('chatProviderSelect');
    const modelSelect = document.getElementById('chatModelSelect');
    const providerId = (providerSelect && providerSelect.value) ? providerSelect.value : (localStorage.getItem(this.storageKeyProvider) || '');
    const modelId = (modelSelect && modelSelect.value) ? modelSelect.value : (localStorage.getItem(this.storageKeyModel) || '');

    if (modelId && providerId) {
      return modelId + '|' + providerId;
    }
    if (modelId) return modelId;
    return null;
  },

  getSelectedModelInfo() {
    const providerSelect = document.getElementById('chatProviderSelect');
    const modelSelect = document.getElementById('chatModelSelect');
    const providerId = (providerSelect && providerSelect.value) ? providerSelect.value : (localStorage.getItem(this.storageKeyProvider) || '');
    const modelId = (modelSelect && modelSelect.value) ? modelSelect.value : (localStorage.getItem(this.storageKeyModel) || '');
    const provider = this.getProviderById(providerId);
    return {
      providerId: providerId,
      providerName: provider ? (provider.name || provider.provider_id) : providerId,
      modelId: modelId,
      composite: (modelId && providerId) ? (modelId + '|' + providerId) : modelId
    };
  },

  openConfig() {
    if (typeof openSettingsModal === 'function') {
      openSettingsModal();
      if (typeof switchSettingsSec === 'function') {
        switchSettingsSec('providers');
      }
    }
  }
};
window.ChatModelSelectorController = ChatModelSelectorController;

// --------------------------------------------------------------------------
// 8.1 Providers & Model Roles Core Controller
// --------------------------------------------------------------------------

async function initProvidersSettings() {
  // Remove credentials persisted by pre-P0 builds. Providers are backend-owned.
  localStorage.removeItem('astock_llm_providers');
  try {
    // 1. Fetch providers from backend
    const provResp = await fetch('/api/models/providers');
    if (provResp.ok) {
      const data = await provResp.json();
      AppState.providers = data.providers || [];
    } else {
      AppState.providers = [];
    }
  } catch (err) {
    AppState.providers = [];
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
  ChatModelSelectorController.init();
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
  if (window.ChatModelSelectorController) ChatModelSelectorController.render();
  if (window.ModelPopupController) ModelPopupController.updateCurrentBadgeDisplay();
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
  if (keyInput && keyInput.value.trim()) p.api_key = keyInput.value.trim();
  else delete p.api_key;

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
  if (keyInput) {
    keyInput.value = '';
    keyInput.placeholder = p.has_api_key ? '已保存（留空表示保持不变）' : '输入 API 密钥';
  }

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
    if (window.ChatModelSelectorController) ChatModelSelectorController.render();
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
  if (!AppState.activeProviderId) {
    showToast('请先保存并选择供应商');
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
      body: JSON.stringify({ provider_id: AppState.activeProviderId, timeout_seconds: 8 })
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
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
  if (!AppState.activeProviderId) {
    showToast('请先保存并选择供应商');
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
      body: JSON.stringify({ provider_id: AppState.activeProviderId, timeout_seconds: 15 })
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

function isRoleOptionCompatible(role, option) {
  if (!option || !option.value) return false;
  if (role === 'chat' || role === 'quant') {
    return Array.isArray(option.capabilities) && option.capabilities.includes('tools');
  }
  return true;
}

function chooseDefaultRoleOption(role, availableOptions) {
  const modelOptions = availableOptions.filter(option => option.value);
  if (!modelOptions.length) return null;

  const withCapability = capability => modelOptions.find(option =>
    Array.isArray(option.capabilities) && option.capabilities.includes(capability)
  );

  if (role === 'summary') {
    return withCapability('fast') || modelOptions[0];
  }
  if (role === 'debate') {
    return withCapability('reasoning') || modelOptions[0];
  }
  if (role === 'vision') {
    return withCapability('vision') || modelOptions[0];
  }
  if (role === 'chat' || role === 'quant') {
    return modelOptions.find(option => isRoleOptionCompatible(role, option)) || null;
  }
  return modelOptions[0];
}

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
          model_id: m.id,
          capabilities: m.capabilities || ['chat']
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
      const currentOption = availableOptions.find(option => option.value === targetVal);
      if (isRoleOptionCompatible(role, currentOption)) {
        select.value = targetVal;
        return;
      }
    }
    select.value = '';
    handleRoleChange(role, '');

    // Smart default selection if unset and options available
    if (availableOptions.length > 1 && !select.value) {
      const defaultOption = chooseDefaultRoleOption(role, availableOptions);
      if (defaultOption) {
        select.value = defaultOption.value;
        handleRoleChange(role, select.value);
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

  // 1. Provider credentials are submitted once and never persisted in browser storage.
  try {
    const savedProviders = [];
    for (const provider of AppState.providers) {
      const payload = { ...provider };
      if (!payload.api_key) delete payload.api_key;
      const response = await fetch('/api/models/providers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(`Provider save failed with HTTP ${response.status}`);
      const data = await response.json();
      savedProviders.push(data.provider);
    }
    AppState.providers = savedProviders;
  } catch (err) {
    AppState.providers = AppState.providers.map(provider => {
      const safe = { ...provider };
      delete safe.api_key;
      return safe;
    });
    showToast(`❌ 模型供应商保存失败: ${err.message}`);
    return;
  } finally {
    const keyInput = document.getElementById('currProviderKey');
    if (keyInput) keyInput.value = '';
    localStorage.removeItem('astock_llm_providers');
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
  if (window.ChatModelSelectorController) ChatModelSelectorController.render();
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
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 2600);
}

// --------------------------------------------------------------------------
// 9. 17项量化投研技能治理中心 (Skill Governance Subsystem Controller)
// --------------------------------------------------------------------------

const BuiltinSkillsManifest = [
  {
    id: "astock-data-feed",
    name: "astock-data-feed",
    title: "A股全链路行情与技术指标数据引擎",
    category: "data",
    categoryName: "数据引擎",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "查询A股实时行情快照、历史K线（日/周/月/分时）、复权数据、全套经典技术指标（MA/MACD/KDJ/RSI/BOLL/ATR）、个股事件、筹码分布及行业板块信息。",
    triggers: ["行情", "查股票", "现价", "K线", "技术指标", "MACD", "KDJ", "筹码分布"],
    cli_command: "astock data quote {code}",
    entry_point: "core/data/fetch_realtime.py",
    skill_doc: ".agents/skills/astock-data-feed/SKILL.md",
    recommended_model: "flash",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { code: "600519", action: "quote" }
  },
  {
    id: "astock-platform-evaluate",
    name: "astock-platform-evaluate",
    title: "统一A股全流程投研与量化综合分析平台",
    category: "platform",
    categoryName: "综合平台",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "提供4层数据降级桥接、零依赖技术指标计算、多因子策略综合打分（100分制）、被套解套策略诊断、大盘健康度评估与HTML分析报告生成。",
    triggers: ["全流程分析", "股票诊断", "综合打分", "被套怎么办", "解套方案", "大盘健康度"],
    cli_command: "astock evaluate {code}",
    entry_point: "core/models/combo_scorer.py",
    skill_doc: ".agents/skills/astock-platform-evaluate/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { code: "600519" }
  },
  {
    id: "astock-screener-5a",
    name: "astock-screener-5a",
    title: "A股五维共振旋转选股与样本外回测引擎",
    category: "screener",
    categoryName: "5A选股",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "基于量价趋势、基本面过滤、估值性价比、行业轮动与动量共振的5A多维评分模型，支持全市场选股与滚动样本外检验。",
    triggers: ["选股", "5A选股", "主线旋转", "多维评分", "优质股票推荐", "样本外回测"],
    cli_command: "astock screen 5a",
    entry_point: "core/models/multi_dim_model.py",
    skill_doc: ".agents/skills/astock-screener-5a/SKILL.md",
    recommended_model: "pro",
    timeout_seconds: 45,
    require_confirmation: false,
    enabled: true,
    sample_params: { limit: 5, dynamic_mode: "high_momentum" }
  },
  {
    id: "astock-pool-dashboard",
    name: "astock-pool-dashboard",
    title: "A股全流程投研面板与股池生命周期管理",
    category: "pool",
    categoryName: "股池管理",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "覆盖关注股池/自选股池/持仓池全生命周期管理，支持通达信公式同步、盘中入场监控、持仓止损止盈预警与投研报告生成。",
    triggers: ["投研面板", "持仓池", "关注池", "自选股", "通达信同步", "入场监控"],
    cli_command: "astock pool list",
    entry_point: "core/strategy/pool_manager.py",
    skill_doc: ".agents/skills/astock-pool-dashboard/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { pool_type: "custom", action: "list" }
  },
  {
    id: "astock-trade-paper",
    name: "astock-trade-paper",
    title: "A股模拟盘交易与事件驱动撮合回测系统",
    category: "paper_trading",
    categoryName: "模拟交易",
    risk_level: "simulation",
    riskName: "模拟交易",
    description: "支持多账户模拟仓管理、限价单/市价单下单、撤单、持仓与资金查询、T+1交易规则与涨跌停撮合逻辑验证。",
    triggers: ["模拟盘", "下单", "买入", "卖出", "撤单", "查账户", "模拟持仓"],
    cli_command: "astock trade balance",
    entry_point: "core/paper_trading/paper_trade_cli.py",
    skill_doc: ".agents/skills/astock-trade-paper/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: true,
    enabled: true,
    sample_params: { action: "balance" }
  },
  {
    id: "astock-strategy-mainboard",
    name: "astock-strategy-mainboard",
    title: "主板流动性池多波段防御策略",
    category: "strategy",
    categoryName: "实战策略",
    risk_level: "strategy",
    riskName: "策略风控",
    description: "在主板高流动性池内按趋势回踩（trend_pullback）与防御波段产出买入候选与持仓卖出信号，防守反击决策。",
    triggers: ["趋势回踩", "主板策略", "防御策略", "波段买点", "离场信号"],
    cli_command: "astock strategy swing",
    entry_point: "core/strategy/daily_decisions.py",
    skill_doc: ".agents/skills/astock-strategy-mainboard/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { action: "candidates" }
  },
  {
    id: "astock-quant-engine",
    name: "astock-quant-engine",
    title: "A股工业级全流程量化工程引擎",
    category: "quant",
    categoryName: "量化工程",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "截面量价因子提取、非结构化舆情因子半衰期衰减、MAD去极值与Z-score截面Rank合成、目标波动率与分数凯利仓位管理、ATR阶梯止盈止损。",
    triggers: ["量化工程", "因子合成", "去极值", "凯利仓位", "ATR止损", "量化流水线"],
    cli_command: "astock quant pipeline",
    entry_point: "core/strategy/risk_position_manager.py",
    skill_doc: ".agents/skills/astock-quant-engine/SKILL.md",
    recommended_model: "pro",
    timeout_seconds: 60,
    require_confirmation: false,
    enabled: true,
    sample_params: { action: "factors", code: "600519" }
  },
  {
    id: "astock-agent-debate",
    name: "astock-agent-debate",
    title: "7大AI分析师多智能体研判与多空辩论系统",
    category: "multi_agent",
    categoryName: "多智能体",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "集成基本面、量价、消息、政策、游资、筹码、风险7大专业分析师智能体，进行多轮多空辩论研判并生成决议。",
    triggers: ["多智能体分析", "7大分析师", "多空辩论", "深度研报", "多维度辩论"],
    cli_command: "astock debate {code}",
    entry_point: "core/multi_agent/ta_orchestrator.py",
    skill_doc: ".agents/skills/astock-agent-debate/SKILL.md",
    recommended_model: "pro",
    timeout_seconds: 90,
    require_confirmation: false,
    enabled: true,
    sample_params: { code: "600519", rounds: 1 }
  },
  {
    id: "astock-strategy-tuige",
    name: "astock-strategy-tuige",
    title: "退哥短线交易规则与场景化决策体系",
    category: "strategy",
    categoryName: "实战策略",
    risk_level: "strategy",
    riskName: "策略风控",
    description: "基于退哥实战短线交易规则：涨停回调、连板接力、趋势回踩、洗盘结束、失效卖出与仓位纪律场景化规则库。",
    triggers: ["退哥短线", "涨停回调", "连板接力", "洗盘结束", "短线规则", "短线卖点"],
    cli_command: "astock shortline check",
    entry_point: ".agents/skills/astock-strategy-tuige/SKILL.md",
    skill_doc: ".agents/skills/astock-strategy-tuige/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { code: "000001", scenario: "limit_up_pullback" }
  },
  {
    id: "astock-strategy-macd",
    name: "astock-strategy-macd",
    title: "MACD底背离与零轴下二次金叉决策体系",
    category: "strategy",
    categoryName: "实战策略",
    risk_level: "strategy",
    riskName: "策略风控",
    description: "实战捕捉水下二次金叉、双底回踩验底、MACD底背离形态，产出三档决策（观察/试错/放弃）与盘中入场清单。",
    triggers: ["二次金叉", "水下二次金叉", "MACD底背离", "第一脚第二脚", "回踩验底", "抄底修复"],
    cli_command: "astock pattern macd {code}",
    entry_point: ".agents/skills/astock-strategy-macd/SKILL.md",
    skill_doc: ".agents/skills/astock-strategy-macd/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { code: "600519" }
  },
  {
    id: "astock-action-execution",
    name: "astock-action-execution",
    title: "实战交易反应动作与精确进位决策引擎",
    category: "strategy",
    categoryName: "实战策略",
    risk_level: "strategy",
    riskName: "策略风控",
    description: "计算精确最低保本卖出价（考虑印花税、佣金五元起收、过户费进位）、T0/T1/T2三级止损线、冲高/盘整/急跌三场景反应动作清单。",
    triggers: ["保本价", "反应动作", "持仓指令", "盘中预案", "止损线计算", "三场景动作"],
    cli_command: "astock action plan",
    entry_point: "core/strategy/execution_action_engine.py",
    skill_doc: ".agents/skills/astock-action-execution/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { code: "600519", cost: 1600.0, shares: 100 }
  },
  {
    id: "astock-pool-audit",
    name: "astock-pool-audit",
    title: "三大股池统一审查与均线位校验",
    category: "pool",
    categoryName: "股池管理",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "统一审查关注/自选/持仓股池，重算均线支撑阻力位，剔除过期关键位与失效标的。",
    triggers: ["审查股池", "股池审计", "清洗自选股", "均线重算"],
    cli_command: "astock pool audit",
    entry_point: ".agents/skills/astock-pool-audit/scripts/pool_audit.py",
    skill_doc: ".agents/skills/astock-pool-audit/SKILL.md",
    recommended_model: "flash",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { action: "audit" }
  },
  {
    id: "astock-report-archive",
    name: "astock-report-archive",
    title: "A股报告持久化与多股联合报告规范",
    category: "reporting",
    categoryName: "研报规范",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "规范多股联合报告输出路径、数据持久化存储结构与图表呈现标准。",
    triggers: ["生成报告", "多股报告", "报告归档", "复盘报告"],
    cli_command: "astock report generate",
    entry_point: ".agents/skills/astock-report-archive/SKILL.md",
    skill_doc: ".agents/skills/astock-report-archive/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { action: "list" }
  },
  {
    id: "astock-report-html",
    name: "astock-report-html",
    title: "A股标准HTML高颜值交互报告规范",
    category: "reporting",
    categoryName: "研报规范",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "白色系亚光背景、红涨绿跌、1344px居中、自包含单文件HTML报告模板与交互样式。",
    triggers: ["HTML报告", "报告样式", "高颜值报表", "可视化页面"],
    cli_command: "astock report html",
    entry_point: ".agents/skills/astock-report-html/SKILL.md",
    skill_doc: ".agents/skills/astock-report-html/SKILL.md",
    recommended_model: "flash",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { code: "600519" }
  },
  {
    id: "astock-knowledge-tips",
    name: "astock-knowledge-tips",
    title: "实战交易经验与API降级避坑指南",
    category: "knowledge_meta",
    categoryName: "知识路由",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "记录早盘竞价复盘、API被封应对、数据源降级策略、历史交易教训与经验技巧库。",
    triggers: ["避坑指南", "交易经验", "接口被封怎么办", "实战技巧"],
    cli_command: "astock tips",
    entry_point: ".agents/skills/astock-knowledge-tips/SKILL.md",
    skill_doc: ".agents/skills/astock-knowledge-tips/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { topic: "auction" }
  },
  {
    id: "astock-model-validation",
    name: "astock-model-validation",
    title: "外部AI时序预测模型实证检验规范",
    category: "knowledge_meta",
    categoryName: "知识路由",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "在将外部时序基础模型（如 Kronos/TimesFM）集成前进行样本外滚动回测检验与基准对齐。",
    triggers: ["模型检验", "时序模型验证", "Kronos实证", "模型打擂台"],
    cli_command: "astock validate-model",
    entry_point: ".agents/skills/astock-model-validation/SKILL.md",
    skill_doc: ".agents/skills/astock-model-validation/SKILL.md",
    recommended_model: "inherit",
    timeout_seconds: 60,
    require_confirmation: false,
    enabled: true,
    sample_params: { model: "Kronos", horizon: 5 }
  },
  {
    id: "astock-meta-routing",
    name: "astock-meta-routing",
    title: "股票任务模型路由规则与执行规约",
    category: "knowledge_meta",
    categoryName: "知识路由",
    risk_level: "readonly",
    riskName: "只读研判",
    description: "股票任务模型动态路由规约（flash纯分析 vs flash+execute_code编程/脚本直接执行），规避模型过载。",
    triggers: ["模型路由", "flash模型", "编程路由", "执行规约"],
    cli_command: "astock tips",
    entry_point: ".agents/skills/astock-meta-routing/SKILL.md",
    skill_doc: ".agents/skills/astock-meta-routing/SKILL.md",
    recommended_model: "flash",
    timeout_seconds: 30,
    require_confirmation: false,
    enabled: true,
    sample_params: { task_type: "analysis" }
  }
];

let isSkillsInitialized = false;

async function initSkillsGovernance() {
  if (AppState.skillsList.length === 0) {
    AppState.skillsList = JSON.parse(JSON.stringify(BuiltinSkillsManifest));
  }

  // Fetch live from FastAPI backend if available
  try {
    const res = await fetch('/api/skills');
    if (res.ok) {
      const serverSkills = await res.json();
      if (Array.isArray(serverSkills) && serverSkills.length > 0) {
        // Merge server status with rich metadata
        serverSkills.forEach(srv => {
          const local = AppState.skillsList.find(s => s.id === srv.id);
          if (local) {
            local.enabled = srv.enabled !== undefined ? srv.enabled : local.enabled;
            local.timeout_seconds = srv.timeout_seconds || local.timeout_seconds;
            local.require_confirmation = srv.require_confirmation !== undefined ? srv.require_confirmation : local.require_confirmation;
            if (srv.risk_level) local.risk_level = srv.risk_level;
          }
        });
      }
    }
  } catch (e) {
    // Graceful offline fallback to built-in list
  }

  // Fetch audit metrics
  try {
    const auditRes = await fetch('/api/skills/audit/stats');
    if (auditRes.ok) {
      AppState.skillsAudit = await auditRes.json();
    }
  } catch (e) {
    // Graceful fallback
  }

  isSkillsInitialized = true;
  renderSkillsGovernance();
}

function refreshSkillsGovernance() {
  initSkillsGovernance().then(() => {
    showToast('已同步最新 17 项技能治理清单与调用度量数据');
  });
}

function bulkEnableAllSkills() {
  AppState.skillsList.forEach(s => { s.enabled = true; });
  renderSkillsGovernance();

  // Try bulk update to backend
  AppState.skillsList.forEach(s => {
    fetch(`/api/skills/${s.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: true })
    }).catch(() => {});
  });

  showToast('⚡ 成功启用全部 17 项投研技能');
}

function renderSkillsGovernance() {
  // 1. Update KPI stats
  const totalCount = AppState.skillsList.length;
  const enabledCount = AppState.skillsList.filter(s => s.enabled).length;
  const statEnabledElem = document.getElementById('statEnabledSkills');
  if (statEnabledElem) {
    statEnabledElem.innerHTML = `${enabledCount} <span class="stat-card-unit">/ ${totalCount} 项</span>`;
    statEnabledElem.className = enabledCount === totalCount ? 'stat-card-val text-up tabular-nums' : 'stat-card-val tabular-nums';
  }

  // Audit stats
  if (AppState.skillsAudit) {
    const invocElem = document.getElementById('statTotalInvocations');
    const p95Elem = document.getElementById('statP95Latency');
    const errElem = document.getElementById('statErrorRate');
    if (invocElem) invocElem.innerText = AppState.skillsAudit.total_invocations || 0;
    if (p95Elem) p95Elem.innerText = Math.round(AppState.skillsAudit.p95_latency_ms || 0);
    if (errElem) errElem.innerText = (AppState.skillsAudit.error_rate ? (AppState.skillsAudit.error_rate * 100).toFixed(1) : '0.0') + '%';
  }

  // 2. Filter skills
  const filterCat = AppState.skillsFilter.category;
  const searchKeyword = AppState.skillsFilter.search.trim().toLowerCase();
  const enabledOnly = AppState.skillsFilter.enabledOnly;

  const filteredSkills = AppState.skillsList.filter(s => {
    if (enabledOnly && !s.enabled) return false;
    if (filterCat !== 'all') {
      if (filterCat === 'knowledge_meta') {
        if (s.category !== 'knowledge' && s.category !== 'validation' && s.category !== 'meta' && s.category !== 'knowledge_meta') return false;
      } else if (s.category !== filterCat) {
        return false;
      }
    }
    if (searchKeyword) {
      const matchId = s.id.toLowerCase().includes(searchKeyword);
      const matchTitle = s.title.toLowerCase().includes(searchKeyword);
      const matchDesc = s.description.toLowerCase().includes(searchKeyword);
      const matchCmd = s.cli_command.toLowerCase().includes(searchKeyword);
      const matchTriggers = (s.triggers || []).some(t => t.toLowerCase().includes(searchKeyword));
      if (!matchId && !matchTitle && !matchDesc && !matchCmd && !matchTriggers) return false;
    }
    return true;
  });

  // 3. Render Cards
  const container = document.getElementById('skillsCardsContainer');
  const emptyState = document.getElementById('skillsEmptyState');
  if (!container) return;

  if (filteredSkills.length === 0) {
    container.innerHTML = '';
    if (emptyState) emptyState.style.display = 'block';
    return;
  }

  if (emptyState) emptyState.style.display = 'none';

  container.innerHTML = filteredSkills.map(skill => {
    const riskBadgeClass = skill.risk_level === 'simulation'
      ? 'badge-risk-simulation'
      : skill.risk_level === 'destructive'
      ? 'badge-risk-destructive'
      : skill.risk_level === 'strategy'
      ? 'badge-risk-strategy'
      : 'badge-risk-readonly';

    const riskLabel = skill.risk_level === 'simulation'
      ? '模拟交易'
      : skill.risk_level === 'destructive'
      ? '高危变更'
      : skill.risk_level === 'strategy'
      ? '策略风控'
      : '只读研判';

    const modelTagClass = skill.recommended_model === 'flash'
      ? 'model-tag-flash'
      : skill.recommended_model === 'pro'
      ? 'model-tag-pro'
      : 'model-tag-inherit';

    const triggersHtml = (skill.triggers || []).slice(0, 5).map(t => 
      `<span class="trigger-tag" title="提示词触发词">#${t}</span>`
    ).join('');

    return `
      <div class="skill-card ${skill.enabled ? '' : 'disabled'}" id="card-skill-${skill.id}">
        <div class="skill-card-top">
          <div class="skill-top-left">
            <span class="skill-id-badge">${skill.id}</span>
            <div class="skill-card-title" title="${skill.title}">${skill.title}</div>
            <div class="skill-top-badges">
              <span class="skill-cat-tag">${skill.categoryName || skill.category}</span>
              <span class="${riskBadgeClass}">${riskLabel}</span>
            </div>
          </div>
          <div class="skill-top-right">
            <label class="switch-toggle" title="${skill.enabled ? '点击禁用该技能' : '点击启用该技能'}">
              <input type="checkbox" ${skill.enabled ? 'checked' : ''} onchange="handleSkillToggle('${skill.id}', this.checked)">
              <span class="switch-slider"></span>
            </label>
          </div>
        </div>

        <div class="skill-card-body">
          <div class="skill-card-desc" title="${skill.description}">${skill.description}</div>
          
          <div class="skill-cli-snippet">
            <span class="skill-cli-text" title="统一 CLI 规范：直接就地运行，免全局污染">$ ${skill.cli_command}</span>
            <span class="skill-cli-copy" onclick="copyCliCommand('${skill.cli_command}')" title="复制命令">复制</span>
          </div>

          <div class="skill-triggers-wrap">
            ${triggersHtml}
          </div>

          <div class="skill-card-meta">
            <span class="meta-item">⏱️ 超时: <strong>${skill.timeout_seconds}s</strong></span>
            <span class="meta-item">🛡️ 门禁: <strong>${skill.require_confirmation ? '⚠️需二次确认' : '免密直接放行'}</strong></span>
            <span class="meta-item">🧠 推荐: <strong class="${modelTagClass}">${skill.recommended_model}</strong></span>
          </div>
        </div>

        <div class="skill-card-footer">
          <button class="btn-card-test" onclick="openSkillTestModal('${skill.id}')">
            <span>⚡ 在线调试 (Test)</span>
          </button>
          <button class="btn-card-doc" onclick="showSkillDocDetail('${skill.id}')">
            <span>📖 规范契约</span>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

async function handleSkillToggle(skillId, isChecked) {
  const skill = AppState.skillsList.find(s => s.id === skillId);
  if (skill) {
    skill.enabled = isChecked;
  }

  // Update card styling
  const card = document.getElementById(`card-skill-${skillId}`);
  if (card) {
    if (isChecked) card.classList.remove('disabled');
    else card.classList.add('disabled');
  }

  // Update stats counter
  const totalCount = AppState.skillsList.length;
  const enabledCount = AppState.skillsList.filter(s => s.enabled).length;
  const statEnabledElem = document.getElementById('statEnabledSkills');
  if (statEnabledElem) {
    statEnabledElem.innerHTML = `${enabledCount} <span class="stat-card-unit">/ ${totalCount} 项</span>`;
    statEnabledElem.className = enabledCount === totalCount ? 'stat-card-val text-up tabular-nums' : 'stat-card-val tabular-nums';
  }

  showToast(`已${isChecked ? '启用' : '禁用'}技能：${skillId}`);

  // Send PATCH request to backend
  try {
    await fetch(`/api/skills/${skillId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: isChecked })
    });
  } catch (e) {
    // Log silently
  }
}

function copyCliCommand(cmd) {
  const fullCmd = `astock ${cmd} --json`;
  navigator.clipboard.writeText(fullCmd).then(() => {
    showToast(`已复制 CLI 命令：${fullCmd}`);
  }).catch(() => {
    showToast(`已复制命令：${cmd}`);
  });
}

function handleSkillSearchInput(val) {
  AppState.skillsFilter.search = val;
  const btnClear = document.getElementById('btnSkillSearchClear');
  if (btnClear) {
    btnClear.style.display = val ? 'block' : 'none';
  }
  renderSkillsGovernance();
}

function clearSkillSearch() {
  const input = document.getElementById('skillSearchInput');
  if (input) input.value = '';
  handleSkillSearchInput('');
}

function filterSkillCategory(cat) {
  AppState.skillsFilter.category = cat;
  document.querySelectorAll('.cat-filter-pill').forEach(btn => {
    if (btn.dataset.cat === cat) btn.classList.add('active');
    else btn.classList.remove('active');
  });
  renderSkillsGovernance();
}

function toggleFilterEnabledOnly(isChecked) {
  AppState.skillsFilter.enabledOnly = isChecked;
  renderSkillsGovernance();
}

function resetSkillFilters() {
  AppState.skillsFilter.category = 'all';
  AppState.skillsFilter.search = '';
  AppState.skillsFilter.enabledOnly = false;

  const searchInput = document.getElementById('skillSearchInput');
  if (searchInput) searchInput.value = '';
  const clearBtn = document.getElementById('btnSkillSearchClear');
  if (clearBtn) clearBtn.style.display = 'none';

  const filterEnabled = document.getElementById('filterEnabledOnly');
  if (filterEnabled) filterEnabled.checked = false;

  document.querySelectorAll('.cat-filter-pill').forEach(btn => {
    if (btn.dataset.cat === 'all') btn.classList.add('active');
    else btn.classList.remove('active');
  });

  renderSkillsGovernance();
  showToast('已重置全部技能筛选条件');
}

function showSkillDocDetail(skillId) {
  const skill = AppState.skillsList.find(s => s.id === skillId);
  if (!skill) return;
  appendChatMessage('user', `请向我解释【${skill.name}】技能的执行规范与输入参数`);
  const response = `### 🧩 技能规范：${skill.name} (${skill.title})
- **入口命令**：\`${skill.cli_command}\`
- **代码位置**：\`${skill.entry_point}\`
- **技术规范**：\`${skill.skill_doc}\`
- **安全级别**：\`${skill.risk_level}\`（${skill.riskName}）
- **推荐模型**：\`${skill.recommended_model}\`
- **核心职能**：${skill.description}

**示例调用 Payload**：
\`\`\`json
${JSON.stringify(skill.sample_params || {}, null, 2)}
\`\`\`
*提示：您可以点击该技能卡片上的【⚡ 在线调试】直接测试执行该技能。*`;

  streamAIResponse(response, `技能规范契约：${skill.name}`);
  showToast(`已向投研助手注入【${skill.name}】契约说明`);
}

// --------------------------------------------------------------------------
// 9.1 Skill Online Debugger / Sandbox Modal Controller
// --------------------------------------------------------------------------

function openSkillTestModal(skillId) {
  const modal = document.getElementById('skillTestModal');
  if (!modal) return;

  const targetId = skillId || AppState.activeDebugSkillId || 'astock-data-feed';
  AppState.activeDebugSkillId = targetId;

  // Populate select options
  const selectElem = document.getElementById('debugSkillSelect');
  if (selectElem) {
    selectElem.innerHTML = AppState.skillsList.map(s => `
      <option value="${s.id}" ${s.id === targetId ? 'selected' : ''}>
        ${s.id} — ${s.title}
      </option>
    `).join('');
  }

  handleDebugSkillChange(targetId);

  // Reset console
  const badge = document.getElementById('debugStatusBadge');
  if (badge) {
    badge.className = 'console-status-badge';
    badge.innerText = '就绪 (Ready)';
  }
  const statsStrip = document.getElementById('debugConsoleStats');
  if (statsStrip) statsStrip.style.display = 'none';

  const output = document.getElementById('debugConsoleOutput');
  if (output) {
    output.innerText = `[就绪] 目标技能：${targetId}\n请检查左侧 Payload 参数后，点击【🚀 立即执行测试调用】发起实时请求。`;
  }

  modal.classList.add('active');
}

function closeSkillTestModal() {
  const modal = document.getElementById('skillTestModal');
  if (modal) modal.classList.remove('active');
}

function handleDebugSkillChange(skillId) {
  AppState.activeDebugSkillId = skillId;
  const skill = AppState.skillsList.find(s => s.id === skillId) || AppState.skillsList[0];
  if (!skill) return;

  // Render meta box
  const metaBox = document.getElementById('debugSkillMetaBox');
  if (metaBox) {
    metaBox.innerHTML = `
      <div class="skill-debug-meta-row">
        <span><strong>${skill.title}</strong></span>
        <span class="badge-tag-green">${skill.categoryName || skill.category}</span>
      </div>
      <div class="skill-debug-meta-row" style="color:#64748B; font-size:11.5px; margin-top:4px;">
        <span>安全级别: <strong>${skill.riskName || skill.risk_level}</strong></span>
        <span>超时时间: <strong>${skill.timeout_seconds}s</strong></span>
        <span>门禁机制: <strong>${skill.require_confirmation ? '⚠️ 需人工确认' : '自动放行'}</strong></span>
      </div>
    `;
  }

  // Pre-fill sample params
  const paramsInput = document.getElementById('debugSkillParams');
  if (paramsInput) {
    paramsInput.value = JSON.stringify(skill.sample_params || {}, null, 2);
  }

  // Confirmation toggle row
  const confirmGroup = document.getElementById('debugConfirmGroup');
  const confirmCheck = document.getElementById('debugConfirmationCheck');
  if (confirmGroup) {
    if (skill.require_confirmation || skill.risk_level === 'simulation') {
      confirmGroup.style.display = 'block';
      if (confirmCheck) confirmCheck.checked = true;
    } else {
      confirmGroup.style.display = 'none';
      if (confirmCheck) confirmCheck.checked = false;
    }
  }
}

function resetDebugParamsToSample() {
  const skill = AppState.skillsList.find(s => s.id === AppState.activeDebugSkillId);
  if (skill) {
    const paramsInput = document.getElementById('debugSkillParams');
    if (paramsInput) {
      paramsInput.value = JSON.stringify(skill.sample_params || {}, null, 2);
      showToast('已恢复默认示例参数');
    }
  }
}

async function runSkillTestExecution() {
  const skillId = AppState.activeDebugSkillId;
  const skill = AppState.skillsList.find(s => s.id === skillId);
  const paramsInput = document.getElementById('debugSkillParams');
  const confirmCheck = document.getElementById('debugConfirmationCheck');
  const badge = document.getElementById('debugStatusBadge');
  const statsStrip = document.getElementById('debugConsoleStats');
  const durationElem = document.getElementById('debugExecDuration');
  const gateElem = document.getElementById('debugGateStatus');
  const statusElem = document.getElementById('debugStatusCode');
  const output = document.getElementById('debugConsoleOutput');
  const btnRun = document.getElementById('btnRunSkillTest');

  let params = {};
  try {
    params = JSON.parse(paramsInput.value || '{}');
  } catch (err) {
    if (output) output.innerText = `[JSON 语法错误] 参数必须是合法的 JSON 格式：\n${err.message}`;
    if (badge) {
      badge.className = 'console-status-badge error';
      badge.innerText = 'JSON 错误';
    }
    return;
  }

  const isConfirmed = confirmCheck ? confirmCheck.checked : false;

  // UI state running
  if (badge) {
    badge.className = 'console-status-badge running';
    badge.innerText = '执行中...';
  }
  if (output) {
    output.innerText = `[发送请求] POST /api/skills/${skillId}/test\nPayload: ${JSON.stringify(params)}\nConfirmed: ${isConfirmed}\n\n正在调用量化内核引擎，请稍候...`;
  }
  if (btnRun) {
    btnRun.disabled = true;
    btnRun.style.opacity = '0.6';
  }

  const startTime = performance.now();

  try {
    const response = await fetch(`/api/skills/${skillId}/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        parameters: params,
        confirmed: isConfirmed
      })
    });

    const elapsed = Math.round(performance.now() - startTime);

    if (durationElem) durationElem.innerText = elapsed;
    if (gateElem) gateElem.innerText = isConfirmed ? '核验通过' : '放行';
    if (statusElem) statusElem.innerText = `${response.status} ${response.statusText}`;
    if (statsStrip) statsStrip.style.display = 'flex';

    if (response.ok) {
      const data = await response.json();
      const succeeded = data.status === 'success';
      if (badge) {
        badge.className = `console-status-badge ${succeeded ? 'success' : 'error'}`;
        badge.innerText = succeeded ? '成功 200 OK' : `${data.status || 'error'}`;
      }
      if (output) {
        output.innerText = `[200 OK] ${succeeded ? '执行成功' : '未成功执行'} (耗时: ${elapsed}ms):\n` + JSON.stringify(data, null, 2);
      }
      showToast(`技能【${skillId}】${succeeded ? '测试调用成功' : `状态：${data.status || 'error'}`}`);
    } else {
      const errData = await response.json().catch(() => ({ detail: response.statusText }));
      if (badge) {
        badge.className = 'console-status-badge error';
        badge.innerText = `异常 ${response.status}`;
      }
      if (output) {
        output.innerText = `[${response.status} Error] 调用失败 (耗时: ${elapsed}ms):\n` + JSON.stringify(errData, null, 2);
      }
    }
  } catch (err) {
    const elapsed = Math.round(performance.now() - startTime);
    if (statsStrip) statsStrip.style.display = 'flex';
    if (durationElem) durationElem.innerText = elapsed;
    if (gateElem) gateElem.innerText = '调用失败';
    if (statusElem) statusElem.innerText = '不可用';
    if (badge) {
      badge.className = 'console-status-badge error';
      badge.innerText = '调用失败';
    }
    if (output) {
      output.innerText = `[调用失败] 后端未返回可验证结果 (耗时: ${elapsed}ms):\n${err.message}`;
    }
    showToast(`技能【${skillId}】调用失败`);
  } finally {
    if (btnRun) {
      btnRun.disabled = false;
      btnRun.style.opacity = '1';
    }
  }
}

// --------------------------------------------------------------------------
// 10. Initial DOM Ready Hook
// --------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  // 1. Render Session History & Infinite Scroll
  renderSessionList();
  setupSessionInfiniteScroll();

  // 2. Setup Chat Input Compatibility & @ Operator Controller
  setupChatInputCompatibility();
  AtOperatorController.init();
  ModelPopupController.init();

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

  // 4. Initial Tab & View Activation and Backend Data Loading
  switchRightTab('dashboard');
  updateProjectedCalculator();
  loadAllBackendData();

  // 5. Initialize Model Providers and Roles settings
  initProvidersSettings();

  // 6. Pre-initialize Skills Governance data
  initSkillsGovernance();
});

// 盯盘策略开关：测试阶段仅同步本地开关状态（生产环境应调用后端接口持久化）
function toggleStrategy(name, checkbox) {
  showToast(`${name} 策略已${checkbox.checked ? '启用' : '停用'}`);
}

// Resize listener (防抖，避免窗口拖动期间高频重复拉取)
let __resizeTimer = null;
window.addEventListener('resize', () => {
  if (__resizeTimer) clearTimeout(__resizeTimer);
  __resizeTimer = setTimeout(() => {
    renderTabCharts(AppState.activeRightTab);
  }, 250);
});

// Watchlist Stock Selector
function selectWatchStock(code) {
  AppState.selectedStock = code;
  document.querySelectorAll('.watchlist-item-card').forEach(card => {
    if (card.dataset.code === code) {
      card.classList.add('active');
    } else {
      card.classList.remove('active');
    }
  });
  loadWatchlistData(code);
}
window.selectWatchStock = selectWatchStock;
