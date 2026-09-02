# ==============================================================================
# a_stock_agents 一键安装与环境部署脚本 (Windows PowerShell)
# ==============================================================================
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " [A-Stock Agents] 正在部署 A股全流程智能体与量化投研体系..." -ForegroundColor Cyan
Write-Host " 项目目录: $ProjectRoot" -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. 检查 Python 解释器
$PyBin = "py"
try {
    $ver = & py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
} catch {
    $PyBin = "python"
    try {
        $ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    } catch {
        Write-Error "[错误] 未检测到 Python 解释器，请先安装 Python 3.9 及以上版本。"
        exit 1
    }
}
Write-Host "[1/4] 检测到 Python 版本: $ver" -ForegroundColor Green

# 2. 创建或更新独立虚拟环境
if (-not (Test-Path ".venv")) {
    Write-Host "[2/4] 创建独立 Python 虚拟环境 (.venv)..." -ForegroundColor Yellow
    & $PyBin -m venv .venv
} else {
    Write-Host "[2/4] 复用现有虚拟环境 (.venv)..." -ForegroundColor Green
}

$VenvPy = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvPip = Join-Path $ProjectRoot ".venv\Scripts\pip.exe"

# 3. 安装依赖
Write-Host "[3/4] 安装项目核心量化与分析依赖 (requirements.txt)..." -ForegroundColor Yellow
& $VenvPip install --upgrade pip -q
& $VenvPip install -r requirements.txt -q

# 4. 初始化目录
New-Item -ItemType Directory -Force -Path "data\pools", "data\positions", "cache", "reports" | Out-Null

# 5. 运行快速自检
Write-Host "----------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "[自检] 运行验证套件 (verify.py)..." -ForegroundColor Yellow
& $VenvPy verify.py

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " [成功] a_stock_agents 部署完成！" -ForegroundColor Green
Write-Host " 使用方法："
Write-Host "   - 运行 CLI:   .instock.cmd --help"
Write-Host "   - 查询行情:   .instock.cmd data quote sh600519"
Write-Host "   - 技能清单:   .instock.cmd skill list"
Write-Host "======================================================================" -ForegroundColor Cyan
