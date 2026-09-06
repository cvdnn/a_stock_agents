// ==========================================================================
// A-Stock Agents Web AIChat UI - Main Application Engine
// Three-Column Architecture with Independent Dual-Scroll & Bidirectional Linkage
// ==========================================================================

const AppState = {
  activeRightTab: 'dashboard', // 'dashboard' | 'market' | 'watchlist' | 'returns' | 'projected-action' etc.
  layoutMode: 'chat-center',   // 'chat-center' (投研助手居中) | 'workspace-main' (业务主工作区居中，AI助手在右)
  isCopilotCollapsed: false,
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
    chatMessages.innerHTML = `
      <div class="message-item message-ai">
        <div class="message-bubble-ai">
          <div class="ai-msg-header">
            <div class="ai-avatar-pill">AI</div>
            <div class="ai-msg-header-text">
              <h3 class="ai-msg-title">智能投研助手就绪</h3>
              <p class="ai-msg-summary">已开启新一轮多因子量化研判会话，支持随时针对右侧盘面提问与调参</p>
            </div>
          </div>
          <div class="ai-content-body">
            <p>您好！我是您的 A股智能量化投研助手。当前右侧已为您保持【整体投研盘面】，您可以：</p>
            <ul>
              <li>点击右侧工具栏的 <strong>“💬 针对此内容提问”</strong> 一键诊断；</li>
              <li>点击左侧菜单切换 <strong>市场行情、自选个股、收益分析</strong>；</li>
              <li>提问任意个股，例如：“<em>分析中芯国际突破买点与保本价</em>”。</li>
            </ul>
          </div>
        </div>
      </div>
    `;
  }
  showToast('已创建新投研会话！右侧内容已完整保留');
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
  const btnExpandTab = document.getElementById('btnExpandChatTab');

  if (!container) return;
  AppState.layoutMode = mode;

  if (mode === 'chat-center') {
    container.classList.remove('layout-workspace-main');
    container.classList.add('layout-chat-center');

    if (chatTitle) chatTitle.innerText = '投研助手';
    if (chatStatus) {
      chatStatus.innerText = '● 在线';
      chatStatus.style.color = '#52C41A';
    }
    if (collapseIcon) collapseIcon.innerText = '◀';
    if (collapseText) collapseText.innerText = '收起';
    if (btnCollapse) btnCollapse.title = '收起投研助手';

    if (btnExpandTab) {
      btnExpandTab.style.display = container.classList.contains('chat-collapsed') ? 'inline-flex' : 'none';
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

    if (btnExpandTab) btnExpandTab.style.display = 'none';
  }

  // Trigger resize event for canvas charts
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 320);
}

// --------------------------------------------------------------------------
// 3. Right Multi-Tab Management (保留当前右侧内容)
// --------------------------------------------------------------------------
const ViewDescriptions = {
  'dashboard': '整体投研盘面 (大盘/自选/持仓监控/策略开关)',
  'market': '市场行情全景 (四大指数/情绪仪表盘/日K线/板块流向)',
  'watchlist': '自选个股深度研判 (宁德时代多周期K线/主力控盘)',
  'returns': '投资收益全景分析 (资产净值曲线/胜率/盈亏归因)',
  'projected-action': '实战交易三原则指令单 (保本价进位试算器/三级止损)'
};

function switchRightTab(tabId) {
  AppState.activeRightTab = tabId;

  // 1. 同步布局模式：投研盘面居中，其他功能主工作区居中+AI助手在右
  if (tabId === 'dashboard') {
    switchLayoutMode('chat-center');
  } else {
    switchLayoutMode('workspace-main');
  }

  // 2. Update Tab Bar
  document.querySelectorAll('.right-tab').forEach(tab => {
    if (tab.dataset.tab === tabId) tab.classList.add('active');
    else tab.classList.remove('active');
  });

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

  // 4. Update Context Indicators
  const desc = ViewDescriptions[tabId] || `自定义工作台 [${tabId}]`;
  const viewNameElem = document.getElementById('currentViewName');
  if (viewNameElem) viewNameElem.innerText = `当前展示：${desc}`;

  const linkedContextElem = document.getElementById('linkedContextText');
  if (linkedContextElem) linkedContextElem.innerText = desc;

  // 5. Re-render Canvas Charts for this tab
  setTimeout(() => {
    renderTabCharts(tabId);
  }, 40);
}

// Dynamically open a new tab on the right without closing previous ones
function openRightTab(tabId, title, icon = '📑', isClosable = true) {
  const tabsBar = document.getElementById('rightTabsBar');
  if (!tabsBar) return;

  let existingTab = tabsBar.querySelector(`.right-tab[data-tab="${tabId}"]`);
  if (!existingTab) {
    existingTab = document.createElement('div');
    existingTab.className = 'right-tab';
    existingTab.dataset.tab = tabId;
    existingTab.onclick = () => switchRightTab(tabId);
    existingTab.innerHTML = `
      <span class="tab-icon">${icon}</span>
      <span>${title}</span>
      ${isClosable ? `<span class="tab-close" onclick="closeRightTab('${tabId}', event)" title="关闭标签">×</span>` : ''}
    `;
    tabsBar.appendChild(existingTab);
  }

  switchRightTab(tabId);
}

// Close a tab and fallback safely to dashboard
function closeRightTab(tabId, event) {
  if (event) event.stopPropagation();

  const tabsBar = document.getElementById('rightTabsBar');
  if (!tabsBar) return;

  const targetTab = tabsBar.querySelector(`.right-tab[data-tab="${tabId}"]`);
  if (targetTab) targetTab.remove();

  if (AppState.activeRightTab === tabId) {
    switchRightTab('dashboard');
    showToast('已关闭投射标签，平滑返回【投研盘面】');
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
  } else {
    // Mode 1: 收起居中投研助手
    toggleChatCollapse();
  }
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

// Toggle ChatUI collapse / expand (Mode 1: 投研助手居中模式下的收起 / 展开)
function toggleChatCollapse() {
  const container = document.getElementById('appContainer') || document.querySelector('.app-container');
  const chatCol = document.getElementById('appMiddleChat');
  const expandTabBtn = document.getElementById('btnExpandChatTab');

  if (!container) return;

  const isCollapsed = container.classList.toggle('chat-collapsed');
  if (chatCol) chatCol.classList.toggle('collapsed', isCollapsed);

  if (expandTabBtn) {
    expandTabBtn.style.display = isCollapsed ? 'inline-flex' : 'none';
  }

  if (isCollapsed) {
    showToast('已收起 AI 投研助手，右侧内容展示区已最大化展开');
  } else {
    showToast('已展开 AI 投研助手 (占比 40%)');
  }

  // Trigger resize event so Canvas charts smoothly re-render to new width
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 320);
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
    FinancialCharts.drawSparkline('sparklineSh', [3390, 3405, 3400, 3415, 3422, 3418, 3426.56], true);
    FinancialCharts.drawSparkline('sparklineSz', [10750, 10780, 10820, 10800, 10860, 10892.14], true);
    FinancialCharts.drawSparkline('sparklineCy', [2250, 2265, 2260, 2278, 2282, 2289.76], true);

    FinancialCharts.drawDonutChart('portfolioDonut', [
      { name: '持仓市值', value: 328.56, color: '#1677FF' },
      { name: '现金', value: 125.68, color: '#4096FF' }
    ], { centerTitle: '总市值', centerValue: '328.56万' });
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
        <div class="risk-card-actions">
          <button class="project-btn" onclick="projectToRight('action', {code:'300750', name:'宁德时代', cost:320, shares:1000})">
            <span>⛶ 放大投射到右侧工作台</span>
          </button>
          <button class="project-btn secondary" onclick="openModifyRightParam()">
            <span>✏️ 修改风控参数</span>
          </button>
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
          <span class="action-chip" onclick="showToast('感谢反馈：已标记有用！')">👍 有用</span>
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
        <span>已完成数据调取与实战三原则保本价精算（税费最低卖出价向上进位至分）</span>
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

function handleSendChat() {
  if (AppState.isChatStreaming) return;

  const input = document.getElementById('chatInput');
  const text = input ? input.value.trim() : '';
  if (!text) return;

  appendChatMessage('user', text);
  input.value = '';

  let tpl = PromptTemplates['行情分析'];
  if (text.includes('指标') || text.includes('技术') || text.includes('金叉')) {
    tpl = PromptTemplates['技术指标'];
  } else if (text.includes('选股') || text.includes('模型') || text.includes('因子')) {
    tpl = PromptTemplates['选股模型'];
  }

  streamAIResponse(tpl.body, tpl.title, tpl.summary);
}

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

function regenerateLastMessage() {
  showToast('正在重新调用 AI 模型与风控规则...');
  streamAIResponse(PromptTemplates['行情分析'], '重算行情研报');
}

// --------------------------------------------------------------------------
// 8. Modals Management (系统设置 & 参数修改)
// --------------------------------------------------------------------------
function openSettingsModal() {
  const modal = document.getElementById('settingsModal');
  if (modal) modal.classList.add('active');
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
}

function saveSettings() {
  closeSettingsModal();
  showToast('系统设置已成功保存！大模型网关与实战风控已平滑热重载');
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
      const content = PromptTemplates[key] || PromptTemplates['行情分析'];
      appendChatMessage('user', `请帮我执行【${key}】并出具研报`);
      streamAIResponse(content, `${key} 深度诊断`);
    });
  });

  // 4. Initial Tab & View Activation
  switchRightTab('dashboard');
  updateProjectedCalculator();
});

// Resize listener
window.addEventListener('resize', () => {
  renderTabCharts(AppState.activeRightTab);
});
