"""Application settings loaded from environment variables / .env files."""

import re
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DASHBOARD_URL_RE = re.compile(r"supabase\.com/dashboard/project/(?P<ref>[a-z0-9]+)")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # In local dev the shared .env lives at the monorepo root; on Vercel
        # everything comes from real environment variables.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Supabase ---
    supabase_url: str = ""
    supabase_api_secret_key: str = ""
    supabase_api_publishable_key: str = ""

    # --- Embeddings ---
    # Providers: "hf" (Hugging Face Inference API), "deepinfra",
    # "cloudflare" (Workers AI) or "mock" (deterministic vectors for dev/tests).
    embedding_provider: str = "hf"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    hf_token: str = ""
    deepinfra_api_key: str = ""
    cf_account_id: str = ""
    cf_api_token: str = ""

    # --- TMDb enrichment (optional: posters + overview) ---
    tmdb_api_key: str = ""

    # --- Retrieval tuning ---
    candidate_pool_size: int = 40  # candidates fetched per match_movie call
    keyword_match_count: int = 12  # keywords fetched for query expansion
    keyword_similarity_threshold: float = 0.55
    max_expansion_keywords: int = 6
    rrf_k: int = 60
    quality_weight: float = 0.12  # how much vote_average influences final rank

    # --- CORS ---
    frontend_origin: str = "*"

    @property
    def supabase_rest_url(self) -> str:
        """Project REST endpoint, accepting either the project API URL or the
        dashboard URL (https://supabase.com/dashboard/project/<ref>) in env."""
        url = self.supabase_url.strip().rstrip("/")
        match = _DASHBOARD_URL_RE.search(url)
        if match:
            return f"https://{match.group('ref')}.supabase.co/rest/v1"
        return f"{url}/rest/v1"

    @property
    def supabase_key(self) -> str:
        return self.supabase_api_secret_key or self.supabase_api_publishable_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
