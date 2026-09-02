# AKShare API 版本兼容性速查

记录实测验证过的 AKShare（v1.18.64）函数名与返回值。

## 核心行情函数

| 数据需求 | 函数名 | 实测版本 | 状态 |
|---|---|---|---|
| A 股日线 OHLCV（前复权） | `ak.stock_zh_a_hist(symbol, period="daily", adjust="qfq")` | v1.18.64 | ✅ |
| 实时行情快照 | `ak.stock_bid_ask_em(symbol)` | v1.18.64 | ✅ |
| 分钟线 | `ak.stock_zh_a_hist_min_em(symbol, period="1")` | v1.18.64 | ✅ |

## 基本面函数

| 数据需求 | 函数名 | 实测版本 | 状态 |
|---|---|---|---|
| 利润表 | `ak.stock_profit_sheet_by_report_em(symbol)` | v1.18.64 | ✅ |
| 资产负债表 | `ak.stock_balance_sheet_by_report_em(symbol)` | v1.18.64 | ✅ |
| 现金流量表 | `ak.stock_cash_flow_sheet_by_report_em(symbol)` | v1.18.64 | ✅ |
| 按年利润表 | `ak.stock_profit_sheet_by_yearly_em(symbol)` | v1.18.64 | ✅ |
| 按年资产负债表 | `ak.stock_balance_sheet_by_yearly_em(symbol)` | v1.18.64 | ✅ |
| 按年现金流量表 | `ak.stock_cash_flow_sheet_by_yearly_em(symbol)` | v1.18.64 | ✅ |
| 按季度利润表 | `ak.stock_profit_sheet_by_quarterly_em(symbol)` | v1.18.64 | ✅ |

## 新闻与事件函数

| 数据需求 | 函数名 | 实测版本 | 状态 |
|---|---|---|---|
| 公司新闻 | `ak.stock_news_em(symbol)` | v1.18.64 | ✅ |
| ❌ 旧名 `stock_info_news_em` | — | — | ❌ 不存在 |
| 龙虎榜 | `ak.stock_lhb_stock_detail_em(date)` | v1.18.64 | ✅ |
| ❌ 旧名 `stock_lhbyy_em` | — | — | ❌ 不存在 |
| 龙虎榜明细（东方财富） | `ak.stock_lhb_detail_em(date)` | v1.18.64 | ✅ |
| 龙虎榜营业部排名 | `ak.stock_lhb_yybph_em()` | v1.18.64 | ✅ |

## 其他常用函数

| 函数 | 说明 | 状态 |
|---|---|---|
| `ak.stock_profit_forecast_em(symbol)` | 业绩预测 | ✅ |
| `ak.stock_history_dividend(symbol)` | 历史分红 | ✅ |
| `ak.stock_sector_fund_flow_hist(symbol)` | 行业资金流 | ✅ |
| `ak.stock_concept_fund_flow_hist(symbol)` | 概念资金流 | ✅ |
| `ak.stock_hsgt_hist_em(symbol, start_date, end_date)` | 沪深港通资金 | ✅ |

## 已知陷阱

### 1. 函数名不向后兼容

某些文档/第三方代码中的函数名可能在当前版本中不存在。典型例子：
- `stock_info_news_em` → 实际为 `stock_news_em` ❌
- `stock_lhbyy_em` → 实际为 `stock_lhb_stock_detail_em` ❌

**始终通过 `dir(akshare)` 或交互式 Python 验证函数是否存在。**

### 2. 列名变化

AKShare 的东方财富源有时会调整中文列名（如 `涨跌幅`↔`涨跌额`）。建议使用前打印列名检查：

```python
df = ak.stock_zh_a_hist(symbol="002230", period="daily", start_date="20250101", adjust="qfq")
print(list(df.columns))
```

### 3. 返回空 DataFrame 而非 None

某些接口在无数据时返回空 DataFrame 而非 None，需用 `df.empty` 而非 `df is None` 判断：

```python
df = ak.stock_zh_a_hist(...)
if df is None or df.empty:  # 两种都要检查
    return "无数据"
```

### 4. 模块目录名与文件名冲突（Python import 陷阱）

**问题**：当你有一个 `dataflows/utils.py` 文件和一个 `dataflows/utils/` 目录同时存在时，Python 的包导入机制会优先处理目录，导致 `from .utils import X` 报错。

**症状**：
```
ImportError: cannot import name 'X' from 'package.dataflows.utils'
```

**原因**：Python 发现 `utils/` 目录（含 `__init__.py`）后，将其视为包，不再查找 `utils.py` 文件。

**解决方法**：将自定义目录重命名为不冲突的名称（如 `akshare_utils/`），或使用绝对导入路径绕过。

**检查方法**：
```bash
# 查看目录下是否有与文件同名的子目录
ls -la tradingagents/dataflows/ | grep -E "^d.*utils"
# 如果存在，rename 即可
```

### 5. AKShare 请求频率限制

东方财富接口有隐性限流，高频请求可能被临时封禁（返回空数据或 HTTP 429）。

**建议**：
- 请求间添加 `time.sleep(0.5)` 间隔
- 首次获取数据后缓存到本地 CSV 文件（至少缓存 5 分钟）
- 批量查询时使用 8-12 并发（受网络带宽限制）
