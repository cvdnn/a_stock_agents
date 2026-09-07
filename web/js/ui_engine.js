// ==========================================================================
// Agent2UI (A2UI) Core Frontend Engine - v1.0
// Universal Agent-to-UI Dispatcher, Skeleton Orchestrator & Progressive Hydrator
// ==========================================================================

const UIEngine = {
  // 1. Component Registry (IoC Container)
  components: {},

  registerComponent(name, definition) {
    if (!name || !definition) return;
    this.components[name] = definition;
    console.log(`[UIEngine] Registered domain component: ${name}`);
  },

  getComponent(name) {
    return this.components[name] || null;
  },

  // Active Tasks Tracking
  tasks: {},

  // --------------------------------------------------------------------------
  // 2. Stage 0: Skeleton Orchestration (1:1 Layout Pre-allocation)
  // --------------------------------------------------------------------------
  mountSkeleton(taskId, target = 'both_linked', layoutMeta = {}, skeletonTree = []) {
    const taskState = {
      taskId,
      target,
      layoutMeta,
      skeletonTree,
      chatCardEl: null,
      workbenchPaneEl: null,
      stage: 'skeleton',
      data: {}
    };
    this.tasks[taskId] = taskState;

    const title = layoutMeta.title || '量化投研综合研报';
    const icon = layoutMeta.icon || '📊';

    // A. Mount into Chat Card
    if (target === 'chat_card' || target === 'both_linked') {
      const chatMessages = document.getElementById('chatMessages');
      if (chatMessages) {
        const msgItem = document.createElement('div');
        msgItem.className = 'message-item message-ai';
        msgItem.id = `msg_${taskId}`;

        const card = document.createElement('div');
        card.className = 'a2ui-card';
        card.id = `card_${taskId}`;

        let slotsHtml = '';
        skeletonTree.forEach(node => {
          const comp = this.getComponent(node.component);
          const skelHtml = comp && comp.renderSkeleton 
            ? comp.renderSkeleton('compact') 
            : `<div class="skeleton-shimmer a2ui-skeleton-slot" style="height:${node.height || 60}px"></div>`;
          slotsHtml += `<div class="a2ui-slot-wrapper" id="slot_chat_${taskId}_${node.slot_id}">${skelHtml}</div>`;
        });

        card.innerHTML = `
          <div class="a2ui-card-header">
            <div class="a2ui-card-title-box">
              <span class="a2ui-card-icon">${icon}</span>
              <span class="a2ui-card-title">${title}</span>
            </div>
            <span class="a2ui-stage-badge" id="badge_${taskId}">⏳ 骨架预占中</span>
          </div>
          <div class="a2ui-content-text" id="text_${taskId}" style="font-size:12px; color:#4E5969; margin-bottom:10px; line-height:1.6;"></div>
          <div class="a2ui-card-body" id="body_${taskId}">${slotsHtml}</div>
          <div class="a2ui-card-actions" id="actions_${taskId}" style="display:none;"></div>
        `;

        msgItem.appendChild(card);
        chatMessages.appendChild(msgItem);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        taskState.chatCardEl = card;
      }
    }

    // B. Mount into Workbench Tab
    if (target === 'workbench' || target === 'both_linked') {
      const tabMeta = layoutMeta.workbench_tab || {
        tab_id: `tab_${taskId}`,
        tab_title: title,
        closable: true
      };

      // Ensure Workbench is visible in Mode 1
      if (typeof AppState !== 'undefined' && AppState.layoutMode === 'chat-center' && AppState.isWorkbenchCollapsed) {
        if (typeof toggleWorkbenchCollapse === 'function') toggleWorkbenchCollapse(false);
      }

      // Open new tab without destroying existing tabs
      if (typeof openRightTab === 'function') {
        openRightTab(tabMeta.tab_id, tabMeta.tab_title, icon, tabMeta.closable !== false);
      }

      // Mount skeleton in Pane
      const pane = document.getElementById('pane-projected');
      if (pane) {
        let wbSlotsHtml = '';
        skeletonTree.forEach(node => {
          const comp = this.getComponent(node.component);
          const skelHtml = comp && comp.renderSkeleton 
            ? comp.renderSkeleton('expanded') 
            : `<div class="skeleton-shimmer a2ui-skeleton-slot" style="height:${(node.height || 60) * 1.8}px"></div>`;
          wbSlotsHtml += `<div class="a2ui-wb-slot-wrapper" id="slot_wb_${taskId}_${node.slot_id}">${skelHtml}</div>`;
        });

        pane.innerHTML = `
          <div class="a2ui-workbench-panel" id="wb_${taskId}">
            <div class="radar-expanded-header">
              <h4>${icon} ${title}</h4>
              <span class="a2ui-stage-badge" id="wb_badge_${taskId}">⏳ 正在生成专业看板...</span>
            </div>
            <div class="a2ui-wb-content">${wbSlotsHtml}</div>
          </div>
        `;
        taskState.workbenchPaneEl = pane;

        // Pop-in slide animation
        pane.classList.remove('popup-slide-from-left');
        void pane.offsetWidth;
        pane.classList.add('popup-slide-from-left');
      }
    }

    return taskState;
  },

  // --------------------------------------------------------------------------
  // 3. Progressive Hydration Pipeline
  // --------------------------------------------------------------------------
  hydrateFast(taskId, slotId, props = {}) {
    const task = this.tasks[taskId];
    if (!task) return;

    task.data[slotId] = { ...(task.data[slotId] || {}), ...props };
    const node = task.skeletonTree.find(n => n.slot_id === slotId);
    if (!node) return;

    const comp = this.getComponent(node.component);
    if (!comp) return;

    // A. Hydrate Chat Slot
    const chatSlot = document.getElementById(`slot_chat_${taskId}_${slotId}`);
    if (chatSlot && comp.renderCompact) {
      chatSlot.innerHTML = comp.renderCompact(props);
      if (comp.onMounted) comp.onMounted(chatSlot, props, 'compact');
    }

    // B. Hydrate Workbench Slot
    const wbSlot = document.getElementById(`slot_wb_${taskId}_${slotId}`);
    if (wbSlot && comp.renderExpanded) {
      wbSlot.innerHTML = comp.renderExpanded(props);
      if (comp.onMounted) comp.onMounted(wbSlot, props, 'expanded');
    }

    this.updateStageBadge(taskId, '⚡ 快数据已水合');
  },

  streamTextDelta(taskId, textDelta) {
    const textEl = document.getElementById(`text_${taskId}`);
    if (!textEl) return;
    textEl.innerHTML += textDelta;
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
  },

  hydrateHeavy(taskId, slotId, props = {}) {
    const task = this.tasks[taskId];
    if (!task) return;

    task.data[slotId] = { ...(task.data[slotId] || {}), ...props };
    const node = task.skeletonTree.find(n => n.slot_id === slotId);
    if (!node) return;

    const comp = this.getComponent(node.component);
    if (!comp) return;

    // Hydrate heavy views
    const chatSlot = document.getElementById(`slot_chat_${taskId}_${slotId}`);
    if (chatSlot && comp.renderCompact) {
      chatSlot.innerHTML = comp.renderCompact(task.data[slotId]);
      if (comp.onMounted) comp.onMounted(chatSlot, task.data[slotId], 'compact');
    }

    const wbSlot = document.getElementById(`slot_wb_${taskId}_${slotId}`);
    if (wbSlot && comp.renderExpanded) {
      wbSlot.innerHTML = comp.renderExpanded(task.data[slotId]);
      if (comp.onMounted) comp.onMounted(wbSlot, task.data[slotId], 'expanded');
    }

    this.updateStageBadge(taskId, '📈 图表与量能已渲染');
  },

  hydrateActionSheet(taskId, actions = []) {
    const task = this.tasks[taskId];
    if (!task) return;

    const actionsContainer = document.getElementById(`actions_${taskId}`);
    if (!actionsContainer) return;

    actionsContainer.innerHTML = '';
    actionsContainer.style.display = 'flex';

    actions.forEach(act => {
      const btn = document.createElement('button');
      btn.className = `project-btn ${act.secondary ? 'secondary' : ''}`;
      btn.innerHTML = `<span>${act.label}</span>`;
      btn.onclick = () => {
        if (act.type === 'project') {
          UIEngine.ActionBus.projectToWorkbench(taskId, act.target_tab);
        } else if (act.type === 'prompt') {
          UIEngine.ActionBus.injectPrompt(act.prompt);
        } else if (typeof act.handler === 'function') {
          act.handler(taskId, task.data);
        }
      };
      actionsContainer.appendChild(btn);
    });

    this.updateStageBadge(taskId, '✓ 投研报告就绪', true);
  },

  updateStageBadge(taskId, label, isDone = false) {
    const badges = [
      document.getElementById(`badge_${taskId}`),
      document.getElementById(`wb_badge_${taskId}`)
    ];
    badges.forEach(b => {
      if (b) {
        b.innerText = label;
        if (isDone) b.classList.add('done');
      }
    });
  },

  // --------------------------------------------------------------------------
  // 4. Bidirectional Action & State Bus
  // --------------------------------------------------------------------------
  ActionBus: {
    projectToWorkbench(taskId, tabId = 'projected-action') {
      if (typeof openRightTab === 'function') {
        const task = UIEngine.tasks[taskId];
        const title = task?.layoutMeta?.title || '量化投研报告';
        openRightTab(tabId, title, '⛶', true);
      }

      if (typeof AppState !== 'undefined' && AppState.layoutMode === 'chat-center' && AppState.isWorkbenchCollapsed) {
        if (typeof toggleWorkbenchCollapse === 'function') toggleWorkbenchCollapse(false);
      }

      const pane = document.getElementById('pane-projected');
      if (pane) {
        pane.classList.remove('popup-slide-from-left');
        void pane.offsetWidth;
        pane.classList.add('popup-slide-from-left');
      }

      if (typeof showToast === 'function') {
        showToast('已放大投射到右侧工作台（原内容完整保留）');
      }
    },

    injectPrompt(promptText) {
      const input = document.getElementById('chatInput');
      if (input) {
        input.value = promptText;
        input.focus();
        if (typeof showToast === 'function') {
          showToast('已载入快捷提问提示词，直接回车即可执行！');
        }
      }
    }
  }
};

window.UIEngine = UIEngine;
