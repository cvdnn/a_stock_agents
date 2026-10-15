#!/usr/bin/env bash
# astock-agent-debate 运行环境检查与配置辅助
#
# 2026-10-15 (P0-05 整改):
# - 移除依赖安装动作，防止污染宿主 Python 环境；
# - 移除向临时 vendor 目录写入凭据的行为，指引统一配置 local/settings/.env；
# - 移除安装脚本尾部发起真实外网与 LLM 试跑的非幂等逻辑；
# - 使用 bundle.json 向上探测 Bundle 根路径，严禁使用固定父目录层数；
# - 统一使用当前技能 ID astock-agent-debate。

set -euo pipefail

# ── 1. 探测 Bundle 根目录（严禁固定父目录层数） ─────────────────────────────
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT="$CURRENT_DIR"
while [ ! -f "$BUNDLE_ROOT/bundle.json" ]; do
  PARENT="$(dirname "$BUNDLE_ROOT")"
  if [ "$PARENT" = "$BUNDLE_ROOT" ]; then
    echo "错误: 未找到 bundle.json，需在完整的 A-Stock Agents Bundle 内运行" >&2
    exit 1
  fi
  BUNDLE_ROOT="$PARENT"
done

# ── 2. 寻找隔离 Python 解释器 ───────────────────────────────────────────────
# 优先级: 显式 A_STOCK_PYTHON > Bundle 外部 .venv > 宿主当前激活的 VIRTUAL_ENV
PYTHON_EXEC=""
if [ -n "${A_STOCK_PYTHON:-}" ] && [ -x "$A_STOCK_PYTHON" ]; then
  PYTHON_EXEC="$A_STOCK_PYTHON"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PYTHON_EXEC="$VIRTUAL_ENV/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/Scripts/python.exe" ]; then
  PYTHON_EXEC="$VIRTUAL_ENV/Scripts/python.exe"
elif [ -x "$BUNDLE_ROOT/../.venv/bin/python" ]; then
  PYTHON_EXEC="$BUNDLE_ROOT/../.venv/bin/python"
elif [ -x "$BUNDLE_ROOT/../.venv/Scripts/python.exe" ]; then
  PYTHON_EXEC="$BUNDLE_ROOT/../.venv/Scripts/python.exe"
fi

if [ -z "$PYTHON_EXEC" ]; then
  echo "⚠️ 未检测到已激活或就绪的隔离虚拟环境 (.venv)" >&2
  echo "提示: A-Stock 遵循无宿主污染原则，严禁直接向系统全局 Python 安装包" >&2
  echo "请先创建并激活虚拟环境: python -m venv .venv && source .venv/bin/activate (或设置 A_STOCK_PYTHON)" >&2
  exit 1
fi

# ── 3. 运行基础健康诊断 ─────────────────────────────────────────────────────
echo "═══ [astock-agent-debate] 运行环境自检 ═══"
echo "Bundle 路径: $BUNDLE_ROOT"
echo "Python 解释器: $PYTHON_EXEC"

"$PYTHON_EXEC" "$BUNDLE_ROOT/runtime/doctor.py"

echo ""
echo "─── LLM 凭据配置指引 ───"
echo "如需运行 Phase 2 (7分析师多Agent辩论)，请确保在以下私有配置文件中写入 API Key:"
echo "  local/settings/.env (推荐) 或环境变量 A_STOCK_CONFIG_PATH"
echo "  支持的供应商配置示例:"
echo "    MINIMAX_API_KEY=sk-xxx"
echo "    DEEPSEEK_API_KEY=sk-xxx"
echo "    DASHSCOPE_API_KEY=sk-xxx (通义千问)"
echo "    ZHIPU_API_KEY=sk-xxx (智谱 GLM)"
echo ""
echo "✅ 环境检查完毕。执行分析命令示例:"
echo "  Windows: .\\bin\\astock.ps1 debate 600519 --json"
echo "  Linux/macOS: ./bin/astock debate 600519 --json"
