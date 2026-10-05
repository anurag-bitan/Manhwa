# Manhwa AI backend

FastAPI service with an embedded OCR → Gemini → TTS pipeline (`PIPELINE_EXECUTION_MODE=local`).

## Production (Render)

Deploy via the repo root [`render.yaml`](../render.yaml) Blueprint or a Render Web Service using this folder as the Docker context.

See **[docs/RENDER_VERCEL.md](../docs/RENDER_VERCEL.md)** for environment variables and steps.

## Health check

`GET /health` — no authentication required.

## Local

```powershell
docker compose up --build
```

API on `http://localhost:8000`.

`docker-compose.yml` mounts `FIREBASE_SERVICE_ACCOUNT_PATH` from `.env` (your host JSON file) into the container at `/run/secrets/firebase-sa.json`. Without this mount, API calls return **401** and the upload page sends you back to login.
