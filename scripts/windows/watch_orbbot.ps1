$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ControlDir = Join-Path $RepoRoot "LiveState\control"
$LogDir = Join-Path $RepoRoot "LiveState"
$Log = Join-Path $LogDir "supervisor_watchdog.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue

if (-not (Test-Path $Python)) {
    "$(Get-Date -Format o) trading Python missing: $Python" | Add-Content $Log
    exit 1
}

Push-Location $RepoRoot
try {
    $Raw = & $Python -m src.ops.cli --state-dir $ControlDir status 2>&1
    $Receipt = ($Raw | Select-Object -Last 1) | ConvertFrom-Json
    if ($Receipt.state -eq "stopped" -or $Receipt.supervisor_alive) {
        exit 0
    }
    $StartRaw = & $Python -m src.ops.cli --state-dir $ControlDir start --mode $Receipt.state --actor "windows-watchdog" 2>&1
    "$(Get-Date -Format o) $($StartRaw -join ' ')" | Add-Content $Log
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
