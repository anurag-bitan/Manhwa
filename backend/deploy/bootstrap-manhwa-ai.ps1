# One-time setup for project manhwa-ai-509114 (Manhwa AI).
# Run after: gcloud auth login anuragproffesional2@gmail.com
#            gcloud config set project manhwa-ai-509114

$ErrorActionPreference = "Stop"

$PROJECT_ID = "manhwa-ai-509114"
$REGION = "europe-west1"
$REPOSITORY = "manhwa"
$API_SA = "manhwa-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
$WORKER_SA = "manhwa-worker-sa@$PROJECT_ID.iam.gserviceaccount.com"
$DEPLOY_USER = "anuragproffesional2@gmail.com"

$GcloudBin = "C:\Users\Anurag Bhattacharya\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
if (Test-Path $GcloudBin) { $env:Path = "$GcloudBin;$env:Path" }

function Require-Gcloud {
    if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
        Write-Host "Install Google Cloud CLI: winget install Google.CloudSDK" -ForegroundColor Red
        exit 1
    }
}

Require-Gcloud

$activeProject = (gcloud config get-value project 2>$null).Trim()
if ($activeProject -ne $PROJECT_ID) {
    Write-Host "Setting gcloud project to $PROJECT_ID ..."
    gcloud config set project $PROJECT_ID | Out-Null
}

Write-Host "Ensuring $DEPLOY_USER has Editor on this project only ..."
gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="user:$DEPLOY_USER" `
    --role="roles/editor" 2>$null | Out-Null

Write-Host "Enabling required APIs (may take 1-2 minutes) ..."
gcloud services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    secretmanager.googleapis.com `
    aiplatform.googleapis.com `
    identitytoolkit.googleapis.com `
    firebase.googleapis.com `
    firebasehosting.googleapis.com `
    --project=$PROJECT_ID

Write-Host "Creating Artifact Registry repository (if missing) ..."
gcloud artifacts repositories describe $REPOSITORY --location=$REGION --project=$PROJECT_ID 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud artifacts repositories create $REPOSITORY `
        --repository-format=docker `
        --location=$REGION `
        --description="Manhwa API and worker images" `
        --project=$PROJECT_ID
}

Write-Host "Creating service accounts (if missing) ..."
gcloud iam service-accounts describe $API_SA --project=$PROJECT_ID 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create manhwa-api-sa `
        --display-name="Manhwa Cloud Run API" `
        --project=$PROJECT_ID
}

gcloud iam service-accounts describe $WORKER_SA --project=$PROJECT_ID 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create manhwa-worker-sa `
        --display-name="Manhwa pipeline worker" `
        --project=$PROJECT_ID
}

Write-Host "Granting Vertex AI User to API and worker service accounts ..."
gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="serviceAccount:$API_SA" `
    --role="roles/aiplatform.user" | Out-Null

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="serviceAccount:$WORKER_SA" `
    --role="roles/aiplatform.user" | Out-Null

Write-Host ""
Write-Host "Bootstrap complete for $PROJECT_ID." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1. Create Secret Manager secret supabase-service-role (Supabase service role key)."
Write-Host "  2. Copy api.env.yaml.example -> api.env.yaml and worker.env.yaml.example -> worker.env.yaml"
Write-Host "  3. From backend/: gcloud builds submit --config cloudbuild.yaml --substitutions=_REGION=$REGION,_REPOSITORY=$REPOSITORY ."
Write-Host "  4. Run .\deploy-cloud-run.ps1"
Write-Host "  5. Set a billing budget in Console for $DEPLOY_USER"
