"""Pipeline tests with a faked Supabase layer (no network needed).

Run: .venv/Scripts/python -m pytest tests/ -q  (or python tests/test_retrieval.py)
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["EMBEDDING_PROVIDER"] = "mock"

from app.config import Settings  # noqa: E402
from app.retrieval import Recommender, _rrf_fuse  # noqa: E402
from app.schemas import RecommendRequest  # noqa: E402


def make_movie(movie_id, title, similarity, popularity=10, vote=7.0):
    return {
        "id": movie_id,
        "movie_id": movie_id,
        "genres": ["Drama"],
        "origin_country": ["United States"],
        "original_title": title,
        "popularity": popularity,
        "release_date": "2010-01-01",
        "vote_average": vote,
        "similarity": similarity,
    }


class FakeSupabase:
    """match_movie returns different rankings depending on the query vector,
    emulating direct vs keyword-expanded retrieval."""

    def __init__(self):
        self.calls = 0

    async def match_movie(self, vector, count):
        self.calls += 1
        if self.calls == 1:  # direct query
            return [
                make_movie(1, "Movie A", 0.80),
                make_movie(2, "Movie B", 0.75),
                make_movie(3, "Movie C", 0.70),
            ]
        return [  # expanded query: B rises, D appears
            make_movie(2, "Movie B", 0.82),
            make_movie(4, "Movie D", 0.78, popularity=999),
            make_movie(1, "Movie A", 0.71),
        ]

    async def match_keyword(self, vector, count):
        return [
            {"keyword": "dystopia", "similarity": 0.71},
            {"keyword": "memory loss", "similarity": 0.66},
            {"keyword": "unrelated", "similarity": 0.20},  # below threshold
        ]


def test_rrf_fuse_dedupes_and_keeps_best_similarity():
    fused = _rrf_fuse(
        [
            [make_movie(1, "A", 0.8), make_movie(2, "B", 0.7)],
            [make_movie(2, "B", 0.9)],
        ],
        k=60,
    )
    assert set(fused) == {1, 2}
    assert fused[2]["similarity"] == 0.9
    # Movie 2 appears in both lists, so its RRF must beat movie 1's.
    assert fused[2]["rrf"] > fused[1]["rrf"]
    print("ok: rrf fusion dedupes and rewards cross-list presence")


def test_pipeline_expands_keywords_and_ranks():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_api_secret_key="test",
        embedding_provider="mock",
        tmdb_api_key="",
    )
    recommender = Recommender(settings)
    fake = FakeSupabase()
    recommender.supabase = fake

    response = asyncio.run(
        recommender.recommend(
            RecommendRequest(query="sci-fi about memory", limit=10)
        )
    )

    # Keyword expansion: only keywords above the 0.55 threshold survive.
    assert response.expanded_keywords == ["dystopia", "memory loss"]
    # Both retrieval passes ran.
    assert fake.calls == 2
    # All four movies present, deduped.
    ids = [r.movie_id for r in response.results]
    assert sorted(ids) == [1, 2, 3, 4]
    # Movie B (top-ranked in both lists) must be first.
    assert ids[0] == 2
    assert response.meta.candidates_considered == 4
    print("ok: pipeline expands keywords, fuses and ranks; order:", ids)


def test_discovery_mode_penalizes_popular():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_api_secret_key="test",
        embedding_provider="mock",
        tmdb_api_key="",
    )
    recommender = Recommender(settings)
    recommender.supabase = FakeSupabase()
    normal = asyncio.run(
        recommender.recommend(RecommendRequest(query="sci-fi", limit=10))
    )

    recommender.supabase = FakeSupabase()
    discovery = asyncio.run(
        recommender.recommend(
            RecommendRequest(query="sci-fi", limit=10, discovery=True)
        )
    )

    def position(resp, movie_id):
        return [r.movie_id for r in resp.results].index(movie_id)

    # Movie 4 has popularity 999; discovery mode must not improve its rank.
    assert position(discovery, 4) >= position(normal, 4)
    print("ok: discovery mode does not boost very popular titles")


if __name__ == "__main__":
    test_rrf_fuse_dedupes_and_keeps_best_similarity()
    test_pipeline_expands_keywords_and_ranks()
    test_discovery_mode_penalizes_popular()
    print("all tests passed")
