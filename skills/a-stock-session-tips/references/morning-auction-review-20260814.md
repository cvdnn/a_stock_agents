# 早盘竞价审查配方 (2026-08-14实测 · Windows git-bash 环境)

适用: 开盘前/竞价时段 "早盘审查X、Y主线动作、评估持仓策略" 类任务。全流程零依赖（纯 curl + Python stdlib，无需 pandas/akshare/MyTT）。

## 一次性采集命令

```bash
mkdir -p $LOCALAPPDATA/Temp/astk/kl && cd $LOCALAPPDATA/Temp/astk
# ① 实时竞价: 两股+指数+美股 (GBK编码, 一次HTTP)
timeout 10 curl -s "https://qt.gtimg.cn/q=sh600276,sh601899,sh000001,sz399001,sz399006,sh000688,usDJI,usIXIC" -H "User-Agent: Mozilla/5.0" -o quotes.txt
# ② 金属期货 (紫金/有色类隔夜催化)
timeout 10 curl -s "https://qt.gtimg.cn/q=hf_GC,hf_HG,hf_CL" -H "User-Agent: Mozilla/5.0" -o metals.txt
# ③ 板块排行 (DangInvest, 零积分)
timeout 15 curl -s "https://dang-invest.com/api/market/boards/summary" -H "User-Agent: Mozilla/5.0" -o boards.json
# ④ K线 (qfq 140根; 指数/个股同接口)
for pair in "600276:sh" "601899:sh" "000001:sh"; do code="${pair%%:*}"; pfx="${pair##*:}"; timeout 15 curl -s "https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=${pfx}${code},day,,,140,qfq" -H "User-Agent: Mozilla/5.0" -o "kl/${code}.json"; done
```

## 解析要点

### 股票/指数行情 (qt.gtimg.cn, GBK)
`v_CODE="1~名称~代码~..."` 按 `~` split: `[1]=名 [3]=现价 [4]=昨收 [5]=今开 [6]=量(手) [30]=时间 [33]=高 [34]=低 [38]=换手 [49]=量比`。涨跌幅自算 `(p3-p4)/p4*100`。
- 美股 (usDJI/usIXIC): 字段结构同股票，但 p[30] 是日期串、p[49] 是巨大成交量（非量比），勿误用。
- 竞价时段(09:15-09:25)部分指数返回昨收（涨跌0.00%），勿误读。

### 金属期货 hf_ (qt.gtimg.cn)
**字段顺序与股票完全不同**: `v_hf_GC="4376.23,-1.00,4376.50,4376.90,4419.40,4373.50,09:23:05,4420.40,4408.20,0,1,1,2026-08-14,COMEX黄金"`
split('~') 后: `[0]=现价 [1]=涨跌额 [2..5]=开/高/收/低? [6]=时间 [12]=日期 [13]=名称`。名称在**末尾**。

### DangInvest 板块 (boards/summary)
```json
{"data": {"count": 10, "total": 110, "items": [{"groupKey":"半导体","groupLabel":"半导体","count":197,"totalMarketCapYuan":...,"totalTurnoverYuan":...,"changePct":1.38,"size":...}]}}
```
- 解析: `items = d['data']['items']`（不是 `data` 或 `boards` 顶层列表——按错结构解析得 0 条）。
- 排序: `sorted(items, key=lambda it: -it['changePct'])`。
- `limit` 参数生效（limit=10 只回 10 条，有色/医药可能不在 TOP/BOTTOM 可见范围内）→ 用代表股采样补盲区。
- 返回 `meta.effectiveTradeDate` 为当前生效交易日，竞价时段即反映当日板块强度。

### K线 qfq (ifzq.gtimg.cn fqkline)
`d['data'][code]['qfqday']`（个股）或 `['day']`（指数），list-of-lists `[date, open, close, high, low, vol]`。
- close 在索引 **2**；vol 单位手。
- 指数K线无 `qfqday` 只有 `day`（用 `data.get('qfqday') or data.get('day')`）。

## 零依赖技术指标计算 (heredoc python)

```python
def sma(vals, n): return sum(vals[-n:])/n if len(vals)>=n else None
def ema_series(vals, n):
    k = 2/(n+1); e = vals[0]; out=[e]
    for v in vals[1:]: e = v*k + e*(1-k); out.append(e)
    return out
def macd(closes):
    e12, e26 = ema_series(closes,12), ema_series(closes,26)
    difs = [a-b for a,b in zip(e12,e26)]
    dea = ema_series(difs,9)[-1]
    return dict(dif=difs[-1], dea=dea, bar=2*(difs[-1]-dea))
def kdj(kl, n=9):
    K=D=50
    for i in range(len(kl)):
        hi=max(float(kl[j][3]) for j in range(max(0,i-n+1),i+1))
        lo=min(float(kl[j][4]) for j in range(max(0,i-n+1),i+1))
        rsv=50 if hi==lo else (float(kl[i][2])-lo)/(hi-lo)*100
        K=2/3*K+1/3*rsv; D=2/3*D+1/3*K
    return dict(k=K, d=D, j=3*K-2*D)
def rsi(closes, n=14):
    g=[max(closes[i]-closes[i-1],0) for i in range(1,len(closes))]
    l=[max(closes[i-1]-closes[i],0) for i in range(1,len(closes))]
    ag,al=sum(g[-n:])/n, sum(l[-n:])/n
    return 50 if (ag+al)==0 else 100*ag/(ag+al)
def boll(closes, n=20):
    mid=sum(closes[-n:])/n
    sd=(sum((c-mid)**2 for c in closes[-n:])/n)**0.5
    return dict(mid=mid, upper=mid+2*sd, lower=mid-2*sd)
```
补充: 昨量/5日均量比 = `vol[-1] / mean(vol[-6:-1])`；20日高低点用 `kl[-20:]` 的 high/low 列。

## 早盘审查输出结构

竞价快照表(两股+指数+外盘) → 主线动作判断(板块强弱, 算力/有色/医药) → 技术面表(MA/MACD/KDJ/RSI/BOLL/量比) → 持仓策略矩阵(场景×触发×动作, 以昨日止损/关键价位为锚) → 操作优先级 → 风险提示。策略矩阵中"竞价恰好踩到昨日止损位"要作为最高优先级警示。

## 实测陷阱 (2026-08-14)

1. **竞价价漂移**: 恒瑞 09:21 +0.32% → 09:25 最终 -0.15%；紫金 09:21 -1.02% → 09:25 -1.27%。早于 09:25 的竞价快照不能作为结论。
2. **昨日报告行情数字不可信**: track_601899-600276 报告标注"尾盘"但价格(54.34/32.51/上证3955.33)与实际收盘(53.76/32.21/3926.96)偏差 1~2%——疑似取的是 ~14:30 盘中值。策略价位(止损/压力)是决策产物可沿用，行情数字必须用 K线 API 重取。
3. **fetch_realtime.py 依赖 pandas**: 系统 python 无 pandas 时直接 `ModuleNotFoundError`——不要卡在装依赖上，直接 curl DangInvest API（见上）。
4. **紫金竞价 31.80 = 昨日止损 31.80**: 止损位被竞价精准触及是强触发信号，输出"开盘30分钟定方向"的三场景预案（拉回/弱势反抽/放量破位）。
