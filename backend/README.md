# Manhwa AI backend

FastAPI API with a detached Modal OCR → Gemini/DeepSeek → TTS worker.

## Production (Modal)

Deploy `modal_app.py` with [`scripts/deploy-modal.ps1`](../scripts/deploy-modal.ps1).

See **[docs/MODAL_VERCEL.md](../docs/MODAL_VERCEL.md)** for secrets, model
preparation, budget controls, staging validation, cutover, and rollback.

The existing Render deployment remains available as a rollback until Modal has
passed manual production acceptance. Its instructions are in
**[docs/RENDER_VERCEL.md](../docs/RENDER_VERCEL.md)**.

## Health check

`GET /health` — no authentication required.

## Local

```powershell
docker compose up --build
```

API on `http://localhost:8000`.

`docker-compose.yml` mounts `FIREBASE_SERVICE_ACCOUNT_PATH` from `.env` (your host JSON file) into the container at `/run/secrets/firebase-sa.json`. Without this mount, API calls return **401** and the upload page sends you back to login.
