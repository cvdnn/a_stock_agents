# 板块排行 + 概念板块关键字扫描

## 目的

快速获取 A 股行业板块涨跌排行榜和概念板块关键字匹配结果，用于每日复盘。

## 核心 API

| API | 返回 | 关键列 |
|-----|------|--------|
| `ak.stock_board_industry_name_em()` | 全行业板块(86个) | 板块名称, 涨跌幅, 上涨家数, 下跌家数 |
| `ak.stock_board_concept_name_em()` | 全概念板块(494+) | 板块名称, 涨跌幅, 上涨家数, 下跌家数 |

## 已知陷阱（实测验证）

### 1. 概念板块列名陷阱

**错误写法**（自然语言直觉）：
```python
concept['概念板块名称'].str.contains(kw)
# KeyError: '概念板块名称'
```

**正确写法**：
```python
concept['板块名称'].str.contains(kw)
```

akshare 的 `stock_board_concept_name_em()` 返回列名是 `板块名称`，和行业板块同名。不要从"概念板块"这个语义推导出 `概念板块名称`。

### 2. 关键字重复匹配

```python
# 关键字 '芯片' 和 '存储' 都会匹配到 '存储芯片'
# 输出会重复两行
```

**修复**: 用 `set` 记录已输出的板块名称:
```python
seen = set()
for kw in keywords:
    matches = concept[concept['板块名称'].str.contains(kw, na=False)]
    for _, r in matches.iterrows():
        name = r['板块名称']
        if name not in seen:
            seen.add(name)
            print(...)
```

### 3. tqdm 进度条混入

akshare 使用 tqdm 显示下载进度，在 `python3 -c "..."` 模式下无法完全抑制。最终输出会被 `\r` 刷新覆盖，但管道/日志场景下会污染输出的第一行。

### 4. 涨跌幅已经是百分数

不需要手动除以 100 或乘以 100。`ak.stock_board_industry_name_em()` 的 `涨跌幅` 列已经是 `8.46` 这种格式（表示 8.46%）。

## 输出规范建议

```
行业板块 涨52 跌22  中位数 +1.23%

=== TOP 10 涨幅 ===
  板块名称  涨跌幅  上涨家数  下跌家数
其他生物制品 8.46    37     1
...

=== BOTTOM 10 跌幅 ===
   板块名称   涨跌幅  上涨家数  下跌家数
  玻纤制造 -7.83     0     8
...

=== 概念板块扫描 (17 个关键字) ===
 CPO概念        -3.16%  涨  9家  跌 47家
 存储芯片       +0.92%  涨 61家  跌 66家
 ...
 (未匹配: 铜箔, 树脂, 电子布, OCS)
```

### 关键要素

1. **全市场总览**: 涨跌板块数 + 中位数涨跌幅（一行概览市场情绪）
2. **排行榜**: TOP10 涨幅 + TOP10 跌幅（不重复塞长表）
3. **概念扫描**: 关键字匹配 + 去重 + 未匹配提示
4. **动态对齐**: 概念板块名称用 `板块名称.str.len().max()` 动态计算宽度

## 场景：今日板块复盘

```python
# 注入 _init_patch 后使用（见 SKILL.md 方案B）
import _init_patch
import akshare as ak
import pandas as pd

pd.set_option('display.max_columns', 10)
pd.set_option('display.width', 140)

# 行业板块
df = ak.stock_board_industry_name_em()

# 总览
up = int((df['涨跌幅'] > 0).sum())
down = int((df['涨跌幅'] < 0).sum())
med = df['涨跌幅'].median()
print(f'行业板块 涨{up} 跌{down}  中位数 {med:+.2f}%')

# 排行榜
df_sorted = df.sort_values('涨跌幅', ascending=False)
print(df_sorted[['板块名称', '涨跌幅', '上涨家数', '下跌家数']].head(10).to_string(index=False))
print(df_sorted[['板块名称', '涨跌幅', '上涨家数', '下跌家数']].tail(10).to_string(index=False))

# 概念扫描
concept = ak.stock_board_concept_name_em()
# ... keywords loop with set dedup ...
```
