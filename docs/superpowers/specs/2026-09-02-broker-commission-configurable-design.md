# 券商佣金及费率参数配置化与首次使用提示设计规范 (Design Spec)

- **日期**：2026-09-02
- **状态**：已批准 (Approved - 方案 A)
- **目标**：彻底消除代码库中券商佣金（万2.5及最低5元起收）等交易费率的硬编码与不一致问题，建立全局统一的市场费率配置中心，支持 CLI 交互配置与持久化，并在用户未配置/首次触发保本价计算时提供显式智能提示。

---

## 1. 背景与现状问题

### 1.1 核心问题审计
1. **多处硬编码与费率冲突**：
   - `core/strategy/execution_action_engine.py` 硬编码 `COMMISSION_RATE = 0.00012` (万1.2) 和 `MIN_COMMISSION = 5.0`，与 `config/config.yaml` 中的 `0.00025` (万2.5) 不一致。
   - `core/strategy/risk_position_manager.py` 内部写死 `max(5.0, cost * 0.00025)`。
   - `core/paper_trading/engine.py` 硬编码 `DEFAULT_COMMISSION_RATE = 0.00012`。
   - `core/paper_trading/a_stocks_backtest.py` 遗漏了单笔最低 5 元佣金的保底逻辑。
   - `core/models/multi_dim_model_v3.py` 参数独立写死在构造函数中。
2. **对最低成本价/保本价精度的直接危害**：
   - A股不同投资者的券商佣金费率差异较大（从万分之1到万分之3不等，部分支持免五/无最低5元限制）。
   - 保本卖出价公式依赖于买入与卖出两端的精确摩擦成本扣除：
     $$P_{\text{raw}} = \frac{\text{TotalBuyCost} + \text{SellDeductions}}{\text{Shares}}$$
   - 若使用错误的硬编码费率（如按万1.2计算实盘万2.5），会导致算出的「最低保本卖出价」偏低，用户挂单卖出后依然产生微亏。
3. **缺乏状态追踪与用户引导**：
   - 系统未记录用户是否已核对/配置过自己的真实券商费率。

---

## 2. 系统架构与设计细节

### 2.1 全局配置中心升级 (`core/config.py` 与 `config/config.yaml`)
在 `market` 配置块中增加状态字段并提供标准存取接口：

```yaml
market:
  default_benchmark: "sh000001"
  tax_rate_sell: 0.0005       # 卖出印花税 0.05% (万5)
  commission_rate: 0.00025    # 券商佣金 万2.5 (默认)
  transfer_fee_rate: 0.00001   # 过户费 十万分之1 (沪深双向)
  min_commission: 5.0         # 佣金最低 5 元起收 (免五用户可设为 0.0)
  breakeven_ceil_cent: true   # 最低保本卖出价必须向上精确进位到分
  is_user_configured: false   # 用户是否已确认/自定义过费率
```

**提供统一配置函数**：
- `get_market_config() -> dict`：获取当前生效的市场费率（含默认回退）。
- `save_market_config(...) -> dict`：更新 `config.yaml`，同步热重载内存中的 `GLOBAL_CONFIG`，并将 `is_user_configured` 设为 `true`。
- `check_market_config_prompt() -> Tuple[bool, str]`：检查 `is_user_configured`，若未配置则生成友好提示文本。

---

## 2.2 交易决策与精确保本算法重构 (`core/strategy/execution_action_engine.py`)
1. **移除顶部硬编码常量**，改由 `get_market_config()` 统一提供。
2. **重构 `calc_min_breakeven_price` 算法**：
   - 支持动态传入 `commission_rate`, `min_commission`, `stamp_tax_rate`, `transfer_fee_rate`。
   - 保证买卖双向均严格遵循 $\max(\text{成交金额} \times \text{佣金率}, \text{最低佣金})$。
   - 保留严密的向上精确取整至分（0.01 元）逻辑。
3. **未配置提醒注入**：
   - 当 `is_user_configured` 为 `False` 时，在生成的决策单/卡片中包含「💡 费率未确认提醒」，告知用户当前按万2.5默认计算。

---

## 2.3 业务与回测模块统一接入
1. `core/strategy/risk_position_manager.py`：读取 `get_market_config()` 替代硬编码。
2. `core/paper_trading/engine.py`：读取 `get_market_config()` 替代硬编码。
3. `core/paper_trading/a_stocks_backtest.py`：计算佣金时补充 `min_commission` 逻辑。
4. `core/models/multi_dim_model_v3.py`：接入统一配置中心。
5. `skills/` 对应副本脚本：同步更新保持一致。

---

## 2.4 CLI 命令设计 (`core/cli.py`)
新增 `config market` 子命令：

```bash
# 查看当前费率配置及配置状态
python core/cli.py config market

# 命令行一键配置券商佣金 (如万2.5，最低5元)
python core/cli.py config market --commission 0.00025 --min-commission 5.0

# 针对免五高频交易者一键配置 (如万1，免五)
python core/cli.py config market --commission 0.00010 --min-commission 0.0

# 交互式向导配置
python core/cli.py config market --interactive
```

并在 `python core/cli.py action plan` 计算保本价等业务命令中，若未配置过，输出引导提示。
