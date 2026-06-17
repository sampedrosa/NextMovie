"""Optional TMDb enrichment: posters and overviews for recommended movies.

The Supabase vector index stores only retrieval metadata (title, genres,
dates, votes). When TMDB_API_KEY is set we fetch poster + overview from the
TMDb API using the stored TMDb movie ids; otherwise cards render without
posters and the app still works.
"""

import asyncio
from typing import Any

import httpx

from .config import Settings

POSTER_BASE_URL = "https://image.tmdb.org/t/p/w342"

# Simple per-instance cache; serverless instances are short lived, but warm
# invocations still benefit.
_cache: dict[int, dict[str, Any]] = {}


class TMDbClient:
    def __init__(self, settings: Settings):
        self.api_key = settings.tmdb_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _request_args(self, movie_id: int) -> dict[str, Any]:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        params = {"language": "pt-BR"}
        headers = {}
        # TMDb v4 read tokens are long JWTs used as Bearer; v3 keys are short
        # 32-char strings passed as a query param.
        if len(self.api_key) > 40:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            params["api_key"] = self.api_key
        return {"url": url, "params": params, "headers": headers}

    async def _fetch_one(self, client: httpx.AsyncClient, movie_id: int) -> None:
        if movie_id in _cache:
            return
        try:
            args = self._request_args(movie_id)
            response = await client.get(
                args["url"], params=args["params"], headers=args["headers"]
            )
            if response.status_code != 200:
                return
            data = response.json()
            poster_path = data.get("poster_path")
            _cache[movie_id] = {
                "poster_url": f"{POSTER_BASE_URL}{poster_path}" if poster_path else None,
                "overview": data.get("overview") or None,
            }
        except httpx.HTTPError:
            return

    async def enrich(self, movie_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Fetch poster/overview for the given TMDb ids. Best effort: failures
        simply leave movies un-enriched."""
        if not self.enabled or not movie_ids:
            return {}
        async with httpx.AsyncClient(timeout=10) as client:
            await asyncio.gather(*(self._fetch_one(client, mid) for mid in movie_ids))
        return {mid: _cache[mid] for mid in movie_ids if mid in _cache}
