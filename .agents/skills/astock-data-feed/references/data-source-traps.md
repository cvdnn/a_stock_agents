# 数据源可靠性陷阱（实测记录）

## 1. `--all-quote` 非全市场

通过新浪/腾讯链路调用 `--all-quote` 时，**仅返回约20只股票**，并非全市场5865只。需要全市场统计必须通过 proxy-patch 用 `stock_zh_a_spot_em()`。

## 2. DangInvest API 超时

`--boards-summary` 实测超时率约50%，尤其开盘前30分钟。重试或改用东财+proxy的 `ak.stock_board_industry_name_em()`。

## 3. efinance 指数不稳定

`ef.stock.get_latest_quote(['sh000001'])` 可能报错，改用 `ak.stock_zh_index_daily_em()`。

## 4. 筹码分布盘中不更新

`stock_cyq_em()` 每日仅更新一次（收盘后），盘中数据为前一日收盘快照。

## 0. 技能脚本静默失败

`fetch_realtime.py --boards-summary` 和 `fetch_realtime.py --index` 等脚本可能返回 `BOARDS_FAILED` / `INDEX_FAILED` 而没有任何错误信息到 stderr。这种情况发生在脚本内部依赖的链路超时但异常未被正确传播时。

**应对**：降级到腾讯API直连（方案D），参考 `references/tencent-api-direct.md`。

## 5. 批量逐只调 proxy-patch 行业查询会 aggregate timeout

对 `stock_board_industry_cons_em(symbol=code)` 或 `stock_individual_info_em(symbol=code)` 做**顺序循环**调用时，大约第10-15只后开始卡死超时。实测：30只顺序调用了约26只后在第300秒被超时kill。

**原因**：proxy-patch 网关对短时间高频连接的东财链路有限制，但限制方式不是 HTTP 429，而是 tcp 连接挂起（不返回数据）。

**症状**：
- 前5-8只很快（每只~2s）
- 第10只后逐步变慢
- 第15只后开始卡死不返回

**应对**：
- 不要逐只调 `fetch_sector_info.py --no-concepts CODE` 查行业——超过5只就会累积超时
- 不要逐只调 `stock_board_industry_cons_em()`——同上
- **改用腾讯API直连**批量获取行情，然后用 agent 自身知识判断行业归属
- 如果一定要查行业，单次调用 `stock_board_industry_name_em()` 获取全行业板块列表（不按股票查），然后搜索板块内是否包含该股票
- 另一种可行方案：用 `stock_individual_info_em()` 但每只之间加 time.sleep(2)，并设置每只 10s 超时

## 6. `stock_individual_info_em()` 可能列名不匹配

`ak.stock_individual_info_em(symbol=code)` 在部分 akshare 版本中因 pandas 列数校验失败而抛 `ValueError: Length mismatch: Expected axis has 3 elements, new values have 2 elements`。这是 akshare 版本兼容性问题。

**应对**：不使用此函数获取行业信息。改用 `stock_board_industry_cons_em()`（需 proxy-patch）或直接依赖 agent 行业知识。

## 7. system Python 3.9 + pandas 3.x 不兼容\n\npandas 3.0+ 要求 Python 3.10，但系统 Python 3.9 的 pip 可能误装 3.0.3。报错：\n```\nImportError: cannot import name 'TypeAlias' from 'typing' (/usr/lib64/python3.9/typing.py)\n```\n\n**修复**：\n```bash\npip3 install 'pandas<3.0,>=2.2' --upgrade\n```\n修复后系统 Python 3.9 + pandas 2.3.3 导入仅需 0.6s（vs venv 3.11 + pandas 3.0.3 的 13.8s）。\n\n## 8. cffi `_cffi_backend` C扩展缺失\n\n`akshare` → `curl_cffi` → `_cffi_backend` 依赖链。如果 `_cffi_backend` 缺失，`fetch_realtime.py` 和 `fetch_technical.py` 都会静默失败（exit 1）。\n\n```bash\npip3 install --force-reinstall --no-cache-dir cffi\n```\n\n## 9. venv pandas 冷启动极慢（13.8s vs 0.6s）\n\nvenv Python 3.11 的 pandas 3.0.3 首次导入需 13-20 秒（C 扩展初始化）。同一进程后续调用快，但 AI-Platform terminal() 每次是新进程。\n\n**对策**：\n- 简单的实时查询 → 腾讯API直连（0.1s, 零依赖）\n- 轻量数据脚本 → 系统 Python 3.9（pandas 2.3.3, 0.6s）\n- 重量级分析（proxy-patch/筹码/全市场）→ venv 3.11（13.8s但功能全）/ timeout 设 30s\n\n## 决策速查（更新版）\n\n| 需求 | 最佳调用 | 耗时 | 备注 |\n|------|----------|:----:|------|\n| 实时行情（批量1-20只） | **腾讯API直连** `qt.gtimg.cn` | **~0.1s ⚡** | 零依赖，最稳定 |\n| 快速实时 | efinance `get_latest_quote` | ~0.4s | 5档盘口 |\n| 全市场统计 | `stock_zh_a_spot_em()` via proxy | ~11s | 需 venv |\n| 板块排行 | `stock_board_industry_name_em()` via proxy | ~2s | 需 venv |\n| 筹码分布 | `stock_cyq_em()` via proxy | ~2s | 需 venv |\n| 资金流向 | `--fund-flow CODE` via proxy | ~0.4s | 需 venv |\n| 技术指标 | `fetch_technical.py CODE` | ~1.5s | 系统python 3.9 即可 |\n| 日K线 | `stock_zh_a_hist()` via proxy | ~0.4s | 需 venv |\n\n> 腾讯API直连是终局备选。详见 `references/tencent-api-direct.md`。