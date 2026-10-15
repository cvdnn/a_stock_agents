---
name: astock-meta-routing
description: 宿主内A股能力路由，继承当前模型与权限，通过统一CLI执行确定性量化程序。
metadata:
  version: 1.0.0
  author: ''
  category: stocks
compatibility: Requires the complete a_stock_agents bundle and Python 3.9+; shared
  runtime is not bundled per skill.
---

# 宿主内能力路由

> **调用约定**：从本文件真实路径向上定位含 `bundle.json` 的集合根（下称 `$BUNDLE`，即本文件所在目录的上两级），不依赖当前工作目录。Windows 调用 `$BUNDLE/runtime/astock.ps1`，macOS/Linux 调用 `$BUNDLE/runtime/astock`，启动器不可用时回退 `python $BUNDLE/runtime/cli.py`；所有正式调用追加 `--json`。下文 `astock <子命令>` 均指该启动器。`output/`、`log/`、`temp/`、`local/` 指工作区数据根（`core.workspace.WORKSPACE_ROOT`），不是集合根。共用契约见 [execution-contract.md](../../references/execution-contract.md)。

继承宿主当前模型与权限，不自动切换模型，不假定存在execute_code或delegate_task。按自然语言需求读取同集合的专业技能，再通过共享运行时CLI执行，并追加--json。

量化程序负责行情与指标计算、规则判定和证据；模型负责语义理解与解释。短任务直接执行，长任务使用显式任务状态。多次同类调用以批量父任务组织，不承诺宿主一定呈现WebUI任务卡片。
