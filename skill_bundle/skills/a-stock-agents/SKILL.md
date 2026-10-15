---
name: a-stock-agents
description: A股技能总入口。用于行情、选股、持仓风控、模拟盘、报告及多空辩论；按需求路由到同集合的19项专业技能，以确定性程序计算。
compatibility: Requires complete a_stock_agents bundle, Python 3.9+ and dependencies.
  Supports Windows, macOS and Linux.
metadata:
  product: a_stock_agents
  version: 3.0.0
---

# A-Stock Agents 总入口

本技能只负责导航与自身编排，不保存公共引擎。读取集合的references/execution-contract.md和assets/config/skills_manifest.json，按需读取skills/<id>/SKILL.md。

从本文件真实路径定位带bundle.json的集合根。程序经runtime/bootstrap.py与core.workspace定位，Windows调用runtime/astock.ps1，macOS/Linux调用runtime/astock；所有正式调用追加--json。

空股池停止分析并提示登记；数据不足或能力未实现必须如实返回原因。持仓建议包含精确保本价、三级风控及三场景动作。单项技能不能脱离完整集合独立安装；宿主安装使用完整Release；开发仓库不作为项目发现模式。
