"""Meta handler — serves Stremio meta detail requests for anime.

Movies and series with IMDB IDs are handled by Cinemeta; this addon only
provides metadata for anime with custom IDs (``kitsu:…`` or ``anilist:…``).

Routes::

    GET /meta/{type}/{id}.json
    GET /{config}/meta/{type}/{id}.json
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.providers.tmdb import TMDBClient
from app.utils.helpers import decode_user_config

logger = logging.getLogger(__name__)
router = APIRouter()


async def _handle_meta(
    request: Request,
    content_type: str,
    item_id: str,
    config: str | None = None,
) -> JSONResponse:
    """Resolve metadata for an anime item."""

    # We only handle anime meta — movies/series use Cinemeta
    if content_type != "anime":
        raise HTTPException(
            status_code=404,
            detail="Only anime meta is supported by this addon",
        )

    user_config = decode_user_config(config) if config else None

    anilist_client = request.app.state.anilist_client
    anime_grouper = request.app.state.anime_grouper
    id_mapper = request.app.state.id_mapper
    cache = request.app.state.cache

    # Strip .json suffix if present
    clean_id = item_id.removesuffix(".json")

    # ── Resolve to AniList ID ───────────────────────────────────────────
    anilist_id: int | None = None

    if clean_id.startswith("kitsu:"):
        kitsu_id_str = clean_id.split(":", 1)[1]
        try:
            kitsu_id = int(kitsu_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid kitsu ID: {kitsu_id_str}")
        # Reverse lookup: kitsu → anilist
        anilist_id = await id_mapper.get_anilist_id_from_kitsu(kitsu_id)
    elif clean_id.startswith("anilist:"):
        try:
            anilist_id = int(clean_id.split(":", 1)[1])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid anilist ID: {clean_id}")
    elif clean_id.startswith("tt"):
        # IMDB ID — resolve to AniList
        anilist_id = await id_mapper.get_anilist_id_from_imdb(clean_id)

    if not anilist_id:
        raise HTTPException(status_code=404, detail="Could not resolve anime ID")

    # ── Check cache ─────────────────────────────────────────────────────
    cache_key = f"meta:anime:{anilist_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    # ── Fetch anime details from AniList ────────────────────────────────
    anime_details = await anilist_client.get_anime_details(anilist_id)
    if not anime_details:
        raise HTTPException(status_code=404, detail="Anime not found on AniList")

    # ── Get anime group (all seasons) ───────────────────────────────────
    anime_group = await anime_grouper.get_group_for_meta(anilist_id)

    # ── Build videos array ──────────────────────────────────────────────
    videos: list[dict[str, Any]] = []

    if anime_group and anime_group.seasons:
        for season_entry in anime_group.seasons:
            ep_count = season_entry.episodes or 12  # fallback to 12 if unknown
            season_stremio_id = season_entry.stremio_id or clean_id

            for ep_num in range(1, ep_count + 1):
                videos.append({
                    "id": f"{season_stremio_id}:{season_entry.season_number}:{ep_num}",
                    "title": f"Episode {ep_num}",
                    "season": season_entry.season_number,
                    "episode": ep_num,
                })
    else:
        # Standalone anime (no group or single-season)
        ep_count = anime_details.get("episodes") or 12
        for ep_num in range(1, ep_count + 1):
            videos.append({
                "id": f"{clean_id}:{1}:{ep_num}",
                "title": f"Episode {ep_num}",
                "season": 1,
                "episode": ep_num,
            })

    # ── Build MetaDetail ────────────────────────────────────────────────
    score = anime_details.get("average_score")
    meta: dict[str, Any] = {
        "id": clean_id,
        "type": "anime",
        "name": anime_details.get("title", "Unknown"),
        "poster": anime_details.get("poster"),
        "posterShape": "poster",
        "background": anime_details.get("banner"),
        "description": anime_details.get("description"),
        "releaseInfo": str(anime_details.get("start_year", "")),
        "imdbRating": str(round(score / 10, 1)) if score else None,
        "genres": anime_details.get("genres", []),
        "runtime": f"{anime_details.get('duration', 24)} min" if anime_details.get("duration") else "24 min",
        "videos": videos,
    }

    # ── Localised description from TMDB (if available) ──────────────────
    if user_config and user_config.tmdb_api_key:
        tmdb_id = await id_mapper.get_tmdb_id(anilist_id)
        if tmdb_id:
            try:
                tmdb = TMDBClient(user_config.tmdb_api_key)
                try:
                    tmdb_details = await tmdb.get_series_details(tmdb_id, user_config.language)
                    overview = tmdb_details.get("overview")
                    if overview:
                        meta["description"] = overview
                    # Also grab localised name if available
                    tmdb_name = tmdb_details.get("name")
                    if tmdb_name and user_config.language != "en-US":
                        meta["name"] = tmdb_name
                finally:
                    await tmdb.close()
            except Exception:
                logger.debug("Could not fetch TMDB details for anime %d", anilist_id)

    response = {
        "meta": meta,
        "cacheMaxAge": 86400,  # 24 hours
    }

    # Cache the response
    await cache.set(cache_key, response, ttl=86400)

    return JSONResponse(content=response)


# ── Route definitions ──────────────────────────────────────────────────

@router.get("/meta/{type}/{id}.json")
async def meta_no_config(request: Request, type: str, id: str):
    return await _handle_meta(request, type, id)


@router.get("/{config}/meta/{type}/{id}.json")
async def meta_with_config(request: Request, config: str, type: str, id: str):
    return await _handle_meta(request, type, id, config=config)
