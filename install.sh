#!/usr/bin/env bash
# ==============================================================================
# a_stock_agents 一键安装与环境部署脚本 (Linux / macOS)
# ==============================================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

echo "======================================================================"
echo " [A-Stock Agents] 正在部署 A股全流程智能体与量化投研体系..."
echo " 项目目录: ${PROJECT_ROOT}"
echo "======================================================================"

# 1. 检查 Python 解释器
if command -v python3 &> /dev/null; then
    PY_BIN="python3"
elif command -v python &> /dev/null; then
    PY_BIN="python"
else
    echo "[错误] 未检测到 Python 解释器，请先安装 Python 3.9 及以上版本。"
    exit 1
fi

PY_VER=$($PY_BIN -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[1/4] 检测到 Python 版本: ${PY_VER}"

# 2. 创建或更新独立虚拟环境
if [ ! -d ".venv" ]; then
    echo "[2/4] 创建独立 Python 虚拟环境 (.venv)..."
    $PY_BIN -m venv .venv
else
    echo "[2/4] 复用现有虚拟环境 (.venv)..."
fi

VENV_PY="${PROJECT_ROOT}/.venv/bin/python"
VENV_PIP="${PROJECT_ROOT}/.venv/bin/pip"

# 3. 安装依赖
echo "[3/4] 安装项目核心量化与分析依赖 (requirements.txt)..."
"${VENV_PIP}" install --upgrade pip -q
"${VENV_PIP}" install -r requirements.txt -q

# 4. 设置执行权限与工作区就地挂载
echo "[4/5] 设置执行权限与工作区就地挂载 (.agents/skills)..."
chmod +x bin/astock || true
chmod +x install.sh || true

"${VENV_PY}" core/workspace.py

# 5. 运行快速自检
echo "----------------------------------------------------------------------"
echo "[5/5] 运行全流程验证套件 (verify.py)..."
"${VENV_PY}" verify.py

echo "======================================================================"
echo " [成功] a_stock_agents 部署完成！"
echo " 就地使用指引（零全局污染，开箱即用）："
echo "   - Antigravity: 直接打开当前项目作为工作区，自动就地挂载 17 项技能"
echo "   - Hermes/Codex: 当前目录下直接调用 ./bin/astock <subcommand> --json"
echo "   - 实时行情:     ./bin/astock data quote 600519 --json"
echo "   - 7大分析师辩论: ./bin/astock debate 600519 --json"
echo "   - 技能清单:     ./bin/astock skill list --json"
echo "======================================================================"
