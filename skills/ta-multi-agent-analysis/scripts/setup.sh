#!/bin/bash
# ta-multi-agent-analysis 安装脚本
# 安装 TradingAgents-astock 依赖、配置 .env、验证连通性。
#
# Usage:
#   bash setup.sh                     # 交互式安装
#   bash setup.sh --provider minimax  # 指定 LLM 供应商
#   bash setup.sh --check             # 仅检查已有安装

set -e

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${VENV_PY:-python3}"

# ── 检测已有项目 ──────────────────────────────────────────────────────────────

TA_PROJECT=""
for p in "/mnt/c/Users/user/coding/TradingAgents" \
         "/mnt/c/Users/user/coding/TradingAgents/_original_src" \
         "$HOME/TradingAgents-astock"; do
    if [ -d "$p/tradingagents" ]; then
        TA_PROJECT="$p"
        break
    fi
done

# ── 参数解析 ──────────────────────────────────────────────────────────────────

CHECK_MODE=false
PROVIDER=""
while [ $# -gt 0 ]; do
    case "$1" in
        --check) CHECK_MODE=true; shift ;;
        --provider) PROVIDER="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# ── 检查模式 ──────────────────────────────────────────────────────────────────

if $CHECK_MODE; then
    echo "═══ ta-multi-agent-analysis 安装检查 ═══"
    echo ""
    echo "[1/5] TradingAgents 项目"
    if [ -n "$TA_PROJECT" ]; then
        echo "  ✅ 找到: $TA_PROJECT"
    else
        echo "  ❌ 未找到"
    fi

    echo "[2/5] tradingagents 模块"
    if [ -n "$TA_PROJECT" ] && python3 -c "import tradingagents" 2>/dev/null; then
        echo "  ✅ Python 可导入"
    else
        echo "  ❌ 不可导入（需 pip install -e .）"
    fi

    echo "[3/5] .env 文件"
    ENV_FILE=""
    [ -f "/mnt/c/Users/user/coding/TradingAgents/.env" ] && ENV_FILE="/mnt/c/Users/user/coding/TradingAgents/.env"
    [ -f "/mnt/c/Users/user/coding/TradingAgents/_original_src/.env" ] && ENV_FILE="/mnt/c/Users/user/coding/TradingAgents/_original_src/.env"
    [ -f "$HOME/TradingAgents-astock/.env" ] && ENV_FILE="$HOME/TradingAgents-astock/.env"
    if [ -n "$ENV_FILE" ]; then
        KEY_COUNT=$(grep -c '_API_KEY\|_AUTH_TOKEN' "$ENV_FILE" 2>/dev/null || echo 0)
        echo "  ✅ $ENV_FILE（$KEY_COUNT 个 key 变量）"
    else
        echo "  ❌ 未找到 .env（LLM API 无法调用）"
    fi

    echo "[4/5] a-share-paper-trading"
    if curl -s http://127.0.0.1:18765/health > /dev/null 2>&1; then
        echo "  ✅ 服务运行中（端口 18765）"
    else
        echo "  ⚠️  未启动（Phase 3 需要）"
    fi

    echo "[5/5] AI-Platform cron"
    if command -v AI-Platform &> /dev/null && AI-Platform cron status 2>/dev/null | grep -q "Gateway"; then
        echo "  ✅ AI-Platform cron 可用"
    else
        echo "  ⚠️  cron 未配置（Phase 3 监控部署需要）"
    fi

    echo ""
    if [ -n "$TA_PROJECT" ] && [ -f "$ENV_FILE" ]; then
        echo "结论: ✅ 就绪，可以使用 ta_analyze.py"
    else
        echo "结论: ⚠️  部分依赖缺失，请继续完整安装"
    fi
    exit 0
fi

# ── 完整安装 ──────────────────────────────────────────────────────────────────

echo "═══ ta-multi-agent-analysis 安装 ═══"
echo ""

# Step 1: 克隆/检测 TradingAgents-astock
echo "[1/5] TradingAgents 项目"
if [ -n "$TA_PROJECT" ]; then
    echo "  ✅ 已存在: $TA_PROJECT"
else
    TA_PROJECT="$HOME/TradingAgents-astock"
    echo "  → 克隆到 $TA_PROJECT"
    git clone https://github.com/simonlin1212/TradingAgents-astock.git "$TA_PROJECT"
fi

# Step 2: 安装 Python 依赖
echo ""
echo "[2/5] Python 依赖"
cd "$TA_PROJECT"
if [ -f "pyproject.toml" ]; then
    echo "  → pip install -e ."
    $VENV_PY -m pip install -e . 2>&1 | tail -3
    echo "  ✅ 依赖安装完成"
else
    echo "  → pip install -r requirements.txt"
    $VENV_PY -m pip install -r requirements.txt 2>&1 | tail -3
    echo "  ✅ 依赖安装完成"
fi

# Step 3: 配置 .env
echo ""
echo "[3/5] LLM API Key 配置"
ENV_FILE="$TA_PROJECT/.env"
if [ -f "$ENV_FILE" ]; then
    echo "  ✅ .env 已存在: $ENV_FILE"
else
    if [ -z "$PROVIDER" ]; then
        echo "  请选择 LLM 供应商:"
        echo "    1) MiniMax（推荐，国内直连，性价比高）"
        echo "    2) DeepSeek"
        echo "    3) 通义千问 Qwen"
        echo "    4) 智谱 GLM"
        echo "    5) 稍后手动配置"
        read -p "  选择 [1]: " choice
        choice="${choice:-1}"
        case $choice in
            1) PROVIDER="minimax"; KEY_VAR="MINIMAX_API_KEY" ;;
            2) PROVIDER="deepseek"; KEY_VAR="DEEPSEEK_API_KEY" ;;
            3) PROVIDER="qwen"; KEY_VAR="DASHSCOPE_API_KEY" ;;
            4) PROVIDER="glm"; KEY_VAR="ZHIPU_API_KEY" ;;
            *) PROVIDER=""; KEY_VAR="" ;;
        esac
    fi

    if [ -n "$PROVIDER" ] && [ -n "$KEY_VAR" ]; then
        read -p "  输入 $KEY_VAR: " api_key
        cat > "$ENV_FILE" << EOF
# TradingAgents-astock LLM 配置
# 供应商: $PROVIDER
$KEY_VAR=$api_key
EOF
        echo "  ✅ .env 已创建: $ENV_FILE"
    else
        echo "  ⚠️  跳过 .env 配置，请稍后手动创建"
    fi
fi

# Step 4: 验证
echo ""
echo "[4/5] 验证安装"
if $VENV_PY -c "import tradingagents; print('tradingagents:', tradingagents.__file__)" 2>/dev/null; then
    echo "  ✅ tradingagents 模块可导入"
else
    echo "  ⚠️  tradingagents 不可导入，尝试安装..."
    cd "$TA_PROJECT"
    $VENV_PY -m pip install -e . 2>&1 | tail -3
fi

# Step 5: 测试运行
echo ""
echo "[5/5] 快速测试"
echo "  → 尝试分析 600519（茅台），仅 Phase 1..."
$VENV_PY "$SKILL_DIR/scripts/ta_analyze.py" 600519 --phase 1 --pre-score --brief 2>&1 | head -20

echo ""
echo "═══ 安装完成 ═══"
echo ""
echo "  快速验证:"
echo "    $VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600519 --phase 2 --brief"
echo "    $VENV_PY $SKILL_DIR/scripts/ta_analyze.py 600760 --phase 2 --paper-trade --deploy-monitor"
echo ""
echo "  查看完整文档:"
echo "    skill_view(name='ta-multi-agent-analysis')"
