# 金融新闻搜索（备用通道）

当标准数据源（akshare）超时或阻塞时，使用以下备用通道搜索金融新闻。

## 通道A：东方财富搜索API（最可靠）

```python
import urllib.request, urllib.parse, json

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

query = {
    "uid": "",
    "keyword": "搜索关键词",  # 如 "韩国熔断", "半导体政策"
    "type": ["cmsArticleWebOld"],
    "client": "web",
    "pageNum": 1,
    "pageSize": 10
}
url = f"https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={urllib.parse.quote(json.dumps(query))}"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    text = resp.read().decode('utf-8', errors='ignore')
```

**解析**：搜索 `"cmsArticleWebOld"` 字段，提取 `title` 和 `content`，用正则 `<[^>]+>` 去标签。

## 通道B：DangInvest 板块排行（稳定）

```
GET https://dang-invest.com/api/market/boards/summary?limit=15
```

返回 JSON 格式板块排行，含 `changePct`（涨跌幅）、`totalTurnoverYuan`（成交额）、`groupLabel`（板块名）。是 akshare `stock_board_industry_name_em` 的可靠替代。

## 通道C：腾讯实时行情（最稳定）

```python
prefix = 'sh' if code.startswith('6') else 'sz'
url = f"https://qt.gtimg.cn/q={prefix}{code}"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as resp:
    text = resp.read().decode('gbk')
    items = text.split('~')
    # items[3]=现价, [4]=昨收, [5]=开盘, [32]=涨跌幅, 
    # [33]=最高, [34]=最低, [37]=成交额, [38]=换手率, [39]=市盈率
```

## 通道D：东方财富页面抓取头条新闻

```
curl https://finance.eastmoney.com/a/czqyw.html
```

提取 `<a href="..." title="...">` 标签获取新闻标题列表。

## 注意事项

- 雅虎财经（Yahoo Finance）已被屏蔽，无法使用
- Google News 可能超时
- 优先使用东方财富 API（通道A），返回结构化JSON