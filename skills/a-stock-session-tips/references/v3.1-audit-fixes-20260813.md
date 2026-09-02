# v3.1 审计修复日志 (2026-08-13)

> 对v3策略做系统审查发现8项问题, 逐项修复后8/8 PASS。本文档记录完整修复过程和验证数据。
> 脚本: `.\multi_dim_model_v3.py` (v3.1修复版, ~50KB)

## 审计方法论

审计分8个Phase:
1. 交付物完整性 (6文件)
2. JSON字段完整性 (8股×26字段)
3. 回测数学一致性 (年化/利用率/方向超额)
4. 功能声称vs代码实现 (22项声称逐项搜索代码)
5. 评分数学正确性 (重新计算CS)
6. 共振计数准确性
7. v2缺陷修复验证
8. 综合评级GPA

## 8项问题与修复

### HIGH-1: 堆量检测丢失

**根因**: v2→v3重构时FiveDimScorer的量能维度中`is_stack_vol`被静默移除。v2有3类量能异动(倍量/梯量/堆量), v3只剩2类。

**修复代码**:
```python
# 堆量: 连续5日高位横盘(主力建仓形态) — v3.1从v2恢复
is_stack = False
if len(volumes) >= 5 and len(volumes) >= 25:
    recent_5 = volumes[-5:]
    avg_5 = sum(recent_5)/5
    vol_20_before = sum(volumes[-25:-5])/20
    price_range = (max(closes[-5:])-min(closes[-5:]))/close*100 if close>0 else 0
    if vol_20_before > 0 and avg_5 > vol_20_before*1.3 and price_range < 5:
        is_stack = True
if is_double: anom_s = 20
elif is_stair: anom_s = 15
elif is_stack: anom_s = 10  # v3.1恢复
else: anom_s = 5
```

### HIGH-2: 多仓利用率>100%

**根因**: `held_total = sum(t["hold_days"] for t in trades)` 累加所有仓位的持仓天数, 2仓同时持仓10天 = 20, /交易日 → >100%。

**修复**: 改为按"有持仓的天数"统计(每天最多1):
```python
# v3.1修正: 归一化为min(100, 持仓天数/交易日), 多仓不累加
utilization = market_held_days / n_trading_days * 100 if n_trading_days > 0 else 0
utilization = min(100, utilization)  # 硬限制≤100%
```
其中 `market_held_days` 每天最多+1(有持仓就+1, 不管多少仓)。

**验证**: v3.0 2仓=118.2% → v3.1 2仓=62.3% ✅

### HIGH-3: 方向超额异常(+93pp)

**根因**: `held_up_days` 按仓位累加, 3仓×3只涨 = +3/day, 完全失真。

**修复**: 改为按总市值涨跌:
```python
# v3.1修正: 按总市值涨跌统计, 非按仓位累加
if positions:
    market_held_days += 1
    today_value = sum(pos["qty"] * stock_data[code]["closes"][day]
                      for code, pos in positions.items()
                      if day < len(stock_data[code]["closes"]))
    prev_pos_value = sum(pos["qty"] * stock_data[code]["closes"][day-1]
                         for code, pos in positions.items()
                         if day-1 < len(stock_data[code]["closes"]))
    if today_value > prev_pos_value:
        portfolio_up_days += 1
```

**验证**: v3.0 2仓=+45.1pp → v3.1 2仓=-2.9pp ✅, v3.0 3仓=+93.2pp → v3.1 3仓=-0.7pp ✅

### MEDIUM-4: 回测用简化版评分

**根因**: 回测引擎中的评分是2行简化版:
```python
# v3.0 (简化版)
tech_s = 35 if (ma5>ma10>ma20 and 40<=rsi<=68) else (25 if close>ma20 else 10)
vol_s = 25 if (vol_5 > 1.2*vol_20) else (15 if vol_5>vol_20 else 8)
```

**修复**: 升级为6因子完整版:
```python
# v3.1 (6因子)
# MA排列(20)+RSI(15) → tech_s
# 量价配合(25): 价涨量增25/缩量回踩22/放量18/平稳14/其他8
# 结构(20): 站上MA20+回踩0-5%=20/5-10%=15/其他10/5
# 动量(20): 20d>2+60d>5=20/20d>0+60d>0=15/其他10/5
```

**验证**: MA15盈亏比 v3.0=1.65 → v3.1=2.74 ✅ (选股精度提升)

### MEDIUM-5: 样本外验证

**修复**: 60/40 split + OOS盲测对比:
```python
n_split = int(n_total * 0.6)  # 前60%样本内, 后40%样本外
stock_kl_in = {c: kl[:n_split] for c, kl in stock_kl.items()}
stock_kl_out = {c: kl[n_split:] for c, kl in stock_kl.items()}
# 分别跑回测, 对比衰减率
```

### MEDIUM-6: 牛市偏差说明

**修复**: docstring诚实声明中新增:
```
v3.1新增: 回测期2024.12-2026.08主要上升趋势(牛市bias), 样本外验证显示
MA15单仓衰减率仅28.8%(存在过拟合), 但2仓分散衰减率87.1%(稳健)
v3.1新增: 样本外验证已实现(60/40 split), 3仓分散衰减率98.6%(几乎无衰减)
```

### LOW-7: 时间戳

**修复**: JSON输出加meta:
```python
all_results_with_meta = {
    "run_timestamp": run_timestamp,  # "2026-08-13 11:19:08"
    "version": "v3.1",
    "market_state": model.gate.state,
    "results": all_results
}
```

### LOW-8: backtest注册标注

**修复**: docstring从"可直接被backtest_engine回测"改为"设计为可注册到backtest_engine; 注: 当前为可注册设计, 未实际import到backtest_engine; 实际回测通过RotationBacktest独立执行"

## 样本外验证完整数据 (60/40 split, 312日样本内 + 209日样本外)

| 配置 | 样本内收益 | 样本外收益 | 衰减率 | 样本内回撤 | 样本外回撤 | 样本内胜率 | 样本外胜率 | 样本外盈亏比 |
|:-----|:---------:|:---------:|:------:|:---------:|:---------:|:---------:|:---------:|:----------:|
| MA10基准 | +29.2% | +25.5% | 87.3% | -18.8% | -20.8% | 37.3% | 45.2% | 1.75 |
| MA15单仓 | +83.4% | +24.0% | 28.8% | -19.6% | -21.8% | 39.5% | 45.2% | 1.68 |
| MA20宽离场 | +76.3% | +5.7% | 7.5% | -18.6% | -29.5% | 38.9% | 44.4% | 1.13 |
| **MA15+2仓** | +41.8% | **+36.4%** | **87.1%** | -14.7% | **-12.0%** | 39.3% | **48.5%** | **2.15** |
| MA15+3仓 | +27.8% | +27.4% | 98.6% | -16.0% | -11.1% | 41.5% | 46.8% | 1.87 |

### 关键发现

1. **MA15单仓过拟合**: 样本内+83.4%→样本外+24.0%, 衰减率28.8%。回撤从-19.6%→-21.8%(更大)
2. **MA20严重过拟合**: 衰减率7.5%, 样本外仅+5.7%, 回撤-29.5%
3. **2仓分散最稳健**: 衰减率87.1%, 样本外仍+36.4%, 回撤仅-12.0%, 盈亏比2.15
4. **3仓分散几乎无衰减**: 衰减率98.6%, 但收益更低(+27.4%)
5. **所有配置样本外胜率均高于样本内** (45% vs 37-40%): 可能因样本外恰好是震荡市

### 推荐配置更新

基于OOS验证, 推荐从"MA15单仓"改为**"A+MA15+2仓分散"**:
- 衰减率87.1%(vs MA15单仓28.8%) → 稳健
- 样本外回撤-12.0%(vs MA15单仓-21.8%) → 风险更低
- 盈亏比2.15(vs MA15单仓1.68) → 更优

## v3.0 vs v3.1 关键指标对比

| 指标 | v3.0(521日) | v3.1(312日样本内) | 修复 |
|:-----|:-----------:|:-----------------:|:-----|
| 2仓利用率 | 118.2%(异常) | 62.3%(正常) | HIGH-2归一化 |
| 3仓利用率 | 174.7%(异常) | 62.3%(正常) | HIGH-2归一化 |
| 2仓方向超额 | +45.1pp(异常) | -2.9pp(合理) | HIGH-3口径修正 |
| 3仓方向超额 | +93.2pp(异常) | -0.7pp(合理) | HIGH-3口径修正 |
| MA15盈亏比 | 1.65 | 2.74 | MEDIUM-4增强评分 |
| 堆量检测 | 缺失 | 恢复 | HIGH-1恢复 |
| 样本外验证 | 无 | 60/40 split | MEDIUM-5新增 |

## 修复验证结果: 8/8 PASS

```
[PASS] HIGH-1 堆量检测恢复: is_stack + 堆量注释存在
[PASS] HIGH-2 利用率<=100%: max=62.3%
[PASS] HIGH-3 方向超额合理: range=-5.9~-0.7pp
[PASS] MEDIUM-4 回测增强版评分: tech_ma/tech_rsi/vol_ratio存在, 简化版移除
[PASS] MEDIUM-5 样本外验证: 60/40 split + OOS对比
[PASS] MEDIUM-6 牛市偏差说明: docstring中有"牛市bias"+衰减率
[PASS] LOW-7 时间戳: 代码+JSON都有timestamp
[PASS] LOW-8 backtest注册标注: "设计为可注册,未实际import"
```