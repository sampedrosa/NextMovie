"use client";

import { useState } from "react";

const MAX_CHARS = 500;

const EXAMPLES = [
  "Drama distópico de chorar com o protagonista precisando salvar o mundo e sua família",
  "Um suspense psicológico com final ambíguo e fotografia melancólica",
  "Mulher desvendando mistérios sobrenaturais",
  "Comédia natalina com crítica social",
];

export default function SearchBox({
  onSearch,
  loading,
  searched,
}: {
  onSearch: (query: string) => void;
  loading: boolean;
  searched: boolean;
}) {
  const [query, setQuery] = useState("");

  function submit(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 3 || loading) return;
    onSearch(trimmed.slice(0, MAX_CHARS));
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <p className="mb-4 text-center text-base text-screen-300 sm:text-lg">
        Descreva com suas palavras o tipo de filme que você quer assistir.
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit(query);
        }}
        className="group relative"
      >
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit(query);
            }
          }}
          rows={3}
          maxLength={MAX_CHARS}
          spellCheck={false}
          placeholder="Um drama de guerra futurística..."
          className="w-full resize-none rounded-2xl border border-night-600 bg-night-900/90 p-5 pb-10 pr-32 text-base text-screen-100 placeholder-screen-500 shadow-xl shadow-black/30 outline-none backdrop-blur transition-colors focus:border-marquee-500/60"
        />
        <span className="pointer-events-none absolute bottom-4 left-5 text-xs text-screen-500">
          {query.length}/{MAX_CHARS}
        </span>
        <button
          type="submit"
          disabled={loading || query.trim().length < 3}
          className="absolute bottom-4 right-4 rounded-xl bg-marquee-400 px-5 py-2.5 text-sm font-bold text-night-950 transition-all hover:bg-marquee-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "Buscando…" : "Buscar"}
        </button>
      </form>

      {!searched && (
        <div className="mt-6 flex flex-col items-center gap-3">
          <span className="text-xs uppercase tracking-wide text-screen-500">
            Experimente
          </span>
          <div className="flex flex-wrap justify-center gap-2">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example);
                  submit(example);
                }}
                disabled={loading}
                className="rounded-full border border-night-600 bg-night-800/60 px-3.5 py-1.5 text-xs text-screen-300 transition-colors hover:border-marquee-500/50 hover:text-marquee-300 disabled:opacity-40"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
