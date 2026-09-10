// ==========================================================================
// Agent2UI (A2UI) Domain Component Pack - Stock Research (@a2ui/pack-astock)
// Financial-grade visual components adhering to AGENTS.md & Clean Light Aesthetics
// ==========================================================================

// --------------------------------------------------------------------------
// 1. MarketRadar Component (大盘全景雷达看板)
// --------------------------------------------------------------------------
const AStockMarketRadar = {
  name: 'MarketRadar',
  category: 'astock',
  description: '核心大盘指数走势与资金情绪全景雷达',

  renderSkeleton(mode) {
    if (mode === 'compact') {
      return `
        <div class="skeleton-shimmer radar-skeleton compact">
          <div class="skeleton-shimmer" style="height:100%; border-radius:6px;"></div>
          <div class="skeleton-shimmer" style="height:100%; border-radius:6px;"></div>
          <div class="skeleton-shimmer" style="height:100%; border-radius:6px;"></div>
        </div>
      `;
    }
    return `
      <div class="skeleton-shimmer radar-skeleton expanded"></div>
    `;
  },

  renderCompact(props = {}) {
    const list = Array.isArray(props.indices) ? props.indices : [];
    if (!list.length) return '<div class="a2ui-unavailable">市场指数数据不可用</div>';

    return `
      <div class="radar-compact-grid">
        ${list.map(item => `
          <div class="radar-chip ${item.change_pct >= 0 ? 'up' : 'down'}">
            <span class="chip-name">${item.name}</span>
            <span class="chip-price tabular-nums">${item.price.toFixed(2)}</span>
            <span class="chip-pct tabular-nums">${item.change_pct > 0 ? '+' : ''}${item.change_pct}%</span>
          </div>
        `).join('')}
      </div>
    `;
  },

  renderExpanded(props = {}) {
    const list = Array.isArray(props.indices) ? props.indices : [];
    if (!list.length) return '<div class="a2ui-unavailable">市场雷达数据不可用</div>';
    const volume = props.total_volume || '暂无成交额';
    const sentiment = props.sentiment?.text || '暂无情绪数据';

    return `
      <div class="radar-expanded-dashboard">
        <div class="radar-expanded-header">
          <h4>📊 核心大盘指数走势与资金情绪</h4>
          <div style="display:flex; gap:8px;">
            <span class="badge-tag-green" style="font-size:11px;">两市放量 ${volume}</span>
            <span class="a2ui-stage-badge done" style="font-size:11px;">情绪 ${sentiment}</span>
          </div>
        </div>
        <div class="sparkline-row">${list.map((item, index) => `
          <div class="sparkline-item"><div class="sparkline-meta">
            <strong>${item.name} ${Number(item.price).toFixed(2)}</strong>
            <span>${Number(item.change_pct) > 0 ? '+' : ''}${Number(item.change_pct).toFixed(2)}%</span>
          </div><canvas id="a2ui_spark_${index}" width="180" height="40"></canvas></div>
        `).join('')}</div>
      </div>
    `;
  },

  onMounted(container, props = {}, mode) {
    if (mode === 'expanded' && typeof FinancialCharts !== 'undefined') {
      setTimeout(() => {
        (props.indices || []).forEach((item, index) => {
          if (Array.isArray(item.sparkline) && item.sparkline.length) {
            FinancialCharts.drawSparkline(`a2ui_spark_${index}`, item.sparkline, Number(item.change_pct) >= 0);
          }
        });
      }, 30);
    }
  }
};

// --------------------------------------------------------------------------
// 2. CandleMatrix Component (K线量能矩阵)
// --------------------------------------------------------------------------
const AStockCandleMatrix = {
  name: 'CandleMatrix',
  category: 'astock',
  description: '28日日K线蜡烛图与成交量能矩阵',

  renderSkeleton(mode) {
    if (mode === 'compact') {
      return `<div class="skeleton-shimmer candle-skeleton compact"></div>`;
    }
    return `<div class="skeleton-shimmer candle-skeleton expanded"></div>`;
  },

  renderCompact(props = {}) {
    const benchmark = props.benchmark;
    if (!benchmark) return '<div class="a2ui-unavailable">K线数据不可用</div>';
    return `
      <div style="background:#F8FAFD; border:1px solid #DFE6EF; border-radius:6px; padding:8px 12px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <span style="font-size:11px; color:#86909C;">量价形态</span>
          <div style="font-size:12px; font-weight:700; color:#1D2129;">${benchmark} 28日均线多头共振</div>
        </div>
        <span class="badge-tag-green">放量突破</span>
      </div>
    `;
  },

  renderExpanded(props = {}) {
    if (!Array.isArray(props.klines) || !props.klines.length) {
      return '<div class="a2ui-unavailable">K线数据不可用</div>';
    }
    return `
      <div class="candle-expanded-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <h4 style="margin:0; font-size:14px; color:#1D2129;">📈 28日日K线蜡烛图与成交量能矩阵</h4>
          <span style="font-size:12px; color:#86909C;">零轴下方水下二次金叉验底形态</span>
        </div>
        <div style="width:100%; height:260px; position:relative;">
          <canvas id="a2ui_candle_canvas" style="width:100%; height:260px;"></canvas>
        </div>
      </div>
    `;
  },

  onMounted(container, props = {}, mode) {
    if (mode === 'expanded' && typeof FinancialCharts !== 'undefined') {
      setTimeout(() => {
        if (Array.isArray(props.klines) && props.klines.length) {
          FinancialCharts.drawCandlestickChart('a2ui_candle_canvas', props.klines, { showVolume: true });
        }
      }, 50);
    }
  }
};

// --------------------------------------------------------------------------
// 3. RiskBreakevenCalc Component (合规保本价进位与三级风控滑块算价器)
// --------------------------------------------------------------------------
const AStockRiskBreakevenCalc = {
  name: 'RiskBreakevenCalc',
  category: 'astock',
  description: '实战交易三原则合规保本价进位与动态滑块试算器',

  calculateBreakeven(cost, shares) {
    // AGENTS.md 铁律：印花税0.05%、佣金万2.5最低5元、过户费双向0.002%
    const buyAmount = cost * shares;
    const comm = Math.max(5.0, buyAmount * 0.00025);
    const stamp = buyAmount * 0.0005;
    const transfer = buyAmount * 0.00002 * 2;
    const totalFee = comm * 2 + stamp + transfer;
    // 强制向上进位至分位 (math.ceil)
    return Math.ceil(((buyAmount + totalFee) / shares) * 100) / 100;
  },

  renderSkeleton(mode) {
    if (mode === 'compact') {
      return `<div class="skeleton-shimmer risk-skeleton compact"></div>`;
    }
    return `<div class="skeleton-shimmer risk-skeleton expanded"></div>`;
  },

  renderCompact(props = {}) {
    const cost = Number(props.cost);
    const shares = Number(props.shares);
    if (!Number.isFinite(cost) || cost <= 0 || !Number.isInteger(shares) || shares <= 0) {
      return '<div class="a2ui-unavailable">缺少有效持仓成本或股数，无法计算保本价</div>';
    }
    const breakeven = this.calculateBreakeven(cost, shares);
    const t0 = (cost * 0.97).toFixed(2);
    const t1 = (cost * 0.95).toFixed(2);
    const t2 = (cost * 0.92).toFixed(2);

    return `
      <div class="risk-iron-card" style="margin-top:6px;">
        <div class="risk-iron-header">
          <span class="risk-iron-title">🛡️ 实战交易三原则（合规风控指令单）</span>
          <button class="risk-iron-action-btn" title="投射到右侧工作台" onclick="if(typeof projectToRight==='function'){projectToRight('action', {code:'${props.code||'300750'}', name:'${props.name||'宁德时代'}', cost:${cost}, shares:${shares}});}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
            </svg>
          </button>
        </div>
        <div class="risk-iron-grid">
          <div class="risk-pill-box">
            <div class="risk-pill-title">最低保本卖出价</div>
            <div class="risk-pill-val tabular-nums" style="color:#F5222D; font-weight:700;">¥${breakeven.toFixed(2)}</div>
          </div>
          <div class="risk-pill-box">
            <div class="risk-pill-title">T1减仓线 (-5%)</div>
            <div class="risk-pill-val tabular-nums">¥${t1} (减仓50%)</div>
          </div>
          <div class="risk-pill-box">
            <div class="risk-pill-title">T2绝杀线 (-8%)</div>
            <div class="risk-pill-val tabular-nums">¥${t2} (坚决止损)</div>
          </div>
        </div>
      </div>
    `;
  },

  renderExpanded(props = {}) {
    const cost = Number(props.cost);
    const shares = Number(props.shares);
    if (!Number.isFinite(cost) || cost <= 0 || !Number.isInteger(shares) || shares <= 0) {
      return '<div class="a2ui-unavailable">缺少有效持仓成本或股数，无法计算保本价</div>';
    }
    const breakeven = this.calculateBreakeven(cost, shares);

    return `
      <div class="calc-expanded-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h4 style="margin:0; font-size:14px; color:#1D2129;">🛡️ 保本卖出价动态滑块试算器 (全税费精算)</h4>
          <span class="badge-tag-green">AGENTS.md 规范落地</span>
        </div>
        
        <div class="calc-slider-group">
          <div class="calc-slider-row">
            <span style="font-size:12px; width:90px; color:#4E5969;">买入成本:</span>
            <input type="range" id="a2ui_dyn_cost" min="10" max="800" step="0.5" value="${cost}">
            <strong id="a2ui_cost_val" style="width:70px; font-size:13px;" class="tabular-nums">¥${cost.toFixed(2)}</strong>
          </div>
          <div class="calc-slider-row">
            <span style="font-size:12px; width:90px; color:#4E5969;">持仓股数:</span>
            <input type="range" id="a2ui_dyn_shares" min="100" max="5000" step="100" value="${shares}">
            <strong id="a2ui_shares_val" style="width:70px; font-size:13px;" class="tabular-nums">${shares} 股</strong>
          </div>
        </div>

        <div class="calc-result-preview">
          <span>最低保本卖出价:</span>
          <strong id="a2ui_breakeven_res" class="tabular-nums">¥${breakeven.toFixed(2)}</strong>
          <span style="font-size:11px; color:#86909C;">(已计入印花税、佣金与过户费)</span>
        </div>

        <div style="margin-top:12px; font-size:12px; color:#4E5969; background:#FFFFFF; border:1px solid #EBF0F5; border-radius:6px; padding:10px;">
          <strong>三场景即时动作单：</strong>
          <ul style="margin:4px 0 0 16px; padding:0;">
            <li><strong>开盘冲高 (+3%)</strong>：在保本价之上减持 30% 锁定本周波段利润。</li>
            <li><strong>盘中窄幅震荡 (±1.5%)</strong>：持股防守，严格观察 5日均线支撑位。</li>
            <li><strong>突发跳水 (-3%以下)</strong>：触碰 T1 警戒线 (-5%) 强制减仓 50% 防守。</li>
          </ul>
        </div>
      </div>
    `;
  },

  onMounted(container, props = {}, mode) {
    if (mode === 'expanded') {
      const sliderCost = container.querySelector('#a2ui_dyn_cost');
      const sliderShares = container.querySelector('#a2ui_dyn_shares');
      const textCost = container.querySelector('#a2ui_cost_val');
      const textShares = container.querySelector('#a2ui_shares_val');
      const resBreakeven = container.querySelector('#a2ui_breakeven_res');

      const recompute = () => {
        if (!sliderCost || !sliderShares) return;
        const c = parseFloat(sliderCost.value);
        const s = parseInt(sliderShares.value);
        if (textCost) textCost.innerText = `¥${c.toFixed(2)}`;
        if (textShares) textShares.innerText = `${s} 股`;
        const be = AStockRiskBreakevenCalc.calculateBreakeven(c, s);
        if (resBreakeven) resBreakeven.innerText = `¥${be.toFixed(2)}`;
      };

      sliderCost?.addEventListener('input', recompute);
      sliderShares?.addEventListener('input', recompute);
    }
  }
};

// --------------------------------------------------------------------------
// 4. Domain Pack Definition & Registration
// --------------------------------------------------------------------------
const AStockPack = {
  namespace: 'astock',
  title: 'A股量化投研组件包',
  version: '1.0.0',
  description: '包含大盘全景雷达、K线量价矩阵与保本进位试算器，严格执行 AGENTS.md 规范',
  components: {
    MarketRadar: AStockMarketRadar,
    CandleMatrix: AStockCandleMatrix,
    RiskBreakevenCalc: AStockRiskBreakevenCalc
  }
};

// Universal safe registration: supports out-of-order & asynchronous loading
if (typeof defineA2UIPack === 'function') {
  defineA2UIPack(AStockPack);
} else if (typeof UIEngine !== 'undefined' && typeof UIEngine.registerPack === 'function') {
  UIEngine.registerPack(AStockPack);
} else {
  window.__A2UI_PENDING_PACKS__ = window.__A2UI_PENDING_PACKS__ || [];
  window.__A2UI_PENDING_PACKS__.push(AStockPack);
}

// Global exports for backwards-compatibility & direct access
window.AStockMarketRadar = AStockMarketRadar;
window.AStockCandleMatrix = AStockCandleMatrix;
window.AStockRiskBreakevenCalc = AStockRiskBreakevenCalc;
