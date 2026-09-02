# A-Stock Agents 快速上手指南

## 一、环境要求
- 操作系统：Linux / Windows / macOS
- Python 版本：Python 3.9 ~ 3.13

## 二、一键安装部署

### Linux / macOS
```bash
cd a_stock_agents
chmod +x install.sh bin/astock
./install.sh
```

### Windows (PowerShell)
```powershell
cd a_stock_agents
.\install.ps1
```

安装脚本会自动创建独立的虚拟环境 `.venv` 并安装全部必要依赖。

---

## 三、一键自检与验证

运行全功能自检脚本，确保所有数据接口、技术指标、量化模型、交易引擎及模拟盘均处于正常就绪状态：

```bash
python verify.py
```

---

## 四、CLI 核心功能演示

```bash
# 1. 查询贵州茅台实时行情
./bin/astock data quote sh600519

# 2. 计算五粮液的技术指标 (MA, MACD, KDJ, RSI, BOLL)
./bin/astock data tech sz000858

# 3. 对比亚迪进行综合量化打分诊断
./bin/astock evaluate sz002594

# 4. 生成当前持仓的精确最低保本价与三场景反应动作清单
./bin/astock action plan

# 5. 查看所有可用技能列表
./bin/astock skill list
```
