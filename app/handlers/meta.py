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
    """Resolve metadata for an item."""
    user_config = decode_user_config(config) if config else None
    cache = request.app.state.cache

    # Strip .json suffix if present
    clean_id = item_id.removesuffix(".json")

    cache_key = f"meta:v2:{content_type}:{clean_id}"
    if user_config:
        cache_key += f":{user_config.language}"

    cached = await cache.get(cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    if content_type in ("movie", "series"):
        response = await _handle_tmdb_meta(request, content_type, clean_id, user_config)
    elif content_type == "anime":
        response = await _handle_anime_meta(request, clean_id, user_config)
    else:
        raise HTTPException(status_code=404, detail="Unsupported content type")

    if response:
        await cache.set(cache_key, response, ttl=86400)
        return JSONResponse(content=response)
    
    raise HTTPException(status_code=404, detail="Metadata not found")


async def _handle_anime_meta(request: Request, clean_id: str, user_config: Any) -> dict[str, Any] | None:
    anilist_client = request.app.state.anilist_client
    anime_grouper = request.app.state.anime_grouper
    id_mapper = request.app.state.id_mapper
    cache = request.app.state.cache



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

    return {
        "meta": meta,
        "cacheMaxAge": 86400,  # 24 hours
    }


async def _handle_tmdb_meta(request: Request, content_type: str, clean_id: str, user_config: Any) -> dict[str, Any]:
    if not clean_id.startswith("tmdb:") and not clean_id.startswith("tt"):
        raise HTTPException(status_code=400, detail="Only tmdb: or tt IDs are supported for movies/series")
        
    api_key = user_config.tmdb_api_key if user_config else ""
    if not api_key:
        raise HTTPException(status_code=400, detail="TMDB API Key required for metadata")

    tmdb = TMDBClient(api_key)
    language = user_config.language if user_config else "pt-BR"
    
    try:
        tmdb_id = None
        
        if clean_id.startswith("tt"):
            # Resolve IMDB ID to TMDB ID
            find_res = await tmdb.find_by_external_id(clean_id)
            if content_type == "movie" and find_res.get("movie_results"):
                tmdb_id = find_res["movie_results"][0]["id"]
            elif content_type == "series" and find_res.get("tv_results"):
                tmdb_id = find_res["tv_results"][0]["id"]
            if not tmdb_id:
                raise HTTPException(status_code=404, detail="TMDB ID not found for IMDB ID")
        else:
            try:
                tmdb_id = int(clean_id.split(":")[1])
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid TMDB ID")
        if content_type == "movie":
            details = await tmdb.get_movie_details(tmdb_id, language)
        else:
            details = await tmdb.get_series_details(tmdb_id, language)
            
        rel_date = details.get("release_date") if content_type == "movie" else details.get("first_air_date")
        release_info = str(rel_date)[:4] if rel_date else None
        
        runtime = details.get("runtime")
        runtime_str = f"{runtime} min" if runtime else None
        
        meta = {
            "id": clean_id,
            "type": content_type,
            "name": details.get("title") or details.get("name") or "",
            "poster": tmdb._make_poster_url(details.get("poster_path")),
            "posterShape": "poster",
            "background": tmdb._make_backdrop_url(details.get("backdrop_path")),
            "description": details.get("overview"),
            "releaseInfo": release_info,
            "imdbRating": str(round(details["vote_average"], 1)) if details.get("vote_average") else None,
            "genres": [g["name"] for g in details.get("genres", [])],
            "runtime": runtime_str if content_type == "movie" else None,
        }
        
        import urllib.parse
        links = []
        
        # Build dynamic manifest URL for discover links
        base_url = str(request.base_url).rstrip("/")
        # Extract config from path if present (e.g. /ey.../meta/movie/tt123.json)
        path_parts = request.url.path.strip("/").split("/")
        if len(path_parts) > 3 and path_parts[1] == "meta":
            manifest_url = f"{base_url}/{path_parts[0]}/manifest.json"
        else:
            manifest_url = f"{base_url}/manifest.json"
        encoded_manifest = urllib.parse.quote(manifest_url, safe="")
        
        # Add genres
        for g in details.get("genres", []):
            encoded_genre = urllib.parse.quote(g["name"])
            catalog_id = "movie_popular" if content_type == "movie" else "series_popular"
            links.append({
                "name": g["name"],
                "category": "Genres",
                "url": f"stremio:///discover/{encoded_manifest}/{content_type}/{catalog_id}?genre={encoded_genre}"
            })
            
        # Add cast
        credits_data = details.get("credits") or {}
        cast_list = credits_data.get("cast", [])[:5]
        for c in cast_list:
            encoded_name = urllib.parse.quote(c["name"])
            links.append({
                "name": c["name"],
                "category": "Cast",
                "url": f"stremio:///search?search={encoded_name}"
            })
            
        # Add directors
        crew = credits_data.get("crew", [])
        directors = [c["name"] for c in crew if c.get("job") == "Director"]
        for d in directors:
            encoded_name = urllib.parse.quote(d)
            links.append({
                "name": d,
                "category": "Directors",
                "url": f"stremio:///search?search={encoded_name}"
            })
            
        if links:
            meta["links"] = links

        # Add videos/trailers
        videos_data = details.get("videos") or {}
        trailers = [v for v in videos_data.get("results", []) if v.get("site") == "YouTube" and v.get("type") == "Trailer"]
        if trailers:
            meta["trailers"] = [{"source": t["key"], "type": "Trailer"} for t in trailers]

        # Add logo (title treatment image)
        images_data = details.get("images") or {}
        logos = images_data.get("logos", [])
        if logos:
            # Prefer user's language, then English, then any
            lang_code = language[:2]
            logo = next((l for l in logos if l.get("iso_639_1") == lang_code), None)
            if not logo:
                logo = next((l for l in logos if l.get("iso_639_1") == "en"), None)
            if not logo:
                logo = logos[0]
            if logo and logo.get("file_path"):
                meta["logo"] = f"https://image.tmdb.org/t/p/w500{logo['file_path']}"

        # Add episodes if series
        if content_type == "series" and "seasons" in details:
            meta_videos = []
            for season in details["seasons"]:
                s_num = season.get("season_number")
                # Skip specials (season 0) if you want, but Stremio supports it
                ep_count = season.get("episode_count", 0)
                for ep_num in range(1, ep_count + 1):
                    # We just provide the grid, no need to fetch individual episode names for now to save API calls
                    meta_videos.append({
                        "id": f"{clean_id}:{s_num}:{ep_num}",
                        "title": f"Episódio {ep_num}",
                        "season": s_num,
                        "episode": ep_num,
                    })
            if meta_videos:
                meta["videos"] = meta_videos

        return {
            "meta": meta,
            "cacheMaxAge": 86400,
        }
    finally:
        await tmdb.close()


# ── Route definitions ──────────────────────────────────────────────────

@router.get("/meta/{type}/{id}.json")
async def meta_no_config(request: Request, type: str, id: str):
    return await _handle_meta(request, type, id)


@router.get("/{config}/meta/{type}/{id}.json")
async def meta_with_config(request: Request, config: str, type: str, id: str):
    return await _handle_meta(request, type, id, config=config)
