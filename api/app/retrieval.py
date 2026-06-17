"""Recommendation pipeline.

The goal is to capture the *essence* of the user's prompt, not just obvious
genre/director matches. Strategy:

1. Embed the raw prompt (BGE-M3 is multilingual, so Portuguese prompts match
   English movie text) and retrieve a candidate pool via `match_movie`.
2. Query expansion: map the prompt to known catalog keywords via
   `match_keyword`. Keywords above a similarity threshold are appended to the
   prompt, which is re-embedded and matched again. This pulls in movies whose
   synopsis wording differs from the user's but share the same concepts.
3. Fuse both rankings with Reciprocal Rank Fusion (RRF), which rewards movies
   that appear well-ranked in *both* lists without depending on raw score
   scales.
4. Final score blends RRF with a small quality prior (vote_average). In
   discovery mode, the most popular candidates get a mild penalty so less
   obvious picks can surface.

The reduced Supabase database holds only the `movie` and `keyword` vector
indexes (see supabase/supabase-vector-schema.md). Director/cast signal must be
folded into the movie embedding text at ingestion time (e.g. `Director:` /
`Cast:` lines), since person/company tables are not stored in Supabase.
"""

import asyncio
from typing import Any

from .config import Settings
from .embeddings import EmbeddingClient
from .schemas import MovieResult, RecommendMeta, RecommendRequest, RecommendResponse
from .supabase import SupabaseClient
from .tmdb import TMDbClient


def _rrf_fuse(
    rankings: list[list[dict[str, Any]]], k: int
) -> dict[int, dict[str, Any]]:
    """Reciprocal Rank Fusion keyed by movie_id.

    Returns {movie_id: {"rrf": score, "row": best_row, "similarity": max_sim}}.
    """
    fused: dict[int, dict[str, Any]] = {}
    for ranking in rankings:
        for rank, row in enumerate(ranking):
            movie_id = row["movie_id"]
            entry = fused.setdefault(
                movie_id, {"rrf": 0.0, "row": row, "similarity": 0.0}
            )
            entry["rrf"] += 1.0 / (k + rank + 1)
            similarity = float(row.get("similarity") or 0.0)
            if similarity > entry["similarity"]:
                entry["similarity"] = similarity
                entry["row"] = row
    return fused


def _final_score(
    entry: dict[str, Any],
    max_rrf: float,
    popularity_cutoff: float | None,
    settings: Settings,
) -> float:
    score = entry["rrf"] / max_rrf if max_rrf > 0 else 0.0

    vote_average = entry["row"].get("vote_average")
    if vote_average:
        quality = max(0.0, min(float(vote_average) / 10.0, 1.0))
        score = score * (1 - settings.quality_weight) + quality * settings.quality_weight

    # Discovery mode: nudge down the most popular candidates of this pool.
    if popularity_cutoff is not None:
        popularity = float(entry["row"].get("popularity") or 0)
        if popularity >= popularity_cutoff:
            score *= 0.85

    return score


class Recommender:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embeddings = EmbeddingClient(settings)
        self.supabase = SupabaseClient(settings)
        self.tmdb = TMDbClient(settings)

    async def recommend(self, request: RecommendRequest) -> RecommendResponse:
        settings = self.settings
        pool = settings.candidate_pool_size

        query_vector = await self.embeddings.embed(request.query)

        direct_movies, keyword_rows = await asyncio.gather(
            self.supabase.match_movie(query_vector, pool),
            self.supabase.match_keyword(query_vector, settings.keyword_match_count),
        )

        expansion_keywords = [
            row["keyword"]
            for row in keyword_rows
            if float(row.get("similarity") or 0) >= settings.keyword_similarity_threshold
        ][: settings.max_expansion_keywords]

        rankings = [direct_movies]
        if expansion_keywords:
            expanded_text = f"{request.query}\nKeywords: {', '.join(expansion_keywords)}"
            expanded_vector = await self.embeddings.embed(expanded_text)
            expanded_movies = await self.supabase.match_movie(expanded_vector, pool)
            rankings.append(expanded_movies)

        fused = _rrf_fuse(rankings, settings.rrf_k)

        popularity_cutoff = None
        if request.discovery and fused:
            popularities = sorted(
                float(e["row"].get("popularity") or 0) for e in fused.values()
            )
            # Top ~25% most popular of the candidate pool get penalized.
            popularity_cutoff = popularities[int(len(popularities) * 0.75)]

        max_rrf = max((e["rrf"] for e in fused.values()), default=0.0)
        ranked = sorted(
            fused.values(),
            key=lambda e: _final_score(e, max_rrf, popularity_cutoff, settings),
            reverse=True,
        )[: request.limit]

        enrichment = await self.tmdb.enrich([e["row"]["movie_id"] for e in ranked])

        results = []
        for entry in ranked:
            row = entry["row"]
            movie_id = row["movie_id"]
            extra = enrichment.get(movie_id, {})
            results.append(
                MovieResult(
                    movie_id=movie_id,
                    title=row.get("original_title") or f"Movie {movie_id}",
                    genres=row.get("genres") or [],
                    origin_country=row.get("origin_country") or [],
                    release_date=row.get("release_date"),
                    vote_average=row.get("vote_average"),
                    similarity=round(entry["similarity"], 4),
                    score=round(
                        _final_score(entry, max_rrf, popularity_cutoff, settings), 4
                    ),
                    poster_url=extra.get("poster_url"),
                    overview=extra.get("overview"),
                )
            )

        return RecommendResponse(
            query=request.query,
            expanded_keywords=expansion_keywords,
            results=results,
            meta=RecommendMeta(
                embedding_provider=self.embeddings.provider,
                tmdb_enriched=bool(enrichment),
                discovery=request.discovery,
                candidates_considered=len(fused),
            ),
        )
