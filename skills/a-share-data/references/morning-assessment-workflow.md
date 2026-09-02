# 早盘快速评估工作流

## 触发场景

用户要求评估某只股票的早盘行情（如"评估XXX早盘行情"、"XXX今天怎么样"、"早盘怎么看XXX"）。

## 数据采集顺序

按如下优先级依次执行，**任一失败立即降级**，不反复重试：

### 第1步：实时行情（必选）
```bash
SKILL_DIR="./.AI-Platform/skills/stocks/a-share-data/scripts"
# 方案A（优先，稳定，零积分）
python3 "$SKILL_DIR/fetch_realtime.py" --quote 603893 --json

# 方案A失败时 → 方案D：腾讯API直连
# 注：方案D在terminal中可能被AI-Platform安全扫描阻断，此时降级回方案A的重试
```

### 第2步：大盘指数对照（必选）
```bash
python3 "$SKILL_DIR/fetch_realtime.py" --multi-quote sh000001,sz399001,sz399006 --json
```

### 第3步：板块排行对照（必选，帮判断个股涨幅的板块归因）
```bash
# DangInvest，零积分
python3 "$SKILL_DIR/fetch_realtime.py" --boards-summary --boards-limit 20 --json
```

### 第4步：近期日K线（必选，看趋势结构和关键节点）
```bash
python3 "$SKILL_DIR/fetch_history.py" --kline 603893 --start YYYYMMDD --end YYYYMMDD --freq d --json
# 取近20-30个交易日
```

### 第5步：Tick数据（可选，看开盘首笔方向和集合竞价后的资金意图）
```bash
python3 "$SKILL_DIR/fetch_realtime.py" --tick 603893 --json
# ⚠️ 已知限制：仅覆盖开盘后前几分钟（约09:25-09:35），不足以分析整个早盘
# 主要用于验证开盘首笔方向和集合竞价后的资金意图
```

### 容错策略

| 失败点 | 降级动作 |
|--------|----------|
| proxy-patch 超时(方案B) | → 方案A (系统Python，新浪/腾讯链路) |
| 方案A 超时 | → 方案D (腾讯API直连，但注意终端阻断风险) |
| DangInvest 板块超时 | → 用 proxy-patch 调 `stock_board_industry_name_em()`，或跳过板块分析 |
| tick 数据不足 | → 改用 `--multi-quote` 多次拉取分段汇总实时价变化 |
| AI-Platform阻断python -c | → 方案A技能脚本 |

## 评估输出格式

### 1. 实时行情表

| 指标 | 数值 |
|------|------|
| 最新价 | xx.xx (+x.xx%) |
| 开盘 | xx.xx (较昨收%) |
| 最高 / 最低 | xx.xx / xx.xx |
| 振幅 | x.xx% |
| 昨收 | xx.xx |

### 2. 早盘走势分析

关键观察点：
- **低开/高开**：对比昨收的缺口方向和幅度
- **开盘后方向**：开盘后前5-10分钟的走势方向（结合tick数据）
- **成交量**：同比昨日的放量/缩量程度
- **日内多空**：从价格波动看资金态度

### 3. 近期K线背景

取近20个交易日，标注关键节点：
- 阶段涨幅（起点→昨收）
- 近期高低点
- 单日异常波动（暴涨暴跌日）
- 近期趋势（上行/下行/震荡）

### 4. 板块对照

列出目标股所属板块（半导体、元器件等）的今日涨跌幅，对比个股是否跑赢板块。

### 5. 结论

- **盘口信号**：强/中/弱
- **阻力/支撑**：关键价格位
- **风险提示**：可能冲高回落、上方套牢盘等

## 风格规范

- 表格呈现数据，不堆JSON原文
- 结论在前，数据支撑在后
- 明确标注盘中/休市状态和数据时间
- 不输出未经核实的消息面解读