# 配置驱动的“收盘突破 → 次日早盘拐点”漏斗

> 本漏斗是智能选股系统中的复杂模型示例。后续核心编码、调度和 Web 工作台建设统一以[《智能选股系统功能建设规范》](configurable-funnel-feature-build-spec.md)为实施依据。

## 结论与规则评估

该策略适合作为短线候选生成器，不应直接等同于自动买入系统。日线突破、趋势、放量和资金流入负责压缩股票池；次日大盘门控和高开过滤负责避开弱环境；09:30～09:40 的回调与供需拐点负责确认入场时机。

原始描述存在两组口径冲突，默认配置选择：

- “收盘创 20 日新高”，而不是后文提到的 60 日新高；修改 `breakout_high.lookback` 即可切换。
- 高开 1%～2%；如果实际意图是“任何正高开”，把 `gap_range.min` 改成 `0`，把 `max` 改成 `null`。

“今日量大于昨日量”只代表单日放量，不等于“量能持续放大”。如果需要持续放量，应新增一条多日均量规则，而不是改写现有规则的含义。

问财收盘初筛可按以下自然语言口径执行：`收盘价创20日新高；收盘价大于60日均线；60日均线大于昨日60日均线；成交量大于昨日成交量；主力资金净流入；非ST；非北交所；流通市值大于30亿元；涨幅小于7%`。落地数据统一使用前复权日线，流通市值单位为元；关键字段缺失直接淘汰并标记数据不足。

## 四层漏斗

1. `post_close`（15:05 后）：非 ST、非北交所、流通市值大于 30 亿、当日涨幅小于 7%、创 N 日新高、收盘高于 MA60、MA60 向上、今日量大于昨日量、主力净流入。
2. `market_gate`（次日 09:30）：默认以上证指数 `sh000001` 为大盘，指数实时价必须高于此前 20 个完整交易日收盘均值。门控失败时整批停止；基准指数可在配置中替换。
3. `opening_gap`（09:30）：用开盘价相对昨收计算高开幅度，默认保留 1%～2%。
4. `turning_point`（09:35～09:40）：必须先有 09:30～09:35 冲高回调，再同时确认价格反转和卖压衰减；主动买量增强、五档买盘优势中还须至少满足一项。

拐点阶段优先使用主动买卖量；没有主动买卖量时只允许使用涨跌分钟量作为明确标注的代理。数据点不足时返回 `INSUFFICIENT_DATA`，不会产生买点。

## 输入数据契约

阶段输入可以是 JSON 数组，也可以是：

```json
{
  "records": [{"code": "600001"}],
  "context": {"market": {"current_price": 3200, "completed_closes": [3180]}}
}
```

`post_close` 每条记录需要 `code/name/circulating_market_cap/change_pct/closes/volumes/main_net_inflow`。`opening_gap` 需要 `open/previous_close`。`turning_point` 需要 `minute_points`，每点至少含 `time/price/volume`；推荐再提供 `buy_volume/sell_volume` 和 `order_book.bid_volume/ask_volume`。

## CLI

```bash
./bin/astock funnel validate --json
./bin/astock funnel run --stage post_close --input temp/funnel/post_close.json --save --json
./bin/astock funnel run --stage market_gate --input temp/funnel/market_gate.json --save --json
./bin/astock funnel run --stage opening_gap --input temp/funnel/opening_gap.json --save --json
./bin/astock funnel run --stage turning_point --input temp/funnel/turning_point.json --save --json
```

归档结果位于 `output/pools/funnel/<交易日>/<阶段>.json`，每条淘汰记录都包含失败规则及观测值。
一个阶段生成的 JSON 可以直接作为下一阶段的 `--input`；CLI 会读取其中的 `passed_records`，因此整条流水线无需手工摘取代码。
最终阶段的 `selected_codes` 即为 09:35～09:40 应输出的股票代码列表。

## 扩展方式

阶段顺序、阶段/规则启停、`all/any` 组合逻辑、阈值与规则组合全部定义在 `config/funnel_strategy.yaml`。已有规则类型可以直接组合；新增复杂规则时，在 `build_stock_rule_registry()` 注册一个纯函数即可。执行引擎与数据获取解耦，因此同一漏斗可接问财导出、行情供应商或历史回测数据。

正式使用前必须做滚动样本外验证，至少统计候选数、09:40 后收益分布、次日/3日胜率、最大不利变动和不同大盘状态下的分层表现；不能用同一段数据既调拐点参数又宣称有效。
