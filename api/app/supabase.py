"""Thin async client for the Supabase PostgREST RPC functions.

We call PostgREST directly instead of pulling in supabase-py: the API only
needs the four `match_*` RPCs and this keeps the serverless bundle small.
"""

from typing import Any

import httpx

from .config import Settings


class SupabaseError(RuntimeError):
    pass


class SupabaseClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.supabase_rest_url
        self.headers = {
            "apikey": settings.supabase_key,
            "Authorization": f"Bearer {settings.supabase_key}",
            "Content-Type": "application/json",
        }

    async def _rpc(self, function: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/rpc/{function}",
                headers=self.headers,
                json=payload,
            )
        if response.status_code != 200:
            raise SupabaseError(
                f"RPC {function} failed ({response.status_code}): {response.text[:300]}"
            )
        return response.json()

    @staticmethod
    def _to_pgvector(vector: list[float]) -> str:
        return "[" + ",".join(f"{x:.8f}" for x in vector) + "]"

    async def match_movie(self, vector: list[float], count: int) -> list[dict[str, Any]]:
        return await self._rpc(
            "match_movie",
            {"query_embedding": self._to_pgvector(vector), "match_count": count},
        )

    async def match_keyword(self, vector: list[float], count: int) -> list[dict[str, Any]]:
        return await self._rpc(
            "match_keyword",
            {"query_embedding": self._to_pgvector(vector), "match_count": count},
        )

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/movie?select=id&limit=1",
                    headers=self.headers,
                )
            return response.status_code == 200
        except httpx.HTTPError:
            return False
