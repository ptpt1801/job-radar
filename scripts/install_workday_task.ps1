# Register (or update) the Windows scheduled task that runs scripts\run_workday_local.ps1.
# Runs as the current user, only while logged on (no password stored). Remove with:
#   Unregister-ScheduledTask -TaskName "JobRadar Workday" -Confirm:$false
$script = Join-Path $PSScriptRoot "run_workday_local.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$triggers = @((New-ScheduledTaskTrigger -Daily -At 8:00am), (New-ScheduledTaskTrigger -Daily -At 8:00pm))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "JobRadar Workday" -Action $action -Trigger $triggers -Settings $settings `
    -Description "Job Radar: refresh Workday jobs from this PC and push to GitHub (Workday blocks GitHub runners)." -Force | Out-Null
Get-ScheduledTask -TaskName "JobRadar Workday" | Select-Object TaskName, State
