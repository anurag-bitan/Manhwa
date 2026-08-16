# AWS Amplify + Cognito with a Google Cloud Run backend

This guide deploys the React frontend to AWS Amplify, keeps authentication in
Amazon Cognito (including Google sign-in), and runs the FastAPI/OCR backend on
Google Cloud Run. Supabase remains the private database and asset store.

## Cost and security warning

This is a cost-minimized design, not a guarantee of a permanently zero bill.
Cloud billing accounts can charge when a free allowance is exceeded, and a
Google Cloud budget normally alerts rather than stopping usage. The OCR worker
image may also exceed Artifact Registry's 0.5 GiB free storage allowance.

The code limits processing to one active job, three starts per Cognito user per
rolling 30 days, and ten starts globally per rolling 30 days by default. Cloud
Run is also configured with no worker retry and a two-hour timeout. Lower these
limits if necessary.

Never create or download an AWS access key or a GCP service-account JSON key for
the running application. Cloud Run uses attached service accounts. Cognito JWT
verification uses public signing keys and does not require AWS credentials.

## Important: rotate the exposed Google OAuth secret

A previous screenshot displayed the Google OAuth client secret. Treat it as
compromised even if it was only used for testing.

1. Open **Google Cloud Console > Google Auth Platform > Clients**. In the older
   navigation this is **APIs & Services > Credentials**.
2. Open the Web application OAuth client used by Cognito.
3. Reset or rotate its client secret. Do not paste the old or new secret into
   chat, Git, Amplify variables, or any `VITE_*` variable.
4. Open **AWS Cognito > User pools > your pool > Authentication > Social and
   external providers > Google**, replace the secret, and save.

## Architecture

1. Amplify serves the browser application.
2. Cognito issues an access token after email or Google sign-in.
3. FastAPI verifies that access token, creates a user-owned job, and returns a
   two-hour Supabase signed-upload token.
4. The browser uploads the PDF directly to the private `pdfs` bucket.
5. FastAPI atomically reserves quota and starts one private Cloud Run Job.
6. The job validates the stored PDF, runs extraction/OCR/LLM/TTS, and writes
   status and private asset paths to Supabase.
7. FastAPI verifies job ownership before returning signed asset URLs.

## 1. Supabase configuration

### Get the values

Open **Supabase Dashboard > your project > Project Settings > API** (the page
may be named **API Keys** in the newer layout).

- Project URL -> `SUPABASE_URL` and public `VITE_SUPABASE_URL`
- anon/publishable key -> public `VITE_SUPABASE_ANON_KEY`
- service_role/secret key -> backend secret `SUPABASE_SERVICE_ROLE_KEY`

The service-role key bypasses row-level security. It must exist only in local
`backend/.env` and Google Secret Manager.

### Apply database migrations

Open **Supabase > SQL Editor > New query** and run these files in order:

1. `backend/db/migrations/001_cognito_job_ownership.sql`
2. `backend/db/migrations/002_pipeline_launch_quota.sql`

Then open **Storage** and verify that `pdfs`, `pages`, and `audio` exist and are
private. Edit the `pdfs` bucket and set its file-size limit to 50 MB and allowed
MIME type to `application/pdf`. The frontend does not need a broad bucket upload
policy because each upload uses a short-lived signed token created by the
backend.

## 2. AWS Cognito and Amplify configuration

### Values to copy from Cognito

Open **AWS Console > Amazon Cognito > User pools > your pool** in `eu-north-1`:

- **Overview** -> User pool ID -> `VITE_COGNITO_USER_POOL_ID` and
  `COGNITO_USER_POOL_ID`
- **Applications > App clients > your public SPA client** -> Client ID ->
  `VITE_COGNITO_CLIENT_ID` and `COGNITO_APP_CLIENT_ID`
- **Branding > Domain** -> Cognito domain hostname ->
  `VITE_COGNITO_DOMAIN`

The current Cognito console no longer has a general **App integration** menu.
Use **Branding > Domain**, **Authentication > Social and external providers**,
and **Applications > App clients**.

Use a public SPA app client with no client secret. These IDs are identifiers,
not passwords. Do not create an IAM access key for the frontend or backend.

### Verify the Google OAuth client

In **Google Auth Platform > Branding/Audience/Data Access**:

- Add the application name, support email, and developer email.
- If publishing status is **Testing**, add each Google account under
  **Audience > Test users**.
- Request only `openid`, `email`, and `profile`.
- Add `amazoncognito.com` to authorized domains. Add your own root domain if
  using a Cognito custom domain.

In **Google Auth Platform > Clients > your Web application client**, use:

```text
Authorized JavaScript origin:
https://YOUR_COGNITO_DOMAIN

Authorized redirect URI:
https://YOUR_COGNITO_DOMAIN/oauth2/idpresponse
```

The Google redirect URI goes to Cognito, not Amplify and not Cloud Run.

### Verify the Cognito Google provider and app client

Under **Authentication > Social and external providers > Google**:

- Client ID and the newly rotated client secret must be from the same Google
  Web application client.
- Authorized scopes: `openid email profile` (space-separated).
- Map Google `email` to Cognito `email`.

Under **Applications > App clients > your client > Login pages**, enable Google,
select **Authorization code grant**, and allow `openid`, `email`, and `profile`.
Register exact URLs:

```text
Callback URLs
http://localhost:5173/auth/callback
https://YOUR_AMPLIFY_DOMAIN/auth/callback

Sign-out URLs
http://localhost:5173/login
https://YOUR_AMPLIFY_DOMAIN/login
```

Do not add `/oauth2/idpresponse` as a Cognito app callback; that URL belongs in
the Google client. Domain/DNS changes can take time to propagate.

### Amplify environment variables

Open **AWS Amplify > your app > Hosting > Environment variables > Manage
variables** and set these on the deployed branch:

```dotenv
AMPLIFY_MONOREPO_APP_ROOT=frontend
VITE_API_BASE_URL=https://YOUR_CLOUD_RUN_API_URL
VITE_MAX_PDF_MB=50
VITE_COGNITO_REGION=eu-north-1
VITE_COGNITO_USER_POOL_ID=eu-north-1_EXAMPLE
VITE_COGNITO_CLIENT_ID=YOUR_PUBLIC_APP_CLIENT_ID
VITE_COGNITO_GOOGLE_ENABLED=true
VITE_COGNITO_DOMAIN=YOUR_COGNITO_DOMAIN
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_PUBLIC_ANON_KEY
```

`VITE_COGNITO_DOMAIN` is hostname-only: no `https://`, path, or trailing slash.
Never place the Google secret, Supabase service-role key, Groq key, AWS access
key, or GCP credential in Amplify variables. Vite bundles every `VITE_*` value
into browser JavaScript.

## 3. Google Cloud project and runtime identities

Google Cloud requires a billing account for Cloud Run even when usage remains
inside free allowances.

1. Create/select the Google Cloud project.
2. Open **Billing > My projects** and link the intended billing account.
3. Open **Billing > Budgets & alerts > Create budget**. Use a very small amount
   and thresholds such as 1%, 50%, 90%, and 100%. Remember that alerts normally
   do not stop usage.
4. Install Google Cloud CLI, then run the following in PowerShell with your own
   project ID:

```powershell
$PROJECT_ID = "your-gcp-project-id"
$REGION = "europe-north1"
$REPOSITORY = "manhwa"
$JOB = "manhwa-pipeline"
$API_SERVICE = "manhwa-api"
$API_SA = "manhwa-api-sa@$PROJECT_ID.iam.gserviceaccount.com"
$WORKER_SA = "manhwa-worker-sa@$PROJECT_ID.iam.gserviceaccount.com"

gcloud auth login
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
```

`gcloud auth application-default login` is only needed if you run the API
locally with `PIPELINE_EXECUTION_MODE=cloud_run`. It is not used by deployed
Cloud Run resources.

### Create the repository and service accounts

```powershell
gcloud artifacts repositories create $REPOSITORY --repository-format=docker --location=$REGION --description="Manhwa API and worker images"
gcloud iam service-accounts create manhwa-api-sa --display-name="Manhwa Cloud Run API"
gcloud iam service-accounts create manhwa-worker-sa --display-name="Manhwa pipeline worker"
```

Do not choose **Create new key** on either service account. Cloud Run supplies
short-lived credentials automatically.

### Create backend secrets

Open **Security > Secret Manager > Create secret** and create:

- `supabase-service-role` containing `SUPABASE_SERVICE_ROLE_KEY`
- `groq-api-key` containing `GROQ_API_KEY`

For each secret, select it, open **Permissions**, and grant **Secret Manager
Secret Accessor** only as follows:

- `supabase-service-role`: API service account and worker service account
- `groq-api-key`: worker service account only

Do not make the Cognito IDs or Supabase URL secrets; they are configuration.

## 4. Build the two container images

From the repository root:

```powershell
Set-Location backend
gcloud builds submit --config cloudbuild.yaml --substitutions="_REGION=$REGION,_REPOSITORY=$REPOSITORY" .
```

This builds a small API image from `Dockerfile.api` and a separate OCR worker
image from `Dockerfile`. Do not enable paid Artifact Analysis/vulnerability
scanning for this cost-constrained test project.

## 5. Create the private Cloud Run Job

Create local, ignored configuration copies:

```powershell
Copy-Item deploy/worker.env.yaml.example deploy/worker.env.yaml
Copy-Item deploy/api.env.yaml.example deploy/api.env.yaml
```

Edit both files with the non-secret values for your project. Keep their exact
filenames; Git ignores them.

Create the worker job:

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
  --set-secrets "SUPABASE_SERVICE_ROLE_KEY=supabase-service-role:latest,GROQ_API_KEY=groq-api-key:latest"
```

Do not grant `allUsers` access to the job. Allow only the API service account to
run it with per-execution `JOB_ID` overrides:

```powershell
gcloud run jobs add-iam-policy-binding $JOB `
  --region $REGION `
  --member "serviceAccount:$API_SA" `
  --role "roles/run.jobsExecutorWithOverrides"
```

Cloud Run Jobs Executor With Overrides supplies the required
`run.jobs.runWithOverrides` permission without granting permission to edit or
delete the job. The grant is scoped to this job rather than the whole project.

## 6. Deploy the Cloud Run API

Before deploying, fill `deploy/api.env.yaml` with the exact Amplify origin in
`CORS_ALLOWED_ORIGINS`. An origin has no path and no trailing slash.

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

The service is public at the Cloud Run network layer because browsers cannot
present Google Cloud IAM credentials. Protected FastAPI routes independently
require and verify a Cognito access token. `/health` remains public.

Copy the displayed service URL into Amplify as `VITE_API_BASE_URL`, save, and
redeploy the Amplify branch.

## 7. Verification order

1. Open `https://YOUR_CLOUD_RUN_API_URL/health`; expect `{"status":"ok"}`.
2. Call `/jobs/upload-url` without a bearer token; expect HTTP 401.
3. Sign in through Google. In browser Network tools, confirm the sequence is
   Cognito -> Google -> Cognito `/oauth2/idpresponse` -> Amplify
   `/auth/callback`.
4. Upload a small PDF. Confirm the PDF request goes to Supabase storage, not
   through the Cloud Run API request body.
5. In **Cloud Run > Jobs > manhwa-pipeline > Executions**, confirm one execution
   starts and completes.
6. In Supabase, confirm the row contains the Cognito `sub`, `started_at`, and
   final status. User B must receive 404 for User A's job ID.
7. Confirm the `pdfs`, `pages`, and `audio` public object URLs fail while signed
   URLs returned by `/jobs/{id}/assets` work.

## Cost checks after deployment

- **Cloud Run > Metrics**: API instances should return to zero; job retries must
  remain zero.
- **Artifact Registry > repository**: keep only the current API and worker
  versions. The PaddleOCR worker is likely larger than 0.5 GiB, so some image
  storage charge may remain even with no traffic.
- **Billing > Reports**: group by SKU and check Cloud Run, Artifact Registry,
  Cloud Build, networking, and Secret Manager.
- **Billing > Budgets & alerts**: verify your email receives alerts.
- Keep `MAX_PIPELINE_STARTS_GLOBAL_30D=10` or lower. Increasing it expands cost
  exposure.
- Review Supabase, Groq, Edge TTS, and AWS quotas separately; Google Cloud
  budgets do not cover third-party or AWS usage.

For a hard zero-spend guarantee, do not attach a paid billing account and do not
deploy Cloud Run. Run the backend locally instead. With a linked billing account,
this architecture minimizes and limits usage but cannot promise a zero invoice.
