"""NextMovie API — semantic movie recommendations over a Supabase vector index."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .embeddings import EmbeddingClient, EmbeddingError
from .retrieval import Recommender
from .schemas import HealthResponse, RecommendRequest, RecommendResponse
from .supabase import SupabaseClient, SupabaseError

settings = get_settings()

app = FastAPI(
    title="NextMovie API",
    description="Recomendação semântica de filmes a partir de um prompt livre.",
    version="0.1.0",
)

origins = (
    ["*"]
    if settings.frontend_origin in ("", "*")
    else [o.strip() for o in settings.frontend_origin.split(",")]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

recommender = Recommender(settings)


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "nextmovie-api", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health", response_model=HealthResponse)
async def health():
    supabase_ok = await SupabaseClient(settings).ping()
    embedding_client = EmbeddingClient(settings)
    return HealthResponse(
        status="ok",
        supabase=supabase_ok,
        embedding_provider=embedding_client.provider,
        embedding_ready=embedding_client.is_configured(),
        tmdb_enabled=bool(settings.tmdb_api_key),
    )


@app.post("/api/recommend", response_model=RecommendResponse)
async def recommend(request: RecommendRequest):
    try:
        return await recommender.recommend(request)
    except EmbeddingError as error:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {error}")
    except SupabaseError as error:
        raise HTTPException(status_code=502, detail=f"Vector search failed: {error}")
