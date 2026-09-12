#!/usr/bin/env bash
# ==============================================================================
# a_stock_agents 一键启动脚本 (Linux / macOS / Windows Git Bash / WSL)
# ==============================================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

# 1. 跨平台探测 Python 解释器（按优先级匹配虚拟环境与系统 Python）
if [ -f "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PYTHON_EXEC="${PROJECT_ROOT}/.venv/bin/python"
elif [ -f "${PROJECT_ROOT}/.venv/Scripts/python.exe" ]; then
    PYTHON_EXEC="${PROJECT_ROOT}/.venv/Scripts/python.exe"
elif [ -f "${PROJECT_ROOT}/.venv/Scripts/python" ]; then
    PYTHON_EXEC="${PROJECT_ROOT}/.venv/Scripts/python"
elif [ -f "${PROJECT_ROOT}/.venv/bin/python.exe" ]; then
    PYTHON_EXEC="${PROJECT_ROOT}/.venv/bin/python.exe"
elif command -v python3 &> /dev/null; then
    PYTHON_EXEC="python3"
elif command -v python &> /dev/null; then
    PYTHON_EXEC="python"
elif command -v py &> /dev/null; then
    PYTHON_EXEC="py"
else
    echo "[错误] 未检测到可用的 Python 解释器。"
    echo "请先安装 Python 3.9+ 并执行一键部署: ./install.sh (Windows: .\\install.ps1)"
    exit 1
fi

# 2. 环境完整性提示
if [ ! -d "${PROJECT_ROOT}/.venv" ]; then
    echo "[提示] 未检测到 .venv 虚拟环境，建议先运行 ./install.sh 完成环境初始化。"
fi

# 3. 设置项目环境变量
export PYTHONPATH="${PROJECT_ROOT}/scripts:${PROJECT_ROOT}:${PYTHONPATH:-}"
export A_STOCK_AGENTS_ROOT="${PROJECT_ROOT}"

# 4. 显示欢迎横幅与访问入口
echo "======================================================================"
echo " [A-Stock Agents] 正在启动 A股全流程量化投研与智能体服务..."
echo " Web 智能工作台: http://127.0.0.1:6300"
echo " API 接口文档:   http://127.0.0.1:6300/docs"
echo " API 服务网关:   http://127.0.0.1:6300/api"
echo " 停止服务:       请按 Ctrl+C"
echo "======================================================================"

# 5. 执行服务端启动程序并透传所有外部参数 (如 --port, --host, --reload 等)
exec "${PYTHON_EXEC}" "${PROJECT_ROOT}/scripts/server/run.py" "$@"
