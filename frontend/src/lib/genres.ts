export const GENRE_PT: Record<string, string> = {
  Action: "Ação",
  Adventure: "Aventura",
  Animation: "Animação",
  Comedy: "Comédia",
  Crime: "Crime",
  Documentary: "Documentário",
  Drama: "Drama",
  Family: "Família",
  Fantasy: "Fantasia",
  History: "Histórico",
  Horror: "Terror",
  Music: "Musical",
  Mystery: "Mistério",
  Romance: "Romance",
  "Science Fiction": "Ficção Científica",
  "TV Movie": "TV",
  Thriller: "Suspense",
  War: "Guerra",
  Western: "Faroeste",
};

export function translateGenre(genre: string): string {
  return GENRE_PT[genre] ?? genre;
}
