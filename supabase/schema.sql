-- NextMovie — Supabase/pgvector schema (reference DDL)
--
-- Reduced, Free-tier-friendly database: ONLY `movie` and `keyword`.
-- person/company/job/production are intentionally NOT stored in Supabase;
-- richer relational data stays in local parquet files.
--
-- See supabase/supabase-vector-schema.md for the full description and the
-- embedding-text conventions. Embedding model: BAAI/bge-m3 · 1024 dims · cosine.

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table if not exists movie (
  id              bigint primary key,
  movie_id        bigint,
  genres          jsonb,
  origin_country  jsonb,
  original_title  text,
  popularity      bigint,
  release_date    date,
  vote_average    double precision,
  vector          vector(1024)
);

create table if not exists keyword (
  keyword     text primary key,
  vector      vector(1024)
);

-- ---------------------------------------------------------------------------
-- Metadata indexes
-- ---------------------------------------------------------------------------

create index if not exists movie_movie_id_idx on movie (movie_id);
create index if not exists movie_release_date_idx on movie (release_date);
create index if not exists movie_popularity_idx on movie (popularity desc);

-- Vector (HNSW) indexes. The doc lists these as optional, but at the current
-- scale (~20k movies / ~22k keywords) a sequential scan over 1024-dim vectors
-- exceeds PostgREST's statement_timeout, so the match_* RPCs fail without them.
-- These are created on the live database (build took ~50-60s each).
create index if not exists movie_vector_hnsw_idx
  on movie using hnsw (vector vector_cosine_ops) where vector is not null;
create index if not exists keyword_vector_hnsw_idx
  on keyword using hnsw (vector vector_cosine_ops) where vector is not null;

-- ---------------------------------------------------------------------------
-- RPC functions (semantic retrieval)
-- ---------------------------------------------------------------------------

create or replace function match_movie(
  query_embedding vector(1024),
  match_count integer default 10
)
returns table (
  id bigint,
  movie_id bigint,
  genres jsonb,
  origin_country jsonb,
  original_title text,
  popularity bigint,
  release_date date,
  vote_average double precision,
  similarity double precision
)
language sql stable
as $$
  select
    movie.id, movie.movie_id, movie.genres,
    movie.origin_country, movie.original_title, movie.popularity,
    movie.release_date, movie.vote_average,
    1 - (movie.vector <=> query_embedding) as similarity
  from movie
  where movie.vector is not null
  order by movie.vector <=> query_embedding
  limit match_count;
$$;

create or replace function match_keyword(
  query_embedding vector(1024),
  match_count integer default 10
)
returns table (keyword text, similarity double precision)
language sql stable
as $$
  select
    keyword.keyword,
    1 - (keyword.vector <=> query_embedding) as similarity
  from keyword
  where keyword.vector is not null
  order by keyword.vector <=> query_embedding
  limit match_count;
$$;
