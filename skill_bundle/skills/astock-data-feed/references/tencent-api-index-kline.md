# 腾讯指数日K线 API — 与个股K线的重要差异

## 问题

腾讯 `web.ifzq.gtimg.cn/appstock/app/fqkline/get` API 对**个股**返回 `qfqday`（前复权）字段，但对**指数**返回 `day`（原始）字段。忽略此差异会拿到空数据。

## 指数K线获取

```python
import urllib.request, json

# 个股用 qfqday，指数用 day
# 个股: data['data']['sz000400']['qfqday']
# 指数: data['data']['sh000001']['day']

def get_index_kline(code, days=30):
    """获取指数日K线"""
    url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{days}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))
    # 指数用 'day'，个股用 'qfqday'
    klines = data.get('data', {}).get(code, {}).get('day', [])
    return klines

# 使用示例
sh = get_index_kline('sh000001', 30)   # 上证指数
sz = get_index_kline('sz399001', 30)   # 深证成指
cy = get_index_kline('sz399006', 30)   # 创业板指
```

## 个股K线获取（对比）

```python
def get_stock_kline(code, days=120):
    """获取个股前复权日K线"""
    # 注意：个股代码需要市场前缀，如 sz000400, sh600760
    url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{days},qfq'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))
    klines = data.get('data', {}).get(code, {}).get('qfqday', [])
    return klines
```

## 字段索引（个股和指数一致）

```
[0] = date      (字符串，如 "2026-07-17")
[1] = open      (开盘价)
[2] = close     (收盘价)  ← 注意！不是索引4
[3] = high      (最高价)
[4] = low       (最低价)  ← 注意！不是索引2
[5] = volume    (成交量，指数也返回成交手数)
```

### ⚠️ 索引陷阱

常见OHLC顺序是 open/high/low/close，但腾讯的顺序是 **open/close/high/low**。第一次使用务必先 `print(klines[0])` 确认字段映射。

```python
# ✅ 正确
close = float(k[2])
high = float(k[3])
low = float(k[4])

# ❌ 错误（常见误解）
# close = float(k[4])  # 拿到的其实是 low！
# high = float(k[2])   # 拿到的其实是 close！
```

## 可用指数代码

| 指数 | 代码前缀 |
|:----|:--------:|
| 上证指数 | `sh000001` |
| 深证成指 | `sz399001` |
| 创业板指 | `sz399006` |
| 科创50 | `sh000688` |
| 沪深300 | `sh000300` |
| 深次新股 | `sz399678` |
| 上证50 | `sh000016` |
| 中证500 | `sh000905` |

## 示例：批量获取并计算涨跌幅

```python
import urllib.request, json

indices = {
    'sh000001': '上证指数', 'sz399001': '深证成指',
    'sz399006': '创业板指', 'sh000688': '科创50',
}

for code, name in indices.items():
    klines = get_index_kline(code, 15)
    last = klines[-1]
    prev = klines[-2]
    close = float(last[2])
    prev_close = float(prev[2])
    chg = (close / prev_close - 1) * 100
    print(f'{name:8s} {last[0]} 收{close:>8.2f}  {chg:+7.2f}%')
```

输出示例：
```
上证指数 2026-07-17 收 3764.15   -3.05%
深证成指 2026-07-17 收13706.88   -5.40%
创业板指 2026-07-17 收 3428.63   -7.15%
科创50   2026-07-17 收 1715.40   -7.12%
```