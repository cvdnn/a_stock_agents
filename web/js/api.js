// -*- coding: utf-8 -*-
/**
 * web/js/api.js - A-Stock Quant Client API Service & SSE Streaming Layer
 * Provides unified interface to backend FastAPI endpoints with high-fidelity Mock fallback.
 */

const AStockAPI = {
  baseUrl: '',

  /**
   * Helper method for robust fetch with JSON response
   */
  async _fetchJSON(endpoint, options = {}) {
    try {
      const resp = await fetch(this.baseUrl + endpoint, {
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          ...options.headers
        },
        ...options
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
      }
      return await resp.json();
    } catch (err) {
      console.warn(`[AStockAPI] Fetch error for ${endpoint}, triggering fallback:`, err.message);
      return null;
    }
  },

  // =========================================================================
  // 1. Market Data APIs
  // =========================================================================

  async getMarketIndices() {
    const data = await this._fetchJSON('/api/market/indices');
    if (data && data.indices) return data;
    // Fallback Mock
    return {
      indices: [
        { name: "上证指数", code: "000001", market_type: "主板", price: 3426.56, change: 24.38, change_pct: 0.72, open: 3410.21, high: 3432.76, low: 3402.18, pre_close: 3402.18, turnover_amount: "5,281亿", sparkline: [3390, 3405, 3400, 3415, 3422, 3418, 3426.56] },
        { name: "深证成指", code: "399001", market_type: "深市", price: 10892.14, change: 116.24, change_pct: 1.08, open: 10780.32, high: 10912.65, low: 10775.90, pre_close: 10775.90, turnover_amount: "6,723亿", sparkline: [10750, 10780, 10820, 10800, 10860, 10892.14] },
        { name: "创业板指", code: "399006", market_type: "成长", price: 2289.76, change: 29.32, change_pct: 1.31, open: 2265.40, high: 2301.24, low: 2258.43, pre_close: 2260.44, turnover_amount: "2,890亿", sparkline: [2250, 2265, 2260, 2278, 2282, 2289.76] },
        { name: "科创50", code: "000688", market_type: "硬科技", price: 1012.35, change: 18.42, change_pct: 1.85, open: 995.12, high: 1018.60, low: 988.35, pre_close: 993.93, turnover_amount: "982亿", sparkline: [980, 992, 988, 1005, 1012.35] }
      ],
      timestamp: "2026-09-08 15:00:00"
    };
  },

  async getMarketSentiment() {
    const data = await this._fetchJSON('/api/market/sentiment');
    if (data && data.score) return data;
    return {
      score: 78,
      status_text: "78分 · 市场情绪亢温",
      total_turnover: "1.28万亿",
      turnover_growth: "(+12% 放量上攻)",
      up_count: 3348,
      down_count: 1105,
      limit_up_count: 86,
      limit_down_count: 6,
      flat_count: 892,
      sectors: [
        { name: "半导体/CPO算力", change_pct: 3.85, net_inflow: "+48.6亿" },
        { name: "人工智能/软件开发", change_pct: 3.12, net_inflow: "+32.4亿" },
        { name: "智能网联汽车链", change_pct: 1.68, net_inflow: "+15.2亿" }
      ],
      ai_summary: "大盘放量突破 3,420 点颈线压力位，科技成长共振主升，短线做多情绪充沛，建议顺应主线回踩介入。"
    };
  },

  async getMarketKline(code = '000001', period = 'day') {
    const data = await this._fetchJSON(`/api/market/kline?code=${encodeURIComponent(code)}&period=${encodeURIComponent(period)}`);
    if (data && data.klines) return data;
    return {
      code,
      name: code === '000001' ? '上证指数' : `标的 ${code}`,
      period,
      ma5: 3410.32,
      ma10: 3398.76,
      ma20: 3376.21,
      klines: [
        ["08-01", 3382.5, 3396.8, 3402.0, 3379.0, 46000],
        ["08-04", 3396.8, 3391.4, 3405.2, 3385.1, 43000],
        ["08-05", 3391.4, 3410.5, 3418.0, 3388.0, 49000],
        ["08-06", 3410.5, 3402.1, 3415.6, 3395.2, 44000],
        ["08-07", 3402.1, 3416.8, 3422.0, 3398.4, 48000],
        ["08-08", 3416.8, 3408.3, 3420.5, 3401.0, 42000],
        ["08-11", 3408.3, 3422.6, 3428.0, 3404.2, 51000],
        ["08-12", 3422.6, 3415.0, 3425.4, 3410.1, 46000],
        ["08-13", 3415.0, 3429.8, 3435.0, 3412.5, 53000],
        ["08-14", 3429.8, 3418.5, 3432.1, 3415.0, 47000],
        ["08-15", 3418.5, 3405.2, 3420.0, 3398.2, 45000],
        ["08-18", 3405.2, 3412.0, 3418.5, 3401.4, 43000],
        ["08-19", 3412.0, 3425.6, 3430.0, 3408.0, 49000],
        ["08-20", 3425.6, 3419.2, 3428.4, 3414.0, 46000],
        ["08-21", 3419.2, 3410.8, 3422.0, 3405.5, 44000],
        ["08-22", 3410.8, 3428.5, 3435.0, 3408.2, 52000],
        ["08-25", 3428.5, 3421.0, 3432.4, 3416.0, 48000],
        ["08-26", 3421.0, 3435.8, 3442.0, 3418.5, 56000],
        ["08-27", 3435.8, 3426.5, 3438.0, 3420.1, 50000],
        ["09-08", 3410.2, 3426.56, 3432.76, 3402.18, 52810]
      ]
    };
  },

  async getMarketRanks() {
    const data = await this._fetchJSON('/api/market/ranks');
    if (data && data.gainers) return data;
    return {
      gainers: [
        { rank: 1, code: "920002", name: "N万达轴承", price: 56.80, change_pct: 45.03, change_amount: 17.65 },
        { rank: 2, code: "301128", name: "聚能技术", price: 42.36, change_pct: 20.01, change_amount: 7.06 },
        { rank: 3, code: "688578", name: "艾力斯", price: 76.23, change_pct: 19.98, change_amount: 12.71 },
        { rank: 4, code: "602371", name: "北方华创", price: 432.50, change_pct: 10.02, change_amount: 39.32 },
        { rank: 5, code: "688981", name: "中芯国际", price: 98.76, change_pct: 9.21, change_amount: 8.29 }
      ],
      losers: [
        { rank: 1, code: "600811", name: "*ST东方", price: 1.23, change_pct: -5.76, change_amount: -0.08 },
        { rank: 2, code: "600555", name: "退市海创", price: 0.98, change_pct: -4.87, change_amount: -0.05 },
        { rank: 3, code: "002341", name: "ST新伦", price: 1.45, change_pct: -4.20, change_amount: -0.06 },
        { rank: 4, code: "002717", name: "国航远洋", price: 2.36, change_pct: -3.83, change_amount: -0.09 },
        { rank: 5, code: "600765", name: "中航重机", price: 12.68, change_pct: -3.62, change_amount: -0.48 }
      ],
      northbound: [
        { rank: 1, code: "300750", name: "宁德时代", price: 328.56, change_pct: 2.46, net_inflow: "12.36" },
        { rank: 2, code: "600519", name: "贵州茅台", price: 1502.00, change_pct: 1.83, net_inflow: "8.72" },
        { rank: 3, code: "600036", name: "招商银行", price: 42.36, change_pct: 1.26, net_inflow: "6.58" },
        { rank: 4, code: "601318", name: "中国平安", price: 56.80, change_pct: 0.98, net_inflow: "5.21" },
        { rank: 5, code: "601012", name: "隆基绿能", price: 24.12, change_pct: 2.12, net_inflow: "4.76" }
      ],
      sectors_rank: [
        { name: "半导体", change: "+4.23%" },
        { name: "光伏设备", change: "+3.87%" },
        { name: "消费电子", change: "+3.45%" },
        { name: "电源设备", change: "+3.12%" },
        { name: "软件开发", change: "+2.96%" },
        { name: "医药生物", change: "+2.83%" },
        { name: "电子元件", change: "+2.67%" },
        { name: "通信设备", change: "+2.54%" },
        { name: "计算机应用", change: "+2.31%" },
        { name: "家用电器", change: "+2.18%" }
      ],
      news: [
        { time: "09:32", title: "外资连续3日净买入A股 重点加仓科技板块" },
        { time: "09:28", title: "证监会：加大对量化交易监督管理力度" },
        { time: "09:15", title: "半导体板块持续走强 多股涨停" },
        { time: "08:50", title: "央行开展逆回购操作 释放流动性信号" },
        { time: "08:36", title: "重大政策利好 促进资本市场高质量发展" }
      ],
      hot_concepts: ["AI", "半导体", "机器人", "新能源", "数字经济", "军工", "医药", "芯片", "消费"]
    };
  },

  // =========================================================================
  // 2. Portfolio & Investment APIs
  // =========================================================================

  async getPortfolioOverview() {
    const data = await this._fetchJSON('/api/portfolio/overview');
    if (data && data.total_assets) return data;
    return {
      total_assets: "¥454.24万",
      position_market_value: "¥328.56万",
      position_ratio: 72.3,
      available_cash: "¥125.68万",
      cash_ratio: 27.7,
      today_pnl: "+¥3.86万",
      today_pnl_pct: 1.18,
      total_return_pct: 36.78,
      annualized_return_pct: 18.24,
      risk_status: "账户风控正常",
      cushion_space: "+11.8%",
      cushion_desc: "当前组合距离 T0 警戒线(-3%)平均缓冲空间为 +11.8%；全部标的已建立最低保本卖出价与分级止损预案，无触及预警。",
      holdings: [
        { code: "300750", name: "宁德时代", ratio_pct: 35.0, return_pct: 12.4 },
        { code: "688981", name: "中芯国际", ratio_pct: 25.0, return_pct: 8.6 },
        { code: "688041", name: "海光信息", ratio_pct: 20.0, return_pct: 15.2 }
      ],
      donut_data: [
        { name: "股票持仓", value: 328.56, color: "#1677FF" },
        { name: "现金储备", value: 125.68, color: "#4096FF" }
      ]
    };
  },

  async getPortfolioAnalysis() {
    const data = await this._fetchJSON('/api/portfolio/analysis');
    if (data && data.sharpe_ratio) return data;
    return {
      sharpe_ratio: 1.84,
      win_rate: 68.5,
      win_loss_detail: "54 胜 / 25 负 (79笔)",
      max_drawdown: -8.24,
      pl_ratio: 2.41,
      annualized_return: 42.15,
      total_return: 34.28,
      benchmark_excess: 25.63,
      equity_curve: {
        strategy: [1.00, 1.02, 1.01, 1.05, 1.08, 1.06, 1.12, 1.15, 1.18, 1.16, 1.22, 1.25, 1.28, 1.30, 1.34],
        benchmark: [1.00, 1.01, 0.99, 1.02, 1.03, 1.01, 1.04, 1.05, 1.04, 1.02, 1.05, 1.06, 1.07, 1.08, 1.09],
        labels: ["3月", "4月", "5月", "6月", "7月", "8月", "9月"]
      },
      monthly_pnl: [
        { month: "1月", pnl: 4.8 },
        { month: "2月", pnl: 6.2 },
        { month: "3月", pnl: -1.5 },
        { month: "4月", pnl: 5.4 },
        { month: "5月", pnl: 3.1 },
        { month: "6月", pnl: 7.8 },
        { month: "7月", pnl: -2.1 },
        { month: "8月", pnl: 8.6 }
      ],
      attributions: [
        { name: "5A多因子旋转选股策略", contrib_pct: 15.42, share_pct: 45, color: "#1677FF" },
        { name: "主板趋势回踩与波段防守", contrib_pct: 10.28, share_pct: 30, color: "#52C41A" },
        { name: "MACD水下二次金叉战法", contrib_pct: 6.17, share_pct: 18, color: "#FA8C16" },
        { name: "退哥短线连板龙头首阴", contrib_pct: 2.41, share_pct: 7, color: "#722ED1" }
      ],
      positions: [
        { code: "300750.SZ", name: "宁德时代", shares: 1000, cost: 315.00, price: 328.56, pnl_pct: 4.30, pnl_amount: "+¥13,560", breakeven_price: 315.68, status: "🟢 正常持仓", strategy: "5A多因子" },
        { code: "688981.SH", name: "中芯国际", shares: 2000, cost: 95.20, price: 98.60, pnl_pct: 3.57, pnl_amount: "+¥6,800", breakeven_price: 95.41, status: "🟢 突破持股", strategy: "趋势突破" },
        { code: "688041.SH", name: "海光信息", shares: 1500, cost: 142.00, price: 145.20, pnl_pct: 2.25, pnl_amount: "+¥4,800", breakeven_price: 142.31, status: "🟢 水下金叉验底", strategy: "MACD金叉" },
        { code: "600519.SH", name: "贵州茅台", shares: 200, cost: 1480.00, price: 1465.00, pnl_pct: -1.01, pnl_amount: "-¥3,000", breakeven_price: 1483.21, status: "🟡 靠近T0警戒线", strategy: "价值防守" }
      ]
    };
  },

  // =========================================================================
  // 3. Watchlist & Stock Details APIs
  // =========================================================================

  async getWatchlist(activeCode = '300750') {
    const data = await this._fetchJSON(`/api/watchlist?active_code=${encodeURIComponent(activeCode)}`);
    if (data && data.stocks) return data;
    return {
      stocks: [
        { code: "600519", name: "贵州茅台", price: 1502.00, change_pct: 1.26, net_inflow: "+8.72亿", status: "持有", pool_type: "holding", ratio: "持仓 15%" },
        { code: "300750", name: "宁德时代", price: 328.56, change_pct: 2.77, net_inflow: "+12.36亿", status: "持有", pool_type: "holding", ratio: "持仓 35%" },
        { code: "688981", name: "中芯国际", price: 98.60, change_pct: 4.32, net_inflow: "+12.36亿", status: "持有", pool_type: "holding", ratio: "持仓 25%" },
        { code: "688041", name: "海光信息", price: 145.20, change_pct: 3.87, net_inflow: "+8.76亿", status: "持有", pool_type: "holding", ratio: "持仓 20%" },
        { code: "002594", name: "比亚迪", price: 254.30, change_pct: 3.21, net_inflow: "+5.42亿", status: "自选", pool_type: "watchlist" },
        { code: "601318", name: "中国平安", price: 56.80, change_pct: 0.98, net_inflow: "+5.21亿", status: "自选", pool_type: "watchlist" },
        { code: "600036", name: "招商银行", price: 42.36, change_pct: 1.42, net_inflow: "+6.58亿", status: "自选", pool_type: "watchlist" },
        { code: "300059", name: "东方财富", price: 22.47, change_pct: -0.67, net_inflow: "-2.15亿", status: "自选", pool_type: "watchlist" },
        { code: "601899", name: "紫金矿业", price: 18.76, change_pct: 0.86, net_inflow: "+1.84亿", status: "自选", pool_type: "watchlist" },
        { code: "000651", name: "格力电器", price: 34.12, change_pct: 0.59, net_inflow: "+0.96亿", status: "关注", pool_type: "focus" },
        { code: "002415", name: "海康威视", price: 28.36, change_pct: -0.35, net_inflow: "-1.20亿", status: "关注", pool_type: "focus" },
        { code: "002475", name: "立讯精密", price: 42.78, change_pct: 1.71, net_inflow: "+3.15亿", status: "关注", pool_type: "focus" },
        { code: "600030", name: "中信证券", price: 27.65, change_pct: 1.10, net_inflow: "+2.45亿", status: "关注", pool_type: "focus" },
        { code: "600900", name: "长江电力", price: 28.42, change_pct: 0.28, net_inflow: "+1.10亿", status: "关注", pool_type: "focus" }
      ],
      custom_indices: [
        { name: "自选等权组合指数", change_pct: 2.18, val: 1248.60, sparkline: [1220, 1228, 1235, 1230, 1242, 1248.60] },
        { name: "半导体科技指数", change_pct: 3.62, val: 3120.45, sparkline: [3010, 3045, 3080, 3065, 3105, 3120.45] }
      ],
      active_stock_detail: {
        code: activeCode,
        name: activeCode === '300750' ? "宁德时代" : (activeCode === '688981' ? "中芯国际" : `标的 ${activeCode}`),
        tags: ["深股通", "融资融券", "MSCI"],
        price: activeCode === '300750' ? 328.56 : 98.60,
        change: activeCode === '300750' ? 8.39 : 4.08,
        change_pct: activeCode === '300750' ? 2.77 : 4.32,
        open: activeCode === '300750' ? 322.00 : 95.00,
        high: activeCode === '300750' ? 332.60 : 99.20,
        low: activeCode === '300750' ? 318.45 : 94.60,
        pre_close: activeCode === '300750' ? 320.17 : 94.52,
        volume: "42.36万手",
        amount: "138.66亿元",
        industry: activeCode === '300750' ? "电池" : "半导体",
        concepts: activeCode === '300750' ? "新能源车、锂电池、固态电池、储能" : "国家大基金、芯片制造、科创板",
        circ_market_val: "7,654.32亿",
        total_market_val: "9,832.17亿",
        pe_ttm: 18.76,
        pb: 4.32,
        high_52w: 332.60,
        low_52w: 169.80,
        events: [
          { date: "2026-08-26 · 机构调研", content: "近30家顶级机构现场调研，关注全固态电池量产进度" },
          { date: "2026-08-22 · 分红送转", content: "10派5.00元（含税）除权除息完成" },
          { date: "2026-08-15 · 业绩预告", content: "预计上半年归母净利润同比增长 20%-30%" },
          { date: "2026-08-10 · 限售解禁", content: "解禁股数 1.25 亿股，占总股本 2.3%，实际抛压有限" }
        ],
        capital_flow: {
          main_net: "12.36亿",
          super_large: "7.23亿 (4.96%)",
          large: "5.13亿 (3.49%)",
          medium: "-4.21亿 (-2.87%)",
          small: "-8.15亿 (-5.58%)",
          donut: [
            { name: "超大单", value: 45, color: "#F5222D" },
            { name: "大单", value: 25, color: "#FF7875" },
            { name: "中单", value: 18, color: "#52C41A" },
            { name: "小单", value: 12, color: "#86909C" }
          ],
          trend: [2.5, 4.8, -1.2, 8.6, 12.36],
          dates: ["08-21", "08-22", "08-25", "08-26", "08-27"]
        },
        northbound: { sh_flow: "3.12亿", sz_flow: "2.11亿" },
        main_control: { holding: "12.76亿", ratio: "8.46%", concentration: "71.26%", score: 85 },
        ai_conclusion: {
          summary: "当前处于上升通道，量比配合良好，主力资金持续净流入，短期有望继续走强，关注 320.00元 支撑位，若放量突破 332.00元，有望挑战 350.00元 压力位。",
          tags: ["技术面偏多", "资金流入明显", "机构看好"],
          support_price: 320.00,
          resistance_price: 332.00
        },
        klines: [
          ["08-01", 310.2, 312.4, 315.0, 308.5, 32000],
          ["08-04", 312.4, 314.8, 318.0, 310.2, 36000],
          ["08-05", 314.8, 311.2, 316.5, 309.0, 31000],
          ["08-06", 311.2, 316.5, 320.0, 310.5, 41000],
          ["08-07", 316.5, 315.0, 318.2, 313.4, 35000],
          ["08-08", 315.0, 318.2, 322.0, 314.0, 39000],
          ["08-11", 318.2, 321.0, 325.4, 317.0, 44000],
          ["08-12", 321.0, 319.4, 323.0, 316.5, 38000],
          ["08-13", 319.4, 324.5, 328.0, 318.2, 48000],
          ["08-14", 324.5, 322.8, 326.0, 320.1, 40000],
          ["08-15", 322.8, 318.5, 324.0, 316.0, 36000],
          ["08-18", 318.5, 322.0, 325.2, 317.4, 39000],
          ["08-19", 322.0, 326.4, 330.0, 321.0, 47000],
          ["08-20", 326.4, 324.0, 328.5, 322.0, 41000],
          ["08-21", 324.0, 320.5, 325.0, 318.6, 37000],
          ["08-22", 320.5, 325.2, 329.0, 319.5, 45000],
          ["08-25", 325.2, 322.0, 326.8, 320.0, 39000],
          ["08-26", 322.0, 328.56, 332.6, 318.45, 42360]
        ]
      }
    };
  },

  // =========================================================================
  // 4. Realtime Monitor APIs
  // =========================================================================

  async getMonitorStream() {
    const data = await this._fetchJSON('/api/monitor/stream');
    if (data && data.events) return data;
    return {
      latency_ms: 28,
      is_monitoring: true,
      events: [
        { type: "buy", tag: "买入信号", code: "688981", name: "中芯国际", time: "10:20:15", desc: "放量突破前高平台 ¥98.20，5分钟大单净买入 1.25 亿元，触发趋势突破买点" },
        { type: "main", tag: "主力异动", code: "300750", name: "宁德时代", time: "10:08:42", desc: "出现万手多笔大单密集吸筹，主力控盘评分上升至 85 分" },
        { type: "risk", tag: "风控巡检", code: "002475", name: "立讯精密", time: "09:48:10", desc: "盘中回踩 MA20 均线，距离 T0 警戒线(-3%)仍有 0.9% 安全缓冲" }
      ],
      strategies: [
        { name: "趋势突破策略", status: "监控中", desc: "监控中 · 3只标的", enabled: true },
        { name: "行业主线轮动", status: "在线", desc: "本周超额 +2.36%", enabled: true },
        { name: "实战保本与止损", status: "全仓风控在线", desc: "全仓风控在线", enabled: true },
        { name: "自选极速异动", status: "在线", desc: "毫秒级深度行情", enabled: true }
      ]
    };
  },

  // =========================================================================
  // 5. Chat Sessions APIs (Backend SQLite)
  // =========================================================================

  async listSessions(limit = 30, offset = 0) {
    const data = await this._fetchJSON(`/api/chat/sessions?limit=${limit}&offset=${offset}`);
    if (data && Array.isArray(data.sessions)) {
      return data.sessions;
    }
    return [];
  },

  async createSession(title = '新投研对话', model = 'mock', meta = {}) {
    return await this._fetchJSON('/api/chat/sessions', {
      method: 'POST',
      body: JSON.stringify({ title, model, meta })
    });
  },

  async deleteSession(sessionId) {
    return await this._fetchJSON(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE'
    });
  },

  // =========================================================================
  // 6. AIChat Native SSE Streaming Protocol
  // =========================================================================

  /**
   * Stream completions from backend ReAct runner via SSE
   */
  async streamChatCompletions(message, sessionId, model = 'mock', callbacks = {}) {
    const {
      onStart = () => {},
      onThought = () => {},
      onToolStart = () => {},
      onToolComplete = () => {},
      onDelta = () => {},
      onRiskCard = () => {},
      onDone = () => {},
      onError = () => {}
    } = callbacks;

    try {
      const resp = await fetch(this.baseUrl + '/api/chat/completions/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          model,
          tools_enabled: true
        })
      });

      if (!resp.ok) {
        throw new Error(`SSE Connection failed with HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete trailing line

        let currentEvent = 'message';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.slice(6).trim();
          } else if (trimmed.startsWith('data:')) {
            const rawData = trimmed.slice(5).trim();
            try {
              const parsed = JSON.parse(rawData);
              
              if (currentEvent === 'conversation_start') {
                onStart(parsed);
              } else if (currentEvent === 'thought') {
                onThought(parsed.thought || parsed.content || '');
              } else if (currentEvent === 'tool_call_start') {
                onToolStart(parsed);
              } else if (currentEvent === 'tool_call_complete') {
                onToolComplete(parsed);
              } else if (currentEvent === 'content_delta') {
                onDelta(parsed.delta || parsed.content || parsed.text || '');
              } else if (currentEvent === 'risk_card') {
                onRiskCard(parsed);
              } else if (currentEvent === 'done') {
                onDone(parsed);
              }
            } catch (jsonErr) {
              // Raw text chunk fallback
              if (currentEvent === 'content_delta') {
                onDelta(rawData);
              }
            }
          }
        }
      }

      onDone({ completed: true });
      return true;
    } catch (err) {
      console.warn('[AStockAPI] SSE Streaming failed or disconnected:', err.message);
      onError(err);
      return false;
    }
  }
};

window.AStockAPI = AStockAPI;
