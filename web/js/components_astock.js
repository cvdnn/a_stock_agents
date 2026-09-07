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
    const list = props.indices || [
      { name: '上证指数', price: 3426.56, change_pct: 0.72 },
      { name: '深证成指', price: 10892.14, change_pct: 1.08 },
      { name: '创业板指', price: 2289.76, change_pct: 1.31 }
    ];

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
    const volume = props.total_volume || '1.28万亿元';
    const sentiment = props.sentiment?.text || '78分 贪婪 / 亢温';

    return `
      <div class="radar-expanded-dashboard">
        <div class="radar-expanded-header">
          <h4>📊 核心大盘指数走势与资金情绪</h4>
          <div style="display:flex; gap:8px;">
            <span class="badge-tag-green" style="font-size:11px;">两市放量 ${volume}</span>
            <span class="a2ui-stage-badge done" style="font-size:11px;">情绪 ${sentiment}</span>
          </div>
        </div>
        <div class="sparkline-row">
          <div class="sparkline-item">
            <div class="sparkline-meta">
              <strong style="color:#1D2129;">上证指数 3,426.56</strong>
              <span style="color:#F5222D; font-weight:700;">+0.72%</span>
            </div>
            <canvas id="a2ui_spark_sh" width="180" height="40" style="width:100%; height:40px;"></canvas>
          </div>
          <div class="sparkline-item">
            <div class="sparkline-meta">
              <strong style="color:#1D2129;">深证成指 10,892.14</strong>
              <span style="color:#F5222D; font-weight:700;">+1.08%</span>
            </div>
            <canvas id="a2ui_spark_sz" width="180" height="40" style="width:100%; height:40px;"></canvas>
          </div>
          <div class="sparkline-item">
            <div class="sparkline-meta">
              <strong style="color:#1D2129;">创业板指 2,289.76</strong>
              <span style="color:#F5222D; font-weight:700;">+1.31%</span>
            </div>
            <canvas id="a2ui_spark_cy" width="180" height="40" style="width:100%; height:40px;"></canvas>
          </div>
        </div>
      </div>
    `;
  },

  onMounted(container, props = {}, mode) {
    if (mode === 'expanded' && typeof FinancialCharts !== 'undefined') {
      setTimeout(() => {
        FinancialCharts.drawSparkline('a2ui_spark_sh', [3390, 3405, 3400, 3415, 3422, 3426.56], true);
        FinancialCharts.drawSparkline('a2ui_spark_sz', [10750, 10780, 10820, 10800, 10860, 10892.14], true);
        FinancialCharts.drawSparkline('a2ui_spark_cy', [2250, 2265, 2260, 2278, 2282, 2289.76], true);
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

  renderSkeleton(mode) {
    if (mode === 'compact') {
      return `<div class="skeleton-shimmer candle-skeleton compact"></div>`;
    }
    return `<div class="skeleton-shimmer candle-skeleton expanded"></div>`;
  },

  renderCompact(props = {}) {
    const benchmark = props.benchmark || '上证指数 (000001)';
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
        const klines = (typeof generateKlines === 'function') 
          ? generateKlines(3400, 28, 0.008)
          : [
              ['08-20', 3390, 3405, 3415, 3385, 32000],
              ['08-21', 3405, 3400, 3410, 3392, 34000],
              ['08-22', 3400, 3418, 3425, 3398, 41000],
              ['08-25', 3418, 3426, 3435, 3412, 45000]
            ];
        FinancialCharts.drawCandlestickChart('a2ui_candle_canvas', klines, { showVolume: true });
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
    const cost = props.cost || 320.0;
    const shares = props.shares || 1000;
    const breakeven = this.calculateBreakeven(cost, shares);
    const t0 = (cost * 0.97).toFixed(2);
    const t1 = (cost * 0.95).toFixed(2);
    const t2 = (cost * 0.92).toFixed(2);

    return `
      <div class="risk-iron-card" style="margin-top:6px;">
        <div class="risk-iron-header">🛡️ 实战交易三原则（合规风控指令单）</div>
        <div class="risk-iron-grid">
          <div class="risk-pill-box">
            <div class="risk-pill-title">最低保本卖出价</div>
            <div class="risk-pill-val tabular-nums" style="color:#F5222D; font-weight:700;">¥${breakeven.toFixed(2)} (ceil进位)</div>
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
    const cost = props.cost || 320.0;
    const shares = props.shares || 1000;
    const breakeven = this.calculateBreakeven(cost, shares);

    return `
      <div class="calc-expanded-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h4 style="margin:0; font-size:14px; color:#1D2129;">🛡️ 保本卖出价动态滑块试算器 (税费精算·向上进位至分)</h4>
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
          <span style="font-size:11px; color:#86909C;">(已计入全部税费，强制 ceil 向上进位)</span>
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
// 4. Auto-register all domain components into UIEngine
// --------------------------------------------------------------------------
if (typeof UIEngine !== 'undefined') {
  UIEngine.registerComponent('MarketRadar', AStockMarketRadar);
  UIEngine.registerComponent('CandleMatrix', AStockCandleMatrix);
  UIEngine.registerComponent('RiskBreakevenCalc', AStockRiskBreakevenCalc);
}
