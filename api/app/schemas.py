"""Pydantic models for the public API."""

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    limit: int = Field(default=12, ge=1, le=40)
    # Discovery mode slightly penalizes very popular titles so the ranking
    # surfaces less obvious picks.
    discovery: bool = False


class MovieResult(BaseModel):
    movie_id: int
    title: str
    genres: list[str] = []
    origin_country: list[str] = []
    release_date: str | None = None
    vote_average: float | None = None
    similarity: float
    score: float
    poster_url: str | None = None
    overview: str | None = None


class RecommendMeta(BaseModel):
    embedding_provider: str
    tmdb_enriched: bool
    discovery: bool
    candidates_considered: int


class RecommendResponse(BaseModel):
    query: str
    expanded_keywords: list[str] = []
    results: list[MovieResult]
    meta: RecommendMeta


class HealthResponse(BaseModel):
    status: str
    supabase: bool
    embedding_provider: str
    embedding_ready: bool
    tmdb_enabled: bool
