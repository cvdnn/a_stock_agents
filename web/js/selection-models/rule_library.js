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

  const typeLabels = {
    field_compare: '字段比较', symbol_prefix_exclude: '代码前缀排除',
    text_exclude: '名称关键词排除', rolling_high: '滚动新高',
    above_sma: '价格高于均线', sma_slope: '均线斜率',
    series_compare: '序列比较', volume_sustained_expansion: '持续放量',
    range: '区间筛选', market_above_sma: '大盘高于均线',
    intraday_turning_point: '盘中拐点确认'
  };
  const number = (value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
  const amount = (value) => Number.isInteger(value) ? String(value) : String(value);
  function typeName(type) {
    const meta = (global.SelModels.store.get().ruleTypes || []).find((item) => item.type === type);
    return (meta && meta.label) || typeLabels[type] || '其他规则';
  }
  function displayName(rule) {
    const n = number(rule.value);
    const period = number(rule.period);
    const lookback = number(rule.lookback);
    if (rule.type === 'text_exclude' && rule.field === 'name') {
      const tokens = Array.isArray(rule.tokens) ? rule.tokens.map(String) : [];
      if (tokens.some((token) => token.toUpperCase().includes('ST')) && tokens.includes('退')) return '排除名称含ST或退的股票';
      return '排除名称关键词';
    }
    if (rule.type === 'symbol_prefix_exclude') {
      const prefixes = Array.isArray(rule.prefixes) ? rule.prefixes.map(String) : [];
      if (rule.field === 'code' && prefixes.length === 3 && ['4', '8', '92'].every((p) => prefixes.includes(p))) return '排除北交所代码';
      return '排除指定代码前缀';
    }
    if (rule.type === 'field_compare' && n !== null) {
      const direction = ({ gt: '高于', gte: '不低于', lt: '低于', lte: '不高于', eq: '等于', ne: '不等于' })[rule.op];
      if (direction && rule.field === 'circulating_market_cap') return `流通市值${direction}${amount(n / 100000000)}亿元`;
      if (direction && rule.field === 'change_pct') return `当日涨幅${direction}${amount(n)}%`;
      if (rule.field === 'main_net_inflow' && rule.op === 'gt' && n === 0) return '主力资金净流入';
    }
    if (rule.type === 'rolling_high' && lookback !== null) return `${rule.field === 'closes' ? '收盘价' : '价格'}创${lookback}日新高`;
    if (rule.type === 'above_sma' && period !== null) return `${rule.series_field === 'closes' ? '收盘价' : '价格'}高于${period}日均线`;
    if (rule.type === 'sma_slope' && period !== null) {
      const slope = number(rule.min_slope_pct);
      return slope === 0 ? `${period}日均线向上` : `${period}日均线斜率筛选`;
    }
    if (rule.type === 'series_compare' && rule.field === 'volumes' && rule.left_offset === -1 && rule.right_offset === -2 && rule.op === 'gt') return '今日成交量大于昨日';
    if (rule.type === 'volume_sustained_expansion') {
      const window = number(rule.window);
      return window !== null ? `近${window}日持续放量` : '持续放量';
    }
    if (rule.type === 'market_above_sma' && period !== null) return `大盘站上${period}日均线`;
    if (rule.type === 'range' && rule.field === 'gap_pct') {
      const min = number(rule.min), max = number(rule.max);
      if (min !== null && max !== null) return `开盘涨幅${amount(min)}%～${amount(max)}%`;
      if (min !== null) return `开盘涨幅不低于${amount(min)}%`;
      if (max !== null) return `开盘涨幅不高于${amount(max)}%`;
    }
    if (rule.type === 'intraday_turning_point') return '早盘回调拐点确认';
    return typeName(rule.type);
  }
  function chip(rule) {
    const name = displayName(rule);
    return { name, label: `${name}${rule.enabled === false ? '（停用）' : ''}`,
      title: `规则 ID：${rule.id || ''}；规则类型：${rule.type || ''}（${typeName(rule.type)}）` };
  }

  function render(container) {
    if (!container) return;
    const groups = byCategory();
    const keys = Object.keys(groups);
    if (!keys.length) { global.SelModels.stateViews.empty(container, '暂无规则类型'); return; }
    const esc = global.SelModels.editorHelpers.esc;
    container.innerHTML = `<div class="sel-rule-library-title">规则库 · 选择规则后应用到当前条件组或阶段</div>` + keys.map((cat) => `
      <div class="sel-rule-cat"><div class="sel-rule-cat-title">${esc(cat)}</div>
        ${groups[cat].map((m) => `<button type="button" class="sel-rule-item" data-rule-type="${esc(m.type)}"
            onclick="SelModels.propertyDrawer.openNew('${esc(m.type)}')" title="${esc(m.description || '')}">
            ${esc(m.label)} <span class="sel-rule-ver">v${esc(m.version)}</span>
          </button>`).join('')}
      </div>`).join('');
  }

  global.SelModels.ruleLibrary = { render, byCategory, typeName, displayName, chip };
})(window);
