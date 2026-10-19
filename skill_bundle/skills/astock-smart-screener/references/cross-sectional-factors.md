# 截面因子工程与标准化规范 (Cross-Sectional Factors)

本文档说明 `astock-smart-screener` 中截面因子清洗、去极值、标准化与 IC 分析算法。

---

## 1. 因子清洗三步法

### 步骤一：MAD 去极值 (Median Absolute Deviation)
为防止极端异常值对因子合成造成严重扭曲，采用三倍中位数绝对偏差法：
1. 计算因子截面中位数：$M = \text{median}(X)$；
2. 计算绝对离差中位数：$\text{MAD} = \text{median}(|X - M|)$；
3. 设定上下边界：
   $$X_{\text{upper}} = M + 3 \times 1.4826 \times \text{MAD}$$
   $$X_{\text{lower}} = M - 3 \times 1.4826 \times \text{MAD}$$
4. 超出边界的值截断为边界值。

### 步骤二：行业与市值中性化 (可选)
对规模（Log 市值）与申万一级行业虚拟变量进行多元线性回归，取回归残差作为纯净 Alpha 因子。

### 步骤三：Z-Score 标准化
对去极值后的因子序列进行标准化处理，使其服从均值为 0、标准差为 1 的标准正态分布：
$$z_i = \frac{x_i - \mu}{\sigma}$$

---

## 2. 因子有效性评估指标

- **Rank IC (秩相关系数)**：
  计算 $t$ 日因子暴露排名与 $t+1$ 日（或 $t+N$ 日）个股收益率排名的 Spearman 相关系数。
  - $|\text{Mean}(IC)| > 0.03$：因子具备预测能力；
  - $|\text{Mean}(IC)| > 0.05$：高 Alpha 强效因子。
- **IR (信息比率)**：
  $$\text{IR} = \frac{\text{Mean}(IC)}{\text{Std}(IC)}$$
  $\text{IR} > 0.5$ 表明因子在不同截面上表现稳健，具备长期实战价值。
