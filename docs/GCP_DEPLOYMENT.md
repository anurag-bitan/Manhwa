# Google Cloud deployment (Firebase + Cloud Run + Vertex Gemini)

> **Legacy:** New deployments should use [HF_SPACES_VERCEL.md](HF_SPACES_VERCEL.md) (Hugging Face + Vercel, Gemini API key). This guide is kept for existing Cloud Run stacks only.

This guide deploys the full stack on one Google Cloud project:

- **Firebase Hosting** — React frontend
- **Firebase Authentication** — Google sign-in and email/password
- **Cloud Run API** — FastAPI (upload tokens, context preview, job control)
- **Cloud Run Job** — OCR, Gemini Flash narration, TTS
- **Vertex AI** — Gemini Flash with Google Search grounding
- **Supabase** — private database and asset storage

Video muxing stays in the **user's browser** (WebCodecs). The server never renders MP4.

## 1. Create the GCP project

1. Open [Google Cloud Console](https://console.cloud.google.com) → **New project** (example: `manhwa-video`).
2. **Billing → My projects** → link a billing account.
3. **Billing → Budgets & alerts** → create a small budget with email alerts.

Install [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), then:

```powershell
$PROJECT_ID = "your-gcp-project-id"
$REGION = "europe-west1"
$REPOSITORY = "manhwa"
$JOB = "manhwa-pipeline"
$API_SERVICE = "manhwa-api"
$API_SA = "manhwa-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
$WORKER_SA = "manhwa-worker-sa@$PROJECT_ID.iam.gserviceaccount.com"

gcloud auth login
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com identitytoolkit.googleapis.com firebase.googleapis.com firebasehosting.googleapis.com
```

## 2. Firebase (same project)

1. Open [Firebase Console](https://console.firebase.google.com) → **Add project** → select the **same** GCP project.
2. **Authentication → Sign-in method** → enable **Google** and **Email/Password**.
3. **Authentication → Settings → Authorized domains** → add `localhost` and your Hosting domain.
4. **Project settings → General** → copy the Web app config (`apiKey`, `authDomain`, `projectId`, etc.).

### Frontend environment variables

Create `frontend/.env` from `frontend/.env.example` and set:

```dotenv
VITE_API_BASE_URL=https://YOUR_CLOUD_RUN_API_URL
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=YOUR_PROJECT.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=YOUR_PROJECT_ID
VITE_FIREBASE_STORAGE_BUCKET=YOUR_PROJECT.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=...
VITE_FIREBASE_APP_ID=...
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_PUBLIC_ANON_KEY
```

## 3. Supabase

Run migrations in order from `backend/db/migrations/`. Keep `pdfs`, `pages`, and `audio` buckets private.

Store `SUPABASE_SERVICE_ROLE_KEY` in Secret Manager as `supabase-service-role`. **Do not** store Groq or AWS keys — Gemini uses the Cloud Run service account.

## 4. Service accounts and IAM

```powershell
gcloud artifacts repositories create $REPOSITORY --repository-format=docker --location=$REGION --description="Manhwa API and worker images"
gcloud iam service-accounts create manhwa-api-sa --display-name="Manhwa Cloud Run API"
gcloud iam service-accounts create manhwa-worker-sa --display-name="Manhwa pipeline worker"

gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$API_SA" --role "roles/aiplatform.user"
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$WORKER_SA" --role "roles/aiplatform.user"
```

Grant **Secret Manager Secret Accessor** on `supabase-service-role` to both service accounts. Do not download JSON key files.

## 5. Build container images

```powershell
Set-Location backend
gcloud builds submit --config cloudbuild.yaml --substitutions="_REGION=$REGION,_REPOSITORY=$REPOSITORY" .
```

## 6. Deploy Cloud Run Job (worker)

```powershell
Copy-Item deploy/worker.env.yaml.example deploy/worker.env.yaml
Copy-Item deploy/api.env.yaml.example deploy/api.env.yaml
# Edit both files with your project values. Set CORS to your Firebase Hosting URL.
```

```powershell
$WORKER_IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/manhwa-worker:latest"

gcloud run jobs create $JOB `
  --image $WORKER_IMAGE `
  --region $REGION `
  --service-account $WORKER_SA `
  --tasks 1 `
  --parallelism 1 `
  --max-retries 0 `
  --task-timeout 7200s `
  --cpu 2 `
  --memory 4Gi `
  --env-vars-file deploy/worker.env.yaml `
  --set-secrets "SUPABASE_SERVICE_ROLE_KEY=supabase-service-role:latest"
```

```powershell
gcloud run jobs add-iam-policy-binding $JOB `
  --region $REGION `
  --member "serviceAccount:$API_SA" `
  --role "roles/run.jobsExecutorWithOverrides"
```

## 7. Deploy Cloud Run API

```powershell
$API_IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/manhwa-api:latest"

gcloud run deploy $API_SERVICE `
  --image $API_IMAGE `
  --region $REGION `
  --service-account $API_SA `
  --allow-unauthenticated `
  --port 8080 `
  --min 0 `
  --max 1 `
  --concurrency 20 `
  --timeout 60s `
  --cpu 1 `
  --memory 512Mi `
  --env-vars-file deploy/api.env.yaml `
  --set-secrets "SUPABASE_SERVICE_ROLE_KEY=supabase-service-role:latest"
```

Copy the API URL into `VITE_API_BASE_URL`.

## 8. Deploy Firebase Hosting

From the repository root (after `npm run build` in `frontend`):

```powershell
npm install -g firebase-tools
firebase login
firebase init hosting
# Public directory: frontend/dist
# Single-page app: Yes

Set-Location frontend
npm ci
npm run build
Set-Location ..
firebase deploy --only hosting
```

## 9. Verification

1. `GET /health` → `{"status":"ok"}`
2. `POST /jobs/upload-url` without token → 401
3. Sign in with Google on Hosting
4. Type a manhwa name → context preview returns ≤50 words (or empty if ungrounded)
5. Upload PDF → Cloud Run Job runs → assets ready → browser generates MP4 locally

## Cost notes

- Cloud Run scales to zero; one job at a time limits spend.
- Vertex Gemini Flash is billed per token; batched narration reduces calls vs per-panel.
- Firebase Hosting free tier covers small traffic.
- Set `MAX_PIPELINE_STARTS_GLOBAL_30D=10` or lower to cap usage.
