---
name: astock-data-feed
description: Use when 用户查询A股行情、K线、技术指标、筹码、事件、板块信息，或要求持仓诊断与价格监控。
metadata:
  version: 1.1.0
  author: ''
  tags: '["A股", "数据", "行情", "技术分析", "资金流向", "板块排行"]'
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared
  runtime is not bundled per skill.
---

# A股数据综合分析

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有正式调用追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`），不是集合根。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

## 核心原则

所有行情与指标查询必须通过项目统一 CLI，并追加 `--json`。禁止临时编写网络爬虫，禁止把用户数据写入技能目录。

## 快速调用

```powershell
& "$BUNDLE/runtime/astock.ps1" data quote 600519 --json
& "$BUNDLE/runtime/astock.ps1" data tech 600519 --json
& "$BUNDLE/runtime/astock.ps1" events 600519 --json
& "$BUNDLE/runtime/astock.ps1" cyq 600519 --json
```

Linux/macOS 使用 `"$BUNDLE/runtime/astock"`；仅当启动器不可用时，才调用 `python "$BUNDLE/runtime/cli.py" ... --json`。

## 路由

| 用户意图 | 命令/能力 |
|---|---|
| 实时现价、涨跌幅 | `data quote` |
| MA/MACD/KDJ/RSI/BOLL/ATR | `data tech` |
| 公告与重要事件 | `events` |
| 筹码分布 | `cyq` |
| 多股行情 | `batch` |
| 数据源余额 | `balance` |

数据源降级、代理配置、板块扫描和监控细节按需读取 [完整参考](references/full-reference.md)。

## 持仓与股池规则

持仓数据必须来自 `output/pools/` 或统一 CLI。空池立即终止，不虚构标的；提示登记格式：`000001:1000@12.50`。关注/自选登记直接使用股票代码或名称。

个股实战结论必须同时包含：

1. 含税费且向上进位到分的最低保本卖出价；
2. T0 -3%、T1 -5%、T2 -8% 三级止损；
3. 冲高、窄幅震荡、急跌跳水三场景动作。

## 输出与安全

- 最终报告和股池写入 `output/`；日志写入 `log/`；可重建中间文件写入 `temp/`。
- 任何 API Token 只能从环境变量或用户工作区 `local/settings/.env` 读取。
- 数据不可用时明确返回错误和降级来源，不以缓存冒充实时行情。

## 深入参考

- [API 参考](references/api-reference.md)
- [数据源陷阱](references/data-source-traps.md)
- [技术指标手册](references/technical-indicators-handbook.md)
- [持仓监控流程](references/position-monitoring-workflow.md)
- [完整历史参考](references/full-reference.md)
