---
name: astock-report-html
version: "1.0.0"
author: ""
description: 【全局默认】A股复盘/评估/投研/持仓综合评估HTML报告标准样式。白色系亚光背景、涨红跌绿、1344px居中、自包含单文件。含策略轨迹折叠JS、10列持仓表(含税费最低卖出价)、T0/T1/T2三级止损、三场景分级操作方案。
tags: [A股, HTML, 报告, 复盘, 可视化, 标准样式, 持仓评估, 策略轨迹, 止损]
related_skills: [astock-data-feed, astock-report-archive]
---

# A股HTML报告标准 — 全局默认样式

> ⚠️ **约定：所有股票评估/复盘/投研/持仓报告的HTML输出必须使用此模板。不允许创建重复模板。**

## 风格规范（不可更改）

| 属性 | 值 | 说明 |
|------|:---:|:----:|
| 背景色 | `#f4f5f7` | 白色亚光 |
| 卡片色 | `#ffffff` | 纯白卡片 |
| 涨 | `#d0312d` 🔴 | A股涨=红 |
| 跌 | `#219653` 🟢 | A股跌=绿 |
| 字体 | `-apple-system, PingFang SC, Microsoft YaHei` | 系统原生 |
| 等宽 | `SF Mono, Fira Code, Consolas` | 数字/价格 |
| 布局 | **1344px居中**（旧版960px已升级） | 大屏舒适，小屏自适应 |
| 外链 | 零 | 单文件自包含 |

## 文件位置

```
skills/astock-data-feed/templates/stock-report.html
```

## 占位符（8个）

| 占位符 | 替换内容 |
|:-------|:---------|
| `{{TITLE}}` | 浏览器标题栏 |
| `{{DATE}}` | 报告日期 |
| `{{HEADER_TAG}}` | 顶栏标签（含红圆点） |
| `{{MAIN_TITLE}}` | 主标题 |
| `{{SUB_TITLE}}` | 副标题（大盘+持仓摘要） |
| `{{HEADER_STATS}}` | 顶栏统计卡片（至多4个.hdr-stat） |
| `{{CONTENT}}` | 报告主体HTML（全部.section内容） |
| `{{FOOTER_TEXT}}` | 页脚（数据源+免责） |

## 内置功能

### 1. 策略轨迹时间线（全局折叠）

```html
<div class="tl"><!-- 自动获得.tl-container.collapsed -->
  <div class="tl-item">
    <div class="tl-time">2026-07-17</div>
    <div class="tl-head"><span class="tag tag-up">标签</span> 标题</div>
    <div class="tl-body">描述内容</div>
  </div>
  <!-- 最后一个.tl-item会被JS自动标记.latest，默认展开 -->
</div>
```

- 默认：全部折叠，仅**最新一条**展开
- 标题栏右侧有「▼ 展开历史」按钮，一键控制

### 2. 10列持仓全景表（含最低卖出价）

```html
<table class="tbl">
  <tr><th>代码</th><th>名称</th><th>股数</th><th>成本</th>
      <th>现价</th><th>最低卖出价</th><th>距最低价</th>
      <th>今日涨跌</th><th>市值</th><th>浮盈亏</th></tr>
  <!-- 每个股票一行，共10列 -->
</table>
```

**最低卖出价计算（Python）：**

> ⚠️ **精确进位规则**：按税费公式得出价格后，**必须精确向上进位到 0.01 元**（向上取整到分，例如 ¥6.1413 → ¥6.15，¥6.1463 → ¥6.15），确保挂单卖出时绝对能完全覆盖所有摩擦税费并实现无损保本。

```python
import math

COMMISSION = 0.00012   # 万分之1.2（双边）
STAMP_TAX  = 0.0005    # 万分之5（仅卖出收取）
TRANSFER   = 0.00001   # 万分之0.1（沪深双边）
MIN_FEE    = 5.0       # 单笔佣金最低5元

def calc_min_sell(cost, shares):
    buy_principal = cost * shares
    buy_comm = max(buy_principal * COMMISSION, MIN_FEE)
    buy_transfer = buy_principal * TRANSFER
    total_buy = buy_principal + buy_comm + buy_transfer

    def net(p):
        sell = p * shares
        sc = max(sell * COMMISSION, MIN_FEE)
        st = sell * STAMP_TAX
        sf = sell * TRANSFER
        return sell - sc - st - sf

    lo, hi = cost * 0.8, cost * 1.5
    for _ in range(60):
        mid = (lo + hi) / 2
        if net(mid) >= total_buy: hi = mid
        else: lo = mid
    
    # 均精确向上进位到 0.01 元 (Ceiling to 0.01 Yuan)
    ceil_p = math.ceil(round(hi, 4) * 100) / 100.0
    return ceil_p, round(net(ceil_p) - total_buy, 2)
```

### 3. T0/T1/T2三级止损

| 级别 | 触发条件 | 操作 |
|:----:|:---------|:-----|
| **T0** | 日内跌＞5% | 即时清仓 |
| **T1** | 收盘破MA10 | 减半仓 |
| **T2** | 收盘破MA20 | 全部清仓 |

### 4. 三级操作方案（3场景）

| 场景 | 大盘条件 | 操作基调 |
|:----|:---------|:---------|
| 🌞 乐观 | 大盘企稳，个股突破关键阻力 | 持有+精选加仓 |
| 🌤 中性 | 大盘弱势震荡 | 持有不动，防守为主 |
| 🌧 悲观 | 大盘继续暴跌，个股破位 | 按T1/T2减仓 |

## 生成步骤

```python
from pathlib import Path

# 1. 读取模板
template_path = Path("skills/astock-data-feed/templates/stock-report.html")
html = template_path.read_text(encoding="utf-8")

# 2. 替换8个占位符
html = (html
    .replace("{{TITLE}}", "报告标题")
    .replace("{{DATE}}", "2026-07-30")
    .replace("{{HEADER_TAG}}", "盘中评估 · 2026-07-30")
    .replace("{{MAIN_TITLE}}", "主标题")
    .replace("{{SUB_TITLE}}", "副标题")
    .replace("{{HEADER_STATS}}", "<!-- hdr-stat卡片组 -->")
    .replace("{{CONTENT}}", "<!-- 报告主体 -->")
    .replace("{{FOOTER_TEXT}}", "数据来源<br>⚠️ 免责")
)

# 3. 保存到项目 reports 目录
from core.config import REPORTS_DIR
date_dir = REPORTS_DIR / "20260730"
date_dir.mkdir(parents=True, exist_ok=True)
output_file = date_dir / "report.html"
output_file.write_text(html, encoding="utf-8")


# 4. 浏览器显示规范（Windows用）：报告生成落盘后，向用户提问确认是否在浏览器中弹出显示
# 若用户确认打开，执行系统命令：
# import subprocess
# import webbrowser; webbrowser.open(Path(output).resolve().as_uri())
```


## 费率默认参数

| 项目 | 费率 | 说明 |
|:----|:----:|:-----|
| 佣金 | 万分之1.2 | 双边，单笔最低5元 |
| 印花税 | 万分之5 | 仅卖出收取 |
| 过户费 | 万分之0.1 | 沪深双边收取 |

## 组件清单

| CSS类 | 用途 | 子元素 |
|:------|:-----|:-------|
| `.header`/`.header-inner` | 顶栏 | `.hdr-tag`, `h1`, `.sub`, `.hdr-stats` |
| `.hdr-stat` | 统计卡片 | `.l`/`.v`/`.s` |
| `.sec-title` | 区块标题 | `::after`分隔线 |
| `.card` | 卡片容器 | hover边框 |
| `table.tbl` | 数据表格 | `th`/`td`单色 |
| `.tl`/`.tl-item` | 策略轨迹 | `.tl-time`/`.tl-head`/`.tl-body` |
| `.tl-container.collapsed` | 折叠控制 | JS开关 |
| `.grid-2`/`.grid-3` | 两/三列布局 | 680px自动折行 |
| `.info-box.blue/green/red/ylw` | 提示框 | 4色 |
| `.tag-up/down/blue/ylw/cyan` | 小标签 | 5色 |
| `.up`/`.down`/`.blue`/`.hl` | 行内着色 | — |
| `.quant-grid`/`.quant-metric` | 量化指标网格 | `.qm-label`/`.qm-value`/`.qm-sub` |
| `.eval-bar`/`.eval-bar-fill` | 评估进度条 | 宽度填充 |
| `.eval-grade` 优秀/良好/一般/较差 | 评估等级标签 | 4色(excellent/good/fair/poor) |

### 量化评估组件用法

```html
<div class="card">
  <div class="sec-title">📊 量化评估指标</div>
  <div class="quant-grid">
    <div class="quant-metric">
      <div class="qm-label">综合评分</div>
      <div class="qm-value">82</div>
      <div class="qm-sub">/ 100</div>
    </div>
    <div class="quant-metric">
      <div class="qm-label">方向准确率</div>
      <div class="qm-value up">60%</div>
      <div class="qm-sub">10个决策点</div>
    </div>
    <div class="quant-metric">
      <div class="qm-label">A/B推荐胜率</div>
      <div class="qm-value">100%</div>
      <div class="qm-sub">n=1</div>
    </div>
    <div class="quant-metric">
      <div class="qm-label">评级</div>
      <div class="qm-value"><span class="eval-grade excellent">优秀">优秀⭐⭐⭐⭐</span></div>
    </div>
  </div>
  <div style="margin-top:12px;">
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">评级收益率梯度(5日平均)</div>
    <div class="eval-bar"><div class="eval-bar-fill" style="width:80%;background:var(--up);"></div></div>
    <div style="font-size:11px;color:var(--text-secondary);margin-top:2px;">B级: +2.99% → C级: -1.23% → D级: +0.57%</div>
  </div>
</div>
```

> 量化评估数据来源: `a_stocks.py evaluate <code> --auto --interval 15 --output json`
> 详见 `a-stock-session-tips/references/quant-strategy-gap-analysis-20260731.md`

## 验收清单

- [ ] 背景 `#f4f5f7`，卡片 `#ffffff`
- [ ] `--up`=`#d0312d`（红），`--down`=`#219653`（绿）
- [ ] `max-width:1344px`（两处：`.header-inner` + `.container`）
- [ ] `.tl`时间轴居中验证：线心11px=圈心11px ✅
- [ ] 策略轨迹JS默认折叠，仅`latest`展开
- [ ] 单文件自包含，零CDN
- [ ] 已删除冗余模板文件（`position-report.html`等）
- [ ] 不要创建重复技能或重复模板