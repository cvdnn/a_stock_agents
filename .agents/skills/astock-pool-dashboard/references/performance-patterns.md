# Data Retrieval & Operational Performance Patterns

> Extracted from session-20260622 (a-share-dashboard creation). Durable patterns, not transient errors.

## 1. Individual Stock Query vs Full-Market Scan

### Problem
`stock_zh_a_spot_em` (全市场实时行情) consistently times out after 60+ seconds. The response is unreliable for routine use.

### Solution
Use `stock_zh_a_hist` (个股历史行情) per stock instead. This returns individual stock data in 2–5 seconds with high reliability:

```python
# ✅ Reliable: individual stock query
import akshare as ak
df = ak.stock_zh_a_hist(symbol="600760", period="daily", start_date="20260501", adjust="qfq")

# ❌ Avoid: full-market scan (60+ second timeout)
df = ak.stock_zh_a_spot_em()  # do not use
```

### When to Use Full-Market
- **板块排行**: `stock_board_industry_name_em()` works in 10–20s, acceptable
- **全市场统计**: Use boards data + top-N quotes, not full spot scan

## 2. Position Manager Open Timeout

### Problem
`position_manager.py open` calls `_get_quote()` internally via akshare to fetch current price. This call frequently times out (EastMoney gateway instability), making the open command unreliable.

### Workaround
不要直接编辑技能目录内的 CSV。通过应用的持仓登记入口录入 `股票代码:股数@成本价`，运行时数据统一保存到 `output/pools/positions.csv`；随后使用 `astock pool list --json` 核对股池状态。

### Future Fix
If akshare-proxy-patch stabilizes, the `_get_quote()` call may become reliable again. Re-test before enabling position_manager open as the primary path.

## 3. Python Environment

System Python 3.9 has numpy version conflicts with akshare-proxy-patch dependencies. Always use:

```bash
python scripts/core/cli.py data quote 600760 --json
# 所有行情请求均通过项目统一 CLI 发起
```

## 4. Data Source Timeouts (Known)

| Endpoint | Avg. Response | Notes |
|----------|:------------:|-------|
| `stock_zh_a_hist` | 2–5s | ✅ Reliable for individual stocks |
| `stock_board_industry_name_em` | 10–20s | ✅ Usable for board ranking |
| `stock_individual_fund_flow` | 5–10s | ✅ Usable for fund flow check |
| `stock_zh_a_spot_em` | 60+ / timeout | ❌ Avoid |
| `stock_individual_info_em` | 5–15s | ✅ Usable |

## 5. Field Completeness Policy

Every data entry must carry its full set of analysis fields, not just a stock code. This ensures:
- All information visible in a single `cat` inspection
- CSV files are self-documenting (no hidden context)
- Pool-to-holdings transitions preserve data

| Pool | Minimum Fields |
|------|:-------------:|
| Watch | 11 (code/name/rating/reason/sector/pe/change_pct/fund_flow/entry_condition/market_context/added_date) |
| Selected | 15 (watch fields + ma_status/entry_trigger/stop_loss/take_profit/risk_level/notes) |
| Positions | 18 (selected fields + buy_date/buy_price/qty/status/strategy/expected_days/backtest_result) |
| History | 15 (positions fields + sell_date/sell_price/pnl/pnl_pct, minus ongoing fields) |
