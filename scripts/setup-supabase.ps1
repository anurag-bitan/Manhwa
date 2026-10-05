# Print Supabase bootstrap steps and optionally verify from backend/.env credentials.
param(
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Migrations = Join-Path $Root "backend\db\migrations"
$Backend = Join-Path $Root "backend"

$ordered = @(
    "000_bootstrap_schema.sql",
    "001_cognito_job_ownership.sql",
    "002_pipeline_launch_quota.sql"
)

Write-Host "=== Supabase setup (project in backend/.env) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Open https://supabase.com/dashboard → your project → SQL Editor"
Write-Host "2. Run these files IN ORDER (New query → paste → Run):"
foreach ($name in $ordered) {
    $path = Join-Path $Migrations $name
    if (-not (Test-Path $path)) {
        throw "Missing migration: $path"
    }
    Write-Host "   - $name" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "3. Storage → confirm buckets: pdfs, pages, audio (private)"
Write-Host "4. Restart local API if running: uvicorn in backend/"
Write-Host ""

if ($VerifyOnly -or (Test-Path (Join-Path $Backend ".env"))) {
    Push-Location $Backend
    try {
        if (-not (Test-Path ".venv\Scripts\python.exe")) {
            Write-Host "Skip verify: run 'python -m venv .venv' and pip install -r requirements-api.txt first." -ForegroundColor DarkYellow
            return
        }
        $verifyScript = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\verify_supabase.py"
        $out = .\.venv\Scripts\python.exe $verifyScript 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Write-Host $out
            throw "Supabase verify failed (exit $LASTEXITCODE)."
        }
        Write-Host $out -ForegroundColor Green
    } finally {
        Pop-Location
    }
}
