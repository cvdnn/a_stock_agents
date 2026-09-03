# Cron 监控系统健康诊断方法

## 场景

当用户询问"评估运行过程的状态"、"检查监控是否正常"、或发现推送异常时，按此流程逐层排查。

## 诊断流程（由浅入深）

### Layer 1: 任务级健康检查

```
1. cronjob(action='list') — 列出所有任务
   检查每项：
   ├── last_status: 'ok' / 'error'
   ├── last_run_at: 是否近期运行
   ├── last_delivery_error: 推送是否成功
   ├── enabled: true/false (意外禁用的任务)
   └── state: 'scheduled' / 'paused'
```

**关键信号**：
- `last_status='error'` + `last_delivery_error` 非空 = **推送层失败**（脚本本身可能正常）
- `last_status='error'` + 无 delivery_error = **脚本执行失败**（需看脚本代码）
- 长时间无 `last_run_at` 更新 = **gateway 未运行**（WSL 下需 tmux 持久化）

### Layer 2: 状态文件检查

no_agent 监控脚本通常使用状态文件（`~/.AI-Platform/scripts/*_state.json`）持久化已触发事件，避免重复推送。

```
~/.AI-Platform/scripts/
├── position_stop_monitor_state.json   # 持仓风控已触发预警
├── entry_monitor_state.json           # 入场监控已触发信号（不存在=未触发）
├── entry_monitor_605358_state.json    # 立昂微入场监控状态
└── stock_monitor_002230_state.json    # 科大讯飞股价监控（不存在=未触发）
```

**检查方法**：读取状态文件，对比今日日期，看哪些预警已触发：

```json
{
  "triggered": {
    "002230_43.2_2026-06-23": true,
    "600760_42.0_2026-06-23": true
  }
}
```

**典型状态文件内容**：

| 脚本 | 状态文件 | 字段说明 |
|------|----------|----------|
| `entry_monitor.py` | `entry_monitor_state.json` | `{"triggered_X": true}` — 已触发的入场信号 |
| `entry_monitor_605358.py` | `entry_monitor_605358_state.json` | `{"date", "triggered_today", "last_alert_level"}` — 每日重置 |
| `position_stop_monitor.py` | `position_stop_monitor_state.json` | `{"triggered": {"code_price_date": true}}` — 价格预警 |
| `stock_monitor_002230.py` | `stock_monitor_002230_state.json` | `{"fired": []}` — 已触发的卖出信号 |

**重置方法**：
```bash
rm ~/.AI-Platform/scripts/*_state.json
```

### Layer 3: 脚本代码审计

当任务状态异常时，深入检查脚本自身。常见问题模式：

#### 模式 A: Python dict vs object API 误用

```python
# ❌ BUG: state 是 dict，getattr 对 dict 无效
last_id = getattr(state, "last_sync", None)

# ✅ FIX: 用 dict.get()
last_id = state.get("last_sync")
```

#### 模式 B: 变量作用域泄漏

```python
# ❌ BUG: env 在第一个 try 块内定义，在 except 分支中不可用
rc, stdout, stderr = run_gbrain(["put", slug])
if rc != 0:
    result = subprocess.run([...], env=env)  # env undefined!
```

**保险写法**：始终在函数顶部初始化所有共享变量。

#### 模式 C: 交易时间守卫被忽略

```python
if not is_market_hours():
    return  # 静默退出
```

非交易时间脚本静默退出是预期行为。

#### 模式 D: 依赖数据文件不存在

```python
if not os.path.exists(WATCH_PATH):
    return
```

池文件为空或不存在时脚本不报错也不输出。

### Layer 4: 推送层诊断

当 `last_status='error'` 且 `last_delivery_error` 非空时：

| 错误模式 | 原因 | 处理方案 |
|----------|------|----------|
| `rate limited` | 推送频率过高 | 增大 cron 间隔或合并通知 |
| `iLink sendmessage rate limited` | 微信推送限流 | 降低触发频率 |
| `delivery error` (通用) | 推送通道异常 | 检查 gateway 运行状态 |
| `timeout` | 推送超时 | 减小推送内容体积 |

**微信限流应对**：
- 单只股票的多层预警（黄/橙/红）可能在短时间内多次触发
- 建议对同类预警合并推送
- 或在 `deliver` 参数中暂时降低频率

## 常用命令速查

```bash
# 列出所有 cron 任务
AI-Platform cron list

# 列出所有监控脚本
ls ~/.AI-Platform/scripts/

# 查看所有状态文件
ls ~/.AI-Platform/scripts/*_state.json

# 重置某个监控的状态
rm ~/.AI-Platform/scripts/position_stop_monitor_state.json

# 检查 gateway 是否运行
AI-Platform gateway status

# 查看推送日志
cat ~/.AI-Platform/logs/gateway.log 2>/dev/null | grep -i 'delivery\|send\|error' | tail -20
```
