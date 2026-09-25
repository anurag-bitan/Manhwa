# Deprecated: AWS Amplify + Cognito deployment

This project now runs fully on Google Cloud (Firebase Hosting, Firebase Auth,
Cloud Run, Vertex Gemini). Use [GCP_DEPLOYMENT.md](GCP_DEPLOYMENT.md) instead.

The `cognito_sub` database column is retained for job ownership but now stores
the Firebase user `uid`.
