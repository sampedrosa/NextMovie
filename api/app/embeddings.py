"""Query embedding providers.

The Supabase index was built with BAAI/bge-m3 (1024-dim, cosine), so query
vectors must come from the same model. BGE-M3 is too large to run inside a
Vercel serverless function, so we call a hosted inference endpoint. The
provider is selected via EMBEDDING_PROVIDER:

- "hf":         Hugging Face Inference API (needs HF_TOKEN)
- "deepinfra":  DeepInfra OpenAI-compatible endpoint (needs DEEPINFRA_API_KEY)
- "cloudflare": Cloudflare Workers AI (needs CF_ACCOUNT_ID + CF_API_TOKEN)
- "mock":       deterministic pseudo-random vectors, for local dev and tests
"""

import hashlib
import math
import random

import httpx

from .config import Settings


class EmbeddingError(RuntimeError):
    pass


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


class EmbeddingClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def provider(self) -> str:
        return self.settings.embedding_provider.lower()

    def is_configured(self) -> bool:
        s = self.settings
        return {
            "hf": bool(s.hf_token),
            "deepinfra": bool(s.deepinfra_api_key),
            "cloudflare": bool(s.cf_account_id and s.cf_api_token),
            "mock": True,
        }.get(self.provider, False)

    async def embed(self, text: str) -> list[float]:
        provider = self.provider
        if provider == "hf":
            vector = await self._embed_hf(text)
        elif provider == "deepinfra":
            vector = await self._embed_deepinfra(text)
        elif provider == "cloudflare":
            vector = await self._embed_cloudflare(text)
        elif provider == "mock":
            vector = self._embed_mock(text)
        else:
            raise EmbeddingError(f"Unknown embedding provider: {provider}")

        if len(vector) != self.settings.embedding_dim:
            raise EmbeddingError(
                f"Provider returned {len(vector)} dims, "
                f"expected {self.settings.embedding_dim}"
            )
        return _l2_normalize(vector)

    async def _embed_hf(self, text: str) -> list[float]:
        url = (
            "https://router.huggingface.co/hf-inference/models/"
            f"{self.settings.embedding_model}/pipeline/feature-extraction"
        )
        # x-wait-for-model avoids 503s while the model cold-starts on HF's side;
        # the long timeout covers that first load (warm calls are ~0.4s).
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.hf_token}",
                    "x-wait-for-model": "true",
                },
                json={"inputs": text},
            )
        if response.status_code != 200:
            raise EmbeddingError(f"HF API error {response.status_code}: {response.text[:300]}")
        data = response.json()
        # The API returns [dims] for a single string input, or [[dims]] when
        # batched / depending on backend version.
        if isinstance(data[0], list):
            data = data[0]
        return data

    async def _embed_deepinfra(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.deepinfra.com/v1/openai/embeddings",
                headers={"Authorization": f"Bearer {self.settings.deepinfra_api_key}"},
                json={"model": self.settings.embedding_model, "input": text},
            )
        if response.status_code != 200:
            raise EmbeddingError(
                f"DeepInfra error {response.status_code}: {response.text[:300]}"
            )
        return response.json()["data"][0]["embedding"]

    async def _embed_cloudflare(self, text: str) -> list[float]:
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.settings.cf_account_id}/ai/run/@cf/baai/bge-m3"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {self.settings.cf_api_token}"},
                json={"text": [text]},
            )
        if response.status_code != 200:
            raise EmbeddingError(
                f"Cloudflare error {response.status_code}: {response.text[:300]}"
            )
        return response.json()["result"]["data"][0]

    def _embed_mock(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1, 1) for _ in range(self.settings.embedding_dim)]
