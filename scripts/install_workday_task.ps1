# Register (or update) the Windows scheduled task that runs scripts\run_workday_local.ps1.
# Runs as the current user, only while logged on (no password stored). Remove with:
#   Unregister-ScheduledTask -TaskName "JobRadar Workday" -Confirm:$false
$script = Join-Path $PSScriptRoot "run_workday_local.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$triggers = @((New-ScheduledTaskTrigger -Daily -At 8:00am), (New-ScheduledTaskTrigger -Daily -At 8:00pm))
# Catch-up: 10 min after logon and every 2 hours, run only if no successful run in the last 11 hours (-IfStale).
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = "PT10M"
$every2h = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(30) -RepetitionInterval (New-TimeSpan -Hours 2)
$actionStale = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -IfStale"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "JobRadar Workday" -Action $action -Trigger $triggers -Settings $settings `
    -Description "Job Radar: refresh Workday jobs from this PC and push to GitHub (Workday blocks GitHub runners)." -Force | Out-Null
Register-ScheduledTask -TaskName "JobRadar Workday (catch-up)" -Action $actionStale -Trigger @($logon, $every2h) -Settings $settings `
    -Description "Job Radar: after logon and every 2 hours, run the Workday refresh if the last success is older than 11 hours." -Force | Out-Null
Get-ScheduledTask -TaskName "JobRadar Workday*" | Select-Object TaskName, State
