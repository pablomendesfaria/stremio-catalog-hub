import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class MALClient:
    """Fallback client for MyAnimeList using Jikan API v4."""

    BASE_URL = "https://api.jikan.moe/v4"

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self.client = client or httpx.AsyncClient(timeout=10.0)
        # Jikan allows 3 requests per second
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time = 0.0

    async def close(self):
        await self.client.aclose()

    async def _wait_for_rate_limit(self):
        async with self._rate_limit_lock:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - self._last_request_time
            if elapsed < 0.34:  # ~3 requests per second = 333ms per request
                await asyncio.sleep(0.34 - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    async def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{endpoint}"
        retries = 3
        delay = 1.0

        for attempt in range(retries):
            await self._wait_for_rate_limit()
            
            try:
                response = await self.client.get(url, params=params)
                
                if response.status_code == 429:
                    logger.warning("Jikan API rate limited (429). Backing off.")
                    await asyncio.sleep(delay * 2)
                    delay *= 2
                    continue
                    
                response.raise_for_status()
                data = response.json()
                return data.get("data", {})
                
            except httpx.HTTPError as e:
                logger.error(f"HTTP Error during Jikan request to {endpoint}: {e}")
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(delay)
                delay *= 2

        raise Exception(f"Failed to fetch from Jikan API: {endpoint}")

    def _map_media(self, media: Dict[str, Any]) -> Dict[str, Any]:
        """Map Jikan media object to the unified format (similar to AniList)."""
        titles = media.get("titles", [])
        english_title = next((t["title"] for t in titles if t["type"] == "English"), None)
        romaji_title = media.get("title")
        
        start_year = media.get("year")
        
        genres = [g.get("name") for g in media.get("genres", [])]
        explicit_genres = [g.get("name") for g in media.get("explicit_genres", [])]
        themes = [t.get("name") for t in media.get("themes", [])]
        demographics = [d.get("name") for d in media.get("demographics", [])]
        
        all_tags = themes + demographics
        
        images = media.get("images", {}).get("jpg", {})
        
        return {
            'anilist_id': None,  # Not natively returned by Jikan
            'mal_id': media.get("mal_id"),
            'title': english_title or romaji_title or "Unknown Title",
            'title_romaji': romaji_title,
            'title_english': english_title,
            'poster': images.get("large_image_url") or images.get("image_url"),
            'banner': None,
            'description': media.get("synopsis"),
            'format': media.get("type"),
            'status': media.get("status"),
            'episodes': media.get("episodes"),
            'average_score': int(media.get("score") * 10) if media.get("score") else None,  # Match 100-scale
            'popularity': media.get("popularity"),
            'genres': genres + explicit_genres,
            'tags': all_tags,
            'season': media.get("season").upper() if media.get("season") else None,
            'season_year': media.get("year"),
            'start_year': start_year,
        }

    async def get_anime_details(self, mal_id: int) -> Dict[str, Any]:
        endpoint = f"/anime/{mal_id}/full"
        data = await self._request(endpoint)
        return self._map_media(data)

    async def search_anime(self, query: str, page: int = 1) -> List[Dict[str, Any]]:
        endpoint = "/anime"
        params = {"q": query, "page": page}
        # Note: Jikan response structure has a list of items under 'data' for search
        # So we override the generic request method handling slightly since it returns a list
        url = f"{self.BASE_URL}{endpoint}"
        await self._wait_for_rate_limit()
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            res_data = response.json()
            return [self._map_media(m) for m in res_data.get("data", [])]
        except Exception as e:
            logger.error(f"Failed to search anime on Jikan: {e}")
            raise

    async def get_anime_relations(self, mal_id: int) -> Dict[str, Any]:
        # Need to fetch the title first since relations don't include parent title in Jikan
        try:
            parent_details = await self.get_anime_details(mal_id)
            title = parent_details.get("title")
        except Exception:
            title = f"MAL ID {mal_id}"

        endpoint = f"/anime/{mal_id}/relations"
        url = f"{self.BASE_URL}{endpoint}"
        await self._wait_for_rate_limit()
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            res_data = response.json()
            relations_data = res_data.get("data", [])
        except Exception as e:
            logger.error(f"Failed to fetch relations on Jikan: {e}")
            relations_data = []

        relations_list = []
        for relation_group in relations_data:
            relation_type = relation_group.get("relation", "").upper().replace(" ", "_")
            for entry in relation_group.get("entry", []):
                if entry.get("type") != "anime":
                    continue
                
                relations_list.append({
                    'relation_type': relation_type,
                    'node': {
                        'anilist_id': None,
                        'mal_id': entry.get("mal_id"),
                        'title': entry.get("name"),
                        'format': None,
                        'status': None,
                        'episodes': None,
                        'season': None,
                        'season_year': None,
                    }
                })
                
        return {
            'id': mal_id,
            'title': title,
            'relations': relations_list
        }
