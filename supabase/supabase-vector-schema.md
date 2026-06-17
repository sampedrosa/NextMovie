# Supabase Vector Schema

This document describes the reduced Supabase/Postgres vector database used for semantic retrieval in the Free-tier-friendly setup.

The database is intentionally limited to:

```text
movie
keyword
```

It does not store `person`, `company`, `job`, or `production`. Those richer relational tables remain local in `parquet/` or `parquet-resumed/`.

## Embeddings

Expected embedding model:

```text
BAAI/bge-m3
vector dimension: 1024
distance metric: cosine
```

All vector columns are `vector(1024)`.

The current upload notebook is [nb2.ipynb](D:/PROJETOS/AGENTIC/desafio/nb2.ipynb). Its final Supabase upload block only sends `movie` and `keyword`.

## Data Scope

The upload flow uses:

```text
vector-parquet/movie_vector.parquet
vector-parquet/keyword_vector.parquet
parquet-resumed/movie.parquet
```

`parquet-resumed/movie.parquet` defines the movie subset. It currently contains the top 20,000 movies by `popularity`.

Only these movies are uploaded to Supabase. Only keywords that appear in those movies are uploaded to Supabase.

## Tables

### `movie`

Semantic index for movies. One vector row per movie.

Columns:

| column | type | meaning |
|---|---|---|
| `id` | `bigint primary key` | Vector row id. In the current flow this is the TMDb movie id. |
| `movie_id` | `bigint` | TMDb movie id. Same value as `id` in the current flow. |
| `genres` | `jsonb` | List of genre names, e.g. `["Science Fiction", "Drama"]`. |
| `origin_country` | `jsonb` | List of origin country names/codes from the local movie data. |
| `original_title` | `text` | Original movie title. |
| `popularity` | `bigint` | Popularity proxy from the local data; currently based on vote count. |
| `release_date` | `date` | Movie release date. |
| `vote_average` | `double precision` | Average vote/rating from TMDb/local ETL. |
| `vector` | `vector(1024)` | BGE-M3 embedding for the movie text. |

Expected movie embedding text:

```text
Original Title: <movie.original_title>
Release Date: <movie.release_date>
Genres: <movie.genres>
Keywords: <movie.keywords>
Overview: <movie.overview>
Synopsis: <movie.synopsis>
```

The local embedding notebook may truncate long `overview` and `synopsis` text before embedding.

### `keyword`

Semantic index for unique movie keywords used by the uploaded movie subset.

Columns:

| column | type | meaning |
|---|---|---|
| `keyword` | `text primary key` | Keyword string. |
| `vector` | `vector(1024)` | BGE-M3 embedding for the keyword text. |

Expected keyword embedding text:

```text
Movie keyword: <keyword>
```

## Indexes

Metadata indexes:

```sql
create index if not exists movie_movie_id_idx on movie (movie_id);
create index if not exists movie_release_date_idx on movie (release_date);
create index if not exists movie_popularity_idx on movie (popularity desc);
```

Vector indexes are optional in the Free-tier setup.

The notebook currently leaves:

```python
CREATE_VECTOR_INDEXES_AFTER_UPLOAD = False
```

This avoids creating HNSW indexes immediately, because HNSW can add significant storage and compute pressure on Supabase Free.

If the database remains comfortably below the Free-tier database-size limit after upload, these optional indexes can be created:

```sql
create index if not exists movie_vector_hnsw_idx
on movie using hnsw (vector vector_cosine_ops)
where vector is not null;

create index if not exists keyword_vector_hnsw_idx
on keyword using hnsw (vector vector_cosine_ops)
where vector is not null;
```

## Suggested RPC Functions

If RPC functions are needed, only create movie and keyword match functions.

### `match_movie`

```sql
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
language sql
stable
as $$
    select
        movie.id,
        movie.movie_id,
        movie.genres,
        movie.origin_country,
        movie.original_title,
        movie.popularity,
        movie.release_date,
        movie.vote_average,
        1 - (movie.vector <=> query_embedding) as similarity
    from movie
    where movie.vector is not null
    order by movie.vector <=> query_embedding
    limit match_count;
$$;
```

Example:

```sql
select *
from match_movie('[...]'::vector, 10);
```

### `match_keyword`

```sql
create or replace function match_keyword(
    query_embedding vector(1024),
    match_count integer default 10
)
returns table (
    keyword text,
    similarity double precision
)
language sql
stable
as $$
    select
        keyword.keyword,
        1 - (keyword.vector <=> query_embedding) as similarity
    from keyword
    where keyword.vector is not null
    order by keyword.vector <=> query_embedding
    limit match_count;
$$;
```

Example:

```sql
select *
from match_keyword('[...]'::vector, 10);
```

## Agent Usage Notes

- Use `match_movie` for natural-language movie retrieval.
- Use `match_keyword` to map natural-language concepts to known keyword strings.
- Do not query Supabase for `person`, `company`, `job`, or `production`; those are not part of this reduced database.
- For richer metadata or relationship analysis, use local files in `parquet-resumed/` or `parquet/`.
- Query embeddings must be generated with the same model and normalization strategy used during upload.
- Keep the Supabase Free database below roughly 500 MB. Measure after upload before creating vector indexes.

Useful size check:

```sql
select pg_size_pretty(pg_database_size(current_database()));
```

## Current Connection Note

The direct host `db.<project-ref>.supabase.co` may resolve only to IPv6. In this environment, the working pooler endpoint was:

```text
aws-1-us-west-2.pooler.supabase.com:5432
```

The originally provided port `6543` timed out from this environment.
