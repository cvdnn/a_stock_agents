# a-stocks 已知问题与修复 (absorbed from skill: a-stocks-pitfalls)

> This file was consolidated from the now-archived `a-stocks-pitfalls` skill.
> Load alongside a-stocks when debugging or after code changes.

## 方法名陷阱

| 文件 | 错误调用 | 正确调用 |
|:-----|:--------|:--------|
| `market_assessor.py:102` | `bridge.index_snapshot()` | `bridge.tencent_index()` |
| `a_stocks.py cmd_evaluate` | `auto_scan(code, interval, count)` | `auto_scan(code, interval_days=..., kline_count=...)` |

实例方法用 `tencent_index()`，模块级独立函数用 `index_snapshot()`。

## K线端点性能

| 端点 | 延迟 |
|:-----|:----:|
| `web.ifzq.gtimg.cn` | 21s ❌ |
| `ifzq.gtimg.cn` | 0.18s ✅ |

## 集成冒烟测试

```bash
cd skills/a-stocks/scripts && python3 -c "
from data_bridge import DataBridge; b=DataBridge()
assert len(b.tencent_kline('600519',30))>=26
assert b.get_realtime_quote('600519') is not None
assert len(b.tencent_index())>=3
from technical_indicators import calc_all
t=calc_all(b.tencent_kline('600519',60))
assert 'close' in t['latest']
from combo_scorer import ComboScorer
s=ComboScorer().score_full(b.tencent_kline('600519',60),t['latest'])
assert s['rating'] in 'ABCD'
from data_source_registry import summary
assert summary()['total_sources']==5
print('OK')
"
```

## 数据接口审计

详见 [`references/data-audit-20260728.md`](references/data-audit-20260728.md) — L1 数据接口的延迟、覆盖率、端点对比审计结果。

## 数据解析陷阱: tencent_quote 代码字段污染

`data_bridge.py` `tencent_quote()` 代码提取有 bug:
```python
code_raw = parts[0].split("_")[-1] if "_" in parts[0] else parts[0]
code = code_raw.replace("sh", "").replace("sz", "")
```
腾讯返回格式: `v_sz000400="51~...` → parts[0] = `v_sz000400="51"` → split("_")[-1] = `sz000400="51"` → replace后 code = `000400="51"` (被 `="51"` 后缀污染)。

**影响**: `fetch_batch_snapshot()` 中匹配 `data["code"] == c` 永远为 False，`a_stocks.py batch` 返回 `[]`。
**现象**: 单独 `quote` 命令正常（`get_realtime_quote` 用 name 做 key 不依赖 code 匹配），但 `batch` 命令返回空数组。

修复: 在 tencent_quote 中加 `code_raw = code_raw.split("=")[0]` 去掉后缀。

## analyze/score 命令 KeyError: 'score'

`cmd_analyze` 和 `cmd_score` 遍历 scores 时未跳过非维度键:
```python
for dim, info in scores.items():
    if dim in ("total", "max_total", "rating", "rating_text", "suggested_position"):
        continue
    print(f"  {dim}: {info['score']}/{info['max']} {info['reason']}")
```
`scores` 含 `data_availability`(dict) 和 `effective_max`(int, **P1新增**)，不是带 score/max 的维度 dict。遍历到 `data_availability` 时 `info['score']` → KeyError。

修复: 在 skip 列表中加 `"data_availability", "effective_max"`，并增加 `isinstance(info, dict) and "score" in info` 守卫。
