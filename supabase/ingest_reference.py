"""Referência de ingestão BGE-M3 → Supabase (compatível com o retrieval da API).

NÃO é um pipeline completo — é um molde mostrando exatamente:
  1. o TEXTO de embedding que o retrieval espera (igual ao supabase-vector-schema.md);
  2. como gerar o vetor DENSO de 1024 dims com FlagEmbedding (BGE-M3);
  3. como inserir nas tabelas `movie` e `keyword` via PostgREST.

Pré-requisitos:
    pip install FlagEmbedding httpx
    # alternativa: sentence-transformers (veja embed_st abaixo)

Pontos críticos de COMPATIBILIDADE com a query (lado da API):
  - Use SOMENTE o vetor denso (`dense_vecs`). BGE-M3 também emite sparse/ColBERT — ignore.
  - NÃO adicione prefixo de instrução ("Represent this sentence...") — BGE-M3 não usa.
  - Distância é cosseno, então normalização L2 não altera o ranking (pode normalizar ou não).
"""

import os

import httpx

# ---------------------------------------------------------------------------
# 1) Embedder local (gera o vetor denso 1024d)
# ---------------------------------------------------------------------------
from FlagEmbedding import BGEM3FlagModel

_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)


def embed(texts: list[str]) -> list[list[float]]:
    """Retorna os vetores densos (1024d) — o único output usado pelo retrieval."""
    out = _model.encode(texts, batch_size=12, max_length=8192)["dense_vecs"]
    return [vec.tolist() for vec in out]


# Alternativa com sentence-transformers (mesmo modelo/vetores):
#   from sentence_transformers import SentenceTransformer
#   _model = SentenceTransformer("BAAI/bge-m3")
#   def embed(texts): return _model.encode(texts, normalize_embeddings=True).tolist()


# ---------------------------------------------------------------------------
# 2) Texto de embedding (DEVE seguir este formato — ver supabase-vector-schema.md)
# ---------------------------------------------------------------------------
def movie_text(m: dict) -> str:
    """`m` é um dict com os campos do filme (ex.: vindo do TMDb/seus dados).

    Dica p/ recomendações menos óbvias: inclua diretor, roteirista e elenco
    principal (Director/Writer/Cast) — o retrieval passa a captar a 'assinatura'
    da equipe sem nenhuma mudança na API."""
    genres = ", ".join(m.get("genres", []))
    keywords = ", ".join(m.get("keywords", []))
    parts = [
        f"Original Title: {m.get('original_title', '')}",
        f"Release Date: {m.get('release_date', '')}",
        f"Genres: {genres}",
        f"Keywords: {keywords}",
        f"Overview: {m.get('overview', '')}",
        f"Synopsis: {m.get('synopsis', '')}",
    ]
    # Opcional (recomendado para captar a essência da equipe):
    if m.get("director"):
        parts.append(f"Director: {m['director']}")
    if m.get("cast"):
        parts.append(f"Cast: {', '.join(m['cast'][:8])}")
    return "\n".join(parts)


def keyword_text(keyword: str) -> str:
    return f"Movie keyword: {keyword}"


# ---------------------------------------------------------------------------
# 3) Inserção via PostgREST (upsert)
# ---------------------------------------------------------------------------
def _rest_base() -> str:
    ref = os.environ["SUPABASE_URL"].rstrip("/").rsplit("/", 1)[-1]
    return f"https://{ref}.supabase.co/rest/v1"


def _headers() -> dict:
    key = os.environ["SUPABASE_API_SECRET_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",  # upsert
    }


def upsert_movies(movies: list[dict]) -> None:
    """`movies`: lista de dicts já com os campos do schema + 'vector' (lista 1024d).
    `id` e `movie_id` = TMDb id (um vetor por filme)."""
    rows = []
    for m in movies:
        rows.append(
            {
                "id": m["movie_id"],
                "movie_id": m["movie_id"],
                "genres": m.get("genres", []),
                "origin_country": m.get("origin_country", []),
                "original_title": m.get("original_title"),
                "popularity": m.get("popularity", 0),
                "release_date": m.get("release_date"),
                "vote_average": m.get("vote_average"),
                "vector": m["vector"],
            }
        )
    r = httpx.post(f"{_rest_base()}/movie", headers=_headers(), json=rows, timeout=60)
    r.raise_for_status()


def upsert_keywords(keywords: list[str]) -> None:
    vectors = embed([keyword_text(k) for k in keywords])
    rows = [{"keyword": k, "vector": v} for k, v in zip(keywords, vectors)]
    r = httpx.post(f"{_rest_base()}/keyword", headers=_headers(), json=rows, timeout=60)
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Exemplo mínimo de uso
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    example = {
        "movie_id": 27205,
        "original_title": "Inception",
        "release_date": "2010-07-16",
        "genres": ["Action", "Science Fiction", "Adventure"],
        "origin_country": ["United States"],
        "keywords": ["dream", "subconscious", "heist"],
        "overview": "A thief who steals corporate secrets through dream-sharing...",
        "synopsis": "",
        "popularity": 35000,
        "vote_average": 8.4,
        "director": "Christopher Nolan",
        "cast": ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Elliot Page"],
    }
    example["vector"] = embed([movie_text(example)])[0]
    upsert_movies([example])
    upsert_keywords(["dream", "subconscious", "heist"])
    print("inserido:", len(example["vector"]), "dims")
