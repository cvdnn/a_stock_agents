# A股最低保本卖出价量化精算与精确进位业务规则规范 (Breakeven Price Calculation Rules)

- **规范分类**：业务规则
- **规范编号**：SPEC-BIZ-002
- **文档版本**：v1.2
- **当前状态**：正式规范 (Production Baseline)
- **创建日期**：2026-09-02（修订日期：2026-09-07）
- **适用范围**：A股量化实战交易动作中枢、保本价试算器、HTML交互研报持仓明细表与模拟撮合风控
- **关联设计**：[`biz-broker-commission-configurable-design.md`](biz-broker-commission-configurable-design.md)、[`biz-trading-execution-and-risk-control.md`](biz-trading-execution-and-risk-control.md)、[`../../../AGENTS.md`](../../../AGENTS.md)

---

## 0. 核心原则与铁律 (The Breakeven Iron Law)

> 📌 **核心铁律**：按全摩擦税费公式得出理论保本价后，**必须均强制向上精确进位到 0.01 元 (`math.ceil`)**。实战挂单与止盈止损参考一律采用进位后价格，杜绝任何四舍五入，确保 100% 绝对无损保本。

---

## 1. 费率参数标准 (Market Fee Parameters)

全市场交易摩擦成本动态支持通过 `config/config.yaml` 配置化（参见 [`biz-broker-commission-configurable-design.md`](biz-broker-commission-configurable-design.md)），标准基准参数如下：

| 费用项 | 费率标准 | 收取方向 | 最低门槛 / 规则说明 |
|:---|:---:|:---:|:---|
| **印花税** | 万分之 5.0 ($0.00050$) | **单边收取（仅卖出收取）** | 无最低收费门槛 |
| **券商佣金** | 万分之 2.5 ($0.00025$)（默认） | 双边收取（买入 + 卖出） | **单笔最低 5.00 元起收**（支持免五配置） |
| **过户费** | 万分之 0.1 ($0.00001$) | 双边收取（沪深两市均收） | 无门槛 |

---

## 2. 保本价精算与进位算法数学模型

### 2.1 理论全成本计算（买入总支出）
$$\text{BuyPrincipal} = \text{Cost} \times \text{Shares}$$
$$\text{BuyComm} = \max(\text{BuyPrincipal} \times \text{CommissionRate}, \text{MinCommission})$$
$$\text{BuyTransfer} = \text{BuyPrincipal} \times \text{TransferRate}$$
$$\text{TotalBuyCost} = \text{BuyPrincipal} + \text{BuyComm} + \text{BuyTransfer}$$

### 2.2 理论未进位保本价 ($P_{\text{raw}}$)
卖出时扣除卖出佣金、印花税、过户费后的净收入必须 $\ge \text{TotalBuyCost}$：
$$\text{Denom} = 1 - \text{CommissionRate} - \text{StampTaxRate} - \text{TransferRate}$$
$$P_{\text{raw}} = \frac{\text{TotalBuyCost} + (\text{若卖出佣金不足最低佣金需补足之差额})}{\text{Shares} \times \text{Denom}}$$

### 2.3 强制向上精确进位至 0.01 元规则 ($P_{\text{breakeven}}$)
$$P_{\text{breakeven}} = \frac{\lceil \text{round}(P_{\text{raw}}, 4) \times 100 \rceil}{100.0}$$

**实战案例验证**：
* 案例 1：理论计算为 `¥6.1413` $\longrightarrow$ **`¥6.15`**
* 案例 2：理论计算为 `¥6.1463` $\longrightarrow$ **`¥6.15`**
* 案例 3：**中国中车**（5,000股，成本 ¥6.1411）：理论值 `¥6.1463` $\longrightarrow$ **`¥6.15`**（挂单 ¥6.15 卖出可净落袋 +¥18.51 利润，绝不产生微亏）
* 案例 4：**紫金矿业**（1,500股，成本 ¥31.1163）：理论值 `¥31.1399` $\longrightarrow$ **`¥31.14`**
* 案例 5：**恒瑞医药**（200股，成本 ¥88.4427）：理论值 `¥88.5387` $\longrightarrow$ **`¥88.54`**

---

## 3. Python 标准工程实现

位于 `scripts/core/strategy/execution_action_engine.py`：

```python
import math
from typing import Optional
from scripts.core.config import get_market_config

def calc_min_breakeven_price(
    cost: float,
    shares: int,
    commission_rate: Optional[float] = None,
    min_commission: Optional[float] = None,
    stamp_tax_rate: Optional[float] = None,
    transfer_fee_rate: Optional[float] = None,
) -> float:
    """
    计算最低保本卖出价（严格计入全流程摩擦税费后，强制向上精确进位至 0.01 元）。
    """
    if cost <= 0 or shares <= 0:
        return cost
        
    cfg = get_market_config()
    comm_rate = commission_rate if commission_rate is not None else cfg.get("commission_rate", 0.00025)
    min_comm = min_commission if min_commission is not None else cfg.get("min_commission", 5.0)
    tax_rate = stamp_tax_rate if stamp_tax_rate is not None else cfg.get("tax_rate_sell", 0.0005)
    trans_rate = transfer_fee_rate if transfer_fee_rate is not None else cfg.get("transfer_fee_rate", 0.00001)

    buy_principal = cost * shares
    buy_comm = max(buy_principal * comm_rate, min_comm)
    buy_transfer = buy_principal * trans_rate
    total_buy = buy_principal + buy_comm + buy_transfer

    def net_revenue(p: float) -> float:
        sell = p * shares
        sc = max(sell * comm_rate, min_comm)
        st = sell * tax_rate
        sf = sell * trans_rate
        return sell - sc - st - sf

    # 二分查找理论价格
    lo, hi = cost * 0.8, cost * 1.8
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if net_revenue(mid) >= total_buy:
            hi = mid
        else:
            lo = mid
            
    # 核心进位逻辑：向上精确取整到 0.01 元
    breakeven_price = math.ceil(round(hi, 4) * 100) / 100.0
    return breakeven_price
```

---

## 4. 前端展示去术语化准则 (Presentation Guidelines)

遵循《Web UI 界面设计与交互规范》：
1. **底层计算严格执行**：算法与状态机一律采用 `math.ceil` / `Math.ceil` 进位；
2. **用户界面文案净化**：表头与标签统一使用标准金融词汇 `最低保本卖出价` 或 `保本参考价`，杜绝出现 `(ceil)`、`(math.ceil)` 等代码调试后缀。
