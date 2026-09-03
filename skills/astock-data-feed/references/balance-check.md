# Proxy 积分余额管理

## 余额查询端点

```
GET http://101.201.173.125:47001/api/token/{AUTH_TOKEN}
→ {"balance": 10994}
```

## CLI 命令

```bash
# 查询余额（终端输出）
python3 fetch_realtime.py --balance

# JSON 格式
python3 fetch_realtime.py --balance --json
→ {"balance": 10994}

# 通过 fetch_patched.py 调用（自动带余额预检）
python3 fetch_patched.py fetch_realtime.py --balance --json
```

## 余额预检机制

`fetch_patched.py` 在安装 proxy-patch 前自动检查余额：

| 余额范围 | 行为 |
|:--------:|------|
| ≥ 500 | 静默通过 |
| 100–499 | 输出 `⚡ Proxy 积分余额 N，建议节省使用`（stderr） |
| < 100 | 输出 `⚠️ Proxy 积分余额仅剩 N，低于阈值 100，可能很快耗尽`（stderr） |

余额查询失败（网络超时等）**不阻断**主流程，静默跳过。

## 积分消耗速查

| 操作 | 消耗积分 | 替代方案 |
|------|:--------:|----------|
| `--fund-flow` | ✅ **零**（已切 efinance） | — |
| `--limit-up-pool` | ✅ **零**（已切 efinance） | — |
| 筹码分布 CYQ | 消耗 ~1 | 无 efinance 替代 |
| 全市场行情 | 消耗 ~17 次 | 无 efinance 替代 |
| 行业信息 | 消耗 ~1 | 无 efinance 替代 |
| 个股事件 | 消耗 ~9 次 | 无 efinance 替代 |
| 龙虎榜 `--lhb` | 消耗 ~1 | 改用 `ef.stock.get_daily_billboard()` 零积分 |
| 其他（新浪/腾讯/MyTT）| **零** | — |

## 节省积分建议

1. 资金流向 → 直接用 `ef.stock.get_history_bill(code)` 或 `--fund-flow`（已自动使用 efinance）
2. 龙虎榜/涨停股池 → 直接用 `ef.stock.get_daily_billboard(date)` 或 `--limit-up-pool`（已自动使用 efinance）
3. 单只实时行情 → 直接用 `ef.stock.get_latest_quote(code)` 或腾讯直连 `qt.gtimg.cn`
4. 只在需要筹码分布、全市场行情、行业信息时才走 proxy-patch
