#!/usr/bin/env bash
# a-share-data 技能安装脚本
# 用法: bash setup.sh                        # 交互式（选择 Python 环境）
# 用法: bash setup.sh /path/to/venv/bin/python3  # 指定 Python 路径
#
# 安装完成后，编辑 scripts/config.yaml 配置 TOKEN

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REQUIREMENTS="$SKILL_DIR/requirements.txt"
CONFIG_TEMPLATE="$SKILL_DIR/scripts/config.yaml"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  a-share-data 技能安装脚本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# ── 选择 Python ──
if [ $# -ge 1 ]; then
    PYTHON="$1"
    echo -e "${YELLOW}使用指定 Python: ${PYTHON}${NC}"
else
    echo "选择 Python 环境:"
    echo "  1) 系统 Python (python3)"
    echo "  2) 虚拟环境 (venv)"
    echo "  3) 手动输入路径"
    read -p "请输入 [1/2/3] (默认 1): " choice
    choice="${choice:-1}"

    case "$choice" in
        1) PYTHON="python3" ;;
        2)
            if [ -d ".venv" ]; then
                PYTHON="$(pwd)/.venv/bin/python3"
            elif [ -d "../.venv" ]; then
                PYTHON="$(cd .. && pwd)/.venv/bin/python3"
            else
                echo -e "${RED}未找到 .venv，请手动输入路径${NC}"
                read -p "Python 路径: " PYTHON
            fi
            ;;
        3)
            read -p "Python 路径: " PYTHON
            ;;
    esac
fi

# 验证 Python
if ! "$PYTHON" --version &>/dev/null; then
    echo -e "${RED}错误: Python 不可用: $PYTHON${NC}"
    exit 1
fi
PYVER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}✓ Python $PYVER: $PYTHON${NC}"

# ── 检查 Python 版本 ──
PYMAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PYMINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 9 ]; }; then
    echo -e "${RED}错误: 需要 Python >= 3.9 (当前: $PYVER)${NC}"
    exit 1
fi
if [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -eq 9 ]; then
    echo -e "${YELLOW}⚠ 注意: Python 3.9 可能有 numpy C 扩展兼容问题，推荐 Python >= 3.10${NC}"
fi

# ── 安装依赖 ──
echo ""
echo -e "${YELLOW}安装依赖...${NC}"
"$PYTHON" -m pip install -r "$REQUIREMENTS" -q 2>&1 | tail -3
echo -e "${GREEN}✓ 依赖安装完成${NC}"

# ── 更新 config.yaml 中的 Python 路径 ──
CONFIG_FILE="$SKILL_DIR/scripts/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    # 计算相对于 config.yaml 的 Python 路径
    ABS_PYTHON=$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|venv_python:.*|venv_python: \"$ABS_PYTHON\"|" "$CONFIG_FILE"
    else
        sed -i "s|venv_python:.*|venv_python: \"$ABS_PYTHON\"|" "$CONFIG_FILE"
    fi
    echo -e "${GREEN}✓ config.yaml 已更新 Python 路径: $ABS_PYTHON${NC}"
fi

# ── 提示配置 TOKEN ──
echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  下一步：配置 TOKEN${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo "编辑配置文件:"
echo "  nano $CONFIG_FILE"
echo ""
echo "将 proxy_patch.auth_token 替换为你的 TOKEN"
echo "获取地址: https://ak.cheapproxy.net/dashboard/akshare"
echo ""
echo "配置完成后，验证安装:"
echo "  $PYTHON -c \"from _init_patch import patched_akshare as ak; print('Patch OK')\""
echo ""
echo -e "${GREEN}安装完成！${NC}"