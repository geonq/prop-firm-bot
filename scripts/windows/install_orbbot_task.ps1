param([ValidateSet('paper', 'live')] [string]$Mode = 'paper')

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Script = Join-Path $PSScriptRoot 'run_orbbot.ps1'
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" -Mode $Mode -Auto"
$Triggers = @(
    # Germany-local dual trigger covers the CET/CEST to ET DST mismatch.
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 14:20,
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 15:20
)
Register-ScheduledTask -TaskName 'geonq-orbbot' -Action $Action -Trigger $Triggers -Description 'Frozen ORB paper/live runner' -Force
