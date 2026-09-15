# a-share-paper-trading

独立的 A 股模拟盘 skill，和数据 skill 解耦，负责：

- 多账户模拟交易
- 限价单、市价单、撤单
- 持仓、订单、成交、账户净值
- A 股规则校验与定时撮合
- 回测

## 当前规则

- A 股 `long-only`
- 买入数量必须是 `100` 股整数倍
- 卖出遵守 `T+1`
- 限价单价格必须符合 `0.01` 元最小报价单位
- 超过当日涨跌停的限价单直接拒绝
- 触及涨停价默认买不进（包含一字涨停）
- 触及跌停价默认卖不出（包含一字跌停）
- 市价单仅在连续竞价时段接受
- 集合竞价与午休时段不做自动撮合
- 行情时间戳不是当日时，视为陈旧行情，不执行市价成交
- 费用模型包含最低佣金、卖出印花税、沪市过户费
- 当日未成交 `DAY` 单收盘后过期

## 板块涨跌幅兜底

- 主板普通股：`10%`
- 创业板/科创板：`20%`
- 主板 ST：`5%`

优先使用实时 quote 自带的 `limit_up/limit_down`；只有上游缺失时才走这套兜底规则。

## 启动

默认配置已经改成**项目内**统一运行目录，符合 `AGENTS.md` 的「工作区输出目录规范 (Three-Bucket Discipline)」，**严禁**把数据库/日志写到系统全局目录：

- 数据库与 PID：`{PROJECT_ROOT}/output/cache/paper_trading/paper_trading.db`
- 服务运行日志：`{PROJECT_ROOT}/log/paper_trading/service.log`
- 临时下载/解压：`{PROJECT_ROOT}/temp/paper_trading/`（如启用）

> 早期版本曾以 macOS `~/Library/Application Support/a-share-paper-trading/` 与 Linux `~/.local/share/a-share-paper-trading/` 作为落点，**已废弃**，请使用 `A_STOCK_AGENTS_ROOT` / `A_STOCK_OUTPUT_DIR` / `A_STOCK_LOG_DIR` 环境变量进行覆盖。

默认监听地址：

- `http://127.0.0.1:18765`

前台启动：

```bash
python3 "$PROJECT_ROOT/scripts/core/paper_trading/paper_trading_service.py" --host 127.0.0.1 --port 18765
```

推荐用控制脚本后台常驻：

```bash
python3 "$PROJECT_ROOT/scripts/core/paper_trading/paper_trading_ctl.py" start
python3 "$PROJECT_ROOT/scripts/core/paper_trading/paper_trading_ctl.py" status
python3 "$PROJECT_ROOT/scripts/core/paper_trading/paper_trading_ctl.py" stop
```

若希望开机自动拉起，可安装 launchd：

```bash
python3 "$PROJECT_ROOT/scripts/core/paper_trading/paper_trading_ctl.py" install-launchd
```

## 验证脚本

- 规则回归：`scripts/rule_regression_check.py`
- 真实股票校验：`scripts/real_stock_rule_validation.py`

其中真实股票校验会用 22 只真实股票做 3 轮验证，覆盖主板、创业板、科创板、ST。
