# Kronos 项目实证结论 + 技术要点（2026-08 实测）

> 案例结论：开箱即用 Kronos 对 A股**不可靠**，不建议集成。此页保留证据与模型细节，供未来复现或评估同类模型参照。

## 实证结果

### Kronos-mini（6标的 × 10窗口，n=60/水平）
| 标的 | 1日 | 5日 | 10日 | 20日 | MAPE/昨收不变 |
|:----|:---:|:---:|:---:|:---:|:--:|
| 茅台 600519 | 60% | 50% | 60% | 50% | 1.48 |
| 五粮液 000858 | 40% | 50% | 40% | 40% | 2.19 |
| 平安 601318 | 50% | 60% | 50% | 40% | 1.25 |
| 宁德 300750 | 50% | 30% | 40% | 50% | 2.10 |
| 沈飞 600760 | 70% | 70% | 60% | 40% | 1.62 |
| 上证指数 | 40% | 50% | 30% | 40% | 1.97 |
| **均值** | **51.7%** | **51.7%** | **46.7%** | **43.3%** | **1.77** |

- 所有方向命中率与抛硬币(50%)无统计差异（标准误±6.5%），20日甚至倾向低于随机。
- **MAPE 平均比"照抄昨收"误差高 77%（1.25~2.19），6只全部劣于朴素。**

### Kronos-small 抽查（n=5，base tokenizer）
- 茅台 1d=0%、20d=20%（远低于随机）；五粮液 20d=40%、MAPE 0.91（唯一略优）。
- n 过小，但方向结论与 mini 一致；CPU 上 ~48s/窗口，不实用。

### 结论偏乐观的说明
Kronos 预训练或与测试期重叠（若记忆过则虚高），即便如此仍未跑赢随机——更坐实"开箱不可靠"。

## Kronos 技术要点
- **本质**：金融K线(OHLCV)基础模型，decoder-only；两阶段=分层离散 tokenizer（量化 OHLCV→层次化离散token）+ 自回归 Transformer。训练于45家全球交易所（加密/美股为主）。
- **依赖**：Python 3.10+、torch>=2.0、pandas、numpy、huggingface_hub、safetensors、einops。
- **模型**：mini(4.1M)/small(24.7M)/base(102M)/large(499M闭源)；small/base 上下文仅 **512**，mini 为 2048。
- **API**：`KronosPredictor(model, tokenizer, device, max_context).predict(df, x_timestamp, y_timestamp, pred_len, T, top_p, sample_count)`；`predict_batch` 批量多序列（须同长、同 pred_len）。df 列须含 open/high/low/close，volume/amount 可选。
- **CPU 性能**：mini ~3s/窗口(PRED=20)，small ~48s/窗口；大批量务必用 `predict_batch`，无 GPU 优先 mini。
- **腾讯K线格式注意**：`[date, open, close, high, low, volume]`（close 在 high 前）。
- 有效路径是领域微调：官方提供 Qlib 加载 A股→微调 tokenizer+predictor→top-K 回测的完整管线。

## 决策
**不集成进 a-stocks。** 开箱即用无方向优势、价格劣于朴素基准 77%、且需 torch+GPU 违背零依赖设计。未来若要"向前看"，离线微调 A股权重再谈接入——独立工程。
