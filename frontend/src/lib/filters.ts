import type { Filters, MovieResult } from "./types";

export interface FilterOptions {
  genres: string[];
}

/** Derives the available genres from a result set. */
export function deriveOptions(results: MovieResult[]): FilterOptions {
  const genres = new Set<string>();
  for (const movie of results) {
    movie.genres.forEach((g) => genres.add(g));
  }
  return {
    genres: [...genres].sort((a, b) => a.localeCompare(b, "pt")),
  };
}

function yearOf(movie: MovieResult): number | null {
  if (!movie.release_date) return null;
  const year = parseInt(movie.release_date.slice(0, 4), 10);
  return Number.isFinite(year) ? year : null;
}

/** Applies the active filters and sorting to the results. */
export function applyFilters(
  results: MovieResult[],
  filters: Filters
): MovieResult[] {
  const { genres, sortBy } = filters;

  const filtered =
    genres.length > 0
      ? results.filter((movie) => movie.genres.some((g) => genres.includes(g)))
      : results;

  if (sortBy === "relevance") return filtered;

  const sorted = [...filtered];
  sorted.sort((a, b) => {
    switch (sortBy) {
      case "rating":
        return (b.vote_average ?? 0) - (a.vote_average ?? 0);
      case "year_desc":
        return (yearOf(b) ?? -Infinity) - (yearOf(a) ?? -Infinity);
      case "year_asc":
        return (yearOf(a) ?? Infinity) - (yearOf(b) ?? Infinity);
      default:
        return 0;
    }
  });
  return sorted;
}
