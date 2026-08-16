# Manhwa to Hindi Video Platform

Monorepo for the Manhwa AI frontend and processing backend.

## Repository layout

- `frontend/` — React + Vite web application, deployed with AWS Amplify Hosting
- `backend/` — FastAPI API plus an on-demand Cloud Run OCR/LLM/TTS job
- `docs/` — Cognito and deployment-related setup notes
- `amplify.yml` — Amplify monorepo build specification

## Local development

Create local environment files from the committed examples. Never commit the
real `.env` files.

```powershell
Copy-Item frontend/.env.example frontend/.env
Copy-Item backend/.env.example backend/.env
```

Run the frontend:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Run the backend stack after configuring `backend/.env`:

```powershell
Set-Location backend
docker compose up --build
```

Amplify must use `frontend` as the monorepo application root. Production uses a
small Cloud Run API and a separate on-demand Cloud Run Job; neither runs in
Amplify Hosting. See `docs/HYBRID_AWS_GCP_DEPLOYMENT.md` for the complete setup.
