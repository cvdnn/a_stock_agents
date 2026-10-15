param([Parameter(Mandatory=$true)][string]$Target, [Parameter(Mandatory=$true)][string]$Entry)
$ErrorActionPreference = 'Stop'
if ($Target.StartsWith('\\')) { throw 'Junction target must be a local directory' }
if (Test-Path -LiteralPath $Entry) { throw 'Entry already exists' }
New-Item -ItemType Junction -Path $Entry -Target $Target | Out-Null
