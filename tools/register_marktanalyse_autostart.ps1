# Register Marktanalyse.exe for autostart at user logon (Task Scheduler + optional shortcut).
param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [string]$TaskName = "R3 Marktanalyse",
    [int]$DelaySeconds = 15
)

$ErrorActionPreference = "Stop"
$ExePath = (Resolve-Path -LiteralPath $ExePath).Path
$WorkDir = (Resolve-Path -LiteralPath $WorkDir).Path

$action = New-ScheduledTaskAction -Execute $ExePath -WorkingDirectory $WorkDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT${DelaySeconds}S"
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Output "Task registered: $TaskName (logon + ${DelaySeconds}s)"
