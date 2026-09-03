# Cron 脚本 Python 3.9 兼容注意事项

## 问题

WSL 系统的 `python3` 是 Python 3.9（`/usr/bin/python3`），而 `python3.11` 或 venv 可能安装在其他路径。部署到 cron 的 no-agent 脚本由 AI-Platform 调度器自动用 `python3` 运行（即系统 Python 3.9）。

## 不支持的语法

### 联合类型注解 (Python 3.10+)
```python
# SyntaxError ❌
def get_quote(code: str) -> dict[str, Any] | None:

# 兼容写法 ✅
def get_quote(code):
```

### 类型注解中的 `Optional` / `Union`
```python
# SyntaxError ❌ (在3.9下 `list[dict]` 可用，但 `| None` 不行)
def fn() -> list[dict] | None:

# 兼容写法 ✅
def fn():
```

## 最佳实践

1. **所有 cron no-agent 脚本去掉所有函数返回类型注解**（不需要 `-> dict:`、`-> str:` 等）
2. 脚本顶部不留不再使用的 `from typing import Any`
3. 使用 `from __future__ import annotations` 可以开启后向兼容，但不绝对保证所有模式
4. 最安全的策略：**去类型注解**（cron 脚本没有 mypy 检查）

## 检查清单

部署新脚本前：
```bash
grep -n '->' ./.AI-Platform/scripts/xxx.py
# 如果看到 list[dict] | None、dict[str, Any] | None 等 → 需要移除
```