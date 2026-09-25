# Full deploy: GCP bootstrap, Cloud Build, Cloud Run, Firebase Hosting.
# Account: anuragproffesional2@gmail.com | Project: manhwa-ai-509114
#
# Usage (PowerShell):
#   cd scripts
#   .\deploy-all.ps1
#
# Optional env before run:
#   $env:SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
#   $env:SUPABASE_URL = "https://iljgvihujaeqnijktaqg.supabase.co"

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\gcloud-env.ps1"

$PROJECT_ID = "manhwa-ai-509114"
$REGION = "europe-west1"
$REPOSITORY = "manhwa"
$DEPLOY_USER = "anuragproffesional2@gmail.com"
$SUPABASE_URL_DEFAULT = "https://iljgvihujaeqnijktaqg.supabase.co"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$BackendRoot = Join-Path $RepoRoot "backend"
$DeployDir = Join-Path $BackendRoot "deploy"
$Gcloud = Get-GcloudExe

function Ensure-GcloudAuth {
    $list = & $Gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null
    if ($list -match $DEPLOY_USER) {
        Write-Host "Using gcloud account: $DEPLOY_USER" -ForegroundColor Green
        return
    }
    Write-Host "Opening browser to sign in as $DEPLOY_USER ..." -ForegroundColor Yellow
    & $Gcloud auth login $DEPLOY_USER
    & $Gcloud auth application-default login
    if ($LASTEXITCODE -ne 0) { throw "gcloud login failed" }
}

function Ensure-SupabaseSecret {
    $secretName = "supabase-service-role"
    $key = $env:SUPABASE_SERVICE_ROLE_KEY
    if (-not $key) {
        $secure = Read-Host "Paste Supabase service_role key (input hidden)" -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr)
    }
    if (-not $key) { throw "SUPABASE_SERVICE_ROLE_KEY is required" }

    & $Gcloud secrets describe $secretName --project=$PROJECT_ID 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Adding new version to secret $secretName ..."
        $key | & $Gcloud secrets versions add $secretName --data-file=- --project=$PROJECT_ID
    } else {
        Write-Host "Creating secret $secretName ..."
        $key | & $Gcloud secrets create $secretName --data-file=- --project=$PROJECT_ID
    }

    $apiSa = "manhwa-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
    $workerSa = "manhwa-worker-sa@$PROJECT_ID.iam.gserviceaccount.com"
    foreach ($member in @("serviceAccount:$apiSa", "serviceAccount:$workerSa")) {
        & $Gcloud secrets add-iam-policy-binding $secretName `
            --project=$PROJECT_ID `
            --member=$member `
            --role="roles/secretmanager.secretAccessor" 2>$null | Out-Null
    }
}

function Ensure-DeployEnvFiles {
    $apiEnv = Join-Path $DeployDir "api.env.yaml"
    $workerEnv = Join-Path $DeployDir "worker.env.yaml"
    $supabaseUrl = if ($env:SUPABASE_URL) { $env:SUPABASE_URL } else { $SUPABASE_URL_DEFAULT }

    if (-not (Test-Path $apiEnv)) {
        Copy-Item (Join-Path $DeployDir "api.env.yaml.example") $apiEnv
        (Get-Content $apiEnv) -replace 'https://your-project.supabase.co', $supabaseUrl | Set-Content $apiEnv
    }
    if (-not (Test-Path $workerEnv)) {
        Copy-Item (Join-Path $DeployDir "worker.env.yaml.example") $workerEnv
        (Get-Content $workerEnv) -replace 'https://your-project.supabase.co', $supabaseUrl | Set-Content $workerEnv
    }
}

function Ensure-FrontendEnv {
    $feEnv = Join-Path $RepoRoot "frontend\.env"
    $example = Join-Path $RepoRoot "frontend\.env.example"
    if (Test-Path $feEnv) { return }

    if (-not (Test-Path $example)) { return }
    Copy-Item $example $feEnv
    $supabaseUrl = if ($env:SUPABASE_URL) { $env:SUPABASE_URL } else { $SUPABASE_URL_DEFAULT }
    (Get-Content $feEnv) -replace 'https://your-project.supabase.co', $supabaseUrl | Set-Content $feEnv

    Write-Host ""
    Write-Host "Created frontend/.env — you MUST set Firebase VITE_* keys from Firebase Console." -ForegroundColor Yellow
    Write-Host "  https://console.firebase.google.com/project/$PROJECT_ID/settings/general" -ForegroundColor Yellow
    if (-not $env:VITE_SUPABASE_ANON_KEY) {
        Write-Host "Also set VITE_SUPABASE_ANON_KEY in frontend/.env (Supabase anon key)." -ForegroundColor Yellow
    }
}

Write-Host "=== Manhwa AI full deploy ($PROJECT_ID) ===" -ForegroundColor Cyan

& $Gcloud config set project $PROJECT_ID | Out-Null
Ensure-GcloudAuth

$billingOk = (& $Gcloud billing projects describe $PROJECT_ID --format="value(billingEnabled)" 2>$null).Trim()
if ($billingOk -ne "True") {
    Write-Host "Billing is not active on $PROJECT_ID (required for Cloud Run)." -ForegroundColor Red
    Write-Host "Open: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
    Write-Host "Reactivate 'My Billing Account' or link a new billing account, then re-run this script."
    exit 1
}

Set-Location (Join-Path $DeployDir)
& .\bootstrap-manhwa-ai.ps1

Ensure-DeployEnvFiles
Ensure-SupabaseSecret

Write-Host "Submitting Cloud Build (API + worker images) ..." -ForegroundColor Cyan
Set-Location $BackendRoot
& $Gcloud builds submit --config cloudbuild.yaml --substitutions="_REGION=$REGION,_REPOSITORY=$REPOSITORY" .

Set-Location $DeployDir
& .\deploy-cloud-run.ps1

$apiUrl = & $Gcloud run services describe manhwa-api --region $REGION --project $PROJECT_ID --format="value(status.url)"
Write-Host "Cloud Run API: $apiUrl" -ForegroundColor Green

Ensure-FrontendEnv
$feEnvPath = Join-Path $RepoRoot "frontend\.env"
if (Test-Path $feEnvPath) {
    $content = Get-Content $feEnvPath -Raw
    if ($content -notmatch 'VITE_API_BASE_URL=https://') {
        $content = $content -replace 'VITE_API_BASE_URL=.*', "VITE_API_BASE_URL=$apiUrl"
        Set-Content $feEnvPath $content -NoNewline
    }
}

$firebase = Get-Command firebase -ErrorAction SilentlyContinue
if ($firebase) {
    $hasFirebaseConfig = Select-String -Path $feEnvPath -Pattern 'VITE_FIREBASE_API_KEY=your-' -Quiet -ErrorAction SilentlyContinue
    if (-not $hasFirebaseConfig) {
        Set-Location (Join-Path $RepoRoot "frontend")
        npm ci
        npm run build
        Set-Location $RepoRoot
        firebase use $PROJECT_ID
        firebase deploy --only hosting --non-interactive
        Write-Host "Firebase Hosting deploy finished." -ForegroundColor Green
    } else {
        Write-Host "Skip Firebase deploy: fill VITE_FIREBASE_* in frontend/.env then run: npm run deploy" -ForegroundColor Yellow
    }
} else {
    Write-Host "Install Firebase CLI: npm install -g firebase-tools" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. API health: $apiUrl/health" -ForegroundColor Green
