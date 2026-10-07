# Deploy: Modal backend + Vercel frontend

Modal is the target backend. The API scales to zero and dispatches OCR work to a
detached worker. Vercel, Firebase, and Supabase remain unchanged.

Keep the existing Render service and `render.yaml` available until staging has
completed a real authenticated PDF and the user has approved the output and
usage. Render is the rollback target during this migration.

## 1. Prerequisites and environments

Install Python 3.10+ and the deployment dependencies:

```powershell
python -m pip install -r backend/requirements-modal.txt
python -m modal setup
python -m modal environment create staging
python -m modal environment create production
```

`modal setup` opens a browser and stores a local token. Use separate Modal
environments so staging secrets, URLs, calls, and spend are distinguishable
from production. Apply `backend/db/migrations/003_modal_dispatch_and_budget.sql`
before starting staging, and re-run it after pulling lease/heartbeat fixes
(`create or replace` is safe). Deployment automation does not modify the
database.

## 2. Create the named Modal secret

The app expects a named secret called `manhwa-backend-secrets` in each Modal
environment. Create a temporary dotenv file outside the repository containing:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-public-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-server-only-service-role-key
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-3.8-flash
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
NARRATION_PROVIDER=deepseek
CORS_ALLOWED_ORIGINS=https://your-staging-frontend.vercel.app
PIPELINE_EXECUTION_MODE=modal
MODAL_APP_NAME=manhwa-video-backend
MODAL_WORKER_FUNCTION_NAME=process-job
MODAL_WORKER_TIMEOUT_SECONDS=7200
MODAL_WORKER_CPU=2
MODAL_WORKER_MEMORY_MIB=10240
MODAL_HEARTBEAT_INTERVAL_SECONDS=30
MODAL_LEASE_SECONDS=180
MAX_PIPELINE_STARTS_PER_USER_DAY=5
MAX_PIPELINE_STARTS_GLOBAL_MONTH=150
MODAL_MONTHLY_COMPUTE_BUDGET_USD=27.50
MODAL_JOB_ADMISSION_COST_USD=0.50
MAX_PDF_BYTES=52428800
NARRATION_BATCH_SIZE=12
TTS_CONCURRENCY=4
OCR_ENGINE=paddle
```

The Firebase JSON must be minified onto one line. Then create the secret:

```powershell
python -m modal secret create --env staging --from-dotenv C:\secure\modal-staging.env manhwa-backend-secrets
python -m modal secret create --env production --from-dotenv C:\secure\modal-production.env manhwa-backend-secrets
```

Delete the temporary files after confirming the secrets in the Modal dashboard.
Never commit them, `backend/.env`, a Firebase key file, or Modal tokens.
Production CORS must contain the exact Vercel production origin; add preview
origins only when they are intentionally allowed.

If the secret name referenced by `backend/modal_app.py` changes, use that exact
name here as well.

## 3. Prepare models and deploy

The worker image build runs its PaddleOCR model initializer and bakes the
downloaded assets into the immutable image. The first deploy is therefore the
model preparation step and can take substantially longer. It must finish
successfully before validating a worker; normal jobs should not download model
weights at runtime.

```powershell
.\scripts\deploy-modal.ps1 -Environment staging -InstallDependencies
```

Later deploys reuse Modal's image layers when requirements and the initializer
have not changed:

```powershell
.\scripts\deploy-modal.ps1 -Environment staging
.\scripts\deploy-modal.ps1 -Environment production
```

Record the stable `modal.run` web URL printed by `modal deploy`. Check the image
build logs for successful PaddleOCR initialization; a download during a job is
a failed preparation, not an expected cold start.

### GitHub Actions

Create GitHub environments named `modal-staging` and `modal-production`. Add
these environment secrets to both:

- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`

Create a restricted deploy token in Modal rather than uploading the local
profile. Run **Deploy Modal backend** manually, choose `staging` or
`production`. Each deployment rebuilds or reuses the model-bearing image.
Protect `modal-production` with required reviewers. Application secrets stay
in Modal and are not copied into GitHub.

## 4. Cost controls

Modal credits are account credits, not a hard spending cap. Before running a
real worker:

1. Open the Modal workspace billing/usage settings.
2. Configure the workspace's monthly hard spend/usage limit at **$30 USD**.
3. Enable usage alerts below the limit (for example $20 and $27).
4. Confirm in the current Modal UI that the selected control blocks new paid
   usage; a budget notification by itself is not a hard cap. Do not cut over
   if the workspace plan does not provide an enforceable limit.
5. Keep worker concurrency at one, API and worker minimum containers at zero,
   and do not configure scheduled warm containers.

The app has a second, conservative admission guard:

- `MODAL_MONTHLY_COMPUTE_BUDGET_USD=27.50` rejects new starts with HTTP `429`
  before the workspace cap.
- User starts are limited to 5/day and global starts to 150/calendar month.
- Completed worker runtime and estimated compute cost must be persisted and
  checked before accepting another job.

The app guard is defense in depth, not a billing guarantee. Concurrent calls,
pricing changes, failed containers, and delayed accounting can make estimates
lag. DeepSeek, Supabase, Firebase, and Vercel charges are separate from Modal's
workspace limit.

## 5. Staging validation

Do not change Vercel production yet. Against the staging URL:

1. Confirm `GET /health` returns success after a cold start.
2. Confirm the Vercel staging origin passes CORS and an invalid token gets
   `401`.
3. Sign in with Firebase, upload one representative PDF through the signed
   Supabase flow, and start the job once.
4. Confirm the start request returns immediately, the job advances from queued
   to processing, and duplicate starts do not launch duplicate workers.
5. Confirm a real 30-panel PDF reaches the terminal TTS state and all page and
   audio URLs work.
6. Inspect Modal logs and Supabase metadata for call ID, heartbeat, completion,
   runtime, and estimated cost.
7. Confirm only one heavy worker runs, containers return to zero, and no model
   download occurs during the job.
8. Exercise the configured quota/budget rejection and stale-job recovery in a
   controlled staging account.

Manual approval of output quality, measured usage, and scale-to-zero behavior
is required before production cutover.

## 6. Vercel cutover

Deploy the same accepted revision to the Modal `production` environment and
repeat `/health`, auth, and CORS checks. Then:

1. In Vercel, set Production `VITE_API_BASE_URL` to the production
   `https://...modal.run` URL, without a trailing slash.
2. Keep Preview pointed at staging unless previews are intended to exercise
   production.
3. Redeploy `frontend/`; `VITE_*` values are embedded at build time.
4. Run a production smoke upload and watch Modal/Supabase status and spend.
5. Leave Render deployed but remove normal traffic only after acceptance.

Do not expose `SUPABASE_SERVICE_ROLE_KEY`, Firebase service-account JSON,
DeepSeek keys, Gemini keys, or Modal tokens in Vercel.

## 7. Roll back to Render

If Modal fails before or after cutover:

1. Stop new starts if necessary and inspect in-flight Supabase jobs.
2. Restore Vercel `VITE_API_BASE_URL` to the previous Render URL.
3. Redeploy the frontend and verify Render `GET /health`.
4. Confirm Render still has its environment variables and
   `PIPELINE_EXECUTION_MODE=local`.
5. Reconcile any Modal job left queued/processing before retrying it; do not
   blindly start a second worker.

Keep `render.yaml`, `backend/Dockerfile`, and
[`RENDER_VERCEL.md`](RENDER_VERCEL.md) until this rollback window is explicitly
closed. Local development remains `docker compose up --build`.
