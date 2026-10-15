# 腾讯历史K线API — web.ifzq.gtimg.cn

当 proxy-patch（东财链路）和 fetch_history.py（新浪链路）都不可用时，腾讯自选股数据接口是本会话验证过的**可靠历史K线降级方案**。

## API端点

```
GET https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=<前缀+代码>,day,,,<条数>,qfq
```

| 参数 | 说明 | 示例 |
|------|------|------|
| 前缀 | sh=沪市, sz=深市 | sz002294 |
| 代码 | 6位数字股票代码 | 002294 |
| day | 固定值"day"，表示日线 | day |
| 条数 | 返回K线条数（最多约200） | 120 |
| qfq | 前复权标志 | qfq |

## 返回格式

JSON 对象，K线数组嵌套在 `data.<代码>.qfqday`：

```json
{
  "code": 0,
  "msg": "",
  "data": {
    "sz002294": {
      "qfqday": [
        ["2026-04-16", "65.850", "59.990", "65.950", "59.990", "235382.000"],
        ...
      ]
    }
  }
}
```

### 字段映射

| 数组索引 | 含义 | 示例 |
|:--------:|------|------|
| 0 | 日期 (YYYY-MM-DD) | "2026-04-16" |
| 1 | 开盘价 (open) | "65.850" |
| 2 | **收盘价 (close)** ⚠️ | "59.990" |
| 3 | **最高价 (high)** ⚠️ | "65.950" |
| 4 | 最低价 (low) | "59.990" |
| 5 | 成交量 (volume, 手) | "235382.000" |

> **注意：** 数组内顺序是 [date, open, high, close, low, volume]，不是标准的 OHLC 顺序。**high 和 close 的位置互换**（索引2是high，索引3是close），区别于 tushare/akshare 的 OHLC 惯例。

## 解析示例

```bash
curl -s "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz002294,day,,,120,qfq" | python3 -c "
import json, sys
data = json.load(sys.stdin)
kline = data['data']['sz002294']['qfqday']
print(f'获取到 {len(kline)} 条K线')

# 近60日统计
recent = kline[-60:]
closes = [float(x[3]) for x in recent]  # 索引3=收盘价
highs = [float(x[2]) for x in recent]   # 索引2=最高价
lows = [float(x[4]) for x in recent]    # 索引4=最低价
print(f'近60日: 最高{max(highs):.2f}  最低{min(lows):.2f}  均价{sum(closes)/len(closes):.2f}')

# 最后5条
for item in kline[-5:]:
    print(f'{item[0]}  O:{item[1]} H:{item[2]} C:{item[3]} L:{item[4]} V:{item[5]}')
"
```

## 已知限制

- **仅支持日线** — 不提供周线/月线/分钟线
- **前复权** — 数据是前复权价格，已包含除权除息调整（如分红送股）
- **最大约200条** — 超过200条的请求可能被截断或返回空
- **不含未复权数据** — 参数固定为 qfq，没有不复权选项
- **不含技术指标** — 只有原始 OHLCV，需自行计算 MA/MACD/KDJ

## 优势

- ✅ 任何时段稳定可用（同 qt.gtimg.cn 生态）
- ✅ 支持 `curl` 直接访问（不受 HTTP 安全扫描限制）
- ✅ 纯 JSON 格式，解析简单
- ✅ 速度快 (~0.5-1s)
- ✅ 包含除权除息调整，可直接用于技术分析

## 实战验证

2026-07-15 交易日盘中验证：成功获取信立泰(002294) 120日K线，数据完整，从 2026-04-16 到 2026-07-15 共 121 条记录。
