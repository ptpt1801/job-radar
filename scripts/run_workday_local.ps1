# Job Radar - refresh Workday companies from this computer and push the data to GitHub.
# Why: Workday rate-limits GitHub's shared runner IPs (HTTP 429); a home connection is not blocked.
# Scheduled by scripts\install_workday_task.ps1 (08:00 and 20:00; runs late if the PC was off).
# Logs: logs\workday-local-*.log (git-ignored, last 30 kept).
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
New-Item -ItemType Directory -Force (Join-Path $repo "logs") | Out-Null
$log = Join-Path $repo ("logs\workday-local-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".log")
function Write-Log($m) { "$(Get-Date -Format s) $m" | Out-File -FilePath $log -Append -Encoding utf8 }
function Invoke-Retry([scriptblock]$block, [int]$tries = 4) {
    for ($i = 1; $i -le $tries; $i++) {
        & $block
        if ($LASTEXITCODE -eq 0) { return $true }
        Write-Log "attempt $i failed (exit $LASTEXITCODE); retrying"
        Start-Sleep -Seconds (20 * $i)
    }
    return $false
}

Write-Log "start"
# The GitHub bot owns data/: drop any leftover local data changes before syncing.
git restore --staged --worktree data site/i18n/taxonomy.json 2>$null
if (-not (Invoke-Retry { git pull --rebase -q origin main 2>&1 | Out-File $log -Append -Encoding utf8 })) { Write-Log "git pull failed; stop"; exit 1 }

$py = Join-Path $repo ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"
$profilePath = Join-Path $repo "private\cv_profile.json"
if (Test-Path $profilePath) { $env:CV_PROFILE_JSON = Get-Content $profilePath -Raw -Encoding UTF8 }

& $py -m pipeline --only-new --only-ats workday 2>&1 | Out-File $log -Append -Encoding utf8
if ($LASTEXITCODE -ne 0) { Write-Log "pipeline failed"; git restore data 2>$null; exit 1 }
& $py -m pytest -q pipeline/tests 2>&1 | Out-File $log -Append -Encoding utf8
if ($LASTEXITCODE -ne 0) { Write-Log "tests failed; data not pushed"; git restore data 2>$null; exit 1 }
& $py scripts/privacy_guard.py 2>&1 | Out-File $log -Append -Encoding utf8
if ($LASTEXITCODE -ne 0) { Write-Log "privacy guard FAILED; data not pushed"; git restore data 2>$null; exit 1 }

git add data site/i18n/taxonomy.json
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Log "no data changes"; exit 0 }
$new = & $py -c "import json;print(json.load(open('data/meta.json'))['last_run']['new'])"
git commit -q -m "data: workday local update $(Get-Date -Format 'yyyy-MM-dd HH:mm') (+$new new)"
# If the bot pushed meanwhile, keep this run's fresh data on conflicts.
$ok = Invoke-Retry { git pull --rebase -X theirs -q origin main 2>&1 | Out-File $log -Append -Encoding utf8; if ($LASTEXITCODE -eq 0) { git push -q origin main 2>&1 | Out-File $log -Append -Encoding utf8 } }
if (-not $ok) { Write-Log "push failed; will retry next run" ; exit 1 }
Write-Log "done (+$new new)"
Get-ChildItem (Join-Path $repo "logs") -Filter "workday-local-*.log" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item -Force
exit 0
