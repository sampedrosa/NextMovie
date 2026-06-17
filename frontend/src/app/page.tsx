"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import SearchBox from "@/components/SearchBox";
import Results from "@/components/Results";
import FilterBar from "@/components/FilterBar";
import { fetchRecommendations } from "@/lib/api";
import { applyFilters, deriveOptions } from "@/lib/filters";
import type { Filters, RecommendResponse } from "@/lib/types";

export default function Home() {
  const [data, setData] = useState<RecommendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [searchSeq, setSearchSeq] = useState(0);
  const [filters, setFilters] = useState<Filters>({
    genres: [],
    sortBy: "relevance",
  });

  const options = useMemo(() => deriveOptions(data?.results ?? []), [data]);

  // Reset filters on each new search.
  useEffect(() => {
    setFilters({ genres: [], sortBy: "relevance" });
  }, [searchSeq]);

  const view = useMemo(
    () => applyFilters(data?.results ?? [], filters),
    [data, filters]
  );

  async function handleSearch(query: string) {
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const response = await fetchRecommendations(query, { limit: 20 });
      setData(response);
      setSearchSeq((seq) => seq + 1);
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : "Erro inesperado");
    } finally {
      setLoading(false);
    }
  }

  function updateFilters(next: Partial<Filters>) {
    setFilters((prev) => ({ ...prev, ...next }));
  }

  function clearFilters() {
    setFilters({ genres: [], sortBy: "relevance" });
  }

  const showFilters =
    !loading && !error && data !== null && data.results.length > 0;

  return (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 sm:px-6">
        <section
          className={`flex flex-col items-center text-center transition-all duration-500 ${
            searched ? "pb-8 pt-10" : "pb-12 pt-16 sm:pt-20"
          }`}
        >
          <Image
            src="/nextmovie-logo.png"
            alt="NextMovie"
            width={132}
            height={150}
            priority
            className={`drop-shadow-[0_8px_24px_rgba(0,0,0,0.55)] transition-all duration-500 ${
              searched ? "w-20" : "w-28 sm:w-32"
            } h-auto`}
          />
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.25em] text-marquee-400">
            • Seu recomendador de filme •
          </p>
          <h1 className="mt-2 font-display text-5xl font-bold tracking-tight text-screen-100 sm:text-6xl">
            Next<span className="text-marquee-400">Movie</span>
          </h1>
        </section>

        <SearchBox onSearch={handleSearch} loading={loading} searched={searched} />

        <section className="space-y-6 pb-20 pt-12">
          {(data?.expanded_keywords.length ?? 0) > 0 && !loading && (
            <div className="flex flex-wrap items-center gap-1.5 text-sm text-screen-500">
              <span>Conceitos detectados:</span>
              {data!.expanded_keywords.map((keyword) => (
                <span
                  key={keyword}
                  className="rounded-full bg-night-800 px-2 py-0.5 text-xs text-marquee-300"
                >
                  {keyword}
                </span>
              ))}
            </div>
          )}

          {showFilters && (
            <FilterBar
              options={options}
              filters={filters}
              onChange={updateFilters}
              onClear={clearFilters}
              totalCount={data!.results.length}
              filteredCount={view.length}
            />
          )}

          <Results
            data={data}
            results={view}
            loading={loading}
            error={error}
            onClearFilters={clearFilters}
          />
        </section>
      </main>

      <footer className="border-t border-night-800 py-6 text-center text-xs text-screen-500">
        NextMovie - Desenvolvido por Samuel Pedrosa.
      </footer>
    </div>
  );
}
