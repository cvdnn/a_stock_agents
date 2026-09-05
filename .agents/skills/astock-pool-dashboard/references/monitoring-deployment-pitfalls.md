# 监控脚本部署陷阱记录

## 1. 路径解析失效（2026-06-29 发现）

### 现象

`sandbox.py` 复制到 `~/.AI-Platform/scripts/` 后，`--json` 输出：

```json
{"timestamp": "...", "positions": [], "selected": []}
```

而非预期的持仓/自选股数据。默认模式输出AI模板（旧版本回退）而非持仓摘要。

### 根因

```python
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

- 在技能目录运行时：`SKILL_DIR = skills/a-share-dashboard/` → 正确
- 在 `~/.AI-Platform/scripts/` 运行时：`SKILL_DIR = ~/.AI-Platform/` → 找不到 `data/positions.csv`

### 影响范围

所有通过 `cp` 部署到 `~/.AI-Platform/scripts/` 的脚本，如果使用 `SKILL_DIR` 自动解析来定位数据文件，都会受影响：

| 脚本 | 数据文件 | 影响 |
|------|----------|------|
| sandbox.py | positions.csv, selected_pool.csv | **已确认** — 空数据运行数天 |
| position_stop_monitor.py | positions.csv | **可能受影响** — 读不到持仓则无止损检测 |
| entry_monitor.py | watch_pool.csv | **不受影响** — WATCH_PATH 硬编码在脚本内 |

### 修复

在 `sandbox.py` 和 `position_stop_monitor.py` 顶部加：

```python
# 部署到 ~/.AI-Platform/scripts/ 后 SKILL_DIR 会解析错误，此处硬编码
SKILL_DIR = "./.AI-Platform/skills/stocks/a-share-dashboard"
```

或者创建符号链接：

```bash
ln -s ./.AI-Platform/skills/stocks/a-share-dashboard/data ./.AI-Platform/scripts/data
```

### 验证方法

```bash
cd ./.AI-Platform/scripts/
python3 sandbox.py --positions-json   # 应该输出持仓列表而非空数组
```

## 2. WeChat 推送限流丢失止损信号（2026-06-29 确认）

### 现象

cron 日志：
```
delivery error: Weixin send failed: iLink sendmessage rate limited: ret=-2
```

而同时 `position_stop_monitor_state.json` 已记录触发：
```json
{"002230_stopped_2026-06-29": true, "600760_40.5_2026-06-29": true}
```

止损信号被记录下来但**从未送达用户**。

### 影响

no-agent cron 脚本的输出是`仅通过推送信道投递`的——如果微信限流失败且没有其他信道，用户相当于**没有监控**。

### 防御

- 配置至少2个推送信道（`send_message --action list` 查看可用信道）
- 在 `--deliver all` 中确认至少有一条信道能送达
- 考虑加一个健康检查脚本，定期比对 state.json 中的 trigger 记录和推送日志

### 修复：Gateway 重启

2026-06-30 实测：当 WeChat iLink 持续限流（`rate limited; cooldown active for 30.0s`），且多次重试后仍不恢复，**重启 gateway 即可恢复**。

```bash
# 注意：restart_drain_timeout=180s，重启可能耗时1~2分钟
# 期间 gateway 会进入 deactivating (stop-sigterm) 状态，不是卡死
AI-Platform gateway restart

# 或手动 kill + 等重启：
kill <PID> && sleep 90 && AI-Platform gateway status
```

**重启后检查限流是否解除**：
```bash
AI-Platform send --to weixin "...测试消息..."
# 预期输出: Sent to weixin home channel (chat_id: ...)
```

**根本原因推测**：Gateway 长时间持续运行（1天+）后，iLink 长连接状态可能变陈旧或触发服务端流控。重启建立新连接后恢复正常。建议每周定时重启 gateway 作为预防：

```bash
AI-Platform cron create \
  --name "gateway-每周重启" \
  --schedule "0 6 * * 0" \
  --no-agent \
  --script ./.AI-Platform/scripts/gateway_weekly_restart.sh
```

其中脚本内容：
```bash
#!/bin/bash
systemctl --user restart AI-Platform-gateway
```

### 触发信号特征

当出现以下所有条件时即 iLink 限流而非网络故障：
```
1. `AI-Platform send --to weixin` 返回 `rate limited; cooldown active for 30.0s`
2. 等待30s后重试仍得到相同的 `cooldown active for 30.0s`（说明每次重试重置了冷却计时器）
3. Gateway 本身正常运行（`Active: active (running)`）
4. 其他推送信道（如果有）正常

## 3. 空输出 ≠ 完全静默

`print()` 即使输出空字符串，AI-Platform 的 cron 系统也会认为有内容并尝试推送。一个空行推送在微信上表现为一条空白消息。

### 规则

- 无事件时完全无输出（`sys.exit(0)`，不调用任何 `print()`）
- 有事件时只输出事件内容
- 不要用 `print()` 后跟条件检查来"跳过"——用 `if not events: sys.exit(0)`

## 4. Proxy-patch Eastmoney 链路频繁超时（2026-06-29 实测）

### 现象

`fetch_patched.py`（走 proxy-patch Eastmoney 链路）批量调用时超时率极高。单次调用偶尔成功（~13s），但批量10只几乎全部超时。`fetch_technical.py`、`fetch_realtime.py --board-summary` 等依赖 proxy-patch 的调用同样不稳定。

### 影响范围

| 脚本/组件 | 数据源 | 可靠性 | 影响 |
|-----------|--------|:------:|------|
| `entry_monitor.py` | proxy-patch (fetch_patched.py) | ❌ 高概率超时 | 监控可能静默失效 |
| `sandbox.py` | proxy-patch (fetch_patched.py) | ❌ 高概率超时 | 行情数据为空 |
| `realtime_quotes.py` (策略技能) | 腾讯直连 | ✅ 稳定 | 不受影响 |
| `position_stop_monitor.py` | 腾讯直连 (qt.gtimg.cn) | ✅ 稳定 | 不受影响 |
| `fetch_history.py` | Sina/腾讯日线 | ⚠️ 较慢但稳定(~13s/只) | 可用但批量慢 |

### 数据可靠性分层

```
高可靠（2秒返回）：腾讯行情API qt.gtimg.cn → 实时价/涨跌幅/换手率
中可靠（13秒返回）：fetch_history.py Sina/腾讯链路 → 日K线/MA数据
低可靠（频繁超时）：fetch_patched.py proxy-patch Eastmoney → 技术指标/资金流/筹码
```

### 替代方案：硬编码MA20监控脚本

对于cron监控场景，MA20日线值一天只变化一次，不需要每次检测都重新获取。采用**日线策略跑分时预计算MA20，写入脚本硬编码**的机制：

```
周期: 每日收盘后
  └─ 运行 daily_decisions.py 或手动跑分 → 获取最新MA20值
  └─ 更新脚本顶部 STOCK_CONFIG 的 MA20 参数
  └─ cron每5分检测仅用腾讯API拉实时价，对比硬编码MA20
```

优势：避免proxy-patch超时导致监控失效；腾讯API 2秒返回；MA20误差日线收盘到下次日线收盘前<0.5%。

参见 `templates/entry_monitor_hardcoded_ma20.py` 模板。

## 5. boards-summary sort 参数失效

`--boards-summary --sort change_pct_desc --json` 依然返回 `market_cap_desc` 顺序。

DangInvest API 忽略 `sort` 参数。如需按涨跌幅排序，客户端对返回的 `data` 数组自行排序：

```python
data = sorted(data, key=lambda x: x['changePct'], reverse=True)
```
