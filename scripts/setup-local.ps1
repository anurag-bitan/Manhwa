# Local dev: create .env files and start API in Docker.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$Backend = Join-Path $RepoRoot "backend"
$Frontend = Join-Path $RepoRoot "frontend"
$SUPABASE_URL = "https://iljgvihujaeqnijktaqg.supabase.co"

if (-not (Test-Path (Join-Path $Backend ".env"))) {
    Copy-Item (Join-Path $Backend ".env.example") (Join-Path $Backend ".env")
    (Get-Content (Join-Path $Backend ".env")) `
        -replace 'your-gcp-project-id', 'manhwa-ai-509114' `
        -replace 'https://your-project.supabase.co', $SUPABASE_URL |
        Set-Content (Join-Path $Backend ".env")
    Write-Host "Created backend/.env — add SUPABASE_SERVICE_ROLE_KEY and keys." -ForegroundColor Yellow
}

if (-not (Test-Path (Join-Path $Frontend ".env"))) {
    Copy-Item (Join-Path $Frontend ".env.example") (Join-Path $Frontend ".env")
    (Get-Content (Join-Path $Frontend ".env")) `
        -replace 'https://your-project.supabase.co', $SUPABASE_URL |
        Set-Content (Join-Path $Frontend ".env")
    Write-Host "Created frontend/.env — add Firebase + VITE_SUPABASE_ANON_KEY." -ForegroundColor Yellow
}

Write-Host "Start API: cd backend; docker compose up --build"
Write-Host "Start UI:  cd frontend; npm run dev"
