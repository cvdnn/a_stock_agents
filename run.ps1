# ==============================================================================
# a_stock_agents 一键启动脚本 (Windows PowerShell 优先)
# ==============================================================================
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

# 1. 跨平台探测 Python 解释器（优先匹配独立虚拟环境）
$PythonExec = $null
if (Test-Path "$ProjectRoot\.venv\Scripts\python.exe") {
    $PythonExec = "$ProjectRoot\.venv\Scripts\python.exe"
} elseif (Test-Path "$ProjectRoot\.venv\bin\python.exe") {
    $PythonExec = "$ProjectRoot\.venv\bin\python.exe"
} elseif (Test-Path "$ProjectRoot\.venv\bin\python") {
    $PythonExec = "$ProjectRoot\.venv\bin\python"
} elseif (Get-Command "py" -ErrorAction SilentlyContinue) {
    $PythonExec = "py"
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    $PythonExec = "python"
} elseif (Get-Command "python3" -ErrorAction SilentlyContinue) {
    $PythonExec = "python3"
} else {
    Write-Host "[错误] 未检测到可用的 Python 解释器。" -ForegroundColor Red
    Write-Host "请先安装 Python 3.9+ 并执行一键部署: .\install.ps1" -ForegroundColor Yellow
    exit 1
}

# 2. 虚拟环境就绪性提示
if (-not (Test-Path "$ProjectRoot\.venv")) {
    Write-Host "[提示] 未检测到 .venv 虚拟环境，建议先运行 .\install.ps1 完成环境初始化。" -ForegroundColor Yellow
}

# 3. 设置项目环境变量
$env:PYTHONPATH = "$ProjectRoot\scripts;$ProjectRoot;$env:PYTHONPATH"
$env:A_STOCK_AGENTS_ROOT = $ProjectRoot

# 4. 显示欢迎横幅与服务入口
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " [A-Stock Agents] 正在启动 A股全流程量化投研与智能体服务 (PowerShell)..." -ForegroundColor Green
Write-Host " Web 智能工作台: http://127.0.0.1:6300" -ForegroundColor White
Write-Host " API 接口文档:   http://127.0.0.1:6300/docs" -ForegroundColor White
Write-Host " API 服务网关:   http://127.0.0.1:6300/api" -ForegroundColor White
Write-Host " 停止服务:       请按 Ctrl+C" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan

# 5. 启动服务端并透传所有外部参数 (如 --port, --host, --reload 等)
& $PythonExec "$ProjectRoot\scripts\server\run.py" @args
