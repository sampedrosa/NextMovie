from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import unquote, urlparse

import pandas as pd
import requests
from tqdm.auto import tqdm


LOGGER = logging.getLogger("movie-etl")
UUID_NAMESPACE = uuid.UUID("7fc0c235-c555-43b4-9a8b-e42b7c9ccf5f")
ALLOWED_JOB_DEPARTMENTS = {
    "Actor",
    "Acting",
    "Action Director",
    "Adaptation",
    "Animation Director",
    "Animation Supervisor",
    "Animation Technical Director",
    "Art Direction",
    "Art Designer",
    "Assistant Art Director",
    "Assistant Camera",
    "Assistant Costume Designer",
    "Assistant Director",
    "Assistant Editor",
    "Assistant Makeup Artist",
    "Assistant Production Design",
    "Assistant Script",
    "Assistant Sound Designer",
    "Assistant Sound Editor",
    "Author",
    "Book",
    "Camera Operator",
    "Casting",
    "Casting Director",
    "CG Animator",
    "CG Artist",
    "CG Supervisor",
    "CGI Director",
    "Character Designer",
    "Choreographer",
    "Cinematography",
    "Co-Art Director",
    "Co-Costume Designer",
    "Co-Director",
    "Co-Editor",
    "Co-Writer",
    "Color Grading",
    "Colorist",
    "Comic Book",
    "Compositing Supervisor",
    "Concept Artist",
    "Conceptual Design",
    "Costume Design",
    "Costume Designer",
    "Creative Consultant",
    "Creative Director",
    "Creative Producer",
    "Creator",
    "Creature Design",
    "Dialogue",
    "Dialogue Coach",
    "Dialogue Editor",
    "Digital Colorist",
    "Digital Compositor",
    "Directing",
    "Director",
    "Director of Photography",
    "Director of Previsualization",
    "Dramaturgy",
    "Drone Cinematographer",
    "Editing",
    "Editor",
    "Executive Story Editor",
    "Fight Choreographer",
    "First Assistant Camera",
    "First Assistant Director",
    "First Assistant Editor",
    "Focus Puller",
    "Foley Artist",
    "Foley Editor",
    "Gaffer",
    "Graphic Designer",
    "Hair Designer",
    "Hair Department Head",
    "Head of Animation",
    "Head of Story",
    "Idea",
    "Key Animation",
    "Key Hair Stylist",
    "Key Makeup Artist",
    "Key Special Effects",
    "Lead Animator",
    "Lead Character Designer",
    "Lead Creature Designer",
    "Lead Editor",
    "Lighting Artist",
    "Lighting Design",
    "Lighting Director",
    "Lighting Supervisor",
    "Lyricist",
    "Main Title Designer",
    "Makeup Artist",
    "Makeup Designer",
    "Makeup Effects Designer",
    "Makeup Supervisor",
    "Martial Arts Choreographer",
    "Matte Painter",
    "Mechanical & Creature Designer",
    "Modelling Supervisor",
    "Motion Capture Artist",
    "Music Director",
    "Music Editor",
    "Music Supervisor",
    "Novel",
    "Original Concept",
    "Original Film Writer",
    "Original Music Composer",
    "Original Story",
    "Orchestrator",
    "Production Design",
    "Production Designer",
    "Production Illustrator",
    "Prop Designer",
    "Property Master",
    "Prosthetic Designer",
    "Prosthetic Makeup Artist",
    "Screenplay",
    "Screenstory",
    "Script",
    "Script Consultant",
    "Script Editor",
    "Script Supervisor",
    "Second Unit Director",
    "Second Unit Director of Photography",
    "Set Decoration",
    "Set Designer",
    "Set Dresser",
    "Sound Designer",
    "Sound Director",
    "Sound Editor",
    "Sound Effects Designer",
    "Sound Mixer",
    "Sound Re-Recording Mixer",
    "Sound Recordist",
    "Sound Supervisor",
    "Special Effects Supervisor",
    "Steadicam Operator",
    "Story",
    "Story Artist",
    "Story Consultant",
    "Story Editor",
    "Storyboard Artist",
    "Stunt Coordinator",
    "Supervising Animation Director",
    "Supervising Animator",
    "Supervising Art Director",
    "Supervising Dialogue Editor",
    "Supervising Editor",
    "Supervising Sound Editor",
    "Teleplay",
    "Title Designer",
    "Treatment",
    "Underwater Director of Photography",
    "VFX Artist",
    "VFX Director of Photography",
    "VFX Editor",
    "VFX Supervisor",
    "Visual Development",
    "Visual Effects Art Director",
    "Visual Effects Designer",
    "Visual Effects Director",
    "Visual Effects Editor",
    "Visual Effects Supervisor",
    "Visual Effects Technical Director",
    "Writer",
}


@dataclass
class SourceMovie:
    source: str
    title: str
    release_year: Optional[int] = None
    imdb_id: Optional[str] = None
    wiki_page: Optional[str] = None
    mpst_synopsis: Optional[str] = None
    hf_plot: Optional[str] = None
    hf_plot_summary: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedMovie:
    tmdb_id: int
    source_titles: set[str] = field(default_factory=set)
    source_names: set[str] = field(default_factory=set)
    imdb_ids: set[str] = field(default_factory=set)
    wiki_pages: set[str] = field(default_factory=set)
    synopsis_candidates: list[str] = field(default_factory=list)
    keyword_candidates: list[str] = field(default_factory=list)

    def merge(self, source: SourceMovie) -> None:
        if source.title:
            self.source_titles.add(source.title)
        self.source_names.add(source.source)
        if source.imdb_id:
            self.imdb_ids.add(source.imdb_id)
        if source.wiki_page:
            self.wiki_pages.add(source.wiki_page)
        for text in (source.mpst_synopsis, source.hf_plot):
            if isinstance(text, str) and text.strip():
                self.synopsis_candidates.append(text.strip())
        self.keyword_candidates.extend(split_tag_string(source.extra.get("tags")))

    @property
    def synopsis(self) -> str:
        if not self.synopsis_candidates:
            return ""
        return max(self.synopsis_candidates, key=len)


def clean_text(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def clean_int(value: Any) -> Optional[int]:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def split_tag_string(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def dedupe_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def normalize_title(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def wiki_title_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    if "wikipedia.org" not in parsed.netloc:
        return None
    marker = "/wiki/"
    if marker not in parsed.path:
        return None
    title = parsed.path.split(marker, 1)[1]
    title = title.split("#", 1)[0]
    return unquote(title).replace("_", " ").strip() or None


def site_from_wiki_url(url: Optional[str]) -> str:
    if not url:
        return "enwiki"
    parsed = urlparse(url)
    host = parsed.netloc.split(".")
    if host and host[0]:
        return f"{host[0]}wiki"
    return "enwiki"


class CachedHTTPClient:
    def __init__(self, cache_dir: Path, timeout: int = 30, sleep_seconds: float = 0.0):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.session = requests.Session()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cached_json(
        self,
        cache_key: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any] | list[Any]:
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        data = self.get_json(url, params=params, headers=headers)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)
        return data

    def get_json(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any] | list[Any]:
        last_error: Optional[Exception] = None
        for attempt in range(6):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "5"))
                    time.sleep(retry_after)
                    continue
                if response.status_code >= 500:
                    time.sleep(2**attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2**attempt)
        if last_error:
            raise last_error
        raise RuntimeError(f"Request failed: {url}")


class TMDbClient:
    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(
        self,
        token: str,
        http: CachedHTTPClient,
        language: str = "en-US",
        include_adult: bool = False,
    ):
        self.token = token
        self.http = http
        self.language = language
        self.include_adult = include_adult
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "movie-etl/1.0",
        }
        self._country_names: Optional[dict[str, str]] = None

    def movie_by_id(self, tmdb_id: int) -> Optional[dict[str, Any]]:
        params = {
            "language": self.language,
            "append_to_response": "credits,keywords,external_ids",
        }
        try:
            return self.http.cached_json(
                f"tmdb/movie/{tmdb_id}",
                f"{self.BASE_URL}/movie/{tmdb_id}",
                params=params,
                headers=self.headers,
            )
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def find_by_imdb_id(self, imdb_id: str) -> Optional[int]:
        data = self.http.cached_json(
            f"tmdb/find/{imdb_id}",
            f"{self.BASE_URL}/find/{imdb_id}",
            params={"external_source": "imdb_id", "language": self.language},
            headers=self.headers,
        )
        movie_results = data.get("movie_results", []) if isinstance(data, dict) else []
        if not movie_results:
            return None
        return clean_int(movie_results[0].get("id"))

    def search_movie(self, title: str, release_year: Optional[int]) -> Optional[int]:
        params: dict[str, Any] = {
            "query": title,
            "include_adult": str(self.include_adult).lower(),
            "language": self.language,
            "page": 1,
        }
        if release_year:
            params["primary_release_year"] = release_year

        cache_suffix = f"{normalize_title(title)}-{release_year or 'none'}"
        cache_suffix = re.sub(r"[^a-z0-9._-]+", "_", cache_suffix.casefold())
        data = self.http.cached_json(
            f"tmdb/search/{cache_suffix[:180]}",
            f"{self.BASE_URL}/search/movie",
            params=params,
            headers=self.headers,
        )
        results = data.get("results", []) if isinstance(data, dict) else []
        if not results:
            return None

        wanted = normalize_title(title)
        exact = [
            item
            for item in results
            if normalize_title(str(item.get("title") or item.get("original_title") or ""))
            == wanted
        ]
        result = exact[0] if exact else results[0]
        return clean_int(result.get("id"))

    def country_names(self) -> dict[str, str]:
        if self._country_names is not None:
            return self._country_names
        data = self.http.cached_json(
            "tmdb/configuration/countries",
            f"{self.BASE_URL}/configuration/countries",
            headers=self.headers,
        )
        names: dict[str, str] = {}
        if isinstance(data, list):
            for item in data:
                code = item.get("iso_3166_1")
                name = item.get("english_name") or item.get("native_name")
                if code and name:
                    names[code] = name
        self._country_names = names
        return names

    def country_name(self, code: Optional[str]) -> Optional[str]:
        if not code:
            return None
        return self.country_names().get(code, code)


class WikidataClient:
    API_URL = "https://www.wikidata.org/w/api.php"

    def __init__(self, http: CachedHTTPClient):
        self.http = http
        self.headers = {"User-Agent": "movie-etl/1.0"}
        self.entities_by_site_title: dict[tuple[str, str], dict[str, Any]] = {}

    def preload_sitelinks(self, site_titles: Iterable[tuple[str, str]]) -> None:
        grouped: dict[str, list[str]] = {}
        for site, title in site_titles:
            if title:
                grouped.setdefault(site, []).append(title)

        total_batches = sum((len(set(titles)) + 49) // 50 for titles in grouped.values())
        progress = tqdm(total=total_batches, desc="Wikidata sitelinks", unit="batch")
        for site, titles in grouped.items():
            unique_titles = sorted(set(titles))
            for start in range(0, len(unique_titles), 50):
                batch = unique_titles[start : start + 50]
                cache_key = uuid.uuid5(
                    UUID_NAMESPACE,
                    f"wikidata:{site}:{'|'.join(batch)}",
                ).hex
                data = self.http.cached_json(
                    f"wikidata/sitelinks/{cache_key}",
                    self.API_URL,
                    params={
                        "action": "wbgetentities",
                        "sites": site,
                        "titles": "|".join(batch),
                        "props": "claims",
                        "format": "json",
                    },
                    headers=self.headers,
                )
                entities = data.get("entities", {}) if isinstance(data, dict) else {}
                for entity in entities.values():
                    if entity.get("missing"):
                        continue
                    sitelinks = entity.get("sitelinks", {})
                    if site not in sitelinks:
                        continue
                    title = sitelinks[site].get("title")
                    if title:
                        self.entities_by_site_title[(site, title)] = entity
                progress.update(1)
        progress.close()

    def entity_for_sitelink(self, site: str, title: str) -> Optional[dict[str, Any]]:
        return self.entities_by_site_title.get((site, title))

    @staticmethod
    def first_claim_value(entity: Optional[dict[str, Any]], property_id: str) -> Optional[Any]:
        if not entity:
            return None
        claims = entity.get("claims", {}).get(property_id, [])
        for claim in claims:
            value = (
                claim.get("mainsnak", {})
                .get("datavalue", {})
                .get("value")
            )
            if value is not None:
                return value
        return None


def require_optional_package(package_name: str, install_name: Optional[str] = None) -> None:
    try:
        __import__(package_name)
    except ImportError as exc:
        package = install_name or package_name
        raise RuntimeError(
            f"Missing dependency '{package}'. Install it with: "
            f"{sys.executable} -m pip install {package}"
        ) from exc


def load_mpst_movies(mpst_csv: Optional[Path]) -> list[SourceMovie]:
    csv_path = mpst_csv
    if csv_path is None or not csv_path.exists():
        require_optional_package("kagglehub")
        import kagglehub

        dataset_dir = Path(
            kagglehub.dataset_download("cryptexcode/mpst-movie-plot-synopses-with-tags")
        )
        matches = list(dataset_dir.rglob("mpst_full_data.csv"))
        if not matches:
            raise FileNotFoundError(f"mpst_full_data.csv not found in {dataset_dir}")
        csv_path = matches[0]

    LOGGER.info("Loading MPST from %s", csv_path)
    df = pd.read_csv(csv_path)
    movies: list[SourceMovie] = []
    for row in df.itertuples(index=False):
        record = row._asdict()
        movies.append(
            SourceMovie(
                source="mpst",
                title=clean_text(record.get("title")) or "",
                imdb_id=clean_text(record.get("imdb_id")),
                mpst_synopsis=clean_text(record.get("plot_synopsis")),
                extra={
                    "tags": clean_text(record.get("tags")),
                    "split": clean_text(record.get("split")),
                    "synopsis_source": clean_text(record.get("synopsis_source")),
                },
            )
        )
    return movies


def load_hf_movies_robust(dataset_name: str) -> list[SourceMovie]:
    require_optional_package("datasets")
    from datasets import load_dataset

    LOGGER.info("Loading Hugging Face dataset %s", dataset_name)
    dataset = load_dataset(dataset_name, split="train")
    df = dataset.to_pandas()
    movies: list[SourceMovie] = []
    for _, record in df.iterrows():
        movies.append(
            SourceMovie(
                source="wiki-movie-plots-with-summaries",
                title=clean_text(record.get("Title")) or "",
                release_year=clean_int(record.get("Release Year")),
                wiki_page=clean_text(record.get("Wiki Page")),
                hf_plot=clean_text(record.get("Plot")),
                hf_plot_summary=clean_text(record.get("PlotSummary")),
                extra={
                    "origin_ethnicity": clean_text(record.get("Origin/Ethnicity")),
                    "director": clean_text(record.get("Director")),
                    "cast": clean_text(record.get("Cast")),
                    "genre": clean_text(record.get("Genre")),
                },
            )
        )
    return movies


def resolve_tmdb_id(
    source: SourceMovie,
    tmdb: TMDbClient,
    wikidata: WikidataClient,
) -> Optional[int]:
    if source.wiki_page:
        site = site_from_wiki_url(source.wiki_page)
        wiki_title = wiki_title_from_url(source.wiki_page)
        entity = wikidata.entity_for_sitelink(site, wiki_title) if wiki_title else None
        tmdb_value = wikidata.first_claim_value(entity, "P4947")
        if tmdb_value:
            tmdb_id = clean_int(tmdb_value)
            if tmdb_id:
                return tmdb_id
        imdb_value = wikidata.first_claim_value(entity, "P345")
        if imdb_value:
            tmdb_id = tmdb.find_by_imdb_id(str(imdb_value))
            if tmdb_id:
                return tmdb_id

    if source.imdb_id:
        tmdb_id = tmdb.find_by_imdb_id(source.imdb_id)
        if tmdb_id:
            return tmdb_id

    if source.title:
        return tmdb.search_movie(source.title, source.release_year)
    return None


def prepare_sources(args: argparse.Namespace) -> list[SourceMovie]:
    sources: list[SourceMovie] = []
    sources.extend(load_mpst_movies(args.mpst_csv))
    sources.extend(load_hf_movies_robust(args.hf_dataset))
    return sources


def build_rows(
    resolved: dict[int, ResolvedMovie],
    tmdb: TMDbClient,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    movies: list[dict[str, Any]] = []
    companies_by_id: dict[int, dict[str, Any]] = {}
    persons_by_id: dict[int, dict[str, Any]] = {}
    production_by_id: dict[str, dict[str, Any]] = {}
    jobs_by_id: dict[str, dict[str, Any]] = {}
    failed_details: list[dict[str, Any]] = []

    for tmdb_id, resolved_movie in tqdm(
        resolved.items(),
        desc="TMDb movie details",
        unit="movie",
    ):
        details = tmdb.movie_by_id(tmdb_id)
        if not details:
            failed_details.append(
                {
                    "tmdb_id": tmdb_id,
                    "reason": "TMDb details not found",
                    "source_titles": sorted(resolved_movie.source_titles),
                }
            )
            continue

        production_country_names = [
            item.get("name")
            for item in details.get("production_countries", [])
            if item.get("name")
        ]
        origin_country = [
            name
            for name in (tmdb.country_name(code) for code in details.get("origin_country", []))
            if name
        ]
        if not origin_country:
            origin_country = production_country_names

        release_date = clean_text(details.get("release_date"))
        vote_count = clean_int(details.get("vote_count")) or 0
        if not release_date:
            failed_details.append(
                {
                    "tmdb_id": tmdb_id,
                    "reason": "Missing release_date",
                    "source_titles": sorted(resolved_movie.source_titles),
                }
            )
            continue
        if vote_count < 3:
            failed_details.append(
                {
                    "tmdb_id": tmdb_id,
                    "reason": "vote_count lower than 3",
                    "source_titles": sorted(resolved_movie.source_titles),
                }
            )
            continue

        keywords = dedupe_strings(
            [
                *[
                    item.get("name")
                    for item in details.get("keywords", {}).get("keywords", [])
                    if item.get("name")
                ],
                *resolved_movie.keyword_candidates,
            ]
        )

        movies.append(
            {
                "id": clean_int(details.get("id")),
                "genres": [
                    item.get("name")
                    for item in details.get("genres", [])
                    if item.get("name")
                ],
                "origin_country": origin_country,
                "original_title": clean_text(details.get("original_title")) or "",
                "overview": clean_text(details.get("overview")) or "",
                "synopsis": resolved_movie.synopsis,
                "popularity": vote_count,
                "release_date": release_date,
                "vote_average": float(details.get("vote_average") or 0.0),
                "keywords": keywords,
            }
        )

        for company in details.get("production_companies", []):
            company_id = clean_int(company.get("id"))
            if not company_id:
                continue
            country_name = tmdb.country_name(company.get("origin_country"))
            existing = companies_by_id.setdefault(
                company_id,
                {
                    "id": company_id,
                    "name": clean_text(company.get("name")) or "",
                    "production_countries": set(),
                },
            )
            if country_name:
                existing["production_countries"].add(country_name)
            elif production_country_names:
                existing["production_countries"].update(production_country_names)

            production_id = str(
                uuid.uuid5(UUID_NAMESPACE, f"production:{tmdb_id}:{company_id}")
            )
            production_by_id[production_id] = {
                "id": production_id,
                "movie_id": tmdb_id,
                "company_id": company_id,
            }

        credits = details.get("credits", {})
        for cast_member in credits.get("cast", []):
            person_id = clean_int(cast_member.get("id"))
            if not person_id:
                continue
            department = clean_text(cast_member.get("known_for_department")) or "Acting"
            add_person_and_job(
                persons_by_id,
                jobs_by_id,
                tmdb_id,
                person_id,
                clean_text(cast_member.get("name")) or "",
                department,
                department,
            )

        for crew_member in credits.get("crew", []):
            person_id = clean_int(crew_member.get("id"))
            if not person_id:
                continue
            known_for = clean_text(crew_member.get("known_for_department")) or ""
            function = (
                clean_text(crew_member.get("job"))
                or clean_text(crew_member.get("department"))
                or known_for
                or "Crew"
            )
            add_person_and_job(
                persons_by_id,
                jobs_by_id,
                tmdb_id,
                person_id,
                clean_text(crew_member.get("name")) or "",
                known_for,
                function,
            )

    companies = []
    for row in companies_by_id.values():
        row = dict(row)
        row["production_countries"] = sorted(row["production_countries"])
        companies.append(row)

    return (
        movies,
        companies,
        list(persons_by_id.values()),
        list(production_by_id.values()),
        list(jobs_by_id.values()),
        failed_details,
    )


def add_person_and_job(
    persons_by_id: dict[int, dict[str, Any]],
    jobs_by_id: dict[str, dict[str, Any]],
    movie_id: int,
    person_id: int,
    name: str,
    known_for_department: str,
    department: str,
) -> None:
    name = clean_text(name) or ""
    known_for_department = clean_text(known_for_department) or ""
    department = clean_text(department) or ""
    if department not in ALLOWED_JOB_DEPARTMENTS:
        return
    if not name or not known_for_department:
        return

    existing = persons_by_id.setdefault(
        person_id,
        {
            "id": person_id,
            "name": name,
            "known_for_department": known_for_department,
        },
    )
    if not existing.get("name") and name:
        existing["name"] = name
    if not existing.get("known_for_department") and known_for_department:
        existing["known_for_department"] = known_for_department

    job_id = str(uuid.uuid5(UUID_NAMESPACE, f"job:{movie_id}:{person_id}:{department}"))
    jobs_by_id[job_id] = {
        "id": job_id,
        "movie_id": movie_id,
        "person_id": person_id,
        "department": department,
    }


def json_for_sql(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_sqlite(
    db_path: Path,
    movie_df: pd.DataFrame,
    company_df: pd.DataFrame,
    person_df: pd.DataFrame,
    production_df: pd.DataFrame,
    job_df: pd.DataFrame,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(
            """
            DROP TABLE IF EXISTS job;
            DROP TABLE IF EXISTS production;
            DROP TABLE IF EXISTS person;
            DROP TABLE IF EXISTS company;
            DROP TABLE IF EXISTS movie;

            CREATE TABLE movie (
                id INTEGER PRIMARY KEY,
                genres TEXT,
                origin_country TEXT,
                original_title TEXT,
                overview TEXT,
                synopsis TEXT,
                popularity INTEGER,
                release_date TEXT,
                vote_average REAL,
                keywords TEXT
            );

            CREATE TABLE company (
                id INTEGER PRIMARY KEY,
                name TEXT,
                production_countries TEXT
            );

            CREATE TABLE person (
                id INTEGER PRIMARY KEY,
                name TEXT,
                known_for_department TEXT
            );

            CREATE TABLE production (
                id TEXT PRIMARY KEY,
                movie_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                FOREIGN KEY (movie_id) REFERENCES movie(id),
                FOREIGN KEY (company_id) REFERENCES company(id)
            );

            CREATE TABLE job (
                id TEXT PRIMARY KEY,
                movie_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                department TEXT,
                FOREIGN KEY (movie_id) REFERENCES movie(id),
                FOREIGN KEY (person_id) REFERENCES person(id)
            );
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")

        for table_name, df in (
            ("movie", movie_df),
            ("company", company_df),
            ("person", person_df),
            ("production", production_df),
            ("job", job_df),
        ):
            sql_df = df.map(json_for_sql) if not df.empty else df
            sql_df.to_sql(table_name, conn, if_exists="append", index=False)
        conn.commit()
    finally:
        conn.close()


def write_parquet(parquet_dir: Path, tables: dict[str, pd.DataFrame]) -> None:
    parquet_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(parquet_dir / f"{name}.parquet", index=False)


def write_outputs(
    args: argparse.Namespace,
    movies: list[dict[str, Any]],
    companies: list[dict[str, Any]],
    persons: list[dict[str, Any]],
    productions: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
) -> None:
    tables = {
        "movie": pd.DataFrame(movies),
        "company": pd.DataFrame(companies),
        "person": pd.DataFrame(persons),
        "production": pd.DataFrame(productions),
        "job": pd.DataFrame(jobs),
    }
    write_sqlite(
        args.db_path,
        tables["movie"],
        tables["company"],
        tables["person"],
        tables["production"],
        tables["job"],
    )
    write_parquet(args.parquet_dir, tables)

    for name, df in tables.items():
        LOGGER.info("%s rows: %s", name, len(df))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build movie SQLite/parquet tables from TMDb, Wikidata, MPST, and Hugging Face movie plots."
    )
    parser.add_argument("--db-path", type=Path, default=Path("movie.sqlite"))
    parser.add_argument("--parquet-dir", type=Path, default=Path("parquet"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".etl_cache"))
    parser.add_argument("--mpst-csv", type=Path, default=None)
    parser.add_argument(
        "--hf-dataset",
        default="vishnupriyavr/wiki-movie-plots-with-summaries",
    )
    parser.add_argument("--language", default="en-US")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-adult", action="store_true")
    parser.add_argument("--unresolved-path", type=Path, default=Path("unresolved_movies.csv"))
    parser.add_argument("--failed-details-path", type=Path, default=Path("failed_tmdb_details.csv"))
    parser.add_argument("--tmdb-token", default=os.getenv("TMDB_BEARER_TOKEN") or os.getenv("TMDB_TOKEN"))
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()

    if not args.tmdb_token:
        raise RuntimeError(
            "TMDb token not found. Set TMDB_BEARER_TOKEN or pass --tmdb-token."
        )

    http = CachedHTTPClient(args.cache_dir, timeout=args.timeout, sleep_seconds=args.sleep)
    tmdb = TMDbClient(
        args.tmdb_token,
        http,
        language=args.language,
        include_adult=args.include_adult,
    )
    wikidata = WikidataClient(http)

    sources = prepare_sources(args)
    if args.limit:
        sources = sources[: args.limit]
    LOGGER.info("Source records: %s", len(sources))

    site_titles = []
    for source in sources:
        title = wiki_title_from_url(source.wiki_page)
        if title:
            site_titles.append((site_from_wiki_url(source.wiki_page), title))
    wikidata.preload_sitelinks(site_titles)

    resolved: dict[int, ResolvedMovie] = {}
    unresolved: list[dict[str, Any]] = []
    for source in tqdm(sources, desc="Resolving TMDb IDs", unit="movie"):
        try:
            tmdb_id = resolve_tmdb_id(source, tmdb, wikidata)
        except Exception as exc:
            LOGGER.warning("Failed to resolve %s (%s): %s", source.title, source.source, exc)
            tmdb_id = None

        if not tmdb_id:
            unresolved.append(
                {
                    "source": source.source,
                    "title": source.title,
                    "release_year": source.release_year,
                    "imdb_id": source.imdb_id,
                    "wiki_page": source.wiki_page,
                }
            )
            continue

        resolved.setdefault(tmdb_id, ResolvedMovie(tmdb_id=tmdb_id)).merge(source)

    LOGGER.info("Resolved unique TMDb movies: %s", len(resolved))
    if unresolved:
        pd.DataFrame(unresolved).to_csv(args.unresolved_path, index=False)
        LOGGER.info("Unresolved movies saved to %s", args.unresolved_path)

    movies, companies, persons, productions, jobs, failed_details = build_rows(resolved, tmdb)
    if failed_details:
        pd.DataFrame(failed_details).to_csv(args.failed_details_path, index=False)
        LOGGER.info("Failed TMDb detail rows saved to %s", args.failed_details_path)

    write_outputs(args, movies, companies, persons, productions, jobs)
    LOGGER.info("SQLite saved to %s", args.db_path)
    LOGGER.info("Parquet files saved to %s", args.parquet_dir)


if __name__ == "__main__":
    main()
