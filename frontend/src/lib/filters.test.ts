// Run: node --test src/lib/filters.test.ts   (Node 23+ strips the TS types)
import test from "node:test";
import assert from "node:assert/strict";
import { applyFilters, deriveOptions, yearOf } from "./filters.ts";
import type { Filters, MovieResult } from "./types.ts";

function movie(p: Partial<MovieResult>): MovieResult {
  return {
    movie_id: 0,
    title: "X",
    genres: [],
    origin_country: [],
    release_date: null,
    vote_average: null,
    similarity: 0,
    score: 0,
    poster_url: null,
    overview: null,
    ...p,
  };
}

const SAMPLE: MovieResult[] = [
  movie({ movie_id: 1, title: "Zeta", genres: ["Drama"], release_date: "2020-01-01", vote_average: 8.2, score: 0.9 }),
  movie({ movie_id: 2, title: "Alfa", genres: ["Comedy", "Drama"], release_date: "1999-05-01", vote_average: 6.1, score: 0.8 }),
  movie({ movie_id: 3, title: "Mega", genres: ["Sci-Fi"], release_date: "2010-03-01", vote_average: 7.5, score: 0.7 }),
  movie({ movie_id: 4, title: "Beta", genres: ["Drama"], release_date: null, vote_average: null, score: 0.6 }),
];

const base: Filters = {
  genres: [],
  yearRange: [1950, 2026],
  minRating: 0,
  sortBy: "relevance",
};

test("deriveOptions collects genres sorted and year bounds", () => {
  const opt = deriveOptions(SAMPLE);
  assert.deepEqual(opt.genres, ["Comedy", "Drama", "Sci-Fi"]);
  assert.equal(opt.minYear, 1999);
  assert.equal(opt.maxYear, 2020);
});

test("deriveOptions falls back when no results", () => {
  const opt = deriveOptions([]);
  assert.equal(opt.genres.length, 0);
  assert.equal(opt.minYear, 1950);
});

test("relevance sort preserves API order", () => {
  const out = applyFilters(SAMPLE, base);
  assert.deepEqual(out.map((m) => m.movie_id), [1, 2, 3, 4]);
});

test("genre filter matches any selected genre", () => {
  const out = applyFilters(SAMPLE, { ...base, genres: ["Drama"] });
  assert.deepEqual(out.map((m) => m.movie_id), [1, 2, 4]);
});

test("year range excludes out-of-range; null years pass", () => {
  const out = applyFilters(SAMPLE, { ...base, yearRange: [2005, 2021] });
  // 1999 excluded; 2020 and 2010 in; null (movie 4) passes year filter.
  assert.deepEqual(out.map((m) => m.movie_id).sort(), [1, 3, 4]);
});

test("min rating filter; null rating treated as 0 and dropped", () => {
  const out = applyFilters(SAMPLE, { ...base, minRating: 7 });
  assert.deepEqual(out.map((m) => m.movie_id).sort(), [1, 3]);
});

test("rating sort descending", () => {
  const out = applyFilters(SAMPLE, { ...base, sortBy: "rating" });
  assert.deepEqual(out.map((m) => m.movie_id), [1, 3, 2, 4]);
});

test("year sort pushes unknown years last in both directions", () => {
  const desc = applyFilters(SAMPLE, { ...base, sortBy: "year_desc" });
  assert.deepEqual(desc.map((m) => m.movie_id), [1, 3, 2, 4]);
  const asc = applyFilters(SAMPLE, { ...base, sortBy: "year_asc" });
  assert.deepEqual(asc.map((m) => m.movie_id), [2, 3, 1, 4]);
});

test("title sort is locale aware A-Z", () => {
  const out = applyFilters(SAMPLE, { ...base, sortBy: "title" });
  assert.deepEqual(out.map((m) => m.title), ["Alfa", "Beta", "Mega", "Zeta"]);
});

test("yearOf parses or returns null", () => {
  assert.equal(yearOf(movie({ release_date: "2015-07-01" })), 2015);
  assert.equal(yearOf(movie({ release_date: null })), null);
});
