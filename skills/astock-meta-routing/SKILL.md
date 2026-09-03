---
name: astock-meta-routing
version: "1.0.0"
author: ""
description: 股票任务模型路由规则 — 分析用flash，编程也用flash但用execute_code直接执行
category: stocks
---

# 股票任务模型路由规则（v2 — 优化版）

## 核心规则

| 任务类型 | 模型 | 执行方式 |
|---------|------|---------|
| 股票分析/行情/评估 | `deepseek-v4-flash` | 主会话 或 `delegate_task`（子代理继承flash） |
| 策略程序/交易脚本 | `deepseek-v4-flash` | **`execute_code` / 直接工具调用**（主会话执行） |

## 为什么这样设计

### 配置状态
```
delegation.model: ''     # 子代理继承父会话模型（当前为 flash）
                         # 不再全局硬编码为 pro
```

### 关键决策依据
1. **`delegate_task` 不能按调用动态选择模型** — 模型是全局配置或继承父会话
2. **`execute_code` 可以替代大部分编程需求** — 链式调用50个工具，写策略脚本足够
3. **flash 写股票策略代码质量足够** — k线计算、均线、MACD、选股逻辑都是确定性的

### 执行方式对比

| 方式 | 适用场景 | 模型 |
|------|---------|------|
| 主会话直接执行 | 分析、简单查询 | flash（当前会话） |
| `delegate_task` | 复杂分析需隔离上下文 | flash（继承父会话） |
| `execute_code` | 写脚本/策略/数据处理 | flash（主会话） |
| `terminal` | 运行脚本、验证 | 无模型参与 |

## 分类依据

### 走 flash 分析
- 查询实时行情
- 技术指标分析
- 基本面/财务分析
- 持仓盈亏计算
- 风险评估报告

### 走 flash 直接编写
- 策略脚本：`execute_code` 或直接工具调用
- 交易程序：`write_file` → `terminal` 运行
- 监控脚本：直接写文件 + cron部署

## 操作流程

```bash
# 股票分析
# 直接在主会话用 flash 执行，或 delegate_task 派发（子代理继承 flash）

# 股票编程
# 用 execute_code 替代 delegate_task，在主会话中链式调用工具
# from AI-Platform_tools import write_file, terminal, ...
```

## 审核清单
- [ ] 这是纯分析任务？
  - → 主会话 flash 直接执行，或 delegate_task
- [ ] 这是编程/脚本任务？
  - → 使用 `execute_code` / `write_file` / `terminal` 在主会话用 flash 完成
- [ ] 任务极其复杂需要更强推理？
  - → 手动切换模型：`AI-Platform model set deepseek-v4-pro --provider deepseek`
  - → 完成后再切回：`AI-Platform model set deepseek-v4-flash --provider deepseek`
