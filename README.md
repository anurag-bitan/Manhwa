# Manhwa to Hindi Video

React frontend (Vercel) and FastAPI + OCR worker (Modal). Auth is Firebase; jobs and files live in Supabase; video muxing runs in the browser.

## Layout

- `frontend/` — Vite app
- `backend/` — FastAPI API, Modal worker (`modal_app.py`), local Docker
- `backend/db/schema.sql` — full Supabase schema (run once in the SQL editor; safe to re-run)
- `scripts/deploy-modal.ps1` / `scripts/deploy-vercel.ps1`

## Local

```powershell
Copy-Item frontend/.env.example frontend/.env
Copy-Item backend/.env.example backend/.env
```

Fill Supabase, Firebase, and `GEMINI_API_KEY`. Local API uses `PIPELINE_EXECUTION_MODE=local`.

```powershell
Set-Location frontend
npm ci
npm run dev
```

```powershell
Set-Location backend
docker compose up --build
```

API: `http://localhost:8000`. Point `VITE_API_BASE_URL` at that URL and restart Vite.

## Deploy

1. Run `backend/db/schema.sql` in the Supabase SQL editor (if not already applied).
2. Create Modal environments `staging` / `production` and a secret named `manhwa-backend-secrets` (same keys as `backend/.env.example`, plus `PIPELINE_EXECUTION_MODE=modal` and `CORS_ALLOWED_ORIGINS` for the Vercel origin).
3. Cap Modal workspace spend if you use the Starter credit.
4. Deploy:

```powershell
python -m pip install -r backend/requirements-modal.txt
python -m modal setup
.\scripts\deploy-modal.ps1 -Environment staging
.\scripts\deploy-modal.ps1 -Environment production
```

5. Set Vercel `VITE_API_BASE_URL` to the printed `https://…modal.run` URL (no trailing slash) and **redeploy** the frontend. `VITE_*` is baked in at build time.

Never commit `.env` files, Firebase JSON, or Modal tokens.
