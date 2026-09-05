# Phase 2 故障排查与工程笔记

本文档记录 `ta-multi-agent-analysis` 的 Phase 2 (TradingAgents-astock 多Agent管道) 在 WSL 环境下的调通经验。

## 1. 模块导入顺序与耗时

| 导入语句 | 耗时 | 说明 |
|---------|:----:|------|
| `import langchain_core` | ~1.1s | 首次导入 |
| `import langgraph` | ~0.01s | 轻量 |
| `import langgraph.graph` | **~12.25s** | 冷启动最慢的环节 |
| `from langgraph.graph import MessagesState` | ~0.0s | 缓存后极快 |
| `from tradingagents.graph.trading_graph import TradingAgentsGraph` | ~30s | 含子模块递归导入 |
| `import openai` | ~18s | WSL 下 httpx 初始化慢 |

**模式**：第一次导入 `langgraph.graph` 是瓶颈。之后的导入全部使用缓存。子进程（300s timeout）不受影响。

**预热技巧**：在调用 Phase 2 前先在主进程执行一次轻量导入，子进程就能复用缓存缩短一半时间。

```python
# 预热
import sys
sys.path.insert(0, TA_DIR)
from tradingagents.default_config import DEFAULT_CONFIG  # 触发 langgraph 冷启动
```

## 2. DEFAULT_CONFIG merge 模式

`TradingAgentsGraph(config=config)` 要求 config 字典包含 `DEFAULT_CONFIG` 的全部键：

```python
# 错误（缺失 data_cache_dir / results_dir / memory_log_path）：
config = {"llm_provider": "minimax", ...}

# 正确：
from tradingagents.default_config import DEFAULT_CONFIG
config = dict(DEFAULT_CONFIG)
config.update({
    "llm_provider": "minimax",
    "deep_think_llm": "MiniMax-M2.7",
    ...
})
```

**原因**：`TradingAgentsGraph.__init__` 第78行 `os.makedirs(self.config["data_cache_dir"], exist_ok=True)` 直接访问 key，没有 fallback。

## 3. `.env` 路径 fallback

当 `TA_DIR` 指向 `_original_src` 时，`.env` 文件在父目录（项目根）：

```python
env_path = Path(TA_DIR) / '.env'
if not env_path.exists():
    env_path = Path(TA_DIR).parent / '.env'  # fallback
```

## 4. 数据 vendor 不匹配

当前本地代码库状况：

| 目录 | 包含 | 不含 |
|------|------|------|
| `_original_src/tradingagents/` | agents, graph, llm_clients（全量管道） | a_stock.py data vendor |
| `tradingagents/dataflows/` | akshare/ 子模块（自定义） | 无 agents/graph |

`_original_src/dataflows/` 只有 `yfinance` / `alpha_vantage` 等美股数据源，不连 A 股。解决方案：
- 将 `tradingagents/dataflows/akshare/` 下的文件注册到 `_original_src/dataflows/interface.py`
- 或在 config 中指定 data_vendors 走本地链路

## 5. 子进程 stdout 解析

`phase2_multiagent_analysis()` 使用 `__TA_RESULT__` / `__TA_END__` 标记截取子进程输出：

```python
# 子进程必须按此格式输出：
print("__TA_RESULT__")
print(json.dumps(output, ensure_ascii=False))
print("__TA_END__")

# 父进程解析：
start = stdout.find("__TA_RESULT__")
end = stdout.find("__TA_END__")
json_str = stdout[start + len("__TA_RESULT__"):end].strip()
```

**注意**：stderr 不参与解析。如果子进程在 `__TA_RESULT__` 之后出错，父进程会报"无法解析 TradingAgents 输出"。此时应检查 raw_stderr。

## 6. 常见 Phase 2 错误速查

| stderr 特征 | 原因 | 修复 |
|------------|------|------|
| `Yahoo Finance rate limited` | vendor 未切到 a_stock | 检查 `data_vendors` 配置 |
| `KeyError: 'data_cache_dir'` | config 缺少 DEFAULT_CONFIG merge | 用 `dict(DEFAULT_CONFIG)` 初始化 |
| `AuthenticationError: 401` | API Key 无效或过期 | 更新 `.env` |
| `ModuleNotFoundError: tradingagents.graph` | TA_DIR 指向了不完整的 `tradingagents/` | 改用 `_original_src/` |
| 子进程无输出但没超时 | sys.path 没设对 | 检查子进程代码中的 `sys.path.insert(0, TA_DIR)` |
