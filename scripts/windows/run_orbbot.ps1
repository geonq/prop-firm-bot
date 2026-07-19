param(
    [ValidateSet('paper', 'live')] [string]$Mode = 'paper',
    [switch]$Auto
)

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root
& "$Root\.venv\Scripts\python.exe" -m src.live.runner --mode $Mode $(if ($Auto) { '--auto' })
exit $LASTEXITCODE
