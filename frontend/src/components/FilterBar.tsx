"use client";

import type { Filters, SortKey } from "@/lib/types";
import type { FilterOptions } from "@/lib/filters";
import { translateGenre } from "@/lib/genres";

const SORT_LABELS: Record<SortKey, string> = {
  relevance: "Relevância",
  rating: "Maior nota",
  year_desc: "Mais recente",
  year_asc: "Mais antigo",
};

interface Props {
  options: FilterOptions;
  filters: Filters;
  onChange: (next: Partial<Filters>) => void;
  onClear: () => void;
  totalCount: number;
  filteredCount: number;
}

export default function FilterBar({
  options,
  filters,
  onChange,
  onClear,
  totalCount,
  filteredCount,
}: Props) {
  const { genres } = options;

  const hasActiveFilters =
    filters.genres.length > 0 || filters.sortBy !== "relevance";

  function toggleGenre(genre: string) {
    const next = filters.genres.includes(genre)
      ? filters.genres.filter((g) => g !== genre)
      : [...filters.genres, genre];
    onChange({ genres: next });
  }

  return (
    <div className="rounded-2xl border border-night-700 bg-night-900/60 p-4 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        {/* Ordenação */}
        <label className="flex shrink-0 items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-screen-500">
            Ordenar por
          </span>
          <select
            value={filters.sortBy}
            onChange={(e) => onChange({ sortBy: e.target.value as SortKey })}
            className="rounded-lg border border-night-600 bg-night-800 px-3 py-1.5 text-sm text-screen-100 outline-none focus:border-marquee-500/60"
          >
            {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
              <option key={key} value={key}>
                {SORT_LABELS[key]}
              </option>
            ))}
          </select>
        </label>

        {/* Gêneros */}
        {genres.length > 0 && (
          <div className="flex flex-1 flex-wrap items-center gap-2 border-l border-night-700/70 pl-5">
            <span className="text-xs font-semibold uppercase tracking-wide text-screen-500">
              Gêneros
            </span>
            {genres.map((genre) => {
              const active = filters.genres.includes(genre);
              return (
                <button
                  key={genre}
                  type="button"
                  onClick={() => toggleGenre(genre)}
                  aria-pressed={active}
                  className={`rounded-full px-3 py-1 text-xs transition-colors ${
                    active
                      ? "bg-marquee-400 font-semibold text-night-950"
                      : "border border-night-600 text-screen-300 hover:border-marquee-500/50 hover:text-marquee-300"
                  }`}
                >
                  {translateGenre(genre)}
                </button>
              );
            })}
          </div>
        )}

        <div className="ml-auto flex shrink-0 items-center gap-3">
          <span className="text-sm text-screen-500">
            {filteredCount} de {totalCount}
          </span>
          {hasActiveFilters && (
            <button
              type="button"
              onClick={onClear}
              className="rounded-lg border border-night-600 px-3 py-1.5 text-xs text-screen-300 transition-colors hover:border-marquee-500/50 hover:text-marquee-300"
            >
              Limpar filtros
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
