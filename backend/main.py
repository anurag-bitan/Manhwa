import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
from api.routers import upload
from api.routers import jobs
from api.routers import context
from core.auth import AuthenticatedUser, get_current_user
from core.config import settings
from db.supabase_admin import supabase_admin

app = FastAPI(title="Manhwa Video Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(context.router)


@app.get("/")
async def root():
    return {"message": "Backend is running!"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/db-test")
async def db_test(
    _current_user: AuthenticatedUser = Depends(get_current_user),
):
    # Try a simple query to see if Supabase works
    try:
        # Fetch one row from processing_jobs (might be empty)
        data = supabase_admin.table("processing_jobs").select("id").limit(1).execute()
        return {"db_connected": True, "rows": len(data.data)}
    except Exception:
        return {"db_connected": False}
