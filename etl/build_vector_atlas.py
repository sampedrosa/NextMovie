"""Reduces the 1024-dim BAAI/bge-m3 movie vectors to a 3D point cloud for the
frontend "Visualizar Filmes Vetorizados" view.

Reads straight from the Supabase REST API (same credentials the API project
uses), runs UMAP to project every movie vector down to 3 dimensions, then
keeps only the half of the catalog with the highest popularity so the JSON
payload shipped to the browser stays small. Writes the same file to etl/ (for
inspection) and frontend/public/ (so Next.js can serve it statically).

Usage:
    python etl/build_vector_atlas.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from umap import UMAP

ROOT = Path(__file__).resolve().parent.parent
OUT_FILENAME = "movie-vectors-3d.json"
PAGE_SIZE = 1000
KEEP_FRACTION = 0.5  # ship only the top half by popularity


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def rest_base_url(env: dict[str, str]) -> str:
    match = re.search(r"([a-z0-9]{20})", env["SUPABASE_URL"])
    if not match:
        raise ValueError("Could not extract Supabase project ref from SUPABASE_URL")
    return f"https://{match.group(1)}.supabase.co/rest/v1"


def fetch_movies(env: dict[str, str]) -> list[dict[str, Any]]:
    base_url = rest_base_url(env)
    key = env["SUPABASE_API_SECRET_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    columns = "movie_id,original_title,genres,popularity,vector"

    rows: list[dict[str, Any]] = []
    start = 0
    with httpx.Client(timeout=30) as client:
        while True:
            response = client.get(
                f"{base_url}/movie",
                params={"select": columns, "vector": "not.is.null", "order": "movie_id"},
                headers={**headers, "Range": f"{start}-{start + PAGE_SIZE - 1}"},
            )
            response.raise_for_status()
            page = response.json()
            rows.extend(page)
            print(f"fetched {len(rows)} movies...")
            if len(page) < PAGE_SIZE:
                break
            start += PAGE_SIZE
    return rows


def parse_vector(raw: str) -> np.ndarray:
    return np.fromstring(raw.strip("[]"), sep=",", dtype="float32")


def main() -> None:
    env = load_env()
    rows = fetch_movies(env)
    print(f"total movies: {len(rows)}")

    vectors = np.stack([parse_vector(row["vector"]) for row in rows])

    print("running UMAP (1024D -> 3D)...")
    reducer = UMAP(n_components=3, n_neighbors=15, min_dist=0.15, metric="cosine", random_state=42)
    coords = reducer.fit_transform(vectors)

    # Center and scale uniformly (preserve relative cluster shape) to a
    # comfortable range for a three.js scene.
    coords = coords - coords.mean(axis=0)
    coords = coords / coords.std() * 10

    genres = sorted({(row["genres"] or ["Outro"])[0] for row in rows})
    genre_index = {genre: i for i, genre in enumerate(genres)}

    enriched = [
        {
            "x": round(float(coords[i, 0]), 2),
            "y": round(float(coords[i, 1]), 2),
            "z": round(float(coords[i, 2]), 2),
            "g": genre_index[(row["genres"] or ["Outro"])[0]],
            "t": row["original_title"],
            "pop": row["popularity"] or 0,
        }
        for i, row in enumerate(rows)
    ]
    enriched.sort(key=lambda item: item["pop"], reverse=True)
    keep = enriched[: int(len(enriched) * KEEP_FRACTION)]

    payload = {
        "genres": genres,
        "x": [item["x"] for item in keep],
        "y": [item["y"] for item in keep],
        "z": [item["z"] for item in keep],
        "g": [item["g"] for item in keep],
        "t": [item["t"] for item in keep],
    }

    out_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for destination in (ROOT / "etl" / OUT_FILENAME, ROOT / "frontend" / "public" / OUT_FILENAME):
        destination.write_text(out_json, encoding="utf-8")
        print(f"wrote {destination} ({destination.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
