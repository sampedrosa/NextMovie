import Image from "next/image";
import MovieCard from "./MovieCard";
import type { MovieResult, RecommendResponse } from "@/lib/types";

function LoadingState() {
  return (
    <div className="flex items-center justify-center gap-3 py-20">
      <Image
        src="/nextmovie-loading.webp"
        alt="Buscando filmes"
        width={360}
        height={394}
        unoptimized
        priority
        className="h-auto w-16 sm:w-20"
      />
      <p className="animate-pulse font-display text-lg text-screen-300">
        Buscando filmes...
      </p>
    </div>
  );
}

export default function Results({
  data,
  results,
  loading,
  error,
  onClearFilters,
}: {
  data: RecommendResponse | null;
  results: MovieResult[];
  loading: boolean;
  error: string | null;
  onClearFilters: () => void;
}) {
  if (loading) return <LoadingState />;

  if (error) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-red-900/60 bg-red-950/30 p-6 text-center">
        <p className="font-semibold text-red-300">Algo deu errado</p>
        <p className="mt-2 text-sm text-red-200/80">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  if (data.results.length === 0) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-night-600 bg-night-900/60 p-8 text-center">
        <span aria-hidden className="text-3xl">
          🎞️
        </span>
        <p className="mt-3 font-display text-xl text-screen-100">
          Nenhum filme encontrado
        </p>
        <p className="mt-2 text-sm leading-relaxed text-screen-300">
          O catálogo ainda está sendo indexado no banco vetorial. Assim que os
          filmes forem carregados, suas recomendações aparecerão aqui.
        </p>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-night-600 bg-night-900/60 p-8 text-center">
        <span aria-hidden className="text-3xl">
          🔍
        </span>
        <p className="mt-3 font-display text-xl text-screen-100">
          Nenhum filme com esses filtros
        </p>
        <p className="mt-2 text-sm leading-relaxed text-screen-300">
          Encontramos {data.results.length} recomendações, mas nenhuma combina
          com os filtros atuais.
        </p>
        <button
          type="button"
          onClick={onClearFilters}
          className="mt-4 rounded-lg bg-marquee-400 px-4 py-2 text-sm font-semibold text-night-950 transition-colors hover:bg-marquee-300"
        >
          Limpar filtros
        </button>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
      {results.map((movie, index) => (
        <MovieCard key={`${movie.movie_id}-${index}`} movie={movie} index={index} />
      ))}
    </div>
  );
}
