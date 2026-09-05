# 从 TACN/TradingAgents 迁移到 aStocks

## 背景

2026-07-28: TACN 项目 (`/mnt/c/Users/user/coding/TACN`) 和 TradingAgents 工程将被移除。
aStocks 技能完整替代其全部功能，且**独立运行不依赖源代码**。

## 能力对照

| TACN 能力 | aStocks 替代 |
|:----------|:-------------|
| `dataflows/` 数据获取 (akshare/tushare/baostock/yfinance) | `data_bridge.py` 4层降级 (腾讯0.1s直连优先) |
| `graph/` LangGraph 多Agent编排 | `ta-multi-agent-analysis` skill (外部集成) |
| `agents/` 分析师节点 (market/social/news/fundamentals) | `combo_scorer.py` 内置评分逻辑 + `ta-multi-agent-analysis` |
| `llm_clients/` 多LLM工厂 | AI-Platform 原生 LLM 管理 |
| `web/` Streamlit UI | AI-Platform CLI + cron 推送 |
| `cache/` MongoDB/Redis/File 三级缓存 | 腾讯直连零缓存 + a-share-data 文件缓存 |
| `constants/data_sources.py` DataSourceCode 注册表 | 保留为架构参考，a-stocks 按需引用 |
| 报告/导出 | `report_generator.py` + `stock-report-html` 模板 |

## 架构差异

| 维度 | TACN (旧) | aStocks (新) |
|:-----|:----------|:------------|
| **依赖** | FastAPI+Streamlit+MongoDB+LangChain+LangGraph+akshare | Python 标准库 (urllib+math) |
| **数据可靠性** | 单点 akshare 调用 | 4 层降级保证 |
| **启动方式** | `python web/run_web.py` | `python3 a_stocks.py <cmd>` |
| **部署** | 需要 MongoDB/Redis 服务 | 零外部服务 |
| **监控** | 无 | cron 三级止损预警+散户矫正 |
| **核心API** | FastAPI HTTP | CLI + Python import |

## 迁移步骤

1. 确认 aStocks 可用: `python3 a_stocks.py quote 600519`
2. 将持仓数据配置到 `monitor_watchdog.py`
3. 部署 cron 监控: `AI-Platform cron create --script monitor_watchdog.py ...`
4. 验证后移除 TACN 项目目录

## 保留价值

以下 TACN 架构设计已融入 aStocks 设计哲学:
- **DataSourceCode 注册表模式** → a-stocks `data_bridge.py` 内部降级链
- **Provider 抽象层** → `DataBridge` 类统一接口
- **多分析师协作思路** → `combo_scorer.py` 多维度评分 + `ta-multi-agent-analysis` 外部集成
- **DataSourceInfo 数据类** → `config.yaml` 配置分离
