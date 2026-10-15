$ErrorActionPreference = 'Stop'
$PythonExec = $env:A_STOCK_PYTHON
if (-not $PythonExec) {
    $TaskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
    $Candidate = Join-Path $TaskRoot '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $Candidate) { $PythonExec = $Candidate }
    else {
        foreach ($Name in @('python3', 'python', 'py')) {
            if (Get-Command $Name -ErrorAction SilentlyContinue) { $PythonExec = $Name; break }
        }
    }
}
if (-not $PythonExec) { throw 'Python 3.9+ required' }
& $PythonExec (Join-Path $PSScriptRoot 'manage.py') setup @args
exit $LASTEXITCODE
