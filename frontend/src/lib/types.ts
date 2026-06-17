export interface MovieResult {
  movie_id: number;
  title: string;
  genres: string[];
  origin_country: string[];
  release_date: string | null;
  vote_average: number | null;
  similarity: number;
  score: number;
  poster_url: string | null;
  overview: string | null;
}

export interface RecommendResponse {
  query: string;
  expanded_keywords: string[];
  results: MovieResult[];
  meta: {
    embedding_provider: string;
    tmdb_enriched: boolean;
    discovery: boolean;
    candidates_considered: number;
  };
}

export type SortKey = "relevance" | "rating" | "year_desc" | "year_asc";

export interface Filters {
  genres: string[];
  sortBy: SortKey;
}
