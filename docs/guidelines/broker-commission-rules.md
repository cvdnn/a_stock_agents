# 券商佣金及市场交易费率参数配置化业务规则 (Broker Commission & Market Fee Rules)

> **文档类别**：业务规则 (Rules)  
> **适用范围**：A-Stock Agents 交易成本精算、实战动作单生成、模拟盘撮合引擎与策略回测模块  
> **实施进度看板**：[`docs/specs/business/biz-broker-commission-configurable-design.md`](../specs/business/biz-broker-commission-configurable-design.md) (`SPEC-BIZ-001`)

---

## 一、 核心目的与铁律

彻底消除代码库中券商佣金（万2.5及最低5元起收）等交易费率的局部硬编码与不一致问题，建立全局统一的市场费率配置中心，支持 CLI 交互配置与持久化，并在用户未配置/首次触发保本价计算时提供显式智能提示。

---

## 二、 全局配置规范 (`config/config.yaml`)

全系统交易费率基准必须统一从 `config/config.yaml` 的 `market` 字段读取，严禁任何模块内部硬编码数值：

```yaml
market:
  default_benchmark: "sh000001"
  tax_rate_sell: 0.0005       # 卖出印花税 0.05% (万5，单边卖出收取)
  commission_rate: 0.00025    # 券商佣金 万2.5 (默认，双边买卖收取)
  transfer_fee_rate: 0.00001   # 过户费 十万分之1 (双向收取)
  min_commission: 5.0         # 佣金最低 5 元起收 (免五用户可设为 0.0)
  breakeven_ceil_cent: true   # 最低保本卖出价必须向上精确进位到分 (math.ceil)
  is_user_configured: false   # 用户是否已确认/自定义过费率 (未确认时触发提示)
```

---

## 三、 Python 核心访问与热重载接口 (`scripts/core/config.py`)

提供三大统一方法：
1. **`get_market_config() -> dict`**：
   - 获取当前生效的费率字典；如果缺少字段，自动以标准万2.5和最低5元保底回退。
2. **`save_market_config(...) -> dict`**：
   - 接受自定义费率参数，写回 `config.yaml`，触发内存中全局配置即时热重载，并将 `is_user_configured` 标记为 `True`。
3. **`check_market_config_prompt() -> Tuple[bool, str]`**：
   - 检查用户是否自定义核实过费率。若为 `False`，生成带引导文本的友好提示：
     `"💡 提示：当前按默认费率（佣金万2.5/保底5元）核算保本价。可通过 'astock config market' 自定义您的真实佣金费率。"`

---

## 四、 跨模块接入标准 (Integration Standard)

全系统各子系统统一接入 `get_market_config()`，保持单一真理来源（SSOT）：
- **`scripts/core/strategy/execution_action_engine.py`**：保本价精算引擎；
- **`scripts/core/strategy/risk_position_manager.py`**：持仓风控与解套做 T 盈亏试算；
- **`scripts/core/paper_trading/engine.py`**：模拟撮合真实滑点与手续费扣除；
- **`scripts/core/paper_trading/a_stocks_backtest.py`**：历史回测事件驱动摩擦成本；
- **`.agents/skills/`**：各就地技能通过 CLI 或 Python SDK 调用时自动享受配置中心同步。

---

## 五、 CLI 交互与管理命令规范

```bash
# 1. 查看当前生效费率与配置确认状态
astock config market --json

# 2. 命令行一键设置真实佣金 (例: 万2.5，最低5元)
astock config market --commission 0.00025 --min-commission 5.0

# 3. 针对免五高频交易者一键配置 (例: 万1，免五)
astock config market --commission 0.00010 --min-commission 0.0

# 4. 交互式向导配置
astock config market --interactive
```
