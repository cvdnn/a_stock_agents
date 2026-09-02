---
name: a-stock-reporting
version: "1.0.0"
author: ""
description: A股报告持久化规范 — 输出路径约定、多股联合报告模式、Tencent API+Python自算技术指标降级方案
tags: [A股, 报告, 持久化, 格式规范]
related_skills: [stock-report-html, a-stocks, a-share-data]
---

# A股报告持久化与工作流规范

## 报告输出路径约定

```
<工作目录>/<日期>/<报告类型>_<描述>.<ext>
```

当前: `/mnt/c/Users/user/coding/AAAAA/<YYYYMMDD>/`

## Tencent API + Python 自算技术指标

当 fetch_technical.py 因 requests/urllib3 依赖链失败时使用:

```python
from urllib.request import Request, urlopen
import json
from math import sqrt

# 获取前复权日K线 (~0.18s)
url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,120,qfq"
req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
kline = json.loads(urlopen(req, timeout=10).read())
klines = list(kline["data"].values())[0].get("qfqday", [])

# 自算全部指标 (~0.3s)
closes = [float(k[2]) for k in klines]
highs = [float(k[1]) for k in klines]
lows = [float(k[3]) for k in klines]

# MA
ma5 = round(sum(closes[-5:])/5, 2) if len(closes)>=5 else None
ma10 = round(sum(closes[-10:])/10, 2) if len(closes)>=10 else None
ma20 = round(sum(closes[-20:])/20, 2) if len(closes)>=20 else None
ma60 = round(sum(closes[-60:])/60, 2) if len(closes)>=60 else None

# MACD
ema_f = [closes[0]]; ema_s = [closes[0]]
for c in closes[1:]:
    ema_f.append(round(ema_f[-1]*11/13 + c*2/13, 3))
    ema_s.append(round(ema_s[-1]*25/27 + c*2/27, 3))
dif = [ema_f[i]-ema_s[i] for i in range(len(closes))]
dea = [dif[0]]
for d in dif[1:]: dea.append(round(dea[-1]*8/10 + d*2/10, 3))
macd_bar = round(2*(dif[-1]-dea[-1]), 3)

# KDJ (9,3,3)
k0=d0=50; k_list=[k0]; d_list=[d0]
for i in range(len(closes)):
    if i<8: rsv=50
    else: hh=max(highs[i-8:i+1]); ll=min(lows[i-8:i+1]); rsv=0 if hh==ll else (closes[i]-ll)/(hh-ll)*100
    k_list.append(round(k_list[-1]*2/3+rsv*1/3,2))
    d_list.append(round(d_list[-1]*2/3+k_list[-1]*1/3,2))
j = round(3*k_list[-1]-2*d_list[-1],2)

# RSI
def rsi(prices, n=14):
    if len(prices)<=n: return None
    g=sum(max(prices[i]-prices[i-1],0) for i in range(-n,0))
    l=sum(max(prices[i-1]-prices[i],0) for i in range(-n,0))
    return 100 if l==0 else round(100-100/(1+g/l),2)

# BOLL
mid = sum(closes[-20:])/20
std = sqrt(sum((c-mid)**2 for c in closes[-20:])/20)
boll_upper = round(mid+2*std,2); boll_lower = round(mid-2*std,2)
```

## 多股联合报告结构

```
# <日期> 午盘/收盘/早盘评估 · <股票1> / <股票2> / <股票3>

## 大盘背景
## 一、<股票1>(<代码>) — <评级>
### 实时行情 | 技术指标 | 核心评估 | 操作策略
## 二、<股票2>(<代码>) — <评级>
...
## 综合对比
| 排序 | 股票 | 趋势 | 仓位建议 |
## 后续关注事件
## 关键风险提示
```

## 注意事项

1. HTML报告格式以 stock-report-html 技能为准。模板文件原声明在 a-share-data/templates/ 但不存在——直接使用 a-stocks 的 report_generator.py 生成
2. cron no_agent 脚本默认不写盘（仅投递通知），额外写盘需显式添加
3. 多股联合报告无脚本支持，由主会话 execute_code 聚合+计算+撰写

## 已知问题与调试

参见 [references/a-stocks-known-pitfalls.md](references/a-stocks-known-pitfalls.md) — a-stocks 技能的方法名陷阱、K线端点性能对比、集成冒烟测试，以及 [references/data-audit-20260728.md](references/data-audit-20260728.md) — L1 数据接口审计结果。

## 用户反馈验证流程

参见 [references/user-feedback-verification-methodology.md](references/user-feedback-verification-methodology.md) — 用户主观市场观察的验证流程，防止将未核实的主观感受写入策略文档。包含可信度标签规范、量化LLM交叉验证、交易账户限制等补充配置。

## ⚠️ 合规审计：板块必须齐全（2026-07-31 教训）

用户核心要求是**内容板块结构齐全**，仅复用 CSS 骨架（背景/涨红跌绿/1344px/卡片）**不算合规**。曾发生4份报告 CSS 全部正确但板块缺失，被判定"全部不符合"。生成后务必逐项核对以下**必选板块**：

- [ ] 📅 历史策略轨迹全景（`.tl` 时间线 + 折叠JS）— **最常被丢弃的灵魂板块**
- [ ] 📊 10列持仓全景表（含最低卖出价）
- [ ] 💰 最低卖出价税费说明表（含费率）
- [ ] 个股深度分析 ×3（grid-2：关键变化 + 操作策略）
- [ ] 🕵️ 主力动作全景
- [ ] 🔑 关键价位 T0/T1/T2（grid-3）
- [ ] 📋 分级操作方案（🌞🌤🌧 三场景表格）
- [ ] ⚠️ 综合风险提示

**板块顺序**统一为：历史轨迹→持仓全景→税费表→个股分析×3→主力动作→关键价位→分级方案→风险提示。

## 已知坑（必读）

1. **标题日期重复**：模板 `<title>{{TITLE}} | {{DATE}}</title>` 已自动追加日期，`{{TITLE}}` 字符串内**不要再写日期**，否则 `...成本重算 | 2026-07-31 | 2026-07-31`。
2. **JS 死代码**：折叠JS需要 `.tl` 元素存在。若报告没写历史策略轨迹内容却带了JS，JS 找不到 `.tl` 而静默失效——隐性违规。缺时间线内容时把JS一起删掉，或补内容。
3. **dot 重复**：`hdr-tag` 内 `dot` 圆点只能出现一次，勿写成 `<span class="dot"></span><span class="dot">`。
4. **生成方式**：优先写独立 Python 脚本读取模板，用板块构建函数（build_timeline/build_holdings/build_fee_table/build_stock/build_main_force/build_key_prices/build_scenarios/build_risks）填充 8 个占位符再执行，比手写HTML更不易漏板块。
5. **验证**：生成后用脚本核对每份报告 8 个必选板块均在 + `.tl` 元素存在（非死代码）+ dot 无重复 + 标题无重复日期。板块数量不足即视为不合规。
6. **Python 生成脚本 f-string 嵌套引号崩溃（2026-08-04 实测）**：用 f-string 构建表格行时，若在同一字符串内同时取 dict 值 `{s["key"]}` **和** 三元条件写 class（如 `class="{ 'up' if x>=0 else 'down' }"`），会抛 `SyntaxError: f-string: expecting '}'`。连续踩坑两次。**修复**：把条件 class 先提为变量再拼入 f-string：
   ```python
   cls = "up" if pct >= 0 else "down"
   row = f'<td class="{cls}">{s["price"]:.2f}</td>'   # 条件值全部预先计算为局部变量
   ```
   凡 f-string 里出现 dict 下标 + 嵌套引号组合处，一律先算好局部变量。脚本写完先 `python3 -c "compile(open('x.py').read(),'x','exec')"` 或直接运行验证，避免生成到一半才发现。

7. **大报告单次 write_file 会流式超时（2026-08-06 实测）**：6 股联合评估（综合对比表+每股分析卡+验证表+分场景+T0/T1/T2+优先级+风险，HTML 约 25KB / CONTENT 约 11KB）若**一次性**塞进一个 `write_file` 的 `content` 参数，会触发 `stream timed out`，文件未写出。**修复：碎片化生成再组装**——把内容拆成多个小脚本，每个只负责一个板块片段写入 `/tmp/frag_*/NN_xxx.html`，最后用一个小组装器读模板 + `"".join(frag(n))` 拼 CONTENT 并填占位符。每段脚本 <~5KB 参数，避免单次工具调用过大：
   ```python
   # 每个碎片脚本: 定义 S 数据 + 算该板块 → save("01_table", html) 到 /tmp/frag_*/
   # 组装器:
   content = "".join(frag(n) for n in ["03_market","01_table","04_validate","02_cards","05_scenarios","06_stops","07_priority","08_risk"])
   out = open(TPL).read()
   for k,v in repl.items(): out = out.replace(k,v)
   ```
   好处：① 避免大 content 超时；② 分板块文件便于局部重跑/校验；③ 板块顺序在组装器里显式控制（合规审计所需）。生成后仍照坑 #5 校验板块齐全 + dot 无重复 + 占位符零残留。

## 历史策略轨迹报告（多会话追踪专用）

当需要整合多日策略演变（如"7/17首次分析→7/23建仓→7/29午盘→7/30大盘暴跌"这类跨交易日轨迹），采用以下标准结构：

```html
<!-- 策略轨迹时间轴 -->
<div class="section">
  <div class="sec-title">📅 历史策略轨迹全景</div>
  <div class="card">
    <div class="tl">
      <div class="tl-item">
        <div class="tl-time">2026-07-17</div>
        <div class="tl-head"><span class="tag tag-up">标签</span> 标题</div>
        <div class="tl-body">详情 + 验证标签</div>
      </div>
      <!-- tl-item × N -->
    </div>
  </div>
</div>
```

每个 tl-item 尾部必须含验证标签（✅判断准确/⏳待验证/❌判断有误）。

## 持仓全景表标准格式

```html
<div class="section">
  <div class="sec-title">📊 持仓全景 · 日期</div>
  <div class="card">
    <div class="info-box red">大盘背景</div>
    <table class="tbl">
      <tr><th>代码</th><th>名称</th><th>股数</th><th>成本</th><th>现价</th><th>今日涨跌</th><th>市值</th><th>浮盈亏</th><th>vs大盘</th></tr>
      <tr><!-- 每只一行 --></tr>
      <tr style="font-weight:700;border-top:2px solid var(--border)">
        <td colspan="4">合计</td><td></td><td></td>
        <td>{total}</td>
        <td style="color:var(--up)/var(--down)">{pnl}</td>
        <td></td>
      </tr>
    </table>
  </div>
</div>
```

## 分场景操作方案表

```html
<div class="section">
  <div class="sec-title">📋 分场景操作方案</div>
  <div class="card">
    <table class="tbl">
      <tr><th>触发条件</th><th>000400 许继</th><th>600760 沈飞</th><th>002230 科大</th></tr>
      <tr><td class="up"><strong>🌞 乐观</strong><br>条件</td><td>操作</td><td>操作</td><td>操作</td></tr>
      <tr><td class="ylw"><strong>🌤 中性</strong><br>条件</td><td>...</td><td>...</td><td>...</td></tr>
      <tr><td class="down"><strong>🌧 悲观</strong><br>条件</td><td>...</td><td>...</td><td>...</td></tr>
    </table>
  </div>
</div>
```

## T0/T1/T2 三级止损标准

| 级别 | 触发 | 操作 | 含义 |
|:----:|:-----|:-----|:------|
| **T0** | 日内跌幅 > 5% | 即时清仓 | 防日内踩踏，不等收盘 |
| **T1** | 收盘跌破 MA10 | 减半仓 | 趋势走弱预警 |
| **T2** | 收盘跌破 MA20 | 清仓 | 中期趋势破坏 |

## 单股grid-2分析卡标准结构

单股深度分析采用两栏grid-2：
- **左栏**: 7/29→7/30关键指标变化对比表（前日值/当日值/变化方向）
- **右栏**: 基本面/事件+操作策略（含成本、建议、止损位）

## 持仓成本修正规范

当用户修正持仓成本时，报告中所有相关计算必须重新执行：
1. 各股浮盈/亏 = (现价 - 成本) × 股数
2. 总市值 = Σ(现价 × 股数)
3. 总浮盈 = Σ(各股浮盈)
4. 各股占总仓位比例 = 各股市值 / 总市值 × 100%
5. 策略建议根据最新成本和浮盈状况重新评估
6. 历史轨迹中的交易记录须同步修正（如"7/23沈飞卖出500股@43.85"而非"买入"）