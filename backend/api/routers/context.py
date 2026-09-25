from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.auth import AuthenticatedUser, get_current_user
from core.gemini_client import fetch_grounded_context


router = APIRouter(prefix="/context", tags=["context"])


class ContextPreviewRequest(BaseModel):
    manhwa_name: str = Field(min_length=1, max_length=200)
    season: str = Field(default="", max_length=50)
    chapter_number: str = Field(default="", max_length=50)
    genre: str = Field(default="", max_length=100)


@router.post("/preview")
async def preview_context(
    request: ContextPreviewRequest,
    _current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Prefetch a short search-grounded manhwa blurb (max 50 words)."""
    result = fetch_grounded_context(
        request.manhwa_name,
        season=request.season,
        chapter_number=request.chapter_number,
        genre=request.genre,
    )
    return {
        "context": result["context"],
        "grounded": result["grounded"],
        "word_count": result["word_count"],
    }
