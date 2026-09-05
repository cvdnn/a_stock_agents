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

# 4. 工作区就地挂载与目录初始化
Write-Host "[4/5] 正在配置工作区就地挂载 (.agents\skills)..." -ForegroundColor Yellow
& $VenvPy core\workspace.py

# 5. 运行快速自检
Write-Host "----------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "[5/5] 运行全流程验证套件 (verify.py)..." -ForegroundColor Yellow
& $VenvPy verify.py

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " [成功] a_stock_agents 部署完成！" -ForegroundColor Green
Write-Host " 就地使用指引（零全局污染，开箱即用）：" -ForegroundColor Gray
Write-Host '   - Antigravity: 直接打开当前项目作为工作区，自动就地识别 17 项技能'
Write-Host '   - Hermes/Codex: 当前目录下直接调用 .\bin\astock.cmd <子命令> --json'
Write-Host '   - 运行 CLI:     .\bin\astock.cmd --help'
Write-Host '   - 查询行情:     .\bin\astock.cmd data quote 600519 --json'
Write-Host '   - 7大分析师辩论: .\bin\astock.cmd debate 600519 --json'
Write-Host '   - 技能清单:     .\bin\astock.cmd skill list --json'
Write-Host "======================================================================" -ForegroundColor Cyan
