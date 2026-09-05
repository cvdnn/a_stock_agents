# 腾讯行情 API — A股市场数据直连

当 akshare 的东方财富链路断连或超时时，腾讯行情 API 是最稳定的替代方案。

## 大盘指数

```python
import urllib.request

# 批量获取指数/个股行情
# 格式: 腾讯多股接口，~ 分隔字段
url = "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sz399007,sz399008"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
resp = urllib.request.urlopen(req, timeout=10)
text = resp.read().decode("gbk")

# 解析示例：索引 3=现价 4=昨收 30=时间
# v_sh000001="1~上证指数~000001~4028.90~4112.45~..."
for line in text.strip().split("\n"):
    parts = line.split("~")
    name = parts[1]
    price = float(parts[3])
    prev_close = float(parts[4])
    change_pct = (price - prev_close) / prev_close * 100
    print(f"{name}: {price:.2f}  ({change_pct:+.2f}%)")
```

## 关键字段索引

| 索引 | 字段 | 说明 |
|:----:|------|------|
| 1 | name | 名称 |
| 3 | price | 当前价 |
| 4 | prev_close | 昨收 |
| 5 | high | 最高 |
| 6 | low | 最低 |
| 7 | volume | 成交量 |
| 30 | time | 时间 YYYYMMDDHHMMSS |
| 31 | change | 涨跌额 |

## 编码方式

- 上证: `sh` + 代码（如 `sh000001`, `sh600519`）
- 深证: `sz` + 代码（如 `sz399001`, `sz000858`）
- 批量查询: 逗号分隔，一次最多约 80 只

## 可靠性

- **稳定，2秒内返回。** 不依赖东方财富，不触发反爬。
- 用 `urllib` 而非 `requests` / `curl` 成功率更高（腾讯对 urllib UA 更友好）。
- 编码 `gbk`，非 utf-8。

## 同生态：历史K线（web.ifzq.gtimg.cn）

同一个腾讯生态下，**web.ifzq.gtimg.cn** 提供历史前复权日K线（与 qt.gtimg.cn 互补）：

```
https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=<前缀+代码>,day,,,<条数>,qfq
```

示例（信立泰120日K线）：
```
https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz002294,day,,,120,qfq
```

返回 JSON 格式，K线数组在 `data.<代码>.qfqday`，每条格式：
```
["2026-04-16", "65.850", "59.990", "65.950", "59.990", "235382.000"]
#  [date,         open,    high,    close,   low,      volume]
```

**注意：** `web.ifzq.gtimg.cn` 是独立子域名，不受 `qt.gtimg.cn` 的 HTTP 安全扫描限制。可用 `curl` 直接访问。数据频率仅日线，不提供分钟线。

详见 `references/tencent-api-historical-kline.md`。

## 局限性

- 不提供板块排行、资金流向等衍生数据
- 不提供个股财务数据
- 历史K线仅限日线前复权（通过 web.ifzq.gtimg.cn 获取）
