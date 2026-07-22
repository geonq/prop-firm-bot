$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Output = Join-Path $RepoRoot "LiveState\reports\operational-latest.md"
Push-Location $RepoRoot
try {
    & $Python -m src.reporting.operational --state-dir (Join-Path $RepoRoot "LiveState") --control-dir (Join-Path $RepoRoot "LiveState\control") --output $Output
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
