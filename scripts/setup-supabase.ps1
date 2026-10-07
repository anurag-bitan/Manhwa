param([switch]$VerifyOnly)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Schema = Join-Path $Root "backend\db\schema.sql"
$Backend = Join-Path $Root "backend"

if (-not (Test-Path $Schema)) {
    throw "Missing schema: $Schema"
}

Write-Host "Supabase: SQL Editor → paste backend/db/schema.sql → Run"
Write-Host "Storage buckets must be private: pdfs, pages, audio"

if ($VerifyOnly -or (Test-Path (Join-Path $Backend ".env"))) {
    Push-Location $Backend
    try {
        if (-not (Test-Path ".venv\Scripts\python.exe")) {
            Write-Host "Skip verify: create backend/.venv first."
            return
        }
        $verifyScript = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\verify_supabase.py"
        & ".venv\Scripts\python.exe" $verifyScript
    } finally {
        Pop-Location
    }
}
