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

# ── 1. 探测 Bundle 根目录（自定位 ➔ 兄弟定位 ➔ 收据定位） ────────────────────
PROBE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_ROOT=""
while [ "$PROBE" != "/" ] && [ "$PROBE" != "." ]; do
  if [ -f "$PROBE/bundle.json" ]; then
    BUNDLE_ROOT="$PROBE"
    break
  fi
  PARENT="$(dirname "$PROBE")"
  if [ "$PARENT" = "$PROBE" ]; then break; fi
  PROBE="$PARENT"
done

if [ -z "$BUNDLE_ROOT" ]; then
  PROBE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  while [ "$PROBE" != "/" ] && [ "$PROBE" != "." ]; do
    PARENT="$(dirname "$PROBE")"
    if [ -f "$PARENT/a-stock-agents/bundle.json" ]; then
      BUNDLE_ROOT="$PARENT/a-stock-agents"
      break
    fi
    if [ "$PARENT" = "$PROBE" ]; then break; fi
    PROBE="$PARENT"
  done
fi

if [ -z "$BUNDLE_ROOT" ]; then
  RECEIPT=""
  if [ -n "${A_STOCK_WORKSPACE_ROOT:-}" ] && [ -f "$A_STOCK_WORKSPACE_ROOT/install.json" ]; then
    RECEIPT="$A_STOCK_WORKSPACE_ROOT/install.json"
  elif [ -n "${LOCALAPPDATA:-}" ] && [ -f "$LOCALAPPDATA/a_stock_agents/install.json" ]; then
    RECEIPT="$LOCALAPPDATA/a_stock_agents/install.json"
  elif [ -f "$HOME/.local/share/a_stock_agents/install.json" ]; then
    RECEIPT="$HOME/.local/share/a_stock_agents/install.json"
  elif [ -f "$HOME/Library/Application Support/a_stock_agents/install.json" ]; then
    RECEIPT="$HOME/Library/Application Support/a_stock_agents/install.json"
  fi
  if [ -n "$RECEIPT" ]; then
    ROOT_FROM_RECEIPT=$(grep -o '"bundle_root"[[:space:]]*:[[:space:]]*"[^"]*"' "$RECEIPT" | head -n1 | cut -d'"' -f4 || true)
    if [ -z "$ROOT_FROM_RECEIPT" ]; then
      ROOT_FROM_RECEIPT=$(grep -o '"runtime_root"[[:space:]]*:[[:space:]]*"[^"]*"' "$RECEIPT" | head -n1 | cut -d'"' -f4 || true)
      if [ -n "$ROOT_FROM_RECEIPT" ]; then
        ROOT_FROM_RECEIPT="$(dirname "$ROOT_FROM_RECEIPT")"
      fi
    fi
    if [ -n "$ROOT_FROM_RECEIPT" ] && [ -f "$ROOT_FROM_RECEIPT/bundle.json" ]; then
      BUNDLE_ROOT="$ROOT_FROM_RECEIPT"
    fi
  fi
fi

if [ -z "$BUNDLE_ROOT" ]; then
  echo "错误: ANCHOR_SKILL_MISSING (未找到 bundle.json，需安装 a-stock-agents 锚点技能或完整总包)" >&2
  exit 1
fi

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
echo "  Windows: \"$BUNDLE_ROOT/runtime/astock.ps1\" debate 600519 --json"
echo "  Linux/macOS: \"$BUNDLE_ROOT/runtime/astock\" debate 600519 --json"
