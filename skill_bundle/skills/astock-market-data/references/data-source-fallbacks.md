# 数据源 4 级容灾降级与反爬机制 (Data Source Fallbacks)

本文档说明 `astock-market-data` 底层数据适配层的 4 级容灾降级协议、反爬防封策略与 Fail-Closed 判定。

---

## 1. 4 级容灾链路架构

外部金融行情网络环境复杂（可能存在被封禁 IP、接口格式变更、超时等异常）。系统通过 `core/data/` 中的统一 `DataBridge` 实施透明自动降级：

```text
[发起行情请求]
       │
       ▼
 [L1 腾讯财经接口] ──(超时/403/格式异常)──► [L2 东方财富接口]
                                                  │
                                          (解析失败/网络中断)
                                                  │
                                                  ▼
                                          [L3 新浪财经接口]
                                                  │
                                          (全部外网不可达)
                                                  │
                                                  ▼
                                          [L4 本地水位快照]
                                                  │
                                          (无对应标的数据)
                                                  │
                                                  ▼
                                         [Fail-Closed 终止]
                                      返回 DATA_UNAVAILABLE
```

1. **L1 腾讯行情 (Primary)**：
   - 响应耗时：通常 $< 100\text{ms}$；
   - 优势：支持高并发、字段丰富、五档买卖明细与分时量价全面；
2. **L2 东方财富 (Secondary)**：
   - 包含板块涨跌统计、北向资金流向与筹码计算基础数据；
3. **L3 新浪行情 (Tertiary)**：
   - 经典轻量级行情接口，作为前两者的兜底备份；
4. **L4 本地数据水位快照 (Offline Cache)**：
   - 本地 `output/cache/` 或 `local/` 历史交易日收盘切片；
   - 降级至 L4 时，必须在 `evidence_meta` 中标注 `"quote_source": "L4:local_snapshot"` 并提供明确的时间戳，防范盘中误把昨日收盘当现价。

---

## 2. 反爬防封与调用纪律

- **统一 User-Agent 与 Headers**：模拟现代桌面端标准浏览器头，严禁使用 Python 默认的 `urllib` 或 `python-requests` 裸特征；
- **请求节流与指数退避**：单 IP 访问频率建议不超过 5 次/秒；连续失败触发 1s, 2s, 4s 指数退避；
- **绝不硬编码爬虫**：所有技能必须调用 `astock data quote` 或底层 `core.data` 封装，严禁在业务层临时手写网络爬虫。
