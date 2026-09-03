# 持仓分析 + 自动监控工作流

本文件记录完整「用户告知持仓→生成诊断报告→部署自动监控」的实战模式。

## 五步工作流

### 第1步：并行拉取全维数据

一次性并行拉取以下数据：

| 数据维度 | 脚本 | 关键参数 |
|----------|------|----------|
| 实时行情 | `fetch_realtime.py` | `--quote <CODE> --json` |
| 全年K线 | `fetch_history.py` | `--kline <CODE> --start YYYY-01-01 --freq d --json` |
| 技术指标 | `fetch_technical.py` | `--freq 1d --count 120 --indicators MA,MACD,KDJ,RSI,BOLL --json` |
| 个股事件 | `fetch_stock_events.py` | `--code <CODE> --name <NAME> --dates ... --limit 20 --json` |
| 行业信息 | `fetch_sector_info.py` | `--no-concepts --json <CODE>` |
| 板块对比 | `fetch_realtime.py` | `--boards-summary --boards-limit 20 --json` |
| 大盘指数 | `fetch_realtime.py` | `--index --json` |
| 成交明细 | `fetch_realtime.py` | `--tick <CODE> --json` |

### 第2步：持仓画像计算

```python
总成本 = 成本价 × 持仓量
当前市值 = 现价 × 持仓量
浮亏额 = 当前市值 - 总成本
浮亏率 = (现价 - 成本价) / 成本价 × 100
解套需涨 = (成本价 / 现价 - 1) × 100
```

### 第3步：技术面关键信号解读

| 信号 | 含义 |
|------|------|
| KDJ J值 < 0 | **极端超卖**，短期大概率反弹。不要在此时恐慌割肉 |
| MACD零轴下方死叉+绿柱扩大 | 下跌动能未衰竭，不宜补仓 |
| 股价跌破布林下轨 | 极端弱势，但通常有回归中轨的技术需求 |
| RSI < 35 | 接近超卖区域 |
| 均线空头排列（5<10<20<60） | 下降趋势确立，适合分批反弹减仓 |
| 利好频繁但股价加速下跌 | 市场情绪偏空，不应幻想反转 |

### 第4步：三档阶梯减仓方案

在技术支撑位设3个触发价，分批减仓：

| 触发档 | 确定方式 | 减仓比例 |
|--------|----------|----------|
| 触发价1 | 布林下轨 / 前低平台 / 整数关口 | 1/4 ~ 1/3 |
| 触发价2 | MA5附近 / 前次反弹高点 | 1/3 ~ 1/2 |
| 触发价3 | 接近成本价 / MA20附近 | 剩余仓位 |
| 止损价 | 跌破关键支撑无法收回 | 减半仓或清仓 |

**原则**：分批减仓 > 死扛等回本 > 补仓。下降趋势中补仓放大风险。

### 第5步：部署自动监控

详见 SKILL.md 的「自动化价格监控」章节和 `templates/monitor_watchdog.py` 模板。

## 实战案例：科大讯飞 002230

- 用户持仓：4000股，成本价 48.3073
- 当前价：41.09，浮亏 -14.9%，约 2.89万
- 触发价：42.5（减1/4）→ 44.0（减1/3）→ 46.0（减剩余）
- 脚本：`~/.AI-Platform/scripts/stock_monitor_002230.py`
- 状态文件：`~/.AI-Platform/scripts/stock_monitor_002230_state.json`
- 通知：Windows Toast + WeChat（deliver: all）
- 调度：每5分钟，no_agent=True

注意：部署前需确保 Gateway 已安装运行（`AI-Platform cron status`）。
