# Upload the skill profile (never the CV) as a GitHub Secret and rescore all open jobs.
# Usage (from the repo folder):  .\scripts\update_cv.ps1
# Prerequisite: private\cv_profile.json created and reviewed (see BUILD_PROMPT section 7.3).
$ErrorActionPreference = "Stop"
$repo = "ptpt1801/job-radar"
$root = Split-Path -Parent $PSScriptRoot
$profilePath = Join-Path $root "private\cv_profile.json"

if (-not (Test-Path $profilePath)) {
    Write-Host "Missing $profilePath. Ask Claude Code to build it from the CV in private\ first." -ForegroundColor Red
    exit 1
}

# Validate JSON before uploading
try { $json = Get-Content $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch {
    Write-Host "cv_profile.json is not valid JSON." -ForegroundColor Red; exit 1
}
if (-not $json.cv_version -or -not $json.skills) {
    Write-Host "cv_profile.json needs at least 'cv_version' and 'skills'." -ForegroundColor Red; exit 1
}

Write-Host "Uploading skill profile (cv_version $($json.cv_version), $($json.skills.Count) skills) to secret CV_PROFILE_JSON..."
Get-Content $profilePath -Raw -Encoding UTF8 | gh secret set CV_PROFILE_JSON --repo $repo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Starting rescore workflow..."
gh workflow run rescore.yml --repo $repo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Follow the run with:  gh run watch --repo $repo" -ForegroundColor Green
