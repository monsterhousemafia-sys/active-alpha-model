# Register one-shot: run post_reboot_wsl.ps1 at next user logon (then remove itself).
$ErrorActionPreference = "Stop"
$Root = "E:\active_alpha_model"
$TaskName = "AAModel_WSL_PostReboot_Setup"
$Ps1 = Join-Path $Root "tools\post_reboot_wsl.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Ps1`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "OK: Task '$TaskName' runs post_reboot_wsl.ps1 at next logon."
Write-Host "Reboot now: shutdown /r /t 120 /c WSL-Reboot"
