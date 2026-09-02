# Proxy 积分消耗速查表

> 所有走代理的请求（URL 路径在 `hook_domains` 中匹配）均消耗积分。
> 节省积分的唯一方法：不走代理——使用 **新浪/腾讯/MyTT/DangInvest** 等不触及东财域名的数据源。

## 接口 → 实际URL → 积分消耗

| 函数 | 实际请求 URL | 单次积分 | hook 状态 |
|------|-------------|:--------:|:---------:|
| `ak.stock_zh_a_spot_em` | `push2.eastmoney.com/api/qt/clist/get` | **12 ~ 18** ⚠️ | ✅ 路径精确 |
| `ak.stock_board_industry_name_em` | `push2.eastmoney.com/api/qt/clist/get` | 1 ~ 4 | ✅ 同路径 |
| `ak.stock_individual_info_em` | `push2.eastmoney.com/api/qt/stock/get` | 1 ~ 2 | ✅ 路径精确 |
| `ak.stock_cyq_em` (筹码分布) | `push2his.eastmoney.com/api/qt/stock/kline/get` | 1 ~ 2 | ✅ 路径精确 |
| `ak.stock_zh_a_hist` (日K线) | `push2his.eastmoney.com/api/qt/stock/kline/get` | 1 ~ 2 | ✅ 同路径 |
| `ak.stock_zh_index_daily_em` (指数) | `push2his.eastmoney.com/api/qt/stock/kline/get` | 1 ~ 2 | ✅ 同路径 |
| `ak.stock_zt_pool_em` (涨停) | `push2ex.eastmoney.com/getTopicZTPool` | 1 ~ 2 | ✅ 域名级 |
| `ak.stock_zt_pool_previous_em` (连板) | `push2ex.eastmoney.com/getYesterdayZTPool` | 1 ~ 2 | ✅ 域名级 |
| `ak.stock_lhb_detail_em` (龙虎榜) | `datacenter-web.eastmoney.com/api/data/v1/get` | 1 ~ 2 | ✅ 域名级 |
| `ak.stock_hsgt_fund_flow_summary_em` (北向) | `datacenter-web.eastmoney.com/api/data/v1/get` | 1 ~ 2 | ✅ 域名级 |

## 消耗大户排名

| 排名 | 函数 | 单次积分 | 用途 | 省积分替代 |
|:----:|------|:--------:|------|-----------|
| 🥇 | `stock_zh_a_spot_em` | **12~18** | 全市场行情(~5800只) | → 腾讯直连 `qt.gtimg.cn` (零积分) |
| 🥈 | `stock_board_industry_name_em` | 1~4 | 行业板块排行 | → DangInvest (零积分) |
| 🥉 | 其余各接口 | 1~2 | K线/筹码/龙虎榜等 | → 新浪/腾讯链路 (零积分) |

> **注意**：`stock_zh_a_spot_em` 单次 12~18 分，是全表最贵的。一次全市场行情消耗够调 12 次日K线。

## 当前 hook_domains（路径精确化）

```yaml
hook_domains:
  - "push2.eastmoney.com/api/qt/clist/get"     # 全市场行情(12~18分)、行业板块(1~4分)
  - "push2.eastmoney.com/api/qt/stock/get"      # 个股信息(1~2分)
  - "push2his.eastmoney.com/api/qt/stock/kline/get"  # 日K线/筹码分布(1~2分)
  - "push2ex.eastmoney.com"                     # 涨跌停池
  - "datacenter-web.eastmoney.com"              # 龙虎榜、北向资金
```

**省积分效果**：非上述路径的请求（如同域名 `push2.eastmoney.com` 下的其他 API）不会被拦截，直连不消耗积分。

## 各数据源积分速查

| 数据源 | 积分消耗 | 覆盖功能 |
|--------|:--------:|----------|
| 新浪 (hq.sinajs.cn / money.finance.sina.com.cn) | **零** | 行情、K线、指数 |
| 腾讯 (qt.gtimg.cn / web.ifzq.gtimg.cn / stock.gtimg.cn) | **零** | 行情、K线、成交明细 |
| DangInvest (dang-invest.com) | **零** | 板块排行、市场新闻 |
| MyTT (本地计算) | **零** | 技术指标 |
| efinance (若路径在 hook 中) | **消耗积分** | 同东财各接口 |
| proxy (push2.eastmoney.com / push2his / push2ex / datacenter-web) | **消耗积分** | 封控的东财接口 |

## 省积分策略

1. **`stock_zh_a_spot_em` 最贵 (12~18 分/次)** — 非必要不调。替代方案：腾讯直连 `qt.gtimg.cn` 或新浪、DangInvest 均零积分
2. **`--boards-summary` 默认 DangInvest** → 零积分 ✅
3. **日K线 `fetch_history.py` 默认新浪/腾讯** → 零积分 ✅
4. **资金流向 `--fund-flow`**：虽然已切 efinance，但 efinance 仍请求 `push2his.eastmoney.com`。真正零积分走腾讯 `qt.gtimg.cn`
5. **大额调用前查余额**：`python3 fetch_realtime.py --balance`（当前余额 10990 ✅）
6. **临时禁用 proxy**：`akshare_proxy_patch.uninstall_patch()`，之后所有请求直连
