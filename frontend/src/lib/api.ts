import type { RecommendResponse } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchRecommendations(
  query: string,
  options: { limit?: number } = {}
): Promise<RecommendResponse> {
  const response = await fetch(`${API_URL}/api/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      limit: options.limit ?? 12,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Erro ${response.status} ao buscar recomendações`);
  }

  return response.json();
}
