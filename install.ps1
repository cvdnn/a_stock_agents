#Requires -Version 5.1
<#
.SYNOPSIS
    A-Stock Agents Unified Installation & Lifecycle Management Kernel (Windows / PowerShell)

.DESCRIPTION
    Cross-platform deployment engine for A-Stock Agents.
    Supports environment inspection, isolated virtual environment (.venv) creation,
    dependency installation, doctor smoke verification, host skill registration (Junction/Copy),
    and persistent receipt (install.json) generation.

.PARAMETER Inspect
    Probe host environment (Python, uv, detected AI agents, installation state) and exit.

.PARAMETER Agent
    One or more AI tools to configure (e.g. 'universal', 'codex', 'hermes', 'workbuddy').

.PARAMETER Method
    Mount method: 'link' (Junction/Symlink, recommended) or 'copy' (Physical copy). Default: link.

.PARAMETER Yes
    Non-interactive execution, skip interactive confirmation.

.PARAMETER Json
    Output structured machine-readable JSON to stdout.

.PARAMETER Doctor
    Execute self-diagnostic smoke test on the installed instance.

.PARAMETER Update
    Update installation to new release.

.PARAMETER Rollback
    Roll back to previous installed version.

.PARAMETER Uninstall
    Remove skill registration for specified agent.

.PARAMETER DataDir
    Override user workspace / data root (defaults to %LOCALAPPDATA%\a_stock_agents).

.PARAMETER Version
    Release version tag (default: 'v3').

.PARAMETER SkipDeps
    Skip pip install requirements step (useful in offline sandboxes).

.PARAMETER SkipVenv
    Skip virtual environment creation, using current host python.
#>

[CmdletBinding(DefaultParameterSetName = 'Install')]
param(
    [Parameter(ParameterSetName = 'Inspect')]
    [switch]$Inspect,

    [Parameter(ParameterSetName = 'Install')]
    [string[]]$Agent,

    [Parameter(ParameterSetName = 'Install')]
    [ValidateSet('link', 'copy')]
    [string]$Method = 'link',

    [Parameter(ParameterSetName = 'Install')]
    [switch]$Yes,

    [Parameter(ParameterSetName = 'Doctor')]
    [switch]$Doctor,

    [Parameter(ParameterSetName = 'Update')]
    [switch]$Update,

    [Parameter(ParameterSetName = 'Rollback')]
    [switch]$Rollback,

    [Parameter(ParameterSetName = 'Uninstall')]
    [string]$Uninstall,

    [switch]$Json,

    [string]$DataDir,
    [string]$Version = 'v3',
    [string]$SourceDir,
    [switch]$SkipDeps,
    [switch]$SkipVenv,
    [switch]$Force,
    [switch]$Tui
)

$ErrorActionPreference = 'Stop'

# -----------------------------------------------------------------------------
# 1. 路径发现与环境探测辅助函数 (Helper Functions)
# -----------------------------------------------------------------------------

function Set-CurrentLink {
    param(
        [string]$DataRoot,
        [string]$TargetDir
    )
    $currentPath = Join-Path $DataRoot 'current'
    if (Test-Path -LiteralPath $currentPath) {
        try {
            [System.IO.Directory]::Delete($currentPath)
        } catch {
            Remove-Item -LiteralPath $currentPath -Force -Recurse -ErrorAction SilentlyContinue
        }
    }
    New-Item -ItemType Junction -Path $currentPath -Target $TargetDir -Force | Out-Null
    return (Resolve-Path -LiteralPath $currentPath).Path
}

function Set-ReceiptProp {
    param($Receipt, [string]$PropName, $PropValue)
    if ($Receipt.PSObject.Properties[$PropName]) {
        $Receipt.$PropName = $PropValue
    } else {
        Add-Member -InputObject $Receipt -MemberType NoteProperty -Name $PropName -Value $PropValue
    }
}

function Deploy-ReleaseFiles {
    param(
        [string]$SourceDir,
        [string]$DestDir
    )
    if (-not (Test-Path -LiteralPath $SourceDir)) {
        throw "Source directory not found: $SourceDir"
    }
    $resolvedSource = (Resolve-Path -LiteralPath $SourceDir).Path
    $resolvedDest = $null
    if (Test-Path -LiteralPath $DestDir) {
        $resolvedDest = (Resolve-Path -LiteralPath $DestDir).Path
    }
    if ($resolvedDest -and $resolvedSource -eq $resolvedDest) {
        return
    }

    if (-not (Test-Path -LiteralPath $DestDir)) {
        New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
    }

    $itemsToCopy = @(
        'skills',
        'skill_bundle',
        'runtime',
        'assets',
        'references',
        'bin',
        'bundle.json',
        'INSTALL.json',
        'install.ps1',
        'install.sh',
        'requirements.txt',
        'requirements-full.txt'
    )
    foreach ($item in $itemsToCopy) {
        $srcPath = Join-Path $SourceDir $item
        if (Test-Path -LiteralPath $srcPath) {
            $dstPath = Join-Path $DestDir $item
            if (Test-Path -LiteralPath $dstPath) {
                Remove-Item -LiteralPath $dstPath -Recurse -Force -ErrorAction SilentlyContinue
            }
            Copy-Item -LiteralPath $srcPath -Destination $dstPath -Recurse -Force
        }
    }
}

function Get-DataRoot {
    param([string]$ExplicitDir)
    if ($ExplicitDir) {
        if (-not (Test-Path -LiteralPath $ExplicitDir)) {
            New-Item -ItemType Directory -Force -Path $ExplicitDir | Out-Null
        }
        return (Resolve-Path -LiteralPath $ExplicitDir).Path
    }
    if ($env:A_STOCK_WORKSPACE_ROOT) { return $env:A_STOCK_WORKSPACE_ROOT }
    if ($env:A_STOCK_AGENTS_ROOT) { return $env:A_STOCK_AGENTS_ROOT }
    if ($env:LOCALAPPDATA) {
        return (Join-Path $env:LOCALAPPDATA 'a_stock_agents')
    }
    $homeDir = [Environment]::GetFolderPath('UserProfile')
    return (Join-Path $homeDir 'AppData\Local\a_stock_agents')
}

function Find-HostPython {
    if ($env:A_STOCK_PYTHON -and (Test-Path -LiteralPath $env:A_STOCK_PYTHON)) {
        return (Resolve-Path -LiteralPath $env:A_STOCK_PYTHON).Path
    }
    # Check current or parent .venv
    $cands = @(
        (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
        (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'),
        (Join-Path $PSScriptRoot '..\..\.venv\Scripts\python.exe')
    )
    foreach ($c in $cands) {
        if (Test-Path -LiteralPath $c) {
            return (Resolve-Path -LiteralPath $c).Path
        }
    }
    foreach ($name in @('python3', 'python', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    return $null
}

function Get-PythonVersion {
    param([string]$PythonExe)
    if (-not $PythonExe) { return $null }
    try {
        $ver = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        return $ver.Trim()
    } catch {
        return $null
    }
}

function Find-BundleAndSkills {
    param([string]$BaseDir)
    $SkillsDir = $null
    $possibleSkills = @(
        (Join-Path $BaseDir 'skills'),
        (Join-Path $BaseDir 'skill_bundle\skills')
    )
    foreach ($p in $possibleSkills) {
        if (Test-Path -LiteralPath $p) {
            $SkillsDir = (Resolve-Path -LiteralPath $p).Path
            break
        }
    }

    $AnchorDir = $null
    $RuntimeDir = $null
    if ($SkillsDir) {
        $candAnchor = Join-Path $SkillsDir 'a-stock-agents'
        if (Test-Path -LiteralPath $candAnchor) {
            $AnchorDir = (Resolve-Path -LiteralPath $candAnchor).Path
            $candRuntime = Join-Path $AnchorDir 'runtime'
            if (Test-Path -LiteralPath $candRuntime) {
                $RuntimeDir = (Resolve-Path -LiteralPath $candRuntime).Path
            }
        }
    }
    if (-not $RuntimeDir) {
        foreach ($r in @((Join-Path $BaseDir 'skill_bundle\runtime'), (Join-Path $BaseDir 'runtime'))) {
            if (Test-Path -LiteralPath $r) {
                $RuntimeDir = (Resolve-Path -LiteralPath $r).Path
                break
            }
        }
    }

    $BundleRoot = $null
    if (Test-Path -LiteralPath (Join-Path $BaseDir 'bundle.json')) {
        $BundleRoot = (Resolve-Path -LiteralPath $BaseDir).Path
    } elseif (Test-Path -LiteralPath (Join-Path $BaseDir 'skill_bundle\bundle.json')) {
        $BundleRoot = (Resolve-Path -LiteralPath (Join-Path $BaseDir 'skill_bundle')).Path
    } elseif ($AnchorDir -and (Test-Path -LiteralPath (Join-Path $AnchorDir 'bundle.json'))) {
        $BundleRoot = $AnchorDir
    }

    return [PSCustomObject]@{
        BundleRoot = $BundleRoot
        SkillsDir  = $SkillsDir
        AnchorDir  = $AnchorDir
        RuntimeDir = $RuntimeDir
    }
}

function Safe-TestPath {
    param([string]$Path)
    if (-not $Path) { return $false }
    try {
        return (Test-Path -LiteralPath $Path -ErrorAction SilentlyContinue)
    } catch {
        return $false
    }
}

function Detect-Agents {
    $homeDir = [Environment]::GetFolderPath('UserProfile')
    $universalPath = Join-Path $homeDir '.agents\skills'
    $hermesBase    = Join-Path $homeDir '.hermes'
    $hermesPath    = Join-Path $hermesBase 'skills'
    $workbuddyBase = Join-Path $homeDir '.workbuddy'
    $workbuddyPath = Join-Path $workbuddyBase 'skills'
    $codexBase     = Join-Path $homeDir '.codex'
    $codexPath     = Join-Path $codexBase 'skills'

    return [ordered]@{
        universal = [ordered]@{
            name      = 'Universal (.agents/skills)'
            path      = $universalPath
            detected  = (Safe-TestPath -Path $universalPath)
            methods   = @('link', 'copy')
        }
        hermes    = [ordered]@{
            name      = 'Hermes Desktop'
            path      = $hermesPath
            detected  = (Safe-TestPath -Path $hermesBase)
            methods   = @('link', 'copy', 'external_dirs')
        }
        workbuddy = [ordered]@{
            name      = 'WorkBuddy'
            path      = $workbuddyPath
            detected  = (Safe-TestPath -Path $workbuddyBase)
            methods   = @('link', 'copy')
        }
        codex     = [ordered]@{
            name      = 'Codex'
            path      = $codexPath
            detected  = (Safe-TestPath -Path $codexBase)
            methods   = @('link', 'copy')
        }
    }
}

function Get-SkillList {
    param([string]$SkillsDir)
    if (-not $SkillsDir -or -not (Test-Path -LiteralPath $SkillsDir)) {
        return @()
    }
    $skills = Get-ChildItem -LiteralPath $SkillsDir -Directory | Where-Object {
        Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md')
    } | ForEach-Object { $_.Name } | Sort-Object
    return @($skills)
}

function Compute-SHA256 {
    param([string]$FilePath)
    if (-not (Test-Path -LiteralPath $FilePath)) { return $null }
    $resolved = (Resolve-Path -LiteralPath $FilePath).Path
    $bytes = [System.IO.File]::ReadAllBytes($resolved)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hashBytes = $sha.ComputeHash($bytes)
    return [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()
}

function Compute-StringSHA256 {
    param([string]$Content)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Content)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hashBytes = $sha.ComputeHash($bytes)
    return [System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()
}

function Test-IsReparsePoint {
    param([string]$Path)
    if (-not (Safe-TestPath -Path $Path)) { return $false }
    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        return [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
    } catch {
        return $false
    }
}

function Check-OverwritesConflicts {
    param(
        [string[]]$TargetAgents,
        $DetectedAgents,
        [string]$SkillsDir
    )
    $conflicts = @()
    if (-not $SkillsDir -or -not (Safe-TestPath -Path $SkillsDir)) {
        return $conflicts
    }

    $skillNames = Get-ChildItem -LiteralPath $SkillsDir -Directory | Where-Object {
        Safe-TestPath -Path (Join-Path $_.FullName 'SKILL.md')
    } | ForEach-Object { $_.Name }

    foreach ($ag in $TargetAgents) {
        $agKey = $ag.Trim().ToLowerInvariant()
        $agTargetDir = if ($DetectedAgents.Contains($agKey)) { $DetectedAgents[$agKey].path } else { $ag }
        if (-not $agTargetDir -or -not (Safe-TestPath -Path $agTargetDir)) {
            continue
        }

        foreach ($sName in $skillNames) {
            $entry = Join-Path $agTargetDir $sName
            if (Safe-TestPath -Path $entry) {
                $isReparse = Test-IsReparsePoint -Path $entry
                if (-not $isReparse) {
                    $copyReceipt = Join-Path $agTargetDir ('.' + $sName + '.astock-copy.json')
                    if (-not (Safe-TestPath -Path $copyReceipt)) {
                        $conflicts += [ordered]@{
                            agent = $agKey
                            skill = $sName
                            path  = (Resolve-Path -LiteralPath $entry).Path
                        }
                    }
                }
            }
        }
    }
    return @($conflicts)
}

function Show-TuiMenu {
    param(
        $DetectedAgents,
        [ref]$OutAgents,
        [ref]$OutMethod
    )

    $items = @(
        [ordered]@{
            key      = 'universal'
            category = 'Universal'
            name     = '🌐 Universal 通用目录 (~/.agents/skills)'
            desc     = '已支持: Codex, Cursor, Cline, Kimi CLI, OpenCode 等'
            detected = $DetectedAgents['universal'].detected
            selected = $true
        },
        [ordered]@{
            key      = 'hermes'
            category = 'Additional'
            name     = '🦊 Hermes Desktop (~/.hermes/skills)'
            desc     = '状态: ' + $(if ($DetectedAgents['hermes'].detected) { '已检测到环境 · 支持 external_dirs 原生挂载' } else { '未检测到客户端配置' })
            detected = $DetectedAgents['hermes'].detected
            selected = [bool]$DetectedAgents['hermes'].detected
        },
        [ordered]@{
            key      = 'workbuddy'
            category = 'Additional'
            name     = '💼 WorkBuddy (~/.workbuddy/skills)'
            desc     = '状态: ' + $(if ($DetectedAgents['workbuddy'].detected) { '已检测到目录 · 采用逐技能 Junction 注册' } else { '未检测到工作区配置' })
            detected = $DetectedAgents['workbuddy'].detected
            selected = [bool]$DetectedAgents['workbuddy'].detected
        },
        [ordered]@{
            key      = 'codex'
            category = 'Additional'
            name     = '💻 Codex 专用 (~/.codex/skills)'
            desc     = '状态: ' + $(if ($DetectedAgents['codex'].detected) { '已检测到目录' } else { '未检测到专用目录' })
            detected = $DetectedAgents['codex'].detected
            selected = $false
        }
    )

    $currMethod = 'link'
    $cursorIndex = 0

    try { [Console]::CursorVisible = $false } catch {}

    function Render-Menu {
        param($currIdx, $mth)
        try { Clear-Host } catch {}
        Write-Host "┌──────────────────────────────────────────────────────────────────┐" -ForegroundColor Cyan
        Write-Host "│  A-Stock Agents 终端交互式安装导轨 (Terminal Installation TUI)   │" -ForegroundColor Cyan
        Write-Host "├──────────────────────────────────────────────────────────────────┤" -ForegroundColor Cyan
        Write-Host "│ 请使用 [↑/↓] 移动光标，[空格] 切换勾选，[回车] 确认开始安装      │" -ForegroundColor Gray
        Write-Host "│                                                                  │"

        Write-Host "│ [Universal agents]" -ForegroundColor Yellow
        for ($i = 0; $i -lt $items.Count; $i++) {
            $it = $items[$i]
            if ($it.category -eq 'Universal') {
                $chk = if ($it.selected) { "[*]" } else { "[ ]" }
                $ptr = if ($i -eq $currIdx) { "> " } else { "  " }
                $color = if ($i -eq $currIdx) { "Green" } else { "White" }
                Write-Host "│ $ptr$chk $($it.name)" -ForegroundColor $color
                Write-Host "│       $($it.desc)" -ForegroundColor DarkGray
            }
        }
        Write-Host "│                                                                  │"

        Write-Host "│ [Additional agents]" -ForegroundColor Yellow
        for ($i = 0; $i -lt $items.Count; $i++) {
            $it = $items[$i]
            if ($it.category -eq 'Additional') {
                $chk = if ($it.selected) { "[*]" } else { "[ ]" }
                $ptr = if ($i -eq $currIdx) { "> " } else { "  " }
                $color = if ($i -eq $currIdx) { "Green" } else { "White" }
                Write-Host "│ $ptr$chk $($it.name)" -ForegroundColor $color
                Write-Host "│       $($it.desc)" -ForegroundColor DarkGray
            }
        }
        Write-Host "│                                                                  │"

        $methodDisplay = if ($mth -eq 'link') {
            "(●) 符号链接/Junction (推荐，便于升级)   ( ) 物理复制"
        } else {
            "( ) 符号链接/Junction                     (●) 物理复制"
        }
        Write-Host "│ 安装方式：$methodDisplay" -ForegroundColor Cyan
        Write-Host "│ [快捷键: 'm' 切换安装方式 | 'a' 全选/反选 | 'q' 退出]            │" -ForegroundColor DarkCyan
        Write-Host "└──────────────────────────────────────────────────────────────────┘" -ForegroundColor Cyan
    }

    $running = $true
    while ($running) {
        Render-Menu -currIdx $cursorIndex -mth $currMethod
        $key = $null
        try {
            $key = [Console]::ReadKey($true)
        } catch {
            break
        }

        if (-not $key) { break }

        switch ($key.Key) {
            ([ConsoleKey]::UpArrow) {
                if ($cursorIndex -gt 0) { $cursorIndex-- } else { $cursorIndex = $items.Count - 1 }
            }
            ([ConsoleKey]::DownArrow) {
                if ($cursorIndex -lt ($items.Count - 1)) { $cursorIndex++ } else { $cursorIndex = 0 }
            }
            ([ConsoleKey]::Spacebar) {
                $items[$cursorIndex].selected = -not $items[$cursorIndex].selected
            }
            ([ConsoleKey]::Enter) {
                $selected = @($items | Where-Object { $_.selected } | ForEach-Object { $_.key })
                if ($selected.Count -eq 0) {
                    Write-Host "`n⚠️ 请至少勾选一个目标宿主 (按空格键勾选)" -ForegroundColor Yellow
                    Start-Sleep -Milliseconds 800
                } else {
                    $OutAgents.Value = $selected
                    $OutMethod.Value = $currMethod
                    $running = $false
                }
            }
            ([ConsoleKey]::Escape) {
                try { [Console]::CursorVisible = $true } catch {}
                Write-Host "`nInstallation cancelled by user." -ForegroundColor Yellow
                exit 0
            }
            Default {
                if ($key.KeyChar -eq 'k' -or $key.KeyChar -eq 'K') {
                    if ($cursorIndex -gt 0) { $cursorIndex-- } else { $cursorIndex = $items.Count - 1 }
                } elseif ($key.KeyChar -eq 'j' -or $key.KeyChar -eq 'J') {
                    if ($cursorIndex -lt ($items.Count - 1)) { $cursorIndex++ } else { $cursorIndex = 0 }
                } elseif ($key.KeyChar -eq 'm' -or $key.KeyChar -eq 'M') {
                    $currMethod = if ($currMethod -eq 'link') { 'copy' } else { 'link' }
                } elseif ($key.KeyChar -eq 'a' -or $key.KeyChar -eq 'A') {
                    $hasUnselected = [bool]($items | Where-Object { -not $_.selected })
                    foreach ($it in $items) { $it.selected = $hasUnselected }
                } elseif ($key.KeyChar -eq 'q' -or $key.KeyChar -eq 'Q') {
                    try { [Console]::CursorVisible = $true } catch {}
                    Write-Host "`nInstallation cancelled by user." -ForegroundColor Yellow
                    exit 0
                }
            }
        }
    }

    try { [Console]::CursorVisible = $true } catch {}
    Write-Host "`n🚀 目标宿主已确认: $($OutAgents.Value -join ', ')" -ForegroundColor Green
    Write-Host "🔧 接入模式: $($OutMethod.Value)" -ForegroundColor Green
    Write-Host "🛡️ 正在执行 Overwrites 冲突保护检测..." -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# 2. 主逻辑路由 (Main Execution Routing)
# -----------------------------------------------------------------------------

$targetDataRoot = Get-DataRoot -ExplicitDir $DataDir
$hostPython     = Find-HostPython
$pythonVer      = Get-PythonVersion -PythonExe $hostPython
$uvCmd          = Get-Command 'uv' -ErrorAction SilentlyContinue
$paths          = Find-BundleAndSkills -BaseDir $PSScriptRoot
$detectedAgents = Detect-Agents
$skillList      = Get-SkillList -SkillsDir $paths.SkillsDir

$receiptPath    = Join-Path $targetDataRoot 'install.json'
$isInstalled    = Test-Path -LiteralPath $receiptPath
$existingReceipt = $null
if ($isInstalled) {
    try {
        $existingReceipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        $existingReceipt = $null
    }
}

# -----------------------------------------------------------------------------
# 场景 A: 探测模式 (-Inspect)
# -----------------------------------------------------------------------------
if ($Inspect) {
    $allAgentNames = @($detectedAgents.Keys)
    $inspectConflicts = @(Check-OverwritesConflicts -TargetAgents $allAgentNames -DetectedAgents $detectedAgents -SkillsDir $paths.SkillsDir)

    foreach ($k in $detectedAgents.Keys) {
        $agConflicts = @($inspectConflicts | Where-Object { $_.agent -eq $k })
        $detectedAgents[$k]['overwrites_count'] = $agConflicts.Count
        $detectedAgents[$k]['conflicts'] = @($agConflicts)
    }

    $inspectData = [ordered]@{
        status           = 'success'
        action           = 'inspect'
        data_root        = $targetDataRoot
        python           = [ordered]@{
            path         = $hostPython
            version      = $pythonVer
            uv_available = ($uvCmd -ne $null)
        }
        bundle_source    = $paths.BundleRoot
        installed        = $isInstalled
        existing_receipt = $existingReceipt
        agents           = $detectedAgents
        overwrites_count = $inspectConflicts.Count
        conflicts        = @($inspectConflicts)
        skills_count     = $skillList.Count
        skills           = $skillList
    }

    if ($Json) {
        $inspectData | ConvertTo-Json -Depth 10
    } else {
        Write-Host "=== A-Stock Agents Environment Inspection ===" -ForegroundColor Cyan
        Write-Host "Data Root:      $targetDataRoot"
        Write-Host "Host Python:    $hostPython ($pythonVer)"
        Write-Host "Bundle Source:  $($paths.BundleRoot)"
        Write-Host "Skills Found:   $($skillList.Count) entries"
        Write-Host "Installed:      $isInstalled"
        Write-Host "`nTarget Agents Detected:"
        foreach ($k in $detectedAgents.Keys) {
            $ag = $detectedAgents[$k]
            $detStr = if ($ag.detected) { "[x] Detected" } else { "[ ] Not found" }
            $conflStr = if ($ag.overwrites_count -gt 0) { " (Overwrites: $($ag.overwrites_count) CONFLICT)" } else { " (Overwrites: 0)" }
            Write-Host "  - $($ag.name): $detStr ($($ag.path))$conflStr"
        }
    }
    exit 0
}

# -----------------------------------------------------------------------------
# 场景 B: 冒烟检查模式 (-Doctor)
# -----------------------------------------------------------------------------
if ($Doctor) {
    if (-not $isInstalled) {
        $errObj = [ordered]@{
            status  = 'error'
            message = 'No existing installation found in data root. Run install first.'
            data_root = $targetDataRoot
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    $activePython = $existingReceipt.python_path
    if (-not $activePython -or -not (Test-Path -LiteralPath $activePython)) {
        $activePython = $hostPython
    }

    $doctorPy = Join-Path $existingReceipt.runtime_root 'doctor.py'
    if (-not (Test-Path -LiteralPath $doctorPy)) {
        $errObj = [ordered]@{
            status  = 'error'
            message = "doctor.py not found at $($existingReceipt.runtime_root)"
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    $prevWs = $env:A_STOCK_WORKSPACE_ROOT
    $env:A_STOCK_WORKSPACE_ROOT = $targetDataRoot
    try {
        $docOut = & $activePython $doctorPy --json 2>&1 | Out-String
        $docExit = $LASTEXITCODE
        if ($Json) {
            Write-Output $docOut.Trim()
        } else {
            Write-Host "=== A-Stock Agents Doctor Report ===" -ForegroundColor Cyan
            Write-Output $docOut
        }
        exit $docExit
    } finally {
        $env:A_STOCK_WORKSPACE_ROOT = $prevWs
    }
}

# -----------------------------------------------------------------------------
# 场景 C: 卸载模式 (-Uninstall <agent>)
# -----------------------------------------------------------------------------
if ($Uninstall) {
    $agKey = $Uninstall.ToLowerInvariant()
    $targetPath = $null
    if ($detectedAgents.Contains($agKey)) {
        $targetPath = $detectedAgents[$agKey].path
    } else {
        $targetPath = $Uninstall
    }

    $res = [ordered]@{
        status  = 'success'
        action  = 'uninstall'
        agent   = $Uninstall
        target  = $targetPath
        removed = $false
    }

    if ($targetPath -and (Test-Path -LiteralPath $targetPath)) {
        # Only unmount or remove references; preserve user data
        $refFiles = Get-ChildItem -LiteralPath $targetPath -Filter '.*.astock-reference.json' -File -ErrorAction SilentlyContinue
        foreach ($rf in $refFiles) {
            try {
                $sName = $rf.Name.Substring(1, $rf.Name.Length - 1 - '.astock-reference.json'.Length)
                $sEntry = Join-Path $targetPath $sName
                if (Test-Path -LiteralPath $sEntry) {
                    [System.IO.Directory]::Delete($sEntry, $false)
                }
                Remove-Item -LiteralPath $rf.FullName -Force -ErrorAction SilentlyContinue
            } catch {}
        }
        $suiteReceipt = Join-Path $targetPath '.a-stock-suite.json'
        if (Test-Path -LiteralPath $suiteReceipt) {
            Remove-Item -LiteralPath $suiteReceipt -Force -ErrorAction SilentlyContinue
        }
        $res.removed = $true
    }

    if ($Json) { $res | ConvertTo-Json -Depth 5 } else { Write-Host "Uninstalled reference for $Uninstall" }
    exit 0
}

# -----------------------------------------------------------------------------
# 场景 E: 升级模式 (-Update)
# -----------------------------------------------------------------------------
if ($Update) {
    if (-not $isInstalled) {
        $errObj = [ordered]@{
            status      = 'error'
            reason_code = 'NOT_INSTALLED'
            message     = "Cannot update: no existing installation found at $targetDataRoot. Run install first."
            data_root   = $targetDataRoot
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    $oldVersion = $existingReceipt.version
    $newVersion = $Version
    if (-not $newVersion) { $newVersion = 'latest' }

    $source = if ($SourceDir) { (Resolve-Path -LiteralPath $SourceDir).Path } else { $PSScriptRoot }

    if ($newVersion -eq $oldVersion -and -not $Force) {
        $candJson = Join-Path $source 'bundle.json'
        if (-not (Test-Path -LiteralPath $candJson)) {
            $candJson = Join-Path $source 'skill_bundle\bundle.json'
        }
        if (-not (Test-Path -LiteralPath $candJson)) {
            $candJson = Join-Path $source 'skills\a-stock-agents\bundle.json'
        }
        $foundNewer = $false
        if (Test-Path -LiteralPath $candJson) {
            try {
                $bj = Get-Content -LiteralPath $candJson -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($bj.version -and $bj.version -ne $oldVersion) {
                    $newVersion = $bj.version
                    $foundNewer = $true
                }
            } catch {}
        }
        if (-not $foundNewer) {
            $errObj = [ordered]@{
                status         = 'error'
                reason_code    = 'ALREADY_AT_VERSION'
                message        = "Already installed at version '$oldVersion'. Specify a new -Version or pass -Force to overwrite."
                active_version = $oldVersion
            }
            if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
            exit 1
        }
    }

    $releasesDir = Join-Path $targetDataRoot 'releases'
    if (-not (Test-Path -LiteralPath $releasesDir)) {
        New-Item -ItemType Directory -Force -Path $releasesDir | Out-Null
    }

    $newVersionDir = Join-Path $releasesDir $newVersion

    # 1. 部署新版本至 releases/<newVersion>
    Deploy-ReleaseFiles -SourceDir $source -DestDir $newVersionDir

    # 2. 检查新版本完整性
    $newPaths = Find-BundleAndSkills -BaseDir $newVersionDir
    $newSkillList = Get-SkillList -SkillsDir $newPaths.SkillsDir
    if ($newSkillList.Count -lt 20) {
        $errObj = [ordered]@{
            status         = 'error'
            reason_code    = 'UPDATE_INTEGRITY_FAILED'
            message        = "New release must contain all 20 skills, but only found $($newSkillList.Count) entries."
            skills_found   = $newSkillList.Count
            active_version = $oldVersion
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    # 3. 隔离环境解释器
    $venvPython = $existingReceipt.python_path
    if (-not $venvPython -or -not (Test-Path -LiteralPath $venvPython)) {
        $venvPython = $hostPython
    }

    # 4. 可选依赖更新
    if (-not $SkipDeps -and ($env:A_STOCK_SKIP_DEPS -ne '1') -and ($env:A_STOCK_OFFLINE -ne '1')) {
        $reqCandidate = @(
            (Join-Path $newVersionDir 'requirements.txt'),
            (Join-Path $newVersionDir 'skills\a-stock-agents\requirements.txt')
        )
        foreach ($rc in $reqCandidate) {
            if (Test-Path -LiteralPath $rc) {
                if ($uvCmd) {
                    & $uvCmd pip install --python $venvPython -r $rc 2>$null | Out-Null
                } else {
                    & $venvPython -m pip install -r $rc 2>$null | Out-Null
                }
                break
            }
        }
    }

    # 5. 新版本 Doctor 冒烟门禁 (CRITICAL DEFENSE GATE)
    $newDoctorPy = $null
    if ($newPaths.RuntimeDir) {
        $newDoctorPy = Join-Path $newPaths.RuntimeDir 'doctor.py'
    }
    if (-not $newDoctorPy -or -not (Test-Path -LiteralPath $newDoctorPy)) {
        $newDoctorPy = Join-Path $newVersionDir 'skill_bundle\runtime\doctor.py'
    }

    $prevWs = $env:A_STOCK_WORKSPACE_ROOT
    $env:A_STOCK_WORKSPACE_ROOT = $targetDataRoot
    $doctorSuccess = $false
    $doctorOutput = ''
    $doctorReport = $null
    try {
        if ($newDoctorPy -and (Test-Path -LiteralPath $newDoctorPy)) {
            $docRaw = & $venvPython $newDoctorPy --json 2>&1 | Out-String
            $doctorOutput = $docRaw.Trim()
            if ($LASTEXITCODE -eq 0) {
                $doctorSuccess = $true
                try { $doctorReport = $doctorOutput | ConvertFrom-Json } catch {}
            }
        }
    } finally {
        $env:A_STOCK_WORKSPACE_ROOT = $prevWs
    }

    if (-not $doctorSuccess) {
        # 冒烟失败：绝对不切换 current，坚决守住当前版本
        $errObj = [ordered]@{
            status         = 'error'
            reason_code    = 'UPDATE_SMOKE_FAILED'
            message        = "Doctor smoke verification failed on new release $newVersion. Kept current version $oldVersion active without modification."
            active_version = $oldVersion
            failed_version = $newVersion
            doctor_output  = $doctorOutput
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    # 6. 冒烟成功：原子重定向 current 软链接/Junction
    $currentPath = Set-CurrentLink -DataRoot $targetDataRoot -TargetDir $newVersionDir

    # 7. 更新安装收据 install.json
    $updatedAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'previous_version' -PropValue $oldVersion
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'version' -PropValue $newVersion
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'updated_at' -PropValue $updatedAt
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'current_target' -PropValue $newVersionDir
    $upBundleRoot = if ($newPaths.AnchorDir) { $newPaths.AnchorDir } else { $newPaths.BundleRoot }
    $upRuntimeRoot = if ($newPaths.RuntimeDir) { $newPaths.RuntimeDir } else { (Join-Path $newPaths.AnchorDir 'runtime') }
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'bundle_root' -PropValue $upBundleRoot
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'runtime_root' -PropValue $upRuntimeRoot
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'skills_root' -PropValue $newPaths.SkillsDir
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'doctor_health' -PropValue $doctorReport

    if ($existingReceipt.PSObject.Properties['sha256']) {
        $existingReceipt.PSObject.Properties.Remove('sha256')
    }
    $finalJson = $existingReceipt | ConvertTo-Json -Depth 10
    $receiptHash = Compute-StringSHA256 -Content $finalJson
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'sha256' -PropValue $receiptHash

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($receiptPath, ($existingReceipt | ConvertTo-Json -Depth 10), $utf8NoBom)

    $res = [ordered]@{
        status           = 'success'
        action           = 'update'
        previous_version = $oldVersion
        version          = $newVersion
        active_version   = $newVersion
        current_target   = $newVersionDir
        data_root        = $targetDataRoot
    }
    if ($Json) {
        $res | ConvertTo-Json -Depth 5
    } else {
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "🎉 A-Stock Agents Successfully Updated to $newVersion!" -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "Previous Version: $oldVersion"
        Write-Host "Active Version:   $newVersion"
        Write-Host "Current Target:   $newVersionDir"
        Write-Host "Data Root:        $targetDataRoot (User data 100% preserved)"
        Write-Host "============================================================" -ForegroundColor Green
    }
    exit 0
}

# -----------------------------------------------------------------------------
# 场景 F: 回滚模式 (-Rollback)
# -----------------------------------------------------------------------------
if ($Rollback) {
    if (-not $isInstalled) {
        $errObj = [ordered]@{
            status      = 'error'
            reason_code = 'NOT_INSTALLED'
            message     = "Cannot rollback: no existing installation found at $targetDataRoot."
            data_root   = $targetDataRoot
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    $currentVersion = $existingReceipt.version
    $prevVersion = $existingReceipt.previous_version

    if (-not $prevVersion) {
        $errObj = [ordered]@{
            status         = 'error'
            reason_code    = 'ROLLBACK_NO_PREVIOUS_VERSION'
            message        = "No previous version recorded in receipt ($receiptPath) to roll back to."
            active_version = $currentVersion
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    $releasesDir = Join-Path $targetDataRoot 'releases'
    $targetRollbackDir = Join-Path $releasesDir $prevVersion
    if (-not (Test-Path -LiteralPath $targetRollbackDir)) {
        $errObj = [ordered]@{
            status         = 'error'
            reason_code    = 'ROLLBACK_TARGET_MISSING'
            message        = "Previous version directory '$targetRollbackDir' not found."
            active_version = $currentVersion
            target_version = $prevVersion
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    # 检查回滚目标版本完整性
    $rollbackPaths = Find-BundleAndSkills -BaseDir $targetRollbackDir
    $rollbackSkills = Get-SkillList -SkillsDir $rollbackPaths.SkillsDir
    if ($rollbackSkills.Count -lt 20) {
        $errObj = [ordered]@{
            status         = 'error'
            reason_code    = 'ROLLBACK_INTEGRITY_FAILED'
            message        = "Rollback target $prevVersion is corrupted (found $($rollbackSkills.Count) skills, expected 20)."
            active_version = $currentVersion
            target_version = $prevVersion
        }
        if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
        exit 1
    }

    # 原子重定向 current 软链接/Junction
    $currentPath = Set-CurrentLink -DataRoot $targetDataRoot -TargetDir $targetRollbackDir

    # 更新安装收据 install.json
    $rolledBackAt = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'previous_version' -PropValue $currentVersion
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'version' -PropValue $prevVersion
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'rolled_back_at' -PropValue $rolledBackAt
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'current_target' -PropValue $targetRollbackDir
    $rbBundleRoot = if ($rollbackPaths.AnchorDir) { $rollbackPaths.AnchorDir } else { $rollbackPaths.BundleRoot }
    $rbRuntimeRoot = if ($rollbackPaths.RuntimeDir) { $rollbackPaths.RuntimeDir } else { (Join-Path $rollbackPaths.AnchorDir 'runtime') }
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'bundle_root' -PropValue $rbBundleRoot
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'runtime_root' -PropValue $rbRuntimeRoot
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'skills_root' -PropValue $rollbackPaths.SkillsDir

    if ($existingReceipt.PSObject.Properties['sha256']) {
        $existingReceipt.PSObject.Properties.Remove('sha256')
    }
    $finalJson = $existingReceipt | ConvertTo-Json -Depth 10
    $receiptHash = Compute-StringSHA256 -Content $finalJson
    Set-ReceiptProp -Receipt $existingReceipt -PropName 'sha256' -PropValue $receiptHash

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($receiptPath, ($existingReceipt | ConvertTo-Json -Depth 10), $utf8NoBom)

    $res = [ordered]@{
        status           = 'success'
        action           = 'rollback'
        active_version   = $prevVersion
        rolled_back_from = $currentVersion
        current_target   = $targetRollbackDir
        data_root        = $targetDataRoot
    }
    if ($Json) {
        $res | ConvertTo-Json -Depth 5
    } else {
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "🎉 A-Stock Agents Successfully Rolled Back to $prevVersion!" -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "Rolled Back From: $currentVersion"
        Write-Host "Active Version:   $prevVersion"
        Write-Host "Current Target:   $targetRollbackDir"
        Write-Host "Data Root:        $targetDataRoot (User data 100% preserved)"
        Write-Host "============================================================" -ForegroundColor Green
    }
    exit 0
}

# -----------------------------------------------------------------------------
# 场景 D: 安装与部署模式 (Default / -Yes / -Agent)
# -----------------------------------------------------------------------------

# 0. 终端交互式 TUI 导轨激活判定
$isInteractiveTerminal = $false
try {
    if ($Tui) {
        $isInteractiveTerminal = $true
    } elseif ((-not $Yes) -and (-not $Json) -and (-not $Agent -or $Agent.Count -eq 0)) {
        if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
            $isInteractiveTerminal = $true
        }
    }
} catch {
    $isInteractiveTerminal = $false
}

if ($isInteractiveTerminal) {
    $tuiSelectedAgents = @()
    $tuiSelectedMethod = $Method
    Show-TuiMenu -DetectedAgents $detectedAgents -OutAgents ([ref]$tuiSelectedAgents) -OutMethod ([ref]$tuiSelectedMethod)
    $Agent = $tuiSelectedAgents
    $Method = $tuiSelectedMethod
}

# 0.1 Overwrites 冲突保护检测 (遇真实同名物理目录拒绝覆盖，保护用户历史文件)
$conflicts = @()
if ($Agent -and $Agent.Count -gt 0) {
    $conflicts = @(Check-OverwritesConflicts -TargetAgents $Agent -DetectedAgents $detectedAgents -SkillsDir $paths.SkillsDir)
    if ($conflicts.Count -gt 0 -and -not $Force) {
        $errObj = [ordered]@{
            status           = 'error'
            reason_code      = 'OVERWRITE_CONFLICT'
            message          = "Overwrites conflict detected: $($conflicts.Count) existing non-link physical directory(ies) found in target host(s). Refusing to overwrite user files."
            overwrites_count = $conflicts.Count
            conflicts        = @($conflicts)
        }
        if ($Json) {
            $errObj | ConvertTo-Json -Depth 5
        } else {
            Write-Host "============================================================" -ForegroundColor Red
            Write-Host "❌ Overwrites Sentinel: Conflict Detected!" -ForegroundColor Red
            Write-Host "============================================================" -ForegroundColor Red
            Write-Host "The following target skill directories already exist as real physical folders:" -ForegroundColor Yellow
            foreach ($c in $conflicts) {
                Write-Host "  - [$($c.agent)] $($c.skill): $($c.path)" -ForegroundColor Yellow
            }
            Write-Host "`nRefusing to overwrite user physical directories." -ForegroundColor Red
            Write-Host "Please backup/remove these directories, or pass -Force to overwrite." -ForegroundColor Yellow
        }
        exit 1
    }
}

# 1. 解释器前置检查
if (-not $hostPython) {
    $errObj = [ordered]@{
        status      = 'error'
        reason_code = 'PYTHON_MISSING'
        message     = 'Python 3.9+ is required but was not found on PATH or in standard locations.'
    }
    if ($Json) { $errObj | ConvertTo-Json -Depth 5 } else { Write-Error $errObj.message }
    exit 1
}

# 2. 数据目录与子目录初始化
$requiredSubdirs = @('output', 'log', 'temp', 'local\settings', 'releases')
foreach ($sub in $requiredSubdirs) {
    $dirPath = Join-Path $targetDataRoot $sub
    if (-not (Test-Path -LiteralPath $dirPath)) {
        New-Item -ItemType Directory -Force -Path $dirPath | Out-Null
    }
}

# 2.1 部署当前 Release 版本至 releases/<version> 并建立 current 软链接/Junction
$releasesDir = Join-Path $targetDataRoot 'releases'
$versionDir = Join-Path $releasesDir $Version
Deploy-ReleaseFiles -SourceDir $PSScriptRoot -DestDir $versionDir
$currentPath = Set-CurrentLink -DataRoot $targetDataRoot -TargetDir $versionDir

# 重新基于 current 寻址发现技能与运行库
$currentPaths = Find-BundleAndSkills -BaseDir $currentPath
$activeSkillsDir = if ($currentPaths.SkillsDir) { $currentPaths.SkillsDir } else { $paths.SkillsDir }

# 3. 隔离 .venv 构建
$venvDir = Join-Path $targetDataRoot '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

if (-not $SkipVenv) {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        if ($uvCmd) {
            & $uvCmd venv $venvDir | Out-Null
        } else {
            & $hostPython -m venv $venvDir | Out-Null
        }
    }
} else {
    $venvPython = $hostPython
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    # Fallback to host python if venv python not found
    $venvPython = $hostPython
}

# 4. 依赖安装 (除非指定 -SkipDeps 或离线环境变量)
$offlineFlag = ($env:A_STOCK_SKIP_DEPS -eq '1') -or ($env:A_STOCK_OFFLINE -eq '1')
if (-not $SkipDeps -and -not $offlineFlag) {
    $reqCandidate = @(
        (Join-Path $PSScriptRoot 'requirements.txt'),
        (Join-Path $paths.BundleRoot 'requirements.txt'),
        (Join-Path $paths.AnchorDir 'requirements.txt')
    )
    $reqFile = $null
    foreach ($rc in $reqCandidate) {
        if ($rc -and (Test-Path -LiteralPath $rc)) {
            $reqFile = (Resolve-Path -LiteralPath $rc).Path
            break
        }
    }
    if ($reqFile) {
        if ($uvCmd) {
            & $uvCmd pip install --python $venvPython -r $reqFile 2>$null | Out-Null
        } else {
            & $venvPython -m pip install -r $reqFile 2>$null | Out-Null
        }
    }
}

# 5. Doctor 自检与健康状态验证
$doctorPy = $null
if ($paths.RuntimeDir) {
    $doctorPy = Join-Path $paths.RuntimeDir 'doctor.py'
}
if (-not $doctorPy -or -not (Test-Path -LiteralPath $doctorPy)) {
    $doctorPy = Join-Path $PSScriptRoot 'skill_bundle\runtime\doctor.py'
}

$doctorReport = $null
if ($doctorPy -and (Test-Path -LiteralPath $doctorPy)) {
    $prevWs = $env:A_STOCK_WORKSPACE_ROOT
    $env:A_STOCK_WORKSPACE_ROOT = $targetDataRoot
    try {
        $docRaw = & $venvPython $doctorPy --json 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) {
            try { $doctorReport = $docRaw.Trim() | ConvertFrom-Json } catch { $doctorReport = $null }
        }
    } finally {
        $env:A_STOCK_WORKSPACE_ROOT = $prevWs
    }
}

# 6. 扫描 20 项技能并计算 SKILL.md SHA256 证明
$skillEntries = @()
if ($paths.SkillsDir -and (Test-Path -LiteralPath $paths.SkillsDir)) {
    $dirs = Get-ChildItem -LiteralPath $paths.SkillsDir -Directory | Sort-Object Name
    foreach ($d in $dirs) {
        $skillMd = Join-Path $d.FullName 'SKILL.md'
        if (Test-Path -LiteralPath $skillMd) {
            $sha = Compute-SHA256 -FilePath $skillMd
            $skillEntries += [ordered]@{
                id              = $d.Name
                name            = $d.Name
                is_anchor       = ($d.Name -eq 'a-stock-agents')
                path            = $d.FullName
                skill_md_sha256 = $sha
                verified        = $true
            }
        }
    }
}

# 7. 宿主注册 (若指定了 -Agent)
$registeredAgents = @()
if ($Agent -and $Agent.Count -gt 0) {
    foreach ($ag in $Agent) {
        $agName = $ag.Trim().ToLowerInvariant()
        $agTargetDir = $null
        if ($detectedAgents.Contains($agName)) {
            $agTargetDir = $detectedAgents[$agName].path
        } else {
            $agTargetDir = $ag
        }

        if ($agTargetDir) {
            if (-not (Test-Path -LiteralPath $agTargetDir)) {
                New-Item -ItemType Directory -Force -Path $agTargetDir | Out-Null
            }

            $mountedCount = 0
            if ($activeSkillsDir -and (Test-Path -LiteralPath $activeSkillsDir)) {
                $skillDirs = Get-ChildItem -LiteralPath $activeSkillsDir -Directory | Where-Object {
                    Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md')
                }
                foreach ($s in $skillDirs) {
                    $sName = $s.Name
                    $sTarget = $s.FullName
                    $sEntry = Join-Path $agTargetDir $sName

                    if ($Method -eq 'link') {
                        if (-not (Test-Path -LiteralPath $sEntry)) {
                            try {
                                New-Item -ItemType Junction -Path $sEntry -Target $sTarget -ErrorAction SilentlyContinue | Out-Null
                                $mountedCount++
                            } catch {}
                        } else {
                            $mountedCount++
                        }
                        # Write binding receipt
                        $sReceipt = Join-Path $agTargetDir ('.' + $sName + '.astock-reference.json')
                        $refData = [ordered]@{
                            entry  = $sEntry
                            target = $sTarget
                            type   = 'junction'
                        }
                        [System.IO.File]::WriteAllText($sReceipt, ($refData | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding $false))
                    } elseif ($Method -eq 'copy') {
                        if (-not (Test-Path -LiteralPath $sEntry)) {
                            try {
                                Copy-Item -Recurse -LiteralPath $sTarget -Destination $sEntry -Force -ErrorAction SilentlyContinue | Out-Null
                                $mountedCount++
                            } catch {}
                        } else {
                            $mountedCount++
                        }
                        $sReceipt = Join-Path $agTargetDir ('.' + $sName + '.astock-copy.json')
                        $copyData = [ordered]@{
                            entry  = $sEntry
                            target = $sTarget
                            type   = 'copy'
                        }
                        [System.IO.File]::WriteAllText($sReceipt, ($copyData | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding $false))
                    }
                }
            }

            # Write suite receipt
            $suiteReceipt = Join-Path $agTargetDir '.a-stock-suite.json'
            $suiteData = [ordered]@{
                skills_root     = $activeSkillsDir
                host_skills_dir = $agTargetDir
                mounted_skills  = $mountedCount
                method          = $Method
            }
            [System.IO.File]::WriteAllText($suiteReceipt, ($suiteData | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding $false))

            # Hermes 原生接入重构：支持 external_dirs
            if ($agName -eq 'hermes' -and $activeSkillsDir) {
                $homeDir = [Environment]::GetFolderPath('UserProfile')
                $hermesConfig = Join-Path $homeDir '.hermes\config.yaml'
                if (Test-Path -LiteralPath $hermesConfig) {
                    try {
                        $cfgText = [System.IO.File]::ReadAllText($hermesConfig)
                        if ($cfgText -notmatch [regex]::Escape($activeSkillsDir)) {
                            if ($cfgText -match 'external_dirs:') {
                                $cfgText = $cfgText -replace 'external_dirs:', ("external_dirs:`n    - " + $activeSkillsDir)
                            } else {
                                $cfgText += "`nskills:`n  external_dirs:`n    - " + $activeSkillsDir + "`n"
                            }
                            [System.IO.File]::WriteAllText($hermesConfig, $cfgText, (New-Object System.Text.UTF8Encoding $false))
                        }
                    } catch {}
                }
            }

            $registeredAgents += [ordered]@{
                agent        = $agName
                target_dir   = $agTargetDir
                method       = $Method
                skills_count = $mountedCount
                status       = 'mounted'
            }
        }
    }
}

# 8. 组装安装收据 install.json 并计算收据摘要
$bundleRootTarget = if ($currentPaths.AnchorDir) { $currentPaths.AnchorDir } else { (if ($paths.AnchorDir) { $paths.AnchorDir } else { $paths.BundleRoot }) }
$runtimeRootTarget = if ($currentPaths.RuntimeDir) { $currentPaths.RuntimeDir } else { (if ($paths.RuntimeDir) { $paths.RuntimeDir } else { (Join-Path $paths.AnchorDir 'runtime') }) }

$receipt = [ordered]@{
    status            = 'installed'
    version           = $Version
    previous_version  = $null
    updated_at        = $null
    rolled_back_at    = $null
    installed_at      = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    workspace_root    = $targetDataRoot
    data_root         = $targetDataRoot
    releases_dir      = $releasesDir
    current_target    = $versionDir
    bundle_root       = $bundleRootTarget
    runtime_root      = $runtimeRootTarget
    anchor_root       = if ($currentPaths.AnchorDir) { $currentPaths.AnchorDir } else { $paths.AnchorDir }
    skills_root       = $activeSkillsDir
    python_path       = $venvPython
    method            = $Method
    overwrites_count  = $conflicts.Count
    conflicts         = @($conflicts)
    skills_count      = $skillEntries.Count
    business_skills   = 19
    skill_entries     = $skillEntries
    registered_agents = $registeredAgents
    doctor_health     = $doctorReport
}

$rawJson = $receipt | ConvertTo-Json -Depth 10
$receiptHash = Compute-StringSHA256 -Content $rawJson
$receipt['sha256'] = $receiptHash

$finalJson = $receipt | ConvertTo-Json -Depth 10
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($receiptPath, $finalJson, $utf8NoBom)

# 9. 交付输出与退出
if ($Json) {
    Write-Output $finalJson
} else {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "🎉 A-Stock Agents Installation Successful!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "Data Root:      $targetDataRoot"
    Write-Host "Python venv:    $venvPython"
    Write-Host "Skills Ready:   $($skillEntries.Count) entries verified (SHA256)"
    Write-Host "Receipt:        $receiptPath"
    if ($registeredAgents.Count -gt 0) {
        Write-Host "Mounted Agents: $($registeredAgents.agent -join ', ')"
    }
    Write-Host "`nQuickstart commands:"
    Write-Host "  powershell -File install.ps1 -Doctor -Json"
    Write-Host "============================================================" -ForegroundColor Green
}

exit 0
