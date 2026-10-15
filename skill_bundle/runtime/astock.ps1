$ErrorActionPreference = 'Stop'
$RuntimeRoot = $PSScriptRoot
$BundleRoot = Split-Path -Parent $RuntimeRoot
$WorkspaceRoot = if ($env:A_STOCK_WORKSPACE_ROOT) { $env:A_STOCK_WORKSPACE_ROOT } elseif ($env:A_STOCK_AGENTS_ROOT) { $env:A_STOCK_AGENTS_ROOT } else { Split-Path -Parent $BundleRoot }
$PythonExec = $env:A_STOCK_PYTHON
if (-not $PythonExec) {
    $Candidates = @((Join-Path $WorkspaceRoot '.venv/Scripts/python.exe'), (Join-Path $WorkspaceRoot '.venv/bin/python'))
    foreach ($Candidate in $Candidates) { if (Test-Path -LiteralPath $Candidate) { $PythonExec = $Candidate; break } }
}
if (-not $PythonExec) {
    foreach ($Name in @('python3', 'python', 'py')) { if (Get-Command $Name -ErrorAction SilentlyContinue) { $PythonExec = $Name; break } }
}
if (-not $PythonExec) { throw 'Python 3.9+ required; initialize the workspace environment' }
$env:PYTHONPATH = "$RuntimeRoot;$env:PYTHONPATH"
& $PythonExec (Join-Path $RuntimeRoot 'cli.py') @args
exit $LASTEXITCODE
