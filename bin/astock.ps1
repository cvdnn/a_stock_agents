# ==============================================================================
# A-Stock Agents CLI Launcher for Windows PowerShell
# ==============================================================================
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path

# 优先探测 .venv 独立虚拟环境
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
    Write-Host "[错误] 未检测到可用的 Python 解释器。请先运行 .\install.ps1" -ForegroundColor Red
    exit 1
}

$env:PYTHONPATH = "$ProjectRoot\scripts;$ProjectRoot;$env:PYTHONPATH"
$env:A_STOCK_AGENTS_ROOT = $ProjectRoot

$CliPath = "$ProjectRoot\scripts\core\cli.py"
if (-not (Test-Path $CliPath)) {
    $CliPath = "$ProjectRoot\core\cli.py"
}

& $PythonExec $CliPath @args
