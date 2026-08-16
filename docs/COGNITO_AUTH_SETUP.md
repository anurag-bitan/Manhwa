# Cognito authentication and deployment

## What is protected

The home, documentation, and contact pages remain public. `/upload` requires a
Cognito session. The browser obtains a Cognito **access token** with Amplify and
sends it as `Authorization: Bearer <token>` to every job API call.

FastAPI does not trust the frontend login state. It verifies the token's RS256
signature against the pool's JWKS, then checks `exp`, `iat`, `iss`, `token_use`,
and `client_id`. New Supabase jobs store the verified immutable Cognito `sub`.
Status and asset queries match both `job_id` and `cognito_sub`, returning 404 for
another user's job. Supabase files are served with two-hour signed URLs.

## Safe deployment order

1. Back up the Supabase database.
2. Run `backend/db/migrations/001_cognito_job_ownership.sql`, then
   `backend/db/migrations/002_pipeline_launch_quota.sql`, in the Supabase SQL
   editor. Confirm that the `pdfs`, `pages`, and `audio` buckets are private.
3. Review Supabase policies. The browser must not have a permissive `SELECT`
   policy on `processing_jobs` or `storage.objects`; only the backend service
   role should access these records directly.
4. Configure the Cognito pool and public app client as described below.
5. Set the frontend and backend environment variables to the same pool/client.
6. Install the updated backend requirements and deploy backend and worker.
7. Deploy the frontend, then run the verification checklist.

Existing `processing_jobs` rows have a null `cognito_sub` and are intentionally
not visible through the authenticated API. Do not backfill them to a user unless
you have a trustworthy ownership source.

## AWS IAM: what the operator and app need

The running React app and FastAPI service require **no IAM user, access key,
secret key, identity pool, or Cognito IAM role** for this flow. Browser sign-up
and sign-in are public Cognito operations. FastAPI only downloads public Cognito
signing keys and verifies JWTs locally. Never put AWS credentials or an app
client secret in `VITE_*` variables.

For a human who configures an **existing** pool, use an IAM Identity Center
permission set or assumed role and temporarily attach the AWS-managed
`AmazonCognitoPowerUser` policy. Remove it after setup and retain a read-only
operator role for normal inspection. AWS documents that this managed policy can
manage existing Cognito resources but cannot create a new pool; if a new pool is
needed, have an account administrator create it or grant a short-lived custom
role `cognito-idp:CreateUserPool` plus the required app-client update actions.
Avoid long-lived IAM-user access keys.

The backend deployment role should contain only permissions needed by its host
(for example ECS logs/secrets). Do not add `cognito-idp:*`; JWT verification
does not need it.

## Configure the Cognito user pool

Use the region in both app environments (currently `eu-north-1` in the local
frontend configuration).

1. Open **Amazon Cognito > User pools** and select the existing pool, or have an
   administrator create one.
2. Set the pool feature plan to **Essentials** or **Plus**. Passwordless email
   OTP through the `USER_AUTH` flow is unavailable on Lite.
3. Under **Sign-in**, use email as the sign-in identifier. Keep usernames case
   insensitive. Under choice-based sign-in, enable **Email message one-time
   password**.
4. Under **Sign-up**, enable self-service sign-up because the existing login form
   creates new users. Require and automatically verify the `email` attribute.
   If this is an invite-only app, disable self-service sign-up and replace the
   UI's `signUp` path before production.
5. Under **Applications > App clients**, create/select a **public client** for a
   single-page application. It must have **no client secret**.
6. Enable `ALLOW_USER_AUTH` (choice-based sign-in) and
   `ALLOW_REFRESH_TOKEN_AUTH`. Do not enable admin password flows for this app.
7. Set access-token and ID-token validity to 15 minutes. Choose a refresh-token
   lifetime appropriate to your policy (seven days is a reasonable starting
   point). Keep token revocation enabled.
8. Leave Google/social providers disabled until their redirect flow is actually
   configured. The current code intentionally reports `GoogleNotConfigured`.
9. For development, Cognito's default email sender is sufficient within its
   quota. For production, configure a verified Amazon SES identity, monitoring,
   and sending limits. Add AWS WAF rate controls/CAPTCHA if public self-sign-up
   is exposed to reduce OTP/email abuse.
10. Copy the **User pool ID** and **App client ID**. The client ID is public; a
    client secret must not exist for this browser client.

## Google sign-in through Cognito

Google sign-in uses Cognito's OAuth authorization-code flow with PKCE. The
browser redirects to Google through the Cognito user-pool domain; the Google
client secret is stored only in Cognito and never in this repository or an
Amplify environment variable.

### 1. Create the Google OAuth client

1. In Google Cloud Console, select or create a project.
2. Configure the OAuth consent screen. While the app is in testing, add every
   Google account that should be allowed to sign in as a test user.
3. Create an OAuth 2.0 client ID with application type **Web application**.
4. In Cognito, create/select the user-pool domain first. Then add this exact
   Google **Authorized redirect URI**:

   ```text
   https://YOUR_COGNITO_DOMAIN/oauth2/idpresponse
   ```

5. Copy the Google client ID and client secret for the Cognito configuration.

The Google redirect URI points to Cognito, not to Amplify. Do not add the
Google client secret to `VITE_*`, GitHub, or the frontend source.

### 2. Configure Google and OAuth in Cognito

1. Open the existing user pool in `eu-north-1` and create a Cognito domain
   under **Domain**. Record its hostname without `https://`.
2. Under **Social and external providers**, add **Google** with the Google
   client ID and secret. Request `openid email profile` and map Google's email
   claim to the mutable Cognito `email` attribute.
3. Open the existing public SPA app client and edit its managed-login/login-page
   configuration. Enable Google as an identity provider.
4. Enable only **Authorization code grant** for this browser flow and allow the
   `openid`, `email`, and `profile` scopes.
5. Register all exact callback URLs that will initiate sign-in:

   ```text
   http://localhost:5173/auth/callback
   https://YOUR_AMPLIFY_DOMAIN/auth/callback
   https://YOUR_CUSTOM_DOMAIN/auth/callback
   ```

6. Register the corresponding sign-out URLs:

   ```text
   http://localhost:5173/login
   https://YOUR_AMPLIFY_DOMAIN/login
   https://YOUR_CUSTOM_DOMAIN/login
   ```

Only keep URLs for environments that actually exist. Production callback URLs
must use HTTPS; Cognito permits HTTP only for localhost development.

### 3. Enable Google in the frontend host

Set these two Amplify branch environment variables, then redeploy the branch:

```dotenv
VITE_COGNITO_GOOGLE_ENABLED=true
VITE_COGNITO_DOMAIN=YOUR_COGNITO_DOMAIN
```

`VITE_COGNITO_DOMAIN` is a hostname such as
`manhwa-auth.auth.eu-north-1.amazoncognito.com`, without a protocol or trailing
slash. The application derives its callback and sign-out URLs from the current
browser origin, so the matching URLs must already be registered on the Cognito
app client.

### Existing email users and Google

Cognito does not automatically merge a native email-OTP user with a new Google
federated identity that has the same email. Test with a new Google account
first. If one person must use both methods while retaining one Cognito `sub`,
link the Google identity to the existing profile with a carefully reviewed
`AdminLinkProviderForUser` workflow before the first Google sign-in. Do not
automatically link accounts from an untrusted email claim: linking grants the
external identity access to the existing account.

## Environment variables

Frontend (`frontend/.env` locally and the frontend host in production):

```dotenv
VITE_API_BASE_URL=https://api.example.com
VITE_COGNITO_REGION=eu-north-1
VITE_COGNITO_USER_POOL_ID=eu-north-1_EXAMPLE
VITE_COGNITO_CLIENT_ID=exampleclientid
VITE_COGNITO_GOOGLE_ENABLED=false
VITE_COGNITO_DOMAIN=your-prefix.auth.eu-north-1.amazoncognito.com
```

Backend (`backend/.env` locally and a secret/config service in production):

```dotenv
COGNITO_REGION=eu-north-1
COGNITO_USER_POOL_ID=eu-north-1_EXAMPLE
COGNITO_APP_CLIENT_ID=exampleclientid
# Only for a pool configured with AWS's updated issuer type:
# COGNITO_ISSUER=https://issuer-cognito-idp.eu-north-1.amazonaws.com/eu-north-1_EXAMPLE
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://app.example.com
STORAGE_SIGNED_URL_TTL_SECONDS=7200
```

The three Cognito values must match across frontend and backend. If the pool
overview shows an updated issuer URL, set `COGNITO_ISSUER` to that exact URL;
otherwise leave it unset and the regional issuer is used. CORS origins
must be exact origins without paths or trailing slashes. Do not use `*` in
production. Keep `SUPABASE_SERVICE_ROLE_KEY` only in the backend secret store.

## Verification checklist

- `GET /health` returns 200 without a token.
- `POST /jobs/upload-url`, `POST /jobs/{id}/start`, `GET /jobs/{id}`,
  `GET /jobs/{id}/assets`, and `GET /db-test` return 401 without a bearer token.
- Email OTP signup and sign-in both complete, then `/upload` opens.
- The browser's job requests contain an access token in the Authorization
  header; tokens never appear in URLs or application logs.
- A valid **ID token** is rejected by FastAPI; only an access token works.
- User B receives 404 when requesting User A's job ID.
- New `processing_jobs` rows contain User A's Cognito `sub`.
- Asset responses use `/storage/v1/object/sign/` URLs and the equivalent public
  bucket URL does not work.
- After the access token expires, Amplify refreshes it. If refresh fails, the
  poll stops and the user is sent back to sign-in.

Offline JWT verification cannot instantly detect a token that was copied before
logout; the short 15-minute access-token lifetime limits that window. For an
immediate high-risk revocation requirement, add a server-side token denylist or
an online authorization layer rather than increasing token lifetime.
