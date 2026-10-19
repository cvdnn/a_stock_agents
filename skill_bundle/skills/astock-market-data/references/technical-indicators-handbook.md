# 经典技术指标量化手册 (Technical Indicators Handbook)

本文档归纳 `astock-market-data` 中所支持的经典技术指标的数学定义、参数取值与应用判定。所有指标必须由底层 `skill_bundle/runtime/core/data/technical_indicators.py` 计算。

---

## 1. 移动平均线系统 (Moving Average, MA)

- **标准周期**：MA5, MA10, MA20, MA60, MA120, MA250
- **多头排列判定**：
  $$\text{MA}_5 > \text{MA}_{10} > \text{MA}_{20} > \text{MA}_{60}$$
- **乖离率 (BIAS)**：
  $$\text{BIAS}_N = \frac{P - \text{MA}_N}{\text{MA}_N} \times 100\%$$
  - $\text{BIAS}_{20} > 15\%$：短期严重超买，严禁追高；
  - $\text{BIAS}_{20} < -15\%$：超跌反弹酝酿区。

---

## 2. 平滑异同移动平均线 (MACD)

- **标准参数**：FAST=12, SLOW=26, SIGNAL=9
- **核心公式**：
  $$\text{EMA}_{12} = \text{EMA}(P, 12), \quad \text{EMA}_{26} = \text{EMA}(P, 26)$$
  $$\text{DIF} = \text{EMA}_{12} - \text{EMA}_{26}$$
  $$\text{DEA} = \text{EMA}(\text{DIF}, 9)$$
  $$\text{BAR} = 2 \times (\text{DIF} - \text{DEA})$$
- **关键形态**：
  - **水下二次金叉 (Underwater Second Golden Cross)**：DIF 与 DEA 在零轴下方发生第一次金叉后回落但不创新低，再次发生第二次金叉，且第二次金叉的 DIF 极值高于第一次。这是经典的高胜率见底信号。
  - **顶背离 (Top Divergence)**：股价创出新高，但 MACD 红柱高度与 DIF 峰值明显低于前一波峰，警惕大级别见顶。

---

## 3. 随机指标 (KDJ)

- **标准参数**：N=9, M1=3, M2=3
- **超买超卖界限**：
  - $J < 0$：超卖极值，短线见底信号；
  - $J > 100$：超买极值，防范分时急刹车；
  - 低位二次金叉（$K, D < 30$ 时金叉）胜率显著高于中高位金叉。

---

## 4. 相对强弱指标 (RSI)

- **标准参数**：周期 6, 12, 24
- **判定阈值**：
  - $\text{RSI}_6 < 20$：极端弱势超卖，多头酝酿反扑；
  - $\text{RSI}_6 > 80$：高位过热超买；
  - $\text{RSI}_6$ 突破 50 荣枯线确认由弱转强。

---

## 5. 布林线 (Bollinger Bands, BOLL)

- **标准参数**：N=20, K=2
- **三轨定义**：中轨 = MA20，上轨 = 中轨 + 2×标准差，下轨 = 中轨 - 2×标准差
- **带宽指标 (Bandwidth)**：
  $$\text{BW} = \frac{\text{Upper} - \text{Lower}}{\text{Mid}} \times 100\%$$
  - $\text{BW} < 5\%$：布林带极度收口，预示大级别单边突破在即；
  - 股价沿上轨持续推升为强势主升浪形态。

---

## 6. 真实波幅 (Average True Range, ATR)

- **标准参数**：N=14
- **风控用途**：
  - 用于动态波动率跟踪止损设置：$\text{StopLoss} = P - 2 \times \text{ATR}_{14}$；
  - 仓位自适应调整：高波动品种自动降低头寸规模。
