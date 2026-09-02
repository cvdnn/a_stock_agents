# 股池 CSV 数据格式规范 — TA 分析集成

本文档定义 `a-share-dashboard` 的股池 CSV 与 `ta-multi-agent-analysis` 之间的数据交换格式。

## 自选股池 (`data/selected_pool.csv`)

### 完整列定义

| 列名 | 类型 | 必填 | 写入者 | 说明 |
|------|------|:----:|--------|------|
| `code` | str(6) | ✅ | pool_manager | 6位A股代码 |
| `name` | str | ✅ | pool_manager | 股票名称 |
| `added_date` | date | ✅ | pool_manager | YYYY-MM-DD |
| `rating` | str(1) | ✅ | pool_manager / ta_analyze | A/B/C |
| `reason` | str | | pool_manager | 加入理由 |
| `sector` | str | | pool_manager | 所属板块 |
| `pe` | float | | pool_manager | 市盈率 |
| `change_pct` | str | | pool_manager | 涨跌幅 |
| `ma_status` | str | | pool_manager | 多头/震荡/空头 |
| `entry_trigger` | str | | pool_manager | 入场触发条件 |
| `stop_loss` | float | | pool_manager / ta_analyze | 止损价 |
| `take_profit` | float | | pool_manager | 止盈价 |
| `risk_level` | str | | pool_manager | 低/中/高 |
| `market_context` | str | | pool_manager | 市场背景 |
| `notes` | str | | pool_manager | 备注 |
| `ta_decision` | str | | **ta_analyze** | BUY/HOLD/SELL |
| `ta_analysis_date` | date | | **ta_analyze** | 最近TA分析日期 |
| `ta_report_path` | str | | **ta_analyze** | 报告文件路径 |
| `consensus_rating` | str | | **ta_analyze** | 融合评级（如"强烈买入 ⭐⭐⭐⭐"） |

### TA 写入规则

```python
# ta_analyze.py 中 _sync_to_pool() 的写入逻辑:
# BUY  → pool_manager.py add → 写入全部字段
#        ta_decision="BUY", consensus_rating="强烈买入 ⭐⭐⭐⭐"
# SELL → pool_manager.py remove → 删除该行
# HOLD → 不操作 CSV，仅内部记录
```

## 关注股池 (`data/watch_pool.csv`)

### 完整列定义

| 列名 | 类型 | 必填 | 写入者 | 说明 |
|------|------|:----:|--------|------|
| `code` | str(6) | ✅ | pool_manager | 6位A股代码 |
| `name` | str | ✅ | pool_manager | 股票名称 |
| `added_date` | date | ✅ | pool_manager | YYYY-MM-DD |
| `rating` | str(1) | | pool_manager | A/B/C |
| `reason` | str | | pool_manager | 加入理由 |
| `sector` | str | | pool_manager | 所属板块 |
| `pe` | float | | pool_manager | 市盈率 |
| `change_pct` | str | | pool_manager | 涨跌幅 |
| `fund_flow` | str | | pool_manager | 资金流向 |
| `entry_condition` | str | | pool_manager | 入场条件描述 |
| `market_context` | str | | pool_manager | 市场背景 |
| `ta_analysis_date` | date | | **ta_orchestrator** | 最近TA分析日期 |

## 自动创建

当 `pool_manager.py` 启动时，如果 CSV 文件不存在，自动用完整字段列表创建。无需手动初始化。

## 读取方式

```python
import csv
from pathlib import Path

# 读取自选股池
path = Path.home() / ".AI-Platform" / "skills" / "stocks" / "a-share-dashboard" / "data" / "selected_pool.csv"
with open(path) as f:
    rows = list(csv.DictReader(f))

# 过滤出 TA 推荐买入的标的
buy_candidates = [r for r in rows if r.get("ta_decision") == "BUY"]
```
