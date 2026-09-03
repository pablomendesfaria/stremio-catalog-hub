"""Catalog handler — serves Stremio catalog requests.

Routes::

    GET /catalog/{type}/{catalog_id}.json
    GET /catalog/{type}/{catalog_id}/{extra}.json
    GET /{config}/catalog/{type}/{catalog_id}.json
    GET /{config}/catalog/{type}/{catalog_id}/{extra}.json
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models.catalog import CatalogProvider
from app.providers.tmdb import TMDBClient
from app.utils.helpers import (
    decode_user_config,
    get_current_anime_season,
    parse_extra_params,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# TMDB genre-name → genre-id mapping (for Portuguese genre filter labels)
_TMDB_MOVIE_GENRE_MAP: dict[str, int] = {
    "Ação": 28, "Aventura": 12, "Animação": 16, "Comédia": 35,
    "Crime": 80, "Documentário": 99, "Drama": 18, "Família": 10751,
    "Fantasia": 14, "História": 36, "Terror": 27, "Música": 10402,
    "Mistério": 9648, "Romance": 10749, "Ficção científica": 878,
    "Thriller": 53, "Guerra": 10752, "Faroeste": 37,
}
_TMDB_TV_GENRE_MAP: dict[str, int] = {
    "Ação e Aventura": 10759, "Animação": 16, "Comédia": 35,
    "Crime": 80, "Documentário": 99, "Drama": 18, "Família": 10751,
    "Kids": 10762, "Mistério": 9648, "Realidade": 10764,
    "Sci-Fi & Fantasia": 10765, "Soap": 10766, "Talk": 10767,
    "Guerra & Política": 10768, "Faroeste": 37,
}

# AniList: which "genres" are actually tags (for the dropdown filter)
_ANILIST_TAGS = {"Shounen", "Seinen", "Shoujo", "Josei", "Isekai", "Mahou Shoujo"}


def _skip_to_page(skip: int, page_size: int = 20) -> int:
    """Convert a Stremio ``skip`` value to a 1-based page number."""
    return (skip // page_size) + 1


# ── Core handler ────────────────────────────────────────────────────────

async def _handle_catalog(
    request: Request,
    content_type: str,
    catalog_id: str,
    config: str | None = None,
    extra: str | None = None,
) -> JSONResponse:
    user_config = decode_user_config(config) if config else None
    if not user_config or not user_config.tmdb_api_key:
        raise HTTPException(status_code=400, detail="Missing or invalid user configuration")

    extra_params = parse_extra_params(extra)
    skip = int(extra_params.get("skip", "0"))
    search_query = extra_params.get("search")
    genre_filter = extra_params.get("genre")
    language = user_config.language
    page = _skip_to_page(skip)

    cache = request.app.state.cache
    cache_key = f"catalog:{catalog_id}:{language}:{genre_filter}:{search_query}:{page}"

    # Try cache first
    cached = await cache.get(cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    # Look up catalog definition
    catalog_registry = request.app.state.catalog_registry
    catalog_def = await catalog_registry.get_catalog_definition(catalog_id)
    if not catalog_def:
        raise HTTPException(status_code=404, detail=f"Catalog '{catalog_id}' not found")

    metas: list[dict[str, Any]] = []

    if catalog_def.provider == CatalogProvider.TMDB:
        metas = await _fetch_tmdb_catalog(
            request, catalog_id, catalog_def, content_type,
            language, page, search_query, genre_filter,
        )
    elif catalog_def.provider == CatalogProvider.ANILIST:
        metas = await _fetch_anilist_catalog(
            request, catalog_id, catalog_def,
            language, page, search_query, genre_filter,
        )

    response = {
        "metas": metas,
        "cacheMaxAge": catalog_def.refresh_interval_seconds,
        "staleRevalidate": catalog_def.refresh_interval_seconds * 2,
    }

    # Store in cache
    await cache.set(cache_key, response, ttl=catalog_def.refresh_interval_seconds)

    return JSONResponse(content=response)


# ── TMDB fetcher ────────────────────────────────────────────────────────

async def _fetch_tmdb_catalog(
    request: Request,
    catalog_id: str,
    catalog_def: Any,
    content_type: str,
    language: str,
    page: int,
    search_query: str | None,
    genre_filter: str | None,
) -> list[dict[str, Any]]:
    """Fetch catalog data from TMDB and convert to MetaPreview dicts."""
    user_config = decode_user_config(
        request.path_params.get("config")
    )
    api_key = user_config.tmdb_api_key if user_config else ""
    tmdb = TMDBClient(api_key)

    try:
        items: list[dict[str, Any]] = []

        if search_query:
            if content_type == "movie":
                items = await tmdb.search_movies(search_query, language, page)
            else:
                items = await tmdb.search_series(search_query, language, page)
        elif genre_filter:
            genre_map = _TMDB_MOVIE_GENRE_MAP if content_type == "movie" else _TMDB_TV_GENRE_MAP
            genre_id = genre_map.get(genre_filter)
            if genre_id:
                if content_type == "movie":
                    items = await tmdb.discover_movies([genre_id], language, page)
                else:
                    items = await tmdb.discover_series([genre_id], language, page)
        else:
            endpoint = catalog_def.provider_params.get("endpoint", "")
            time_window = catalog_def.provider_params.get("time_window", "week")

            if endpoint == "trending":
                if content_type == "movie":
                    items = await tmdb.get_trending_movies(time_window, language, page)
                else:
                    items = await tmdb.get_trending_series(time_window, language, page)
            elif endpoint == "popular":
                if content_type == "movie":
                    items = await tmdb.get_popular_movies(language, page)
                else:
                    items = await tmdb.get_popular_series(language, page)
            elif endpoint == "now_playing":
                items = await tmdb.get_now_playing_movies(language, page)
            elif endpoint == "airing_today":
                items = await tmdb.get_airing_today_series(language, page)
            elif endpoint == "discover":
                # Thematic catalog — use genre_ids from theme
                genre_ids = catalog_def.provider_params.get("genre_ids", [])
                extra_kwargs: dict[str, Any] = {}
                vote_avg = catalog_def.provider_params.get("vote_average_gte")
                if vote_avg:
                    extra_kwargs["vote_average.gte"] = vote_avg
                yr_range = catalog_def.provider_params.get("release_year_range")
                if yr_range:
                    extra_kwargs["primary_release_date.gte"] = f"{yr_range[0]}-01-01"
                    extra_kwargs["primary_release_date.lte"] = f"{yr_range[1]}-12-31"
                if content_type == "movie":
                    items = await tmdb.discover_movies(genre_ids, language, page, **extra_kwargs)
                else:
                    items = await tmdb.discover_series(genre_ids, language, page, **extra_kwargs)

        return [_tmdb_item_to_meta(item, content_type) for item in items]
    finally:
        await tmdb.close()


def _tmdb_item_to_meta(item: dict[str, Any], content_type: str) -> dict[str, Any]:
    """Convert a TMDB list item dict to a Stremio MetaPreview dict."""
    return {
        "id": f"tmdb:{item['tmdb_id']}",
        "type": content_type,
        "name": item.get("name", ""),
        "poster": item.get("poster"),
        "posterShape": "poster",
        "description": item.get("description"),
        "releaseInfo": item.get("release_info"),
        "imdbRating": str(round(item["vote_average"], 1)) if item.get("vote_average") else None,
    }


# ── AniList fetcher ─────────────────────────────────────────────────────

async def _fetch_anilist_catalog(
    request: Request,
    catalog_id: str,
    catalog_def: Any,
    language: str,
    page: int,
    search_query: str | None,
    genre_filter: str | None,
) -> list[dict[str, Any]]:
    """Fetch catalog data from AniList and convert to MetaPreview dicts."""
    anilist = request.app.state.anilist_client
    grouper = request.app.state.anime_grouper
    id_mapper = request.app.state.id_mapper

    items: list[dict[str, Any]] = []

    if search_query:
        items = await anilist.search_anime(search_query, page)
    elif genre_filter:
        genres_list: list[str] = []
        tags_list: list[str] = []
        if genre_filter in _ANILIST_TAGS:
            tags_list.append(genre_filter)
        else:
            genres_list.append(genre_filter)
        items = await anilist.get_anime_by_genre(genres_list, tags_list, page)
    else:
        endpoint = catalog_def.provider_params.get("endpoint", "")
        if endpoint == "trending":
            items = await anilist.get_trending_anime(page)
        elif endpoint == "popular":
            items = await anilist.get_popular_anime(page)
        elif endpoint == "seasonal":
            season, year = get_current_anime_season()
            items = await anilist.get_seasonal_anime(season, year, page)
        elif endpoint == "by_genre":
            genres = catalog_def.provider_params.get("genres", [])
            tags = catalog_def.provider_params.get("tags", [])
            items = await anilist.get_anime_by_genre(genres, tags, page)

    # Deduplicate anime seasons
    items = await grouper.deduplicate_catalog(items)

    # Convert to MetaPreview format with Stremio IDs
    metas = []
    for item in items:
        anilist_id = item.get("anilist_id")
        stremio_id = await id_mapper.get_stremio_id(anilist_id) if anilist_id else f"anilist:{anilist_id}"
        metas.append(_anilist_item_to_meta(item, stremio_id))

    return metas


def _anilist_item_to_meta(item: dict[str, Any], stremio_id: str) -> dict[str, Any]:
    """Convert an AniList item dict to a Stremio MetaPreview dict."""
    score = item.get("average_score")
    return {
        "id": stremio_id,
        "type": "anime",
        "name": item.get("title", ""),
        "poster": item.get("poster"),
        "posterShape": "poster",
        "description": item.get("description"),
        "releaseInfo": str(item["start_year"]) if item.get("start_year") else None,
        "imdbRating": str(round(score / 10, 1)) if score else None,
        "genres": item.get("genres", []),
    }


# ── Route definitions ──────────────────────────────────────────────────

@router.get("/catalog/{type}/{catalog_id}.json")
async def catalog_no_config(request: Request, type: str, catalog_id: str):
    return await _handle_catalog(request, type, catalog_id)


@router.get("/catalog/{type}/{catalog_id}/{extra}.json")
async def catalog_no_config_extra(request: Request, type: str, catalog_id: str, extra: str):
    return await _handle_catalog(request, type, catalog_id, extra=extra)


@router.get("/{config}/catalog/{type}/{catalog_id}.json")
async def catalog_with_config(request: Request, config: str, type: str, catalog_id: str):
    return await _handle_catalog(request, type, catalog_id, config=config)


@router.get("/{config}/catalog/{type}/{catalog_id}/{extra}.json")
async def catalog_with_config_extra(
    request: Request, config: str, type: str, catalog_id: str, extra: str,
):
    return await _handle_catalog(request, type, catalog_id, config=config, extra=extra)
