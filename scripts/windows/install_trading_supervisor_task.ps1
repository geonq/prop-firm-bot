param(
    [string]$TaskName = "ORBTradingSupervisorWatchdog"
)
$ErrorActionPreference = "Stop"
$ScriptPath = (Resolve-Path (Join-Path $PSScriptRoot "watch_orbbot.ps1")).Path
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$Startup = New-ScheduledTaskTrigger -AtStartup
$Periodic = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($Startup, $Periodic) -Settings $Settings -Description "Recover the fail-closed ORB trading supervisor when desired mode is active." -Force | Out-Null
} catch [Microsoft.Management.Infrastructure.CimException] {
    # Non-elevated Windows sessions may be denied startup-trigger registration.
    # Install the essential per-user five-minute recovery task instead.
    $TaskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    & schtasks.exe /Create /TN $TaskName /TR $TaskCommand /SC MINUTE /MO 5 /RL LIMITED /F | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "schtasks fallback failed with exit code $LASTEXITCODE" }
}
Write-Host "Installed scheduled task: $TaskName"
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
