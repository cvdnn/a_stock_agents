// ==========================================================================
// Agent2UI (A2UI) Core Frontend Engine - v1.0
// Universal Agent-to-UI Dispatcher, Skeleton Orchestrator & Progressive Hydrator
// ==========================================================================

// Global Safe Buffer for Pack Registrations (Decouples loading order)
window.__A2UI_PENDING_PACKS__ = window.__A2UI_PENDING_PACKS__ || [];

window.defineA2UIPack = function(packDef) {
  if (window.UIEngine && typeof window.UIEngine.registerPack === 'function') {
    window.UIEngine.registerPack(packDef);
  } else {
    window.__A2UI_PENDING_PACKS__.push(packDef);
  }
};

window.defineA2UIComponent = function(namespace, name, def) {
  if (window.UIEngine && typeof window.UIEngine.registerComponentToPack === 'function') {
    window.UIEngine.registerComponentToPack(namespace, name, def);
  } else {
    window.__A2UI_PENDING_PACKS__.push({
      namespace: namespace || 'common',
      components: { [name]: def }
    });
  }
};

const UIEngine = {
  // 1. Component & Pack Registry (IoC Container)
  packs: {},
  components: {}, // flat index for backwards-compatibility & short-name fallback

  registerPack(packDef) {
    if (!packDef || !packDef.namespace) {
      console.warn('[UIEngine] Invalid pack definition:', packDef);
      return;
    }
    const ns = packDef.namespace;
    if (!this.packs[ns]) {
      this.packs[ns] = {
        meta: {
          namespace: ns,
          title: packDef.title || ns,
          version: packDef.version || '1.0.0',
          description: packDef.description || ''
        },
        components: {}
      };
    } else {
      this.packs[ns].meta = {
        ...this.packs[ns].meta,
        title: packDef.title || this.packs[ns].meta.title,
        version: packDef.version || this.packs[ns].meta.version,
        description: packDef.description || this.packs[ns].meta.description
      };
    }

    const comps = packDef.components || {};
    Object.keys(comps).forEach(compName => {
      this.registerComponentToPack(ns, compName, comps[compName]);
    });

    console.log(`[UIEngine] Mounted pack: @a2ui/pack-${ns} (v${packDef.version || '1.0.0'}) [${Object.keys(comps).length} components]`);
  },

  registerComponentToPack(namespace, compName, compDef) {
    if (!compDef || !compName) return;
    compDef.name = compName;
    compDef.category = namespace;

    if (!compDef.renderCompact || !compDef.renderExpanded) {
      console.warn(`[UIEngine] Component ${namespace}/${compName} is missing renderCompact or renderExpanded method!`);
    }

    if (!this.packs[namespace]) {
      this.packs[namespace] = {
        meta: { namespace, title: namespace, version: '1.0.0' },
        components: {}
      };
    }
    this.packs[namespace].components[compName] = compDef;

    // Flat index for fallback
    this.components[compName] = compDef;
    // Also index full name with slash and colon
    this.components[`${namespace}/${compName}`] = compDef;
    this.components[`${namespace}:${compName}`] = compDef;
  },

  // Backwards-compatible single component registration
  registerComponent(name, definition) {
    if (!name || !definition) return;
    this.registerComponentToPack('common', name, definition);
    console.log(`[UIEngine] Registered domain component: ${name}`);
  },

  // Dual-path Component Query
  getComponent(identifier) {
    if (!identifier) return null;

    // 1. Direct hit in flat index (covers exact name, namespace/name, namespace:name)
    if (this.components[identifier]) {
      return this.components[identifier];
    }

    // 2. Namespace parsing
    if (identifier.includes('/') || identifier.includes(':')) {
      const [ns, name] = identifier.split(/[\/:]/);
      if (this.packs[ns] && this.packs[ns].components[name]) {
        return this.packs[ns].components[name];
      }
    }

    return null;
  },

  // Flush buffer
  flushPendingPacks() {
    if (Array.isArray(window.__A2UI_PENDING_PACKS__)) {
      while (window.__A2UI_PENDING_PACKS__.length > 0) {
        const pending = window.__A2UI_PENDING_PACKS__.shift();
        this.registerPack(pending);
      }
    }
  },

  // Dynamic Pack Loader (Promise-based)
  loadPack(namespace, customUrl = null) {
    return new Promise((resolve, reject) => {
      if (this.packs[namespace]) {
        return resolve(this.packs[namespace]);
      }

      const scriptUrl = customUrl || `js/components/${namespace}.js`;
      const existingScript = document.querySelector(`script[data-a2ui-pack="${namespace}"]`);
      if (existingScript) {
        existingScript.addEventListener('load', () => resolve(this.packs[namespace]));
        existingScript.addEventListener('error', (e) => reject(e));
        return;
      }

      const script = document.createElement('script');
      script.src = scriptUrl;
      script.async = true;
      script.setAttribute('data-a2ui-pack', namespace);

      script.onload = () => {
        this.flushPendingPacks();
        if (this.packs[namespace]) {
          resolve(this.packs[namespace]);
        } else {
          reject(new Error(`Script ${scriptUrl} loaded but pack '${namespace}' was not registered.`));
        }
      };

      script.onerror = (err) => {
        console.error(`[UIEngine] Failed to load pack @a2ui/pack-${namespace} from ${scriptUrl}`);
        reject(new Error(`Failed to load pack @a2ui/pack-${namespace}: ${err.message || 'Network error'}`));
      };

      document.head.appendChild(script);
    });
  },

  // Catalog & Introspection API
  getCatalog() {
    const packList = Object.keys(this.packs).map(ns => {
      const p = this.packs[ns];
      const comps = Object.keys(p.components).map(cName => {
        const c = p.components[cName];
        return {
          name: c.name,
          fullName: `${ns}/${c.name}`,
          category: ns,
          description: c.description || '',
          supports: ['compact', 'expanded'],
          hasLifecycle: typeof c.onMounted === 'function'
        };
      });
      return {
        namespace: ns,
        title: p.meta.title,
        version: p.meta.version,
        description: p.meta.description,
        components: comps
      };
    });

    let totalComps = 0;
    packList.forEach(p => totalComps += p.components.length);

    return {
      totalPacks: packList.length,
      totalComponents: totalComps,
      packs: packList
    };
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

// Flush any packs that loaded before UIEngine was defined
UIEngine.flushPendingPacks();
