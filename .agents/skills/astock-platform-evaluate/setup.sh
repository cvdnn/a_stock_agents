#!/bin/bash
# aStocks Skill 安装脚本
# 自动探测环境、生成配置、验证核心功能
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$SCRIPT_DIR"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "╔══════════════════════════════════════════════════╗"
echo "║  aStocks Skill 环境安装                           ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ─── 1. 检测 Python ────────────────────────────────
PYTHON=$(which python3 2>/dev/null || echo "")
if [ -z "$PYTHON" ]; then
    echo "❌ 需要 Python 3"
    exit 1
fi
PY_VER=$($PYTHON --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "  System Python: $($PYTHON --version)"

# ─── 2. 检测 a-share-data skill ──────────────────
A_SHARE_DATA="$PROJECT_ROOT/.agents/skills/astock-data-feed"
L1_ONLY=false
if [ -d "$A_SHARE_DATA" ]; then
    echo "  ✅ a-share-data skill: $A_SHARE_DATA"
else
    echo "  ⚠️  a-share-data skill 未找到"
    echo "      L2/L3/L4 降级不可用，仅 L1 腾讯直连模式"
    L1_ONLY=true
fi

# ─── 3. 检测/创建 venv ────────────────────────────
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PY=""
NEED_VENV_SETUP=false

# 优先使用环境变量
if [ -n "${ASTOCKS_VENV_PY:-}" ] && [ -f "$ASTOCKS_VENV_PY" ]; then
    VENV_PY="$ASTOCKS_VENV_PY"
    echo "  ✅ ASTOCKS_VENV_PY: $VENV_PY"
elif [ -f "$VENV_DIR/bin/python3" ]; then
    VENV_PY="$VENV_DIR/bin/python3"
    echo "  ✅ 已有专用 venv: $VENV_PY"
elif [ -f "python3" ]; then
    # 遗留 TACN venv (向后兼容)
    VENV_PY="python3"
    echo "  ⚠️  使用遗留 TACN venv: $VENV_PY"
    echo "     建议迁移到专用 venv: $VENV_DIR"
else
    echo "  📦 未检测到 venv，将创建专用环境..."
    NEED_VENV_SETUP=true
fi

# 创建专用 venv
if [ "$NEED_VENV_SETUP" = true ]; then
    echo "  创建 venv: $VENV_DIR ..."
    $PYTHON -m venv "$VENV_DIR"
    VENV_PY="$VENV_DIR/bin/python3"
    echo "  ✅ 创建完成: $VENV_PY"

    # 安装 L3/L4 增强依赖 (可选)
    echo ""
    echo "  安装 L3/L4 增强依赖 (可跳过)..."
    if "$VENV_PY" -m pip install --quiet akshare efinance 2>/dev/null; then
        echo "  ✅ akshare + efinance 安装成功"
    else
        echo "  ⚠️  增强依赖安装失败 (L3/L4 不可用，L1 仍正常)"
    fi
fi

# ─── 4. 生成 config.yaml ──────────────────────────
echo ""
echo "  生成配置..."

CONFIG_FILE="${ASTOCKS_CONFIG_FILE:-$PROJECT_ROOT/temp/setup/astock-platform-evaluate/config.yaml}"
mkdir -p "$(dirname "$CONFIG_FILE")"
A_SHARE_VAL="$A_SHARE_DATA"
if [ ! -d "$A_SHARE_DATA" ]; then
    A_SHARE_VAL=""
fi

cat > "$CONFIG_FILE" << YAMLEND
# aStocks 技能配置 (自动生成于 $(date -Iseconds))
# 环境变量覆盖: ASTOCKS_VENV_PY, ASTOCKS_SYSTEM_PY, ASTOCKS_A_SHARE_DATA_DIR

python:
  venv_python: "${VENV_PY}"
  system_python: "${PYTHON}"

data_fallback:
  L1_tencent_direct: true
  L2_sina_scripts: true
  L3_proxy_patch: false
  L4_efinance: false

strategy:
  combo:
    ma_structure_max: 25
    macd_max: 20
    volume_max: 15
    cyq_max: 15
    fund_flow_max: 15
    sector_max: 5
    pe_max: 5
    grade_a: 56
    grade_b: 49
    grade_c: 35
  entry:
    a_position: 0.35
    b_position: 0.20
    c_position: 0.0
  stop_loss:
    t0_intraday: -5.0
    t1_ma10: true
    t2_ma20: true

monitor:
  interval: "every 5m"
  delivery: "all"

skills:
  a_share_data: "${A_SHARE_VAL}"
  paper_trading: ""
  dashboard: ""
  trading_combo: ""

llm_analysis:
  enabled: true
  max_stocks_per_batch: 5
  risk_debate_enabled: true
YAMLEND

echo "  ✅ config.yaml 已生成"

# ─── 5. 快速测试 ──────────────────────────────────
echo ""
echo "─── 核心功能测试 ───"
echo ""

echo "  [1/2] 统一 CLI 行情检查 (600519)..."
"$PYTHON" "$PROJECT_ROOT/scripts/core/cli.py" data quote 600519 --json

echo "  [2/2] 统一 CLI 技术指标检查..."
"$PYTHON" "$PROJECT_ROOT/scripts/core/cli.py" data tech 600519 --count 60 --json

# ─── 6. 完成 ──────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  安装完成！                                       ║"
echo "║                                                  ║"
echo "║  环境变量 (可选):                                 ║"
echo "║    export ASTOCKS_VENV_PY=$VENV_PY"
echo "║                                                  ║"
echo "║  命令示例:                                        ║"
echo "║    $PYTHON $PROJECT_ROOT/scripts/core/cli.py data quote 600519 --json"
echo "║    $PYTHON $PROJECT_ROOT/scripts/core/cli.py score 600519 --json"
echo "║    $PYTHON $PROJECT_ROOT/scripts/core/cli.py evaluate 600519 --json"
echo "║                                                  ║"
if [ "$L1_ONLY" = true ]; then
echo "║  ⚠️  L2/L3 需要 a-share-data skill               ║"
fi
echo "╚══════════════════════════════════════════════════╝"
