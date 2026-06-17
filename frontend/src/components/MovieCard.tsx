import Image from "next/image";
import type { MovieResult } from "@/lib/types";
import { translateGenre } from "@/lib/genres";
import { getFlagPath } from "@/lib/countries";

function matchPercent(similarity: number): number {
  return Math.round(Math.max(0, Math.min(similarity, 1)) * 100);
}

export default function MovieCard({
  movie,
  index,
}: {
  movie: MovieResult;
  index: number;
}) {
  const year = movie.release_date?.slice(0, 4);
  const flagPath = movie.origin_country[0]
    ? getFlagPath(movie.origin_country[0])
    : null;

  return (
    <article
      className="card-enter group flex flex-col overflow-hidden rounded-xl border border-night-700 bg-night-900/80 shadow-lg shadow-black/40 transition-all duration-300 hover:-translate-y-1 hover:border-marquee-500/40 hover:shadow-xl hover:shadow-black/50"
      style={{ animationDelay: `${Math.min(index * 60, 600)}ms` }}
    >
      <div className="relative aspect-[2/3] w-full overflow-hidden bg-night-800">
        {movie.poster_url ? (
          <Image
            src={movie.poster_url}
            alt={`Pôster de ${movie.title}`}
            fill
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
            className="object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-gradient-to-br from-night-700 via-night-800 to-night-900 p-4">
            <span aria-hidden className="text-4xl opacity-60">
              🎬
            </span>
            <span className="text-center font-display text-lg leading-snug text-screen-300">
              {movie.title}
            </span>
          </div>
        )}
        <div className="absolute left-2 top-2 rounded-full bg-night-950/85 px-2.5 py-1 text-xs font-bold text-marquee-300 backdrop-blur-sm">
          {matchPercent(movie.similarity)}% match
        </div>
        {movie.vote_average ? (
          <div className="absolute right-2 top-2 rounded-full bg-night-950/85 px-2.5 py-1 text-xs font-semibold text-screen-100 backdrop-blur-sm">
            ★ {movie.vote_average.toFixed(1)}
          </div>
        ) : null}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start gap-2">
          {flagPath && (
            <Image
              src={flagPath}
              alt={movie.origin_country[0]}
              width={20}
              height={14}
              className="mt-1 shrink-0 rounded-sm object-cover"
              unoptimized
            />
          )}
          <h3 className="line-clamp-2 font-display text-lg font-semibold leading-tight text-screen-100">
            {movie.title}
            {year ? (
              <span className="ml-2 text-sm font-normal text-screen-500">{year}</span>
            ) : null}
          </h3>
        </div>

        {movie.genres.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {movie.genres.slice(0, 3).map((genre) => (
              <span
                key={genre}
                className="rounded-full border border-night-600 px-2 py-0.5 text-[11px] text-screen-300"
              >
                {translateGenre(genre)}
              </span>
            ))}
          </div>
        )}

        {movie.overview && (
          <p className="line-clamp-3 text-sm leading-relaxed text-screen-300">
            {movie.overview}
          </p>
        )}
      </div>
    </article>
  );
}
