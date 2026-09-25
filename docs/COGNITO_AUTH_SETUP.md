# Deprecated: Amazon Cognito authentication

Authentication now uses **Firebase Auth** (Google + email/password). See
[GCP_DEPLOYMENT.md](GCP_DEPLOYMENT.md).

The `cognito_sub` column in `processing_jobs` still exists but stores the
Firebase user `uid` for job ownership and quota checks.
