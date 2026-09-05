# A股最低保本价量化精算与精确进位规则 (2026-09-02 制定)

> 📌 **核心原则**：按全摩擦税费公式得出理论保本价后，**必须均精确向上进位到 0.01 元**（向上取整到分）。实战挂单与止损止盈参考一律采用进位后价格，确保 100% 绝对无损保本。

---

## 一、 费率参数标准

| 费用项 | 费率标准 | 收取方向 | 最低门槛 / 规则 |
|:---|:---:|:---:|:---|
| **佣金** | 万分之 1.2 ($0.00012$) | 双边收取（买入 + 卖出） | **单笔最低 5.00 元** |
| **印花税** | 万分之 5.0 ($0.00050$) | **单边收取（仅卖出收取）** | 无门槛 |
| **过户费** | 万分之 0.1 ($0.00001$) | 双边收取（沪深两市均收） | 无门槛 |

---

## 二、 保本价精算与进位算法

### 1. 理论全成本计算（买入总支出）
$$\text{BuyPrincipal} = \text{Cost} \times \text{Shares}$$
$$\text{BuyComm} = \max(\text{BuyPrincipal} \times 0.00012, 5.0)$$
$$\text{BuyTransfer} = \text{BuyPrincipal} \times 0.00001$$
$$\text{TotalBuyCost} = \text{BuyPrincipal} + \text{BuyComm} + \text{BuyTransfer}$$

### 2. 理论未进位保本价 ($P_{\text{raw}}$)
卖出时扣除卖出佣金、印花税、过户费后的净收入需 $\ge \text{TotalBuyCost}$：
$$\text{Denom} = 1 - 0.00012 - 0.0005 - 0.00001 = 0.99937$$
$$P_{\text{raw}} = \frac{\text{TotalBuyCost} + (\text{若卖出佣金不足5元补足差额})}{\text{Shares} \times \text{Denom}}$$

### 3. 精确进位至 0.01 元规则 ($P_{\text{breakeven}}$)
$$P_{\text{breakeven}} = \frac{\lceil \text{round}(P_{\text{raw}}, 4) \times 100 \rceil}{100.0}$$

**实战案例验证**：
* 案例 1：理论计算为 `¥6.1413` $\longrightarrow$ **`¥6.15`**
* 案例 2：理论计算为 `¥6.1463` $\longrightarrow$ **`¥6.15`**
* 案例 3：**中国中车**（5,000股，成本 ¥6.1411）：理论值 `¥6.1463` $\longrightarrow$ **`¥6.15`**（挂单 ¥6.15 卖出可净落袋 +¥18.51 利润，绝不微亏）
* 案例 4：**紫金矿业**（1,500股，成本 ¥31.1163）：理论值 `¥31.1399` $\longrightarrow$ **`¥31.14`**
* 案例 5：**恒瑞医药**（200股，成本 ¥88.4427）：理论值 `¥88.5387` $\longrightarrow$ **`¥88.54`**

---

## 三、 Python 标准实现代码

```python
import math

COMMISSION_RATE = 0.00012   # 万分之1.2（双边）
STAMP_TAX_RATE  = 0.0005    # 万分之5（仅卖出收取）
TRANSFER_RATE   = 0.00001   # 万分之0.1（双边）
MIN_COMMISSION  = 5.0       # 单笔最低5元

def calc_min_breakeven_price(cost: float, shares: int) -> float:
    """
    计算最低保本卖出价（覆盖所有摩擦税费后向上精确进位至0.01元）
    """
    if cost <= 0 or shares <= 0:
        return cost
        
    buy_principal = cost * shares
    buy_comm = max(buy_principal * COMMISSION_RATE, MIN_COMMISSION)
    buy_transfer = buy_principal * TRANSFER_RATE
    total_buy = buy_principal + buy_comm + buy_transfer

    def net_revenue(p):
        sell = p * shares
        sc = max(sell * COMMISSION_RATE, MIN_COMMISSION)
        st = sell * STAMP_TAX_RATE
        sf = sell * TRANSFER_RATE
        return sell - sc - st - sf

    # 二分查找理论价格
    lo, hi = cost * 0.8, cost * 1.5
    for _ in range(60):
        mid = (lo + hi) / 2
        if net_revenue(mid) >= total_buy:
            hi = mid
        else:
            lo = mid
            
    # 核心进位逻辑：向上精确取整到 0.01 元
    breakeven_price = math.ceil(round(hi, 4) * 100) / 100.0
    return breakeven_price
```

---

## 四、 适用范围与生效文件

1. **HTML 报告生成规范**：`stock-report-html` 10 列持仓全景表中的「最低卖出价」；
2. **交易执行引擎**：`execution_action_engine.py` 中的 `calc_min_breakeven_price`；
3. **持仓监控与风控策略**：`a-stock-session-tips` 中的持仓重算与保本跳变判定；
4. **交易决策手册**：[`execution-manual.md`](execution-manual.md)。
