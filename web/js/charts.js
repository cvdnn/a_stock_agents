// A-Stock Quant UI Canvas Charting Engine
// Zero external dependencies, crisp retina-ready rendering, high-performance financial charts

class FinancialCharts {
  static setupCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    return { ctx, width: rect.width, height: rect.height, dpr };
  }

  // 1. Sparkline (used in Index cards)
  static drawSparkline(canvasId, dataPoints, isPositive = true) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!dataPoints || dataPoints.length < 2) return;

    const min = Math.min(...dataPoints);
    const max = Math.max(...dataPoints);
    const range = max - min || 1;
    const padding = 4;
    const usableH = height - padding * 2;
    const stepX = width / (dataPoints.length - 1);

    const lineColor = isPositive ? '#F5222D' : '#52C41A';
    const gradColorStart = isPositive ? 'rgba(245, 34, 45, 0.20)' : 'rgba(82, 196, 26, 0.20)';
    const gradColorEnd = isPositive ? 'rgba(245, 34, 45, 0.0)' : 'rgba(82, 196, 26, 0.0)';

    // Path for line
    ctx.beginPath();
    dataPoints.forEach((val, i) => {
      const x = i * stepX;
      const y = height - padding - ((val - min) / range) * usableH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    // Stroke line
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 1.8;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // Fill gradient area below line
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, 0, 0, height);
    grad.addColorStop(0, gradColorStart);
    grad.addColorStop(1, gradColorEnd);
    ctx.fillStyle = grad;
    ctx.fill();
  }

  // 2. Candlestick + Volume + MA Lines Chart
  static drawCandlestickChart(canvasId, klines, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!klines || klines.length === 0) return;

    ctx.clearRect(0, 0, width, height);

    const showVolume = options.showVolume !== false;
    const mainHeight = showVolume ? height * 0.72 : height - 20;
    const volHeight = showVolume ? height * 0.22 : 0;
    const volTop = height - volHeight - 8;
    const paddingLeft = 10;
    const paddingRight = 55;
    const paddingTop = 20;
    const usableWidth = width - paddingLeft - paddingRight;

    // Prices calculation
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVolume = 0;

    klines.forEach(item => {
      // item: [date, open, close, high, low, volume]
      const [, open, close, high, low, vol] = item;
      if (low < minPrice) minPrice = low;
      if (high > maxPrice) maxPrice = high;
      if (vol > maxVolume) maxVolume = vol;
    });

    const priceRange = maxPrice - minPrice || 1;
    const stepX = usableWidth / klines.length;
    const barWidth = Math.max(2, stepX * 0.65);

    // Calculate MA5, MA10, MA20
    const calcMA = (period) => {
      return klines.map((item, idx, arr) => {
        if (idx < period - 1) return null;
        let sum = 0;
        for (let j = 0; j < period; j++) sum += arr[idx - j][2]; // close
        return sum / period;
      });
    };
    const ma5 = calcMA(5);
    const ma10 = calcMA(10);
    const ma20 = calcMA(20);

    // Coordinate conversion
    const getY = (price) => {
      return paddingTop + (mainHeight - paddingTop) * (1 - (price - minPrice) / priceRange);
    };

    // Draw Background Grid Lines
    ctx.strokeStyle = '#F0F2F5';
    ctx.lineWidth = 1;
    const gridRows = 4;
    for (let r = 0; r <= gridRows; r++) {
      const y = paddingTop + ((mainHeight - paddingTop) / gridRows) * r;
      ctx.beginPath();
      ctx.moveTo(paddingLeft, y);
      ctx.lineTo(width - paddingRight, y);
      ctx.stroke();

      // Right axis price label
      const p = maxPrice - (priceRange / gridRows) * r;
      ctx.fillStyle = '#8C9BAE';
      ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.textAlign = 'left';
      ctx.fillText(p.toFixed(2), width - paddingRight + 6, y + 3);
    }

    // Draw Candlesticks & Volume bars
    klines.forEach((item, i) => {
      const [date, open, close, high, low, vol] = item;
      const x = paddingLeft + i * stepX + stepX / 2;
      const isUp = close >= open;
      const color = isUp ? '#F5222D' : '#52C41A';

      // 1. High-Low Wick
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.moveTo(x, getY(high));
      ctx.lineTo(x, getY(low));
      ctx.stroke();

      // 2. Candle Body
      const openY = getY(open);
      const closeY = getY(close);
      const bodyTop = Math.min(openY, closeY);
      const bodyHeight = Math.max(1.5, Math.abs(openY - closeY));

      ctx.fillStyle = color;
      ctx.fillRect(x - barWidth / 2, bodyTop, barWidth, bodyHeight);

      // 3. Volume Bar
      if (showVolume && maxVolume > 0) {
        const vH = (vol / maxVolume) * (volHeight - 10);
        const vY = height - 4 - vH;
        ctx.fillStyle = isUp ? 'rgba(245, 34, 45, 0.7)' : 'rgba(82, 196, 26, 0.7)';
        ctx.fillRect(x - barWidth / 2, vY, barWidth, vH);
      }
    });

    // Draw MA lines helper
    const drawLine = (data, color) => {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      let started = false;
      data.forEach((val, i) => {
        if (val === null) return;
        const x = paddingLeft + i * stepX + stepX / 2;
        const y = getY(val);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();
    };

    drawLine(ma5, '#FF7A45');   // MA5 Orange
    drawLine(ma10, '#13C2C2');  // MA10 Cyan
    drawLine(ma20, '#722ED1');  // MA20 Purple

    // Volume label
    if (showVolume) {
      ctx.fillStyle = '#8C9BAE';
      ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.textAlign = 'left';
      ctx.fillText('成交量', paddingLeft, volTop + 10);
      ctx.fillText((maxVolume / 10000).toFixed(0) + '万手', width - paddingRight + 6, volTop + 12);
    }
  }

  // 3. Semi-circular Gauge Meter (for 市场情绪 & 主力控盘度)
  static drawGauge(canvasId, value, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);

    ctx.clearRect(0, 0, width, height);

    const min = options.min || 0;
    const max = options.max || 100;
    const percent = Math.min(1, Math.max(0, (value - min) / (max - min)));

    const cx = width / 2;
    const cy = height * 0.82;
    const radius = Math.min(width * 0.40, height * 0.70);
    const strokeWidth = options.strokeWidth || 8;

    const startAngle = Math.PI * 0.85;
    const endAngle = Math.PI * 2.15;
    const totalAngle = endAngle - startAngle;

    // 1. 底层灰色轨道
    ctx.beginPath();
    ctx.arc(cx, cy, radius, startAngle, endAngle);
    ctx.strokeStyle = '#F0F2F5';
    ctx.lineWidth = strokeWidth;
    ctx.lineCap = 'round';
    ctx.stroke();

    // 2. 彩虹/主色刻度弧环
    const currentAngle = startAngle + totalAngle * percent;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, startAngle, currentAngle);

    const rainbowGrad = ctx.createLinearGradient(cx - radius, cy, cx + radius, cy);
    if (options.colorType === 'control') {
      rainbowGrad.addColorStop(0, '#52C41A');
      rainbowGrad.addColorStop(0.5, '#13C2C2');
      rainbowGrad.addColorStop(1, '#1677FF');
    } else {
      rainbowGrad.addColorStop(0, '#52C41A');
      rainbowGrad.addColorStop(0.35, '#73D13D');
      rainbowGrad.addColorStop(0.65, '#FAAD14');
      rainbowGrad.addColorStop(0.85, '#FA541C');
      rainbowGrad.addColorStop(1, '#F5222D');
    }

    ctx.strokeStyle = rainbowGrad;
    ctx.lineWidth = strokeWidth;
    ctx.lineCap = 'round';
    ctx.stroke();

    // 3. 指示游标小点
    const pinX = cx + Math.cos(currentAngle) * radius;
    const pinY = cy + Math.sin(currentAngle) * radius;

    ctx.beginPath();
    ctx.arc(pinX, pinY, strokeWidth * 0.6, 0, Math.PI * 2);
    ctx.fillStyle = '#FFFFFF';
    ctx.shadowColor = 'rgba(0, 0, 0, 0.2)';
    ctx.shadowBlur = 3;
    ctx.fill();
    ctx.shadowBlur = 0;

    ctx.beginPath();
    ctx.arc(pinX, pinY, strokeWidth * 0.35, 0, Math.PI * 2);
    ctx.fillStyle = '#1677FF';
    ctx.fill();

    // 4. 中心标题与数值 (如 主力控盘度 68.32%)
    const title = options.centerTitle || '主力控盘度';
    const valText = options.centerValue || `${value}%`;

    ctx.fillStyle = '#86909C';
    ctx.font = '10.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(title, cx, cy - 22);

    ctx.fillStyle = '#1D2129';
    ctx.font = 'bold 17px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
    ctx.fillText(valText, cx, cy - 3);
  }

  // 4. Donut Chart (for 资金流向分布 & 北向资金)
  static drawDonutChart(canvasId, segments, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);

    ctx.clearRect(0, 0, width, height);

    const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
    const cx = width / 2;
    const cy = height / 2;
    const outerRadius = Math.min(cx, cy) - 5;
    const innerRadius = outerRadius * (options.innerRatio || 0.72);

    let startAngle = -Math.PI / 2;

    segments.forEach(seg => {
      const sliceAngle = (seg.value / total) * (Math.PI * 2);
      const endAngle = startAngle + sliceAngle;

      ctx.beginPath();
      ctx.arc(cx, cy, outerRadius, startAngle, endAngle);
      ctx.arc(cx, cy, innerRadius, endAngle, startAngle, true);
      ctx.closePath();
      ctx.fillStyle = seg.color;
      ctx.fill();

      startAngle = endAngle;
    });

    // Center Text 支持多行渲染
    if (Array.isArray(options.centerLines) && options.centerLines.length > 0) {
      const lines = options.centerLines;
      const totalH = lines.length * 13;
      let startY = cy - totalH / 2 + 6;
      lines.forEach(line => {
        ctx.fillStyle = line.color || '#86909C';
        const weight = line.bold ? 'bold ' : '';
        const size = line.size || 10.5;
        ctx.font = `${weight}${size}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(line.text, cx, startY);
        startY += (size + 3);
      });
    } else if (options.centerTitle || options.centerValue) {
      ctx.fillStyle = '#86909C';
      ctx.font = '10.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      if (options.centerTitle) {
        ctx.fillText(options.centerTitle, cx, cy - 8);
      }
      ctx.fillStyle = options.centerValueColor || '#1D2129';
      ctx.font = 'bold 13px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      if (options.centerValue) {
        ctx.fillText(options.centerValue, cx, cy + 8);
      }
    }
  }

  // 5. Multi-line Trend Chart (for 近5日资金流向: 主力 vs 散户)
  static drawMultiLine(canvasId, labels, series, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);

    ctx.clearRect(0, 0, width, height);

    const padding = { top: 12, right: 12, bottom: 20, left: 34 };
    const usableW = width - padding.left - padding.right;
    const usableH = height - padding.top - padding.bottom;

    let allVals = [];
    series.forEach(s => allVals.push(...s.data));
    const minVal = options.min != null ? options.min : Math.min(-20, ...allVals);
    const maxVal = options.max != null ? options.max : Math.max(20, ...allVals);
    const valRange = maxVal - minVal || 1;

    const getY = (val) => padding.top + usableH * (1 - (val - minVal) / valRange);
    const getX = (idx) => padding.left + (idx / Math.max(1, labels.length - 1)) * usableW;

    // Y Axis Labels & Grid
    const yTicks = options.yTicks || [
      { val: maxVal, text: `${maxVal}亿` },
      { val: maxVal / 2, text: `${Math.round(maxVal / 2)}亿` },
      { val: 0, text: '0' },
      { val: minVal / 2, text: `${Math.round(minVal / 2)}亿` },
      { val: minVal, text: `${minVal}亿` }
    ];

    ctx.fillStyle = '#86909C';
    ctx.font = '9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    yTicks.forEach(tick => {
      const y = getY(tick.val);
      ctx.fillText(tick.text, padding.left - 4, y);

      // Grid line
      ctx.beginPath();
      ctx.strokeStyle = tick.val === 0 ? '#C9CDD4' : '#F0F2F5';
      ctx.lineWidth = 1;
      if (tick.val === 0) ctx.setLineDash([3, 3]);
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();
      ctx.setLineDash([]);
    });

    // Draw Lines
    series.forEach(s => {
      ctx.beginPath();
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 1.8;
      s.data.forEach((val, i) => {
        const x = getX(i);
        const y = getY(val);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      // Points
      s.data.forEach((val, i) => {
        const x = getX(i);
        const y = getY(val);
        ctx.beginPath();
        ctx.arc(x, y, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = '#FFFFFF';
        ctx.fill();
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 1.8;
        ctx.stroke();
      });
    });

    // X Axis Labels
    ctx.fillStyle = '#86909C';
    ctx.font = '9.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    labels.forEach((label, i) => {
      ctx.fillText(label, getX(i), height - 15);
    });
  }

  // 6. Net Inflow Bar Chart (for 近5日北向净买入 / 主力持仓变化)
  static drawBarChart(canvasId, labels, values, options = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);

    ctx.clearRect(0, 0, width, height);

    const padding = { top: 10, right: 10, bottom: 20, left: options.paddingLeft || 30 };
    const usableW = width - padding.left - padding.right;
    const usableH = height - padding.top - padding.bottom;

    const minVal = options.min != null ? options.min : Math.min(0, ...values);
    const maxVal = options.max != null ? options.max : Math.max(0, ...values);
    const range = maxVal - minVal || 1;

    const zeroY = padding.top + usableH * (1 - (0 - minVal) / range);
    const stepX = usableW / labels.length;
    const barW = Math.max(7, Math.min(18, stepX * 0.5));

    // Y Axis Ticks
    if (Array.isArray(options.yTicks)) {
      ctx.fillStyle = '#86909C';
      ctx.font = '9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      options.yTicks.forEach(tick => {
        const y = padding.top + usableH * (1 - (tick.val - minVal) / range);
        ctx.fillText(tick.text, padding.left - 4, y);
        ctx.beginPath();
        ctx.strokeStyle = tick.val === 0 ? '#C9CDD4' : '#F4F5F8';
        ctx.lineWidth = 1;
        if (tick.val === 0) ctx.setLineDash([2, 2]);
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();
        ctx.setLineDash([]);
      });
    } else {
      // Default Zero line
      ctx.beginPath();
      ctx.strokeStyle = '#E5E6EB';
      ctx.lineWidth = 1;
      ctx.moveTo(padding.left, zeroY);
      ctx.lineTo(width - padding.right, zeroY);
      ctx.stroke();
    }

    values.forEach((val, i) => {
      const x = padding.left + i * stepX + (stepX - barW) / 2;
      const isPositive = val >= 0;
      const y = padding.top + usableH * (1 - (val - minVal) / range);
      const barH = Math.max(2, Math.abs(y - zeroY));
      const topY = isPositive ? y : zeroY;

      if (options.barColor) {
        ctx.fillStyle = options.barColor;
      } else {
        ctx.fillStyle = isPositive ? '#F5222D' : '#52C41A';
      }
      ctx.fillRect(x, topY, barW, barH);

      // Label below
      ctx.fillStyle = '#86909C';
      ctx.font = '9.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(labels[i], padding.left + i * stepX + stepX / 2, height - 15);
    });
  }

  // 6. Portfolio Equity Curve vs Benchmark (收益分析净值走势图)
  static drawEquityCurve(canvasId, strategyData, benchmarkData, labels = []) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!strategyData || strategyData.length < 2) return;

    ctx.clearRect(0, 0, width, height);

    const padding = { top: 24, right: 45, bottom: 26, left: 16 };
    const usableW = width - padding.left - padding.right;
    const usableH = height - padding.top - padding.bottom;

    const allVals = [...strategyData, ...(benchmarkData || [])];
    const minVal = Math.min(...allVals) * 0.98;
    const maxVal = Math.max(...allVals) * 1.02;
    const range = maxVal - minVal || 1;

    // Draw grid lines
    ctx.strokeStyle = '#F0F2F5';
    ctx.lineWidth = 1;
    const gridRows = 4;
    for (let r = 0; r <= gridRows; r++) {
      const y = padding.top + (usableH / gridRows) * r;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      const val = maxVal - (range / gridRows) * r;
      ctx.fillStyle = '#86909C';
      ctx.font = '10px tabular-nums -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.textAlign = 'left';
      ctx.fillText(val.toFixed(2), width - padding.right + 6, y + 3);
    }

    const stepX = usableW / (strategyData.length - 1);

    // Draw Benchmark line (dashed gray)
    if (benchmarkData && benchmarkData.length === strategyData.length) {
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = '#B4BCC8';
      ctx.lineWidth = 1.5;
      benchmarkData.forEach((val, i) => {
        const x = padding.left + i * stepX;
        const y = padding.top + usableH * (1 - (val - minVal) / range);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Draw Strategy line (solid blue)
    ctx.beginPath();
    ctx.strokeStyle = '#1677FF';
    ctx.lineWidth = 2.2;
    strategyData.forEach((val, i) => {
      const x = padding.left + i * stepX;
      const y = padding.top + usableH * (1 - (val - minVal) / range);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Fill gradient below strategy line
    ctx.lineTo(padding.left + (strategyData.length - 1) * stepX, padding.top + usableH);
    ctx.lineTo(padding.left, padding.top + usableH);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, padding.top, 0, padding.top + usableH);
    grad.addColorStop(0, 'rgba(22, 119, 255, 0.18)');
    grad.addColorStop(1, 'rgba(22, 119, 255, 0.01)');
    ctx.fillStyle = grad;
    ctx.fill();

    // X-axis labels
    if (labels && labels.length) {
      ctx.fillStyle = '#86909C';
      ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.textAlign = 'center';
      const labelInterval = Math.max(1, Math.floor(labels.length / 5));
      labels.forEach((lbl, i) => {
        if (i % labelInterval === 0 || i === labels.length - 1) {
          const x = padding.left + i * stepX;
          ctx.fillText(lbl, x, height - 6);
        }
      });
    }

    // Legend at top left
    ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
    ctx.fillStyle = '#1677FF';
    ctx.fillRect(padding.left, 8, 10, 3);
    ctx.textAlign = 'left';
    ctx.fillText('策略净值 (当前 +34.28%)', padding.left + 16, 12);

    ctx.strokeStyle = '#86909C';
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(padding.left + 170, 9);
    ctx.lineTo(padding.left + 184, 9);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#86909C';
    ctx.fillText('沪深300 (+8.65%)', padding.left + 190, 12);
  }

  // 7. Monthly PnL Bar Chart (月度盈亏分布图)
  static drawMonthlyPnLChart(canvasId, monthlyData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const { ctx, width, height } = this.setupCanvas(canvas);
    if (!monthlyData || monthlyData.length === 0) return;

    ctx.clearRect(0, 0, width, height);

    const padding = { top: 20, right: 12, bottom: 22, left: 12 };
    const usableW = width - padding.left - padding.right;
    const usableH = height - padding.top - padding.bottom;

    const values = monthlyData.map(d => d.pnl);
    const minVal = Math.min(-2, ...values);
    const maxVal = Math.max(5, ...values);
    const range = maxVal - minVal || 1;

    const zeroY = padding.top + usableH * (1 - (0 - minVal) / range);
    const stepX = usableW / monthlyData.length;
    const barW = Math.max(14, stepX * 0.55);

    // Zero line
    ctx.beginPath();
    ctx.strokeStyle = '#D9D9D9';
    ctx.lineWidth = 1;
    ctx.moveTo(padding.left, zeroY);
    ctx.lineTo(width - padding.right, zeroY);
    ctx.stroke();

    monthlyData.forEach((item, i) => {
      const x = padding.left + i * stepX + (stepX - barW) / 2;
      const isPositive = item.pnl >= 0;
      const y = padding.top + usableH * (1 - (item.pnl - minVal) / range);
      const barH = Math.max(2, Math.abs(y - zeroY));
      const topY = isPositive ? y : zeroY;

      ctx.fillStyle = isPositive ? '#F5222D' : '#52C41A';
      ctx.fillRect(x, topY, barW, barH);

      // Value label on bar
      ctx.fillStyle = isPositive ? '#F5222D' : '#52C41A';
      ctx.font = '10px tabular-nums -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.textAlign = 'center';
      const labelY = isPositive ? topY - 4 : topY + barH + 11;
      ctx.fillText((isPositive ? '+' : '') + item.pnl.toFixed(1) + '%', x + barW / 2, labelY);

      // Month label below zero line
      ctx.fillStyle = '#86909C';
      ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
      ctx.fillText(item.month, x + barW / 2, height - 6);
    });
  }
}

window.FinancialCharts = FinancialCharts;

