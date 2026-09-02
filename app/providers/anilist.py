import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def _strip_html(text: str | None) -> str | None:
    """Strip HTML tags from a string."""
    if not text:
        return text
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)


class AniListClient:
    """Client for AniList GraphQL API."""

    BASE_URL = "https://graphql.anilist.co"

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self.client = client or httpx.AsyncClient(timeout=10.0)
        
    async def close(self):
        await self.client.aclose()

    async def _request(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        retries = 3
        delay = 2.0
        
        for attempt in range(retries):
            try:
                response = await self.client.post(
                    self.BASE_URL,
                    json={"query": query, "variables": variables or {}},
                    headers={"Content-Type": "application/json"}
                )
                
                remaining = int(response.headers.get("X-RateLimit-Remaining", 90))
                if remaining < 5:
                    logger.warning(f"AniList rate limit running low: {remaining} remaining.")
                    await asyncio.sleep(2.0)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"AniList rate limited (429). Waiting {retry_after} seconds.")
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()
                
                if "errors" in data:
                    logger.error(f"AniList GraphQL error: {data['errors']}")
                    raise Exception(f"GraphQL Error: {data['errors']}")
                
                return data["data"]
                
            except httpx.HTTPError as e:
                logger.error(f"HTTP Error during AniList request: {e}")
                if response is not None and response.status_code == 429:
                    # Might happen if Retry-After is not handled
                    await asyncio.sleep(60)
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
                
        raise Exception("Failed to fetch from AniList after multiple retries")

    def _map_media(self, media: Dict[str, Any]) -> Dict[str, Any]:
        """Map AniList media object to our internal format."""
        title = media.get("title", {})
        pref_title = title.get("english") or title.get("romaji") or title.get("userPreferred") or "Unknown Title"
        
        start_date = media.get("startDate", {})
        start_year = start_date.get("year")
        
        return {
            'anilist_id': media.get("id"),
            'mal_id': media.get("idMal"),
            'title': pref_title,
            'title_romaji': title.get("romaji"),
            'title_english': title.get("english"),
            'poster': media.get("coverImage", {}).get("extraLarge") or media.get("coverImage", {}).get("large"),
            'banner': media.get("bannerImage"),
            'description': _strip_html(media.get("description")),
            'format': media.get("format"),
            'status': media.get("status"),
            'episodes': media.get("episodes"),
            'average_score': media.get("averageScore"),
            'popularity': media.get("popularity"),
            'genres': media.get("genres", []),
            'tags': [tag.get("name") for tag in media.get("tags", []) if tag.get("name")],
            'season': media.get("season"),
            'season_year': media.get("seasonYear"),
            'start_year': start_year,
        }

    _MEDIA_FIELDS = """
        id
        idMal
        title { romaji english native userPreferred }
        coverImage { extraLarge large }
        bannerImage
        format
        status
        episodes
        duration
        averageScore
        popularity
        trending
        genres
        tags { name rank }
        startDate { year month day }
        season
        seasonYear
        description
        nextAiringEpisode { airingAt episode }
    """

    async def get_trending_anime(self, page: int = 1, per_page: int = 25) -> List[Dict[str, Any]]:
        query = f"""
        query ($page: Int, $perPage: Int) {{
            Page(page: $page, perPage: $perPage) {{
                media(sort: [TRENDING_DESC, POPULARITY_DESC], type: ANIME, isAdult: false) {{
                    {self._MEDIA_FIELDS}
                }}
            }}
        }}
        """
        data = await self._request(query, {"page": page, "perPage": per_page})
        return [self._map_media(m) for m in data.get("Page", {}).get("media", [])]

    async def get_popular_anime(self, page: int = 1, per_page: int = 25) -> List[Dict[str, Any]]:
        query = f"""
        query ($page: Int, $perPage: Int) {{
            Page(page: $page, perPage: $perPage) {{
                media(sort: [POPULARITY_DESC], type: ANIME, isAdult: false) {{
                    {self._MEDIA_FIELDS}
                }}
            }}
        }}
        """
        data = await self._request(query, {"page": page, "perPage": per_page})
        return [self._map_media(m) for m in data.get("Page", {}).get("media", [])]

    async def get_seasonal_anime(self, season: str, year: int, page: int = 1, per_page: int = 25) -> List[Dict[str, Any]]:
        query = f"""
        query ($season: MediaSeason, $year: Int, $page: Int, $perPage: Int) {{
            Page(page: $page, perPage: $perPage) {{
                media(season: $season, seasonYear: $year, type: ANIME, sort: [POPULARITY_DESC], isAdult: false) {{
                    {self._MEDIA_FIELDS}
                }}
            }}
        }}
        """
        variables = {"season": season.upper(), "year": year, "page": page, "perPage": per_page}
        data = await self._request(query, variables)
        return [self._map_media(m) for m in data.get("Page", {}).get("media", [])]

    async def get_anime_by_genre(
        self, 
        genres: Optional[List[str]] = None, 
        tags: Optional[List[str]] = None, 
        page: int = 1, 
        per_page: int = 25
    ) -> List[Dict[str, Any]]:
        query = f"""
        query ($genres: [String], $tags: [String], $page: Int, $perPage: Int) {{
            Page(page: $page, perPage: $perPage) {{
                media(genre_in: $genres, tag_in: $tags, type: ANIME, sort: [POPULARITY_DESC], isAdult: false) {{
                    {self._MEDIA_FIELDS}
                }}
            }}
        }}
        """
        variables = {
            "page": page,
            "perPage": per_page
        }
        if genres:
            variables["genres"] = genres
        if tags:
            variables["tags"] = tags
            
        data = await self._request(query, variables)
        return [self._map_media(m) for m in data.get("Page", {}).get("media", [])]

    async def search_anime(self, query: str, page: int = 1, per_page: int = 25) -> List[Dict[str, Any]]:
        graphql_query = f"""
        query ($search: String, $page: Int, $perPage: Int) {{
            Page(page: $page, perPage: $perPage) {{
                media(search: $search, type: ANIME, isAdult: false) {{
                    {self._MEDIA_FIELDS}
                }}
            }}
        }}
        """
        data = await self._request(graphql_query, {"search": query, "page": page, "perPage": per_page})
        return [self._map_media(m) for m in data.get("Page", {}).get("media", [])]

    async def get_anime_details(self, anilist_id: int) -> Dict[str, Any]:
        query = f"""
        query ($id: Int) {{
            Media(id: $id, type: ANIME) {{
                {self._MEDIA_FIELDS}
            }}
        }}
        """
        data = await self._request(query, {"id": anilist_id})
        return self._map_media(data.get("Media", {}))

    async def get_anime_relations(self, anilist_id: int) -> Dict[str, Any]:
        query = """
        query ($id: Int) {
            Media(id: $id, type: ANIME) {
                id
                title { romaji english userPreferred }
                relations {
                    edges {
                        relationType(version: 2)
                        node {
                            id
                            idMal
                            type
                            format
                            status
                            season
                            seasonYear
                            episodes
                            title { romaji english userPreferred }
                        }
                    }
                }
            }
        }
        """
        data = await self._request(query, {"id": anilist_id})
        media = data.get("Media", {})
        
        if not media:
            return {}
            
        title_obj = media.get("title", {})
        title = title_obj.get("english") or title_obj.get("romaji") or title_obj.get("userPreferred") or "Unknown"
        
        relations_list = []
        edges = media.get("relations", {}).get("edges", [])
        
        for edge in edges:
            node = edge.get("node", {})
            if node.get("type") != "ANIME":
                continue
                
            node_title_obj = node.get("title", {})
            node_title = node_title_obj.get("english") or node_title_obj.get("romaji") or node_title_obj.get("userPreferred") or "Unknown"
            
            relations_list.append({
                'relation_type': edge.get("relationType"),
                'node': {
                    'anilist_id': node.get("id"),
                    'mal_id': node.get("idMal"),
                    'title': node_title,
                    'format': node.get("format"),
                    'status': node.get("status"),
                    'episodes': node.get("episodes"),
                    'season': node.get("season"),
                    'season_year': node.get("seasonYear"),
                }
            })
            
        return {
            'id': media.get("id"),
            'title': title,
            'relations': relations_list
        }

    async def get_available_genres(self) -> List[str]:
        query = """
        query {
            GenreCollection
        }
        """
        data = await self._request(query)
        return data.get("GenreCollection", [])

    async def get_available_tags(self, exclude_adult: bool = True) -> List[Dict[str, Any]]:
        query = """
        query {
            MediaTagCollection {
                name
                description
                category
                isAdult
            }
        }
        """
        data = await self._request(query)
        tags = data.get("MediaTagCollection", [])
        if exclude_adult:
            tags = [tag for tag in tags if not tag.get("isAdult")]
        return tags
