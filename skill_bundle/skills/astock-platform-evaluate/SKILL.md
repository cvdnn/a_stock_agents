---
name: astock-platform-evaluate
description: Use when 用户要求全流程个股诊断、综合评分、解套方案、大盘健康度或量化分析报告。
metadata:
  version: 1.1.0
  author: ''
  tags: '["A股", "综合评估", "量化评分", "解套", "风控"]'
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared
  runtime is not bundled per skill.
---

# A股全流程分析平台

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有正式调用追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`），不是集合根。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

## 定位

本技能是综合分析入口，底层单一真理来源位于 `$BUNDLE/runtime/core/`。所有正式调用均通过统一 CLI，避免直接复制或修改技能包装器。

## 快速调用

```powershell
& "$BUNDLE/runtime/astock.ps1" evaluate 600519 --json
& "$BUNDLE/runtime/astock.ps1" analyze 600519 --json
& "$BUNDLE/runtime/astock.ps1" trapped 600519 --cost 1300 --shares 100 --json
& "$BUNDLE/runtime/astock.ps1" market --json
& "$BUNDLE/runtime/astock.ps1" report 600519 --json
```

Linux/macOS 将启动器替换为 `"$BUNDLE/runtime/astock"`。

## 分析链路

1. 数据桥接按既定数据源顺序降级，保留来源与时效信息。
2. 本地计算 MA、MACD、KDJ、RSI、BOLL、ATR 等指标。
3. 运行组合评分、入场判断和风险检查。
4. 持仓场景追加保本价、三级止损与三场景动作单。
5. 需要交付物时生成自包含 HTML 至 `output/reports/`。

## 能力路由

| 需求 | 命令 |
|---|---|
| 综合诊断 | `evaluate <code>` |
| 全维度分析 | `analyze <code>` |
| 被套持仓 | `trapped <code> --cost ... --shares ...` |
| 大盘健康度 | `market` |
| 选股 | `screen --dynamic hot_sectors` |
| 风控 | `risk <code>` |
| HTML 报告 | `report <code>` |

## 强制输出规则

涉及具体持仓建议时必须给出精确最低保本卖出价、T0/T1/T2 三级止损和开盘冲高/窄幅震荡/急跌跳水三场景动作。数据不足时停止推演，不补造行情或持仓。

## 文件与安全

- 用户交付物：`output/`
- 运行日志：`log/`
- 可重建中间文件：`temp/`
- 核心实现：`$BUNDLE/runtime/core/`
- 技能目录只保留说明、转发包装器、模板和 `.example` 文件

## 深入参考

- [完整能力与算法参考](references/full-reference.md)
- [动作执行手册](references/action-execution-manual.md)
- [迁移说明](references/migration-from-tacn.md)
