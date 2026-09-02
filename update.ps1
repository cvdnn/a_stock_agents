# ==============================================================================
# a_stock_agents 安全升级脚本 (Windows PowerShell)
# ==============================================================================
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PyBin = "py"
if (Test-Path ".venv\Scripts\python.exe") {
    $PyBin = ".venv\Scripts\python.exe"
}

& $PyBin bin\update.py $args
