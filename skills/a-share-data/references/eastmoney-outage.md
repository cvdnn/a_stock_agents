# 东方财富 API 断连说明

## 背景

自 2025 年中起，东方财富大幅加强反爬策略，其 `push2.eastmoney.com` / `push2his.eastmoney.com` 等核心 API 域名持续拦截爬虫请求。

## 典型报错

```
ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
ProxyError: HTTPSConnectionPool(host='push2.eastmoney.com', port=443): Max retries exceeded...
HTTP 502 Too many 502 error responses
```

## ⚡ 当前状态：已修复

通过 **akshare-proxy-patch** 代理网关，所有东财接口已恢复可用。以下是详细方案。

## 解决方案：akshare-proxy-patch（推荐 ⭐）

发布在 PyPI (2026-06-13)，通过代理网关绕过东财反爬。

### 架构原理（逆向工程于 v0.5.0 源码）

akshare-proxy-patch 的工作原理：

```
Python 代码 → requests.get/post
                       │
                       ▼
           PatchedSession.request()
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
    目标域名?                 非目标域名?
  (push2.eastmoney.com       ┌──────────┐
  等 eastmoney 域名)         │ 原生     │
          │                 │ requests  │
          ▼                 └──────────┘
  1. GET /api/akshare-auth
     ?token=xxx&version=0.5.0
  2. 返回 {ua, cookie, proxy}
  3. 设置 Cookie/代理
  4. curl_cffi Session 发起
     请求（随机 Chrome/Edge
     浏览器指纹伪装）
  5. 失败 → 清除缓存 → 重试
```

关键内部细节：
- **28 秒 TTL 缓存**：`AuthCache` 缓存鉴权响应 28 秒，避免每次请求都鉴权
- **轮询重试**：默认重试 30 次（每次 50ms），依次尝试直到鉴权成功
- **curl_cffi 指纹伪装**：从 Chrome/Edge 浏览器列表中随机选择 impersonate 模式
- **Session 替换**：`requests.Session` 被替换为 `PatchedSession`，同时替换 `requests.get/post`/request，确保所有第三方库的调用都经代理
- **快速模式（fast=True）**：额外替换 akshare 的 `fetch_paginated_data` 及 7 个特定函数（资金流排名、基金信息等）为多线程并发版本

### 积分消耗模型

**核心概念：akshare(proxy-patched) 每次请求消耗代理积分；efinance 直接请求东财 API，不消耗积分。**

akshare-proxy-patch 的每个请求都经过代理网关：
```
请求 → 鉴权（查余额）→ 代理转发 → 东财 API → 返回
         ↓
     消耗 1 次积分
```

efinance 通过不同的请求路径直接访问东财 API，**不受代理限制，零积分消耗**。

### 积分余额查询

所有代理调用的积分余额查询端点：

```
GET http://{gateway}:47001/api/token/{token}
→ {"balance": N}          # N = 剩余积分次数
```
此端点**独立于** `install_patch()` 调用的 `/api/akshare-auth` 鉴权接口。

实测验证（2026-07-15）：
```bash
curl -s "http://101.201.173.125:47001/api/token/202606169K83S6LN"
# → {"balance":10996}
```

建议在启动时或定期检查余额，余额过低时停止代理调用并降级到 efinance / 腾讯直连。

### 积分优化策略：优先用 efinance（零积分）

凡是 efinance 能提供的数据，优先用 efinance（零积分、更快）。只有 efinance 无法提供的功能才走 akshare + proxy-patch。

| 数据需求 | 优先用 | 原因 | 仅当...用 akshare |
|----------|--------|------|-------------------|
| 日K线/OHLCV | efinance `get_quote_history()` | 零积分，~1s | akshare 断连时 |
| 实时行情 | efinance `get_latest_quote()` | 零积分，~0.4s | 需要5档盘口外的字段 |
| 5档盘口 | efinance `get_quote_snapshot()` | 零积分，~0.17s | 不适用 |
| 资金流向 | efinance `get_today_bill()` | 零积分，~0.33s | 需要历史多日资金流 |
| 龙虎榜 | efinance `get_daily_billboard()` | 零积分，~0.11s | 需要详细席位数据 |
| 基本面 | efinance `get_base_info()` | 零积分，~0.26s | 需要完整财务报表数据 |
| 筹码分布 | **akshare** `stock_cyq_em()` | efinance 不支持 | 总是消耗积分 |
| 全市场行情 | **akshare** `stock_zh_a_spot_em()` | efinance 被封 | proxy-patch 可用时 |
| 板块排行 | 技能脚本 `--boards-summary` | DangInvest 独立 API | proxy-patch 断连时 |
| 技术指标 | MyTT 本地计算 | 零积分 | 不适用 |
| A股新闻 | 暂缺（efinance 无新闻 API） | 保留 akshare | 消耗积分 |

### 安装

```bash
pip install akshare-proxy-patch==0.5.0
pip install pyyaml>=6.0       # 用于读取配置文件
```

### 配置

编辑 `scripts/config.yaml`：

```yaml
proxy_patch:
  enabled: true
  gateway: "101.201.173.125"
  auth_token: "你的TOKEN"       # ← 去 https://ak.cheapproxy.net/dashboard/akshare 获取
  retry: 30
  fast: true
  hook_domains:
    - "push2.eastmoney.com"
    - "push2his.eastmoney.com"
```

### 用法

方式一：通过技能包装脚本（推荐）

```bash
VENV_PY="/path/to/.venv/bin/python3"
$VENV_PY scripts/fetch_patched.py fetch_realtime.py --quote 600760 --json
$VENV_PY scripts/fetch_patched.py fetch_sector_info.py --no-concepts --json 600760
```

方式二：直接 Python

```python
import yaml
import akshare_proxy_patch

cfg = yaml.safe_load(open("scripts/config.yaml"))["proxy_patch"]
akshare_proxy_patch.install_patch(cfg["gateway"], auth_token=cfg["auth_token"], fast=True)

import akshare as ak
df = ak.stock_cyq_em(symbol="600760")    # 筹码分布
df = ak.stock_zh_a_spot_em()             # 全市场行情
df = ak.stock_individual_fund_flow(stock="600760", market="sh")  # 资金流向
```

### 重要注意事项

- **Python 版本**：需要 Python >= 3.10。系统 Python 3.9 有 numpy C 扩展版本冲突（`_multiarray_umath.cpython-311.so`），必须使用虚拟环境
- **导入顺序**：`import akshare_proxy_patch` 和 `.install_patch()` 必须在 `import akshare` **之前**
- **TOKEN**：免费获取，有每日用量限制。可在 `scripts/config.yaml` 中修改
- **依赖**：需要 `curl_cffi` 包及其 C 扩展，自动安装

## 影响范围（无 proxy-patch 时）

| 接口 | 状态 | 替代方案 |
|------|------|----------|
| `stock_zh_a_hist_em` (日K线 - 东财) | 被封锁 | `fetch_history.py` → 新浪/腾讯 |
| `stock_zh_a_spot_em` (全市场行情) | 被封锁 | `stock_zh_a_spot()` → 新浪（慢但稳定） |
| `stock_cyq_em` (筹码分布) | 被封锁 | proxy-patch 或 efinance |
| `stock_zh_index_daily_em` (指数) | 被封锁 | `fetch_realtime.py --index` → 新浪 |
| `stock_individual_fund_flow` (资金流向) | 被封锁 | proxy-patch 恢复 |
| `stock_lhb_detail_em` (龙虎榜) | 间歇 | proxy-patch 恢复 |
| 技能脚本 `--quote`, `--kline` | ✓ 稳定 | 新浪/腾讯多源降级 |
| 技能脚本 `--boards-summary` | ✓ 稳定 | DangInvest 独立 API |

> ⚠️ 使用 proxy-patch 后，标记"被封锁"的接口全部恢复可用。

## 历史讨论

- GitHub Issue #6787 (2025-11-18): https://github.com/akfamily/akshare/issues/6787
- 博客园 (2025-11-30): AKShare 高频请求东财数据接口的异常问题及解决方案
- CSDN (2025-06-29): AKShare 项目中的东方财富网数据接口连接问题分析
- 腾讯云 (2026-05-19): efinance/akshare 被限流、封 IP 的替代方案

## 后备方案

如果 proxy-patch 不可用（如 TOKEN 过期或无网络），按以下优先顺序降级：

1. **新浪/腾讯链路**：技能脚本默认链路，稳定但慢（~4-5s/请求）
2. **efinance**：更快的数据获取（0.1-0.5s/请求），参考 `references/efinance-usage.md`
3. **DangInvest**：板块排行和市场新闻，独立 API

## 实时性实测对比（2026-06-16，中航沈飞 600760）

| 数据 | 技能脚本（新浪/腾讯） | proxy-patch（东财） | efinance |
|------|:----:|:----:|:----:|
| 实时行情 | 4.58s | 0.38s ⚡ | 0.43s |
| 5档盘口 | 不支持 | 不支持 | 0.17s ⚡ |
| 日K线 | 3.03s | 0.38s ⚡ | 0.98s |
| 筹码分布 | ❌ | 1.66s ⚡ | ❌ |
| 资金流向 | ❌ | 0.36s ⚡ | 0.33s ⚡ |
| 全市场行情 | 77s | 11.42s ⚡ | ❌ 被封 |
| 板块排行 | DangInvest | — | — |

## 已知问题

- WSL 环境下系统 Python 3.9 与 newer numpy/pandas 存在 `.so` 版本冲突需使用虚拟环境
- efinance 的 `get_realtime_quotes()`（全市场）同样被东财封锁，不建议使用
- proxy-patch TOKEN 有每日用量限制，大量请求时注意控制频率