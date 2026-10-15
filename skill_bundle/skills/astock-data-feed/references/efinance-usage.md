# efinance 替代方案使用指南

## 为什么需要 efinance

**三大核心优势：**

1. **零积分消耗**：efinance 直接请求东方财富 API，不经过代理网关。而 `akshare + proxy-patch` 每次调用都消耗代理积分（余额查询：`http://{gateway}:47001/api/token/{token}`）。凡是 efinance 能提供的数据，优先用它可**大幅节省积分**。

2. **速度快**：技能脚本 `fetch_realtime.py --quote` 走新浪/腾讯链路，单只股票耗时 ~4.6s；efinance 获取相同数据仅需 **0.17~0.43s**，且提供技能脚本没有的5档盘口、逐分钟资金流向、逐笔成交等功能。

3. **现已被集成到技能脚本**：`--fund-flow` 和 `--limit-up-pool` 已默认使用 efinance（零积分、数据更丰富），无需单独调用。

> **黄金法则**：if efinance can provide it -> use efinance (zero credit, faster). Only fall back to akshare + proxy-patch for data efinance cannot provide (筹码分布, 全市场行情, 新闻).

## 安装

```bash
pip install efinance
```

> 本项目在 `.venv` 中使用 Python 3.11，efinance 也需通过 `.venv/bin/python3` 运行。
> 系统 Python 3.9 有 numpy C 扩展版本冲突，不可用。

## 常用接口（实测速度）

| 接口 | 功能 | 速度 | 关键返回字段 |
|------|------|:----:|-------------|
| `get_latest_quote("600760")` | 实时行情 | **0.43s** | 最新价/涨跌幅/换手率/市盈率/总市值 |
| `get_quote_snapshot("600760")` | 5档盘口 | **0.17s** | 买卖五档/均价/涨停价/跌停价 |
| `get_quote_history("600760")` | 日K线 | **0.98s** | 全部历史，含涨跌幅/成交额 |
| `get_today_bill("600760")` | 逐分钟资金流向 | **0.33s** | 主力/小单/中单/大单/超大单 |
| `get_history_bill("600760")` | 历史资金流向 | **0.32s** | 主力净额+占比 |
| `get_deal_detail("600760")` | 逐笔成交 | **0.63s** | 时间/成交价/成交量/单数 |
| `get_base_info("600760")` | 基本面 | **0.26s** | 行业/市盈率/市净率/净利率/ROE |
| `get_daily_billboard("2026-06-16")` | 龙虎榜 | **0.11s** | 当日上榜股票 |

## 代码示例

```python
import efinance as ef

# 实时行情
df = ef.stock.get_latest_quote("600760")
print(df[['代码','名称','最新价','涨跌幅','换手率']])

# 5档盘口（37行 Series）
snap = ef.stock.get_quote_snapshot("600760")
print(f"买一: {snap['买1价']} x {snap['买1数量']}")
print(f"卖一: {snap['卖1价']} x {snap['卖1数量']}")

# 资金流向（逐分钟）
bill = ef.stock.get_today_bill("600760")
print(bill[['时间','主力净流入','小单净流入','中单净流入']])

# K线
hist = ef.stock.get_quote_history("600760", beg="20260601", end="20260616", klt=101)
print(hist[['日期','开盘','收盘','最高','最低','涨跌幅']].tail(5))

# 基本面
info = ef.stock.get_base_info("600760")
print(f"行业: {info['所处行业']}, PE: {info['市盈率(动)']}, PB: {info['市净率']}")
```

## 技能脚本中的 efinance 集成

以下两个 CLI 命令已内嵌 efinance，零积分：

### --fund-flow（资金流向）

```python
# fetch_realtime.py 中的实现
def cmd_fund_flow(code: str, days: int, output_json: bool):
    df = ef.stock.get_history_bill(code)       # 历史资金流向
    if df is None or df.empty:
        df = ef.stock.get_today_bill(code)     # 降级：逐分钟资金流向
```

**输出兼容性**：efinance 列名自动映射为原 akshare 格式（`主力净流入` -> `主力净流入-净额`），调用方无感知。

### --limit-up-pool（涨停股池）

```python
# fetch_realtime.py 中的实现
def cmd_limit_up_pool(date_str: str, top: int, output_json: bool):
    df = ef.stock.get_daily_billboard(date_str)  # 龙虎榜
    df = df[df["涨跌幅"] >= 9.9]                  # 过滤涨停
```

**数据更丰富**：efinance 龙虎榜返回 15+ 列（龙虎榜净买额、上榜原因、流通市值等），原 akshare 涨停池仅 10 列。

### 积分节省效果

| 命令 | 旧方案 | 新方案 | 每次节省 |
|------|--------|--------|:--------:|
| `--fund-flow` | 消耗 1 积分 (proxy) | 零积分 (efinance) | ~1 积分 |
| `--limit-up-pool` | 消耗 1 积分 (proxy) | 零积分 (efinance) | ~1 积分 |

按每天各查 10 次计算，每天节省 ~20 积分。

## 何时用技能脚本 vs efinance

| 需求 | 用哪个 | 原因 | 积分消耗 |
|------|--------|------|:--------:|
| 实时行情（快速） | efinance | 0.17s vs 4.6s | 零 |
| 5档盘口/均价/涨跌停价 | efinance | 技能不支持 | 零 |
| 资金流向 | efinance（已在 `--fund-flow` 内置） | 零积分，速度 0.33s | 零 |
| 涨停股池 | efinance（已在 `--limit-up-pool` 内置） | 零积分，数据更丰富 | 零 |
| 大盘指数 | 技能脚本 `--index` | efinance 不支持 | 零 |
| 板块排行 | 技能脚本 `--boards-summary` | efinance 不支持 | 零 |
| 技术指标 MA/MACD/KDJ | 技能脚本 `fetch_technical.py` | efinance 不支持 | 零（本地计算） |
| 成交明细 | efinance | 0.63s 更快 | 零 |
| 全市场行情 | 技能脚本 + proxy-patch | efinance 东财被封 | 消耗积分 |
| 筹码分布 | AKShare `stock_cyq_em()` | efinance 不支持 | 消耗积分 |
| A股新闻 | AKShare `stock_news_em()` | efinance 不支持 | 消耗积分 |

### 已知限制

- `get_realtime_quotes()`（全市场行情）依赖东财 `push2.eastmoney.com`，已被封锁不可用
- `get_quote_history()` 返回全部历史（可能 >6000行），需手动 `tail()`
- `get_latest_quote(['sh000001'])` 查询指数时可能报错，指数数据建议改用 `ak.stock_zh_index_daily_em()` 或技能脚本 `--index`
- 无内置筹码分布函数
- 无内置技术指标计算（需配合 MyTT 或 `fetch_technical.py`）
