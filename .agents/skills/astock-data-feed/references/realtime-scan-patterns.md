# 盘中实时扫描模式 — 逆势标的快速筛选

## 场景

大盘普跌日（如2026-07-13 上证-1.71%），需要快速扫描全市场中逆势上涨的科技/AI/半导体标的。a-share-data 的 `fetch_realtime.py` 和 `fetch_technical.py` 在 WSL 下超时率高，不适合做全市场扫描。

## 推荐方案：东方财富 HTTP API 直连 + 腾讯 API 验证

### 方案A：全市场涨幅排行（东财 push2 API）

```python
import urllib.request, json

# 全市场涨幅排行（取前100）
url = 'http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fltt=2&fid=f3&fs=m:0+t:6+f:!50,m:0+t:80+f:!50,m:1+t:2+f:!50,m:1+t:23+f:!50&fields=f2,f3,f4,f12,f14'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read().decode())
items = data['data']['diff']

# 过滤：科技方向 + 涨幅>2% + 成交额>3亿
tech_keywords = ['半导体','芯片','微','电子','通信','光','AI','智能','算力','PCB']
for item in items:
    name = item.get('f14', '')
    pct = item.get('f3', 0)
    amount = item.get('f20', 0)  # 成交额
    if any(kw in name for kw in tech_keywords) and pct > 2 and amount > 3e8:
        print(f"{item['f12']} {name} {pct/100:+.2f}% 成交{amount/1e8:.1f}亿")
```

### 方案B：重点科技标的批量行情（腾讯 API）

```python
import urllib.request

# 核心AI/半导体/科技标的
targets = 'sh603893,sh600584,sh603501,sz002156,sz300308,sz300502,sz002371'
url = f'https://qt.gtimg.cn/q={targets}'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=10)
text = resp.read().decode('gbk')
for line in text.strip().split(';'):
    if '~' not in line: continue
    p = line.split('~')
    code, name, price, chg = p[2], p[1], p[3], p[32]
    print(f"{code} {name} {price} {chg}%")
```

### 方案C：行业板块排行（东财 HTTP，非 HTTPS）

```python
url = 'http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&fields=f2,f3,f4,f12,f14,f8,f20,f62&fs=m:90+t:2'
# f3=涨跌幅, f8=涨家数, f20=跌家数, f62=主力净流入
```

## 踩坑记录

1. **HTTPS 被阻断** — `push2.eastmoney.com` 的 HTTPS 接口在 WSL 下会 `RemoteDisconnected`，改用 HTTP 即可。腾讯 `qt.gtimg.cn` 的 HTTP 和 HTTPS 都稳定。
2. **东财 HTTP 限流** — 同一 IP 短时间请求过多会被限流。建议每次扫描间隔 >10s，或切换到腾讯 API 备选。
3. **腾讯日K线接口不稳定** — `web.ifzq.gtimg.cn/appstock/app/fqkline/get` 部分标的返回为空。始终跟 `qt.gtimg.cn` 实时行情配合使用。
4. **`fetch_technical.py` WSL 超时** — 通过 system Python 调用 akshare 脚本时经常超时（>30s）。替代方案：用 venv Python 直接调腾讯 API 做简化评分，或使用 Eastmoney HTTP API。
