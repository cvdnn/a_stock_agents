// -*- coding: utf-8 -*-
/** 选股模型工作台 · 规则库（从 /rule-types 动态渲染，S-06）。 */
(function (global) {
  'use strict';

  function byCategory() {
    const groups = {};
    (global.SelModels.store.get().ruleTypes || []).forEach((meta) => {
      const key = meta.category || '其他';
      (groups[key] = groups[key] || []).push(meta);
    });
    return groups;
  }

  function render(container) {
    if (!container) return;
    const groups = byCategory();
    const keys = Object.keys(groups);
    if (!keys.length) { global.SelModels.stateViews.empty(container, '暂无规则类型'); return; }
    container.innerHTML = keys.map((cat) => `
      <div class="sel-rule-cat"><div class="sel-rule-cat-title">${cat}</div>
        ${groups[cat].map((m) => `<div class="sel-rule-item" data-rule-type="${m.type}"
            onclick="SelModels.propertyDrawer.openNew('${m.type}')" title="${m.description || ''}">
            ${m.label} <span class="sel-rule-ver">v${m.version}</span>
          </div>`).join('')}
      </div>`).join('');
  }

  global.SelModels.ruleLibrary = { render, byCategory };
})(window);