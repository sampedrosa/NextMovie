from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Optional
from urllib.parse import urlparse

import numpy as np
import pandas as pd
from tqdm.auto import tqdm


BGE_M3_DIMENSION = 1024


@dataclass
class SupabaseConfig:
    url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    project_password: str = field(
        default_factory=lambda: os.getenv("SUPABASE_PROJECT_PASSWORD", "")
    )
    api_publishable_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_API_PUBLISHABLE_KEY", "")
    )
    api_secret_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_API_SECRET_KEY", "")
    )
    db_name: str = field(default_factory=lambda: os.getenv("SUPABASE_DB_NAME", "postgres"))
    db_user: str = field(default_factory=lambda: os.getenv("SUPABASE_DB_USER", "postgres"))
    db_port: int = field(default_factory=lambda: int(os.getenv("SUPABASE_DB_PORT", "5432")))
    db_host_override: str = field(default_factory=lambda: os.getenv("SUPABASE_DB_HOST", ""))
    sslmode: str = field(default_factory=lambda: os.getenv("SUPABASE_DB_SSLMODE", "require"))

    @property
    def project_ref(self) -> str:
        return extract_supabase_project_ref(self.url)

    @property
    def normalized_url(self) -> str:
        return f"https://{self.project_ref}.supabase.co"

    @property
    def db_host(self) -> str:
        if self.db_host_override:
            return self.db_host_override
        return f"db.{self.project_ref}.supabase.co"

    @property
    def dsn(self) -> str:
        if not self.project_ref:
            raise ValueError("SUPABASE_URL or project ref is required.")
        if not self.project_password:
            raise ValueError("SUPABASE_PROJECT_PASSWORD is required.")
        return (
            f"host={self.db_host} "
            f"port={self.db_port} "
            f"dbname={self.db_name} "
            f"user={self.db_user} "
            f"password={self.project_password} "
            f"sslmode={self.sslmode}"
        )


@dataclass
class EmbedderConfig:
    model_name: str = "BAAI/bge-m3"
    device: Optional[str] = None
    batch_size: int = 16
    normalize_embeddings: bool = True
    movie_chunk_chars: int = 5500
    movie_chunk_overlap_chars: int = 500
    max_overview_chars: int = 2500
    max_header_chars: int = 1800
    sqlite_path: Path = Path("movie.sqlite")
    parquet_dir: Path = Path("parquet")
    source: Literal["sqlite", "parquet"] = "sqlite"
    local_output_dir: Optional[Path] = None
    recreate_tables: bool = False
    create_vector_indexes: bool = True
    upsert_batch_size: int = 250


@dataclass
class EmbeddingRunResult:
    movie_rows: int
    person_rows: int
    company_rows: int
    keyword_rows: int
    movie_chunks: int


class MovieSupabaseEmbedder:
    """
    Gera embeddings BAAI/bge-m3 para movie/person/company/keyword
    e grava em tabelas Supabase com pgvector.

    Tabelas criadas/atualizadas:
    - movie: chunk index semantico de filmes
    - person: index semantico de pessoas
    - company: index semantico de produtoras
    - keyword: index semantico de keywords unicas
    """

    def __init__(
        self,
        embedder_config: Optional[EmbedderConfig] = None,
        supabase_config: Optional[SupabaseConfig] = None,
    ):
        self.embedder_config = embedder_config or EmbedderConfig()
        self.supabase_config = supabase_config or SupabaseConfig()
        self.embedder = None

    def run(self) -> EmbeddingRunResult:
        movie, person, company = self.load_tables()

        movie_index = self.build_movie_index(movie)
        person_index = self.build_person_index(person)
        company_index = self.build_company_index(company)
        keyword_index = self.build_keyword_index(movie)

        self.add_vectors(movie_index, text_column="embedding_text")
        self.add_vectors(person_index, text_column="embedding_text")
        self.add_vectors(company_index, text_column="embedding_text")
        self.add_vectors(keyword_index, text_column="embedding_text")

        if self.embedder_config.local_output_dir:
            self.save_local_parquets(
                movie_index=movie_index,
                person_index=person_index,
                company_index=company_index,
                keyword_index=keyword_index,
            )

        self.write_supabase(
            movie_index=movie_index,
            person_index=person_index,
            company_index=company_index,
            keyword_index=keyword_index,
        )

        return EmbeddingRunResult(
            movie_rows=len(movie),
            person_rows=len(person_index),
            company_rows=len(company_index),
            keyword_rows=len(keyword_index),
            movie_chunks=len(movie_index),
        )

    def load_tables(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if self.embedder_config.source == "sqlite":
            return self.load_sqlite_tables(self.embedder_config.sqlite_path)
        return self.load_parquet_tables(self.embedder_config.parquet_dir)

    @staticmethod
    def load_sqlite_tables(sqlite_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if not sqlite_path.exists():
            raise FileNotFoundError(sqlite_path)
        conn = sqlite3.connect(sqlite_path)
        try:
            movie = pd.read_sql_query("SELECT * FROM movie", conn)
            person = pd.read_sql_query("SELECT * FROM person", conn)
            company = pd.read_sql_query("SELECT * FROM company", conn)
        finally:
            conn.close()
        return movie, person, company

    @staticmethod
    def load_parquet_tables(parquet_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        return (
            pd.read_parquet(parquet_dir / "movie.parquet"),
            pd.read_parquet(parquet_dir / "person.parquet"),
            pd.read_parquet(parquet_dir / "company.parquet"),
        )

    def build_movie_index(self, movie: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for record in tqdm(movie.to_dict(orient="records"), desc="Preparing movie texts"):
            movie_id = int(record["id"])
            genres = parse_list(record.get("genres"))
            origin_country = parse_list(record.get("origin_country"))
            keywords = parse_list(record.get("keywords"))
            original_title = clean_str(record.get("original_title"))
            release_date = clean_str(record.get("release_date")) or None
            overview = clean_str(record.get("overview"))[: self.embedder_config.max_overview_chars]
            synopsis = clean_str(record.get("synopsis"))

            chunks = self.movie_text_chunks(
                original_title=original_title,
                release_date=release_date,
                genres=genres,
                keywords=keywords,
                overview=overview,
                synopsis=synopsis,
            )

            for chunk_index, text in enumerate(chunks):
                rows.append(
                    {
                        "id": movie_chunk_id(movie_id, chunk_index),
                        "movie_id": movie_id,
                        "chunk_index": chunk_index,
                        "genres": genres,
                        "origin_country": origin_country,
                        "original_title": original_title,
                        "popularity": safe_int(record.get("popularity")),
                        "release_date": release_date,
                        "vote_average": safe_float(record.get("vote_average")),
                        "embedding_text": text,
                    }
                )
        return pd.DataFrame(rows)

    def movie_text_chunks(
        self,
        *,
        original_title: str,
        release_date: Optional[str],
        genres: list[str],
        keywords: list[str],
        overview: str,
        synopsis: str,
    ) -> list[str]:
        header = "\n".join(
            [
                f"Original Title: {original_title}",
                f"Release Date: {release_date or ''}",
                f"Genres: {', '.join(genres)}",
                f"Keywords: {', '.join(keywords)}",
                f"Overview: {overview}",
                "Synopsis:",
            ]
        )
        header = header[: self.embedder_config.max_header_chars]
        full_text = f"{header}\n{synopsis}".strip()
        if len(full_text) <= self.embedder_config.movie_chunk_chars:
            return [full_text]

        chunk_budget = max(1000, self.embedder_config.movie_chunk_chars - len(header) - 80)
        synopsis_chunks = chunk_text(
            synopsis,
            max_chars=chunk_budget,
            overlap_chars=self.embedder_config.movie_chunk_overlap_chars,
        )
        return [
            f"{header}\nChunk {index + 1} of {len(synopsis_chunks)}:\n{chunk}".strip()
            for index, chunk in enumerate(synopsis_chunks)
        ]

    @staticmethod
    def build_person_index(person: pd.DataFrame) -> pd.DataFrame:
        frame = person.copy()
        frame["id"] = frame["id"].astype("int64")
        frame["name"] = frame["name"].fillna("").astype(str)
        frame["embedding_text"] = frame["name"].map(lambda value: f"Person: {value}")
        return frame[["id", "embedding_text"]]

    @staticmethod
    def build_company_index(company: pd.DataFrame) -> pd.DataFrame:
        frame = company.copy()
        frame["id"] = frame["id"].astype("int64")
        frame["name"] = frame["name"].fillna("").astype(str)
        frame["embedding_text"] = frame["name"].map(lambda value: f"Company: {value}")
        return frame[["id", "embedding_text"]]

    @staticmethod
    def build_keyword_index(movie: pd.DataFrame) -> pd.DataFrame:
        keywords: set[str] = set()
        for value in movie.get("keywords", pd.Series(dtype=object)):
            keywords.update(parse_list(value))
        rows = [
            {
                "keyword": keyword,
                "embedding_text": f"Movie keyword: {keyword}",
            }
            for keyword in sorted(keywords, key=str.casefold)
        ]
        return pd.DataFrame(rows)

    def add_vectors(self, frame: pd.DataFrame, *, text_column: str) -> None:
        texts = frame[text_column].fillna("").astype(str).tolist()
        vectors = self.embed_texts(texts)
        frame["vector"] = [vector.astype("float32").tolist() for vector in vectors]

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        self.ensure_embedder()
        vectors = self.embedder.encode(
            texts,
            batch_size=self.embedder_config.batch_size,
            normalize_embeddings=self.embedder_config.normalize_embeddings,
            show_progress_bar=True,
        )
        return np.asarray(vectors, dtype="float32")

    def ensure_embedder(self) -> None:
        if self.embedder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Install sentence-transformers before running: "
                "pip install sentence-transformers"
            ) from exc
        self.embedder = SentenceTransformer(
            self.embedder_config.model_name,
            device=self.embedder_config.device,
        )

    def save_local_parquets(
        self,
        *,
        movie_index: pd.DataFrame,
        person_index: pd.DataFrame,
        company_index: pd.DataFrame,
        keyword_index: pd.DataFrame,
    ) -> None:
        output_dir = self.embedder_config.local_output_dir
        if output_dir is None:
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        movie_index.to_parquet(output_dir / "movie_vector.parquet", index=False)
        person_index.to_parquet(output_dir / "person_vector.parquet", index=False)
        company_index.to_parquet(output_dir / "company_vector.parquet", index=False)
        keyword_index.to_parquet(output_dir / "keyword_vector.parquet", index=False)

    def write_supabase(
        self,
        *,
        movie_index: pd.DataFrame,
        person_index: pd.DataFrame,
        company_index: pd.DataFrame,
        keyword_index: pd.DataFrame,
    ) -> None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install psycopg before running: pip install psycopg[binary]") from exc

        with psycopg.connect(self.supabase_config.dsn) as conn:
            with conn.cursor() as cur:
                self.create_schema(cur)
                conn.commit()

                self.upsert_movie(cur, movie_index)
                self.upsert_person(cur, person_index)
                self.upsert_company(cur, company_index)
                self.upsert_keyword(cur, keyword_index)
                conn.commit()

                if self.embedder_config.create_vector_indexes:
                    self.create_indexes(cur)
                    conn.commit()

    def create_schema(self, cur: Any) -> None:
        if self.embedder_config.recreate_tables:
            cur.execute("DROP TABLE IF EXISTS movie CASCADE")
            cur.execute("DROP TABLE IF EXISTS person CASCADE")
            cur.execute("DROP TABLE IF EXISTS company CASCADE")
            cur.execute("DROP TABLE IF EXISTS keyword CASCADE")

        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS movie (
                id BIGINT PRIMARY KEY,
                movie_id BIGINT NOT NULL,
                chunk_index INTEGER NOT NULL,
                genres JSONB NOT NULL DEFAULT '[]'::jsonb,
                origin_country JSONB NOT NULL DEFAULT '[]'::jsonb,
                original_title TEXT,
                popularity BIGINT,
                release_date DATE,
                vote_average DOUBLE PRECISION,
                vector vector({BGE_M3_DIMENSION})
            )
            """
        )
        cur.execute("ALTER TABLE movie ADD COLUMN IF NOT EXISTS movie_id BIGINT")
        cur.execute("ALTER TABLE movie ADD COLUMN IF NOT EXISTS chunk_index INTEGER")
        cur.execute("ALTER TABLE movie ADD COLUMN IF NOT EXISTS genres JSONB NOT NULL DEFAULT '[]'::jsonb")
        cur.execute("ALTER TABLE movie ADD COLUMN IF NOT EXISTS origin_country JSONB NOT NULL DEFAULT '[]'::jsonb")
        cur.execute("ALTER TABLE movie ADD COLUMN IF NOT EXISTS original_title TEXT")
        cur.execute("ALTER TABLE movie ADD COLUMN IF NOT EXISTS popularity BIGINT")
        cur.execute("ALTER TABLE movie ADD COLUMN IF NOT EXISTS release_date DATE")
        cur.execute("ALTER TABLE movie ADD COLUMN IF NOT EXISTS vote_average DOUBLE PRECISION")
        cur.execute(f"ALTER TABLE movie ADD COLUMN IF NOT EXISTS vector vector({BGE_M3_DIMENSION})")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS person (
                id BIGINT PRIMARY KEY,
                vector vector({BGE_M3_DIMENSION})
            )
            """
        )
        cur.execute(f"ALTER TABLE person ADD COLUMN IF NOT EXISTS vector vector({BGE_M3_DIMENSION})")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS company (
                id BIGINT PRIMARY KEY,
                vector vector({BGE_M3_DIMENSION})
            )
            """
        )
        cur.execute(f"ALTER TABLE company ADD COLUMN IF NOT EXISTS vector vector({BGE_M3_DIMENSION})")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS keyword (
                keyword TEXT PRIMARY KEY,
                vector vector({BGE_M3_DIMENSION})
            )
            """
        )
        cur.execute(f"ALTER TABLE keyword ADD COLUMN IF NOT EXISTS vector vector({BGE_M3_DIMENSION})")

    @staticmethod
    def create_indexes(cur: Any) -> None:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS movie_vector_hnsw_idx "
            "ON movie USING hnsw (vector vector_cosine_ops)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS person_vector_hnsw_idx "
            "ON person USING hnsw (vector vector_cosine_ops)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS company_vector_hnsw_idx "
            "ON company USING hnsw (vector vector_cosine_ops)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS keyword_vector_hnsw_idx "
            "ON keyword USING hnsw (vector vector_cosine_ops)"
        )

    def upsert_movie(self, cur: Any, frame: pd.DataFrame) -> None:
        rows = [
            (
                int(row.id),
                int(row.movie_id),
                int(row.chunk_index),
                json.dumps(row.genres, ensure_ascii=False),
                json.dumps(row.origin_country, ensure_ascii=False),
                row.original_title,
                safe_int(row.popularity),
                row.release_date,
                safe_float(row.vote_average),
                vector_to_pg(row.vector),
            )
            for row in frame.itertuples(index=False)
        ]
        execute_batches(
            cur,
            """
            INSERT INTO movie (
                id,
                movie_id,
                chunk_index,
                genres,
                origin_country,
                original_title,
                popularity,
                release_date,
                vote_average,
                vector
            )
            VALUES (
                %s,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb,
                %s,
                %s,
                %s,
                %s,
                %s::vector
            )
            ON CONFLICT (id) DO UPDATE SET
                movie_id = EXCLUDED.movie_id,
                chunk_index = EXCLUDED.chunk_index,
                genres = EXCLUDED.genres,
                origin_country = EXCLUDED.origin_country,
                original_title = EXCLUDED.original_title,
                popularity = EXCLUDED.popularity,
                release_date = EXCLUDED.release_date,
                vote_average = EXCLUDED.vote_average,
                vector = EXCLUDED.vector
            """,
            rows,
            self.embedder_config.upsert_batch_size,
            desc="Uploading movie vectors",
        )

    def upsert_person(self, cur: Any, frame: pd.DataFrame) -> None:
        rows = [(int(row.id), vector_to_pg(row.vector)) for row in frame.itertuples(index=False)]
        execute_batches(
            cur,
            """
            INSERT INTO person (id, vector)
            VALUES (%s, %s::vector)
            ON CONFLICT (id) DO UPDATE SET vector = EXCLUDED.vector
            """,
            rows,
            self.embedder_config.upsert_batch_size,
            desc="Uploading person vectors",
        )

    def upsert_company(self, cur: Any, frame: pd.DataFrame) -> None:
        rows = [(int(row.id), vector_to_pg(row.vector)) for row in frame.itertuples(index=False)]
        execute_batches(
            cur,
            """
            INSERT INTO company (id, vector)
            VALUES (%s, %s::vector)
            ON CONFLICT (id) DO UPDATE SET vector = EXCLUDED.vector
            """,
            rows,
            self.embedder_config.upsert_batch_size,
            desc="Uploading company vectors",
        )

    def upsert_keyword(self, cur: Any, frame: pd.DataFrame) -> None:
        rows = [
            (str(row.keyword), vector_to_pg(row.vector))
            for row in frame.itertuples(index=False)
        ]
        execute_batches(
            cur,
            """
            INSERT INTO keyword (keyword, vector)
            VALUES (%s, %s::vector)
            ON CONFLICT (keyword) DO UPDATE SET vector = EXCLUDED.vector
            """,
            rows,
            self.embedder_config.upsert_batch_size,
            desc="Uploading keyword vectors",
        )


def execute_batches(cur: Any, sql: str, rows: list[tuple[Any, ...]], batch_size: int, desc: str) -> None:
    for start in tqdm(range(0, len(rows), batch_size), desc=desc):
        cur.executemany(sql, rows[start : start + batch_size])


def extract_supabase_project_ref(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if re.fullmatch(r"[a-z0-9]{20}", value):
        return value

    parsed = urlparse(value)
    host = parsed.netloc
    if host.endswith(".supabase.co"):
        return host.split(".", 1)[0]

    match = re.search(r"/project/([a-z0-9]{20})", parsed.path)
    if match:
        return match.group(1)

    raise ValueError(
        "Could not extract Supabase project ref. Use either "
        "https://<project-ref>.supabase.co or the dashboard project URL."
    )


def parse_list(value: Any) -> list[str]:
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [item.strip() for item in text.split(",") if item.strip()]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def movie_chunk_id(movie_id: int, chunk_index: int) -> int:
    return int(movie_id) * 10000 + int(chunk_index)


def chunk_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    text = clean_str(text)
    if not text:
        return [""]
    paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if not current:
            current = paragraph
            continue
        if len(current) + 2 + len(paragraph) <= max_chars:
            current = f"{current}\n\n{paragraph}"
            continue
        chunks.extend(split_long_piece(current, max_chars=max_chars, overlap_chars=overlap_chars))
        current = paragraph

    if current:
        chunks.extend(split_long_piece(current, max_chars=max_chars, overlap_chars=overlap_chars))

    return chunks or [""]


def split_long_piece(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if boundary > start + int(max_chars * 0.6):
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return chunks


def vector_to_pg(vector: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(item):.8f}" for item in vector) + "]"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate BAAI/bge-m3 embeddings and upload pgvector indexes to Supabase."
    )
    parser.add_argument("--source", choices=["sqlite", "parquet"], default="sqlite")
    parser.add_argument("--sqlite-path", type=Path, default=Path("movie.sqlite"))
    parser.add_argument("--parquet-dir", type=Path, default=Path("parquet"))
    parser.add_argument("--model-name", default="BAAI/bge-m3")
    parser.add_argument("--device", default=None)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--movie-chunk-chars", type=int, default=5500)
    parser.add_argument("--movie-chunk-overlap-chars", type=int, default=500)
    parser.add_argument("--local-output-dir", type=Path, default=None)
    parser.add_argument("--recreate-tables", action="store_true")
    parser.add_argument("--no-vector-indexes", action="store_true")
    parser.add_argument("--upsert-batch-size", type=int, default=250)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    embedder_config = EmbedderConfig(
        model_name=args.model_name,
        device=args.device,
        batch_size=args.batch_size,
        movie_chunk_chars=args.movie_chunk_chars,
        movie_chunk_overlap_chars=args.movie_chunk_overlap_chars,
        sqlite_path=args.sqlite_path,
        parquet_dir=args.parquet_dir,
        source=args.source,
        local_output_dir=args.local_output_dir,
        recreate_tables=args.recreate_tables,
        create_vector_indexes=not args.no_vector_indexes,
        upsert_batch_size=args.upsert_batch_size,
    )
    result = MovieSupabaseEmbedder(embedder_config=embedder_config).run()
    print(result)


if __name__ == "__main__":
    main()
