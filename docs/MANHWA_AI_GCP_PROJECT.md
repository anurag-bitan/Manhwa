# Manhwa AI — your GCP project (`manhwa-ai-509114`)

> **Legacy:** Primary hosting is now [HF_SPACES_VERCEL.md](HF_SPACES_VERCEL.md). This document is for the old Cloud Run / Vertex setup on `manhwa-ai-509114`.

Use this guide for **project Manhwa AI** only. Do not reuse these IDs for other apps.

| Field | Value |
|--------|--------|
| Project name | Manhwa AI |
| Project ID | `manhwa-ai-509114` |
| Project number | `896973672285` |
| Primary login | `anuragproffesional2@gmail.com` |
| Region (Run + Vertex) | `europe-west1` |

## Free tier and safety (important)

Google Cloud is **not** 100% free once billing is linked. This stack is tuned to **minimize cost**:

- Cloud Run API: **min instances 0**, **max 1**
- Cloud Run Job: **max-retries 0**, starts only when a user uploads
- App quotas: **3 jobs/user/30d**, **10 global/30d** (in env files)
- **No** downloaded service-account JSON keys (Cloud Run uses attached identities)
- **Budget alert** on the project (you set amount; alerts do not stop spend)

**Vertex Gemini Flash is billed per use** (not covered by the small Cloud Run free tier). Keep `MAX_PIPELINE_STARTS_GLOBAL_30D` low while testing.

Before heavy testing: **Billing → Budgets & alerts** → create a budget (e.g. ₹500 / $5) and add `anuragproffesional2@gmail.com` at 50%, 90%, 100%.

## Step 0 — Install tools (once)

1. [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (Windows installer).
2. [Firebase CLI](https://firebase.google.com/docs/cli): `npm install -g firebase-tools`
3. Close and reopen PowerShell.

Sign in **only** with your project account:

```powershell
gcloud auth login anuragproffesional2@gmail.com
gcloud config set project manhwa-ai-509114
gcloud auth application-default login
firebase login
```

Confirm:

```powershell
gcloud config get-value project
# must print: manhwa-ai-509114
```

## Step 1 — IAM (this project only)

If you created the project with another account, grant yourself access **on this project only** (not the whole organization):

```powershell
$PROJECT_ID = "manhwa-ai-509114"
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="user:anuragproffesional2@gmail.com" `
  --role="roles/editor"
```

For full console admin on this project only (optional):

```powershell
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="user:anuragproffesional2@gmail.com" `
  --role="roles/owner"
```

Do **not** create API keys or service-account JSON files for day-to-day deploys.

## Step 2 — One-shot backend bootstrap (APIs, registry, service accounts)

From the repository root:

```powershell
Set-Location backend\deploy
.\bootstrap-manhwa-ai.ps1
```

That script enables APIs, creates Artifact Registry, creates `manhwa-api-sa` and `manhwa-worker-sa`, and grants **Vertex AI User** to both. It does **not** deploy containers until you complete Supabase secrets and env files.

## Step 3 — Supabase secret (required)

1. [Supabase](https://supabase.com) → your project → **Settings → API** → copy **service_role** key.
2. GCP Console → **Security → Secret Manager** → **Create secret**
   - Name: `supabase-service-role`
   - Value: paste service role key only here
3. Open the secret → **Permissions** → grant **Secret Manager Secret Accessor** to:
   - `manhwa-api-sa@manhwa-ai-509114.iam.gserviceaccount.com`
   - `manhwa-worker-sa@manhwa-ai-509114.iam.gserviceaccount.com`

## Step 4 — Env files (no secrets in Git)

```powershell
Copy-Item backend\deploy\api.env.yaml.example backend\deploy\api.env.yaml
Copy-Item backend\deploy\worker.env.yaml.example backend\deploy\worker.env.yaml
```

Edit `api.env.yaml` and `worker.env.yaml`:

- Set `SUPABASE_URL` to your real Supabase URL.
- Set `CORS_ALLOWED_ORIGINS` to `http://localhost:5173` and later `https://manhwa-ai-509114.web.app` (or your Firebase Hosting URL).

`api.env.yaml.example` already uses `manhwa-ai-509114` for GCP/Firebase IDs.

## Step 5 — Build and deploy backend

```powershell
$PROJECT_ID = "manhwa-ai-509114"
$REGION = "europe-west1"
$REPOSITORY = "manhwa"

Set-Location backend
gcloud builds submit --config cloudbuild.yaml --substitutions="_REGION=$REGION,_REPOSITORY=$REPOSITORY" .
```

Then run the **job + API** commands from [GCP_DEPLOYMENT.md](GCP_DEPLOYMENT.md) sections 6–7, or:

```powershell
Set-Location backend\deploy
.\deploy-cloud-run.ps1
```

Copy the **Cloud Run API URL** when deploy finishes.

## Step 6 — Firebase (same project)

1. [Firebase Console](https://console.firebase.google.com) → add project → choose existing **`manhwa-ai-509114`**.
2. **Authentication** → enable **Google** and **Email/Password**.
3. **Project settings** → Web app → copy config into `frontend/.env` (see `frontend/.env.example`).
4. Set `VITE_API_BASE_URL` to your Cloud Run API URL.

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
firebase deploy --only hosting
```

## Step 7 — Quick checks

| Check | Expected |
|--------|-----------|
| `https://YOUR-API/health` | `{"status":"ok"}` |
| `POST /jobs/upload-url` without token | 401 |
| Sign in on Hosting with Google | Firebase session works |
| Small PDF upload | One Cloud Run Job execution |

## Console links (bookmark)

- [Project dashboard](https://console.cloud.google.com/home/dashboard?project=manhwa-ai-509114)
- [Cloud Run](https://console.cloud.google.com/run?project=manhwa-ai-509114)
- [Cloud Run Jobs](https://console.cloud.google.com/run/jobs?project=manhwa-ai-509114)
- [Billing budgets](https://console.cloud.google.com/billing/budgets?project=manhwa-ai-509114)
- [Secret Manager](https://console.cloud.google.com/security/secret-manager?project=manhwa-ai-509114)
- [Firebase](https://console.firebase.google.com/project/manhwa-ai-509114)

For the generic architecture reference, see [GCP_DEPLOYMENT.md](GCP_DEPLOYMENT.md).
