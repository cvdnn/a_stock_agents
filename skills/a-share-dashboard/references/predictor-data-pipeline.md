# AI 预测数据采集管线（Predictor Data Pipeline）

## 用途

`scripts/predictor.py` 为 AI 模型（如 DeepSeek-V4-Flash）提供结构化输入，用于辅助 A 股趋势判断和风险评估。

## 采集的数据维度

| 维度 | 来源 | 内容 |
|------|------|------|
| 实时行情 | 东财 proxy-patch | 现价、涨跌幅、成交量、换手率 |
| 日K线（近60日） | 东财 proxy-patch | 开高低收、量能 |
| 技术指标 | MyTT 本地计算 | MA5/10/20/60、MACD、KDJ、RSI、BOLL |
| 资金流向 | 东财 proxy-patch | 近5~10日主力/散户资金流向 |
| 行业信息 | 东财 proxy-patch | 所属板块、板块排行 |
| 筹码分布 | 东财 proxy-patch | 获利比例、平均成本、集中度 |

## 输出结构

`predictor.py` 输出 JSON，包含以下字段：

```json
{
  "stock": {"code": "600760", "name": "中航沈飞", "sector": "航空装备"},
  "market": {"current_price": 41.80, "change_pct": -1.29, "volume": 123456, "turnover_rate": 1.2},
  "technical": {
    "ma5": 42.10, "ma10": 41.50, "ma20": 40.80, "ma60": 38.50,
    "macd_dif": 0.35, "macd_dea": 0.28, "macd_hist": 0.07,
    "kdj_k": 52.3, "kdj_d": 48.1, "kdj_j": 60.7,
    "rsi": 55.2,
    "boll_up": 44.50, "boll_mid": 40.80, "boll_low": 37.10
  },
  "fund_flow": {"main_force_5d": 12345678, "retail_5d": -567890, "large_order_5d": 987654},
  "chip": {"profit_ratio": 0.35, "avg_cost": 45.20, "concentration_90": 0.12, "concentration_70": 0.08}
}
```

## AI 分析能力匹配

| 问题类型 | AI 能力定位 |
|----------|-------------|
| 多因素综合评估 | 强：整合所有数据维度给出综合判断 |
| 趋势形态识别 | 中：可以描述均线排列/MACD形态 |
| 风险预警 | 强：结合筹码+资金+技术发现预警信号 |
| 精确价格预测 | 弱：AI 不适合做精确数值预测 |
| 策略建议 | 中：给出方向性建议（加仓/持有/减仓） |

## 调用方式

```bash
VENV_PY="python3"
SKILL_DIR="./.AI-Platform/skills/stocks/a-share-dashboard/scripts"

# 单只股票完整数据采集（~5-8秒）
$VENV_PY "$SKILL_DIR/predictor.py" --code 600760 --json

# 批量采集（逐个调用，避免连续超时）
$VENV_PY "$SKILL_DIR/predictor.py" --codes 600760,601899,603993
```

## 已知问题

- **东财批量采集偶发超时**：predictor.py 需连续调用东财 5+ 次接口，中间某次可能卡死。详见 a-share-data 的"东财 proxy-patch 批量数据采集偶发超时"陷阱说明。
- **交易日限制**：仅在 A 股交易时段数据有意义（9:30-11:30, 13:00-15:00）
- **技术指标滞后**：MA/MACD 等基于历史数据，不预示未来

## 最佳实践

1. **单次分析**：对单只股票，通常能完整运行
2. **批量分析**：逐个调用而非一次性扫描，避免超时
3. **超时处理**：kill 后重试，或改用 fetch_technical.py 分别获取各维度
4. **AI 使用**：将 JSON 注入上下文，要求 AI 做定性分析而非数值预测