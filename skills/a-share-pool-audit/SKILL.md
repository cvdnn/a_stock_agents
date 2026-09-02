---
name: a-share-pool-audit
version: "1.0.0"
author: ""
description: "Use when 审查/整理A股三大股池(关注/自选/持仓)。统一快照+MA重算+过期关键位检测；不确定的信息不记录。"
license: MIT
tags: [A股, 股池, 审计, 持仓, 关键位]
metadata:
  AI-Platform:
    tags: [A股, 股池, 审计, 持仓, 关键位]
    related_skills: [a-share-dashboard, a-stocks]
---

# A股三大股池审计与整理

## When to Use

用户要求审查/整理 关注股池、自选估值、持股股池；要求"根据最新记录整理三大股池"；或要求刷新池内止损/止盈/MA参考位。

## 数据位置(只读来源)

```
C:\Users\user\AppData\Local\AI-Platform\skills\stocks\a-share-dashboard\data\
  watch_pool.csv        关注股池  列: code,name,added_date,rating,reason,sector,pe,change_pct,fund_flow,entry_condition,market_context,ta_analysis_date
  selected_pool.csv     自选股池  列: ...ma_status,entry_trigger,stop_loss,take_profit,risk_level,market_context,notes,ta_*...
  positions.csv         持仓池    列: code,name,buy_date,buy_price,qty,stop_loss,take_profit,sector,reason,status,strategy,entry_trigger,expected_days,risk_level,ma_status,market_context,backtest_result,notes
  positions_history.csv 平仓历史
```

⚠️ a-share-dashboard 是**用户自有技能**(非 curator 托管)，审计时只读其 data/*.csv，不要 patch 该技能的 SKILL.md 或 scripts/。

## 审计流程(五步)

1. **统一快照**: 一次性拉取所有池内股票(去重合并三池)腾讯 L1 行情。
   - `https://qt.gtimg.cn/q=sh600519,sz000002,...` 批量，decode("gbk")
   - 字段: `v_code="..."` 按 `~` 分割 → p[1]=名称 p[3]=现价 p[4]=昨收 p[39]=PE (p[45] 总市值在本机为空/0，勿依赖)
2. **MA 重算**: 每只取 60 根前复权日K 算 MA5/10/20。
   - `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=<sym>,day,,,60,qfq`
   - K线 close 在 `x[2]`。
3. **逐池比对 + 问题标记**:
   - 关注池: 从 `entry_condition` 里正则抽取数字作为参考位，现价偏离 >5% → ⚠️参考位可能过期
   - 自选池: 止损>现价 → 失效止损；现价≤止损 → 已破止损；现价≥止盈 → 已达止盈
   - 持仓池: 浮盈亏、距止损%、距止盈%、MA状态
4. **MA状态判定**: 价≥MA5≥MA10 且价≥MA20 → 多头；价≤MA5 且价≤MA10 且价≤MA20 → 空头；否则震荡。
5. **评级客观重估**(整理时): 多头+PE<60 → A；多头或震荡 → B；空头 → C。亏损股(PE<0)标注"亏损"。

## 整理原则 — 用户明确要求: 不确定的信息不记录 ⭐

写入池子时只保留**已验证事实**，其余一律清空：

| 字段 | 处理 |
|------|------|
| code/name/added_date/sector/加入理由 | 静态事实，保留 |
| pe / change_pct | 今日行情，更新 |
| rating | 按今日 MA 结构+PE 重估 |
| ma_status(自选/持仓) | 按今日 MA 重算 |
| stop_loss | **现价≤止损 → 清空(已失效)**；仍低于现价 → 保留 |
| take_profit | 现价≥止盈 → 清空(已触发)；未触发 → 保留 |
| notes(持仓) | 重写为今日快照: `现价x.xx(±x.xx%) 浮盈亏±n(±x.x%) 距止损±x.x%/已破止损 距止盈±x.x%/已达止盈` |
| entry_condition / fund_flow / market_context / ta_* / 旧分析文本 | **不确定 → 全部清空**，不要保留旧MA参考位 |

典型陷阱: 旧止损位是"买入价上方"的错误逻辑(如 6 月记录 20.0 而现价 18.65)，看起来是止损其实是过期数据 → 清空而非"下调"。

## 脚本

- `scripts/pool_audit.py` — 一键审计三池: 拉快照→算MA→打标记(过期参考位/失效止损/破位/达止盈/组合盈亏)。Python 3.9+ 兼容、仅标准库，可直接用于 cron no_agent。运行 `python pool_audit.py [--data DIR]`。

## 相关技能(只读引用)

- `a-share-dashboard`(用户自有): pool_manager.py / position_manager.py 负责 CRUD，本技能只负责审计与整理建议
- `a-stocks`(用户自有): 数据桥接/技术指标可替代脚本内的实现，但本技能的腾讯直连+标准库方案零依赖
