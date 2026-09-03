import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

class TMDBClient:
    """
    Async client for TMDB API v3.
    Provides methods for fetching movies, series, details, searching, and discovering.
    """

    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

    def __init__(self, api_key: str):
        """
        Initialize the TMDBClient.
        
        Args:
            api_key (str): TMDB API key provided via user config.
        """
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            params={"api_key": self.api_key},
            timeout=10.0,
        )
        self._genre_cache: Dict[str, Dict[str, Dict[int, str]]] = {
            "movie": {},
            "tv": {}
        }

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Make an HTTP request to the TMDB API with retry logic for rate limits.
        
        Args:
            method (str): HTTP method.
            endpoint (str): API endpoint.
            **kwargs: Additional arguments for httpx.AsyncClient.request.
            
        Returns:
            Dict[str, Any]: JSON response from the API.
            
        Raises:
            httpx.HTTPStatusError: If the API returns an error.
        """
        retries = 3
        backoff = 1.0

        for attempt in range(retries):
            try:
                response = await self._client.request(method, endpoint, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", backoff))
                    logger.warning(f"Rate limited by TMDB. Retrying in {retry_after} seconds.")
                    await asyncio.sleep(retry_after)
                    backoff *= 2
                else:
                    logger.error(f"HTTP error {e.response.status_code} for {endpoint}: {e.response.text}")
                    raise
            except httpx.RequestError as e:
                logger.error(f"Request error for {endpoint}: {str(e)}")
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2

        raise RuntimeError(f"Max retries reached for {endpoint}")

    def _make_poster_url(self, path: Optional[str], width: str = "w500") -> Optional[str]:
        if not path:
            return None
        return f"{self.IMAGE_BASE_URL}/{width}{path}"

    def _make_backdrop_url(self, path: Optional[str], width: str = "w1280") -> Optional[str]:
        if not path:
            return None
        return f"{self.IMAGE_BASE_URL}/{width}{path}"

    def _format_list_item(self, item: Dict[str, Any], media_type: str) -> Dict[str, Any]:
        """
        Format a raw TMDB item into a standard dict for list methods.
        """
        # Determine media type if not explicitly passed
        item_type = item.get("media_type", media_type)
        if item_type == "tv":
            item_type = "series"

        release_date = item.get("release_date") or item.get("first_air_date")
        release_year = str(release_date)[:4] if release_date else None

        return {
            "tmdb_id": item["id"],
            "type": item_type,
            "name": item.get("title") or item.get("name") or "",
            "poster": self._make_poster_url(item.get("poster_path")),
            "banner": self._make_backdrop_url(item.get("backdrop_path")),
            "description": item.get("overview"),
            "release_info": release_year,
            "vote_average": item.get("vote_average"),
            "genre_ids": item.get("genre_ids", []),
            "original_language": item.get("original_language"),
        }

    async def _populate_genre_cache(self, media_type: str, language: str) -> None:
        """Fetch and cache genres for the given media type and language."""
        if language not in self._genre_cache[media_type]:
            logger.info(f"Populating genre cache for {media_type} ({language})")
            data = await self.get_genre_list(media_type, language)
            self._genre_cache[media_type][language] = {g["id"]: g["name"] for g in data.get("genres", [])}

    async def get_genre_list(self, media_type: str, language: str = "pt-BR") -> Dict[str, Any]:
        """Get the list of official genres for movies or TV series."""
        params = {"language": language}
        return await self._request("GET", f"/genre/{media_type}/list", params=params)

    # --- Movies ---

    async def get_trending_movies(self, time_window: str = "week", language: str = "pt-BR", page: int = 1) -> List[Dict[str, Any]]:
        """Get trending movies."""
        params = {"language": language, "page": page}
        data = await self._request("GET", f"/trending/movie/{time_window}", params=params)
        return [self._format_list_item(item, "movie") for item in data.get("results", [])]

    async def get_popular_movies(self, language: str = "pt-BR", page: int = 1) -> List[Dict[str, Any]]:
        """Get popular movies."""
        params = {"language": language, "page": page}
        data = await self._request("GET", "/movie/popular", params=params)
        return [self._format_list_item(item, "movie") for item in data.get("results", [])]

    async def get_now_playing_movies(self, language: str = "pt-BR", page: int = 1) -> List[Dict[str, Any]]:
        """Get now playing movies."""
        params = {"language": language, "page": page}
        data = await self._request("GET", "/movie/now_playing", params=params)
        return [self._format_list_item(item, "movie") for item in data.get("results", [])]

    async def get_external_ids(self, item_id: int, content_type: str) -> dict[str, Any]:
        """Fetch external IDs (IMDB) for a movie or series."""
        endpoint = f"/movie/{item_id}/external_ids" if content_type == "movie" else f"/tv/{item_id}/external_ids"
        return await self._request("GET", endpoint)

    async def find_by_external_id(self, external_id: str, external_source: str = "imdb_id") -> dict[str, Any]:
        """Find TMDB item by external ID."""
        return await self._request("GET", f"/find/{external_id}", params={"external_source": external_source})

    async def get_movie_details(self, movie_id: int, language: str = "en-US") -> dict[str, Any]:
        """Get rich details for a movie."""
        params = {
            "language": language,
            "append_to_response": "credits,videos,external_ids"
        }
        data = await self._request("GET", f"/movie/{movie_id}", params=params)
        return data

    async def search_movies(self, query: str, language: str = "pt-BR", page: int = 1) -> List[Dict[str, Any]]:
        """Search for movies."""
        params = {"query": query, "language": language, "page": page}
        data = await self._request("GET", "/search/movie", params=params)
        return [self._format_list_item(item, "movie") for item in data.get("results", [])]

    async def discover_movies(self, genre_ids: Optional[List[int]] = None, language: str = "pt-BR", page: int = 1, **kwargs: Any) -> List[Dict[str, Any]]:
        """Discover movies with various filters."""
        params: Dict[str, Any] = {"language": language, "page": page}
        if genre_ids:
            params["with_genres"] = ",".join(map(str, genre_ids))
        params.update(kwargs)
        data = await self._request("GET", "/discover/movie", params=params)
        return [self._format_list_item(item, "movie") for item in data.get("results", [])]

    # --- Series (TV) ---

    async def get_trending_series(self, time_window: str = "week", language: str = "pt-BR", page: int = 1) -> List[Dict[str, Any]]:
        """Get trending series."""
        params = {"language": language, "page": page}
        data = await self._request("GET", f"/trending/tv/{time_window}", params=params)
        return [self._format_list_item(item, "series") for item in data.get("results", [])]

    async def get_popular_series(self, language: str = "pt-BR", page: int = 1) -> List[Dict[str, Any]]:
        """Get popular series."""
        params = {"language": language, "page": page}
        data = await self._request("GET", "/tv/popular", params=params)
        return [self._format_list_item(item, "series") for item in data.get("results", [])]

    async def get_airing_today_series(self, language: str = "pt-BR", page: int = 1) -> List[Dict[str, Any]]:
        """Get series airing today."""
        params = {"language": language, "page": page}
        data = await self._request("GET", "/tv/airing_today", params=params)
        return [self._format_list_item(item, "series") for item in data.get("results", [])]

    async def get_series_details(self, tmdb_id: int, language: str = "pt-BR") -> Dict[str, Any]:
        """Get rich details for a TV series, including season details."""
        params = {
            "language": language,
            "append_to_response": "credits,videos,external_ids"
        }
        data = await self._request("GET", f"/tv/{tmdb_id}", params=params)
        return data

    async def search_series(self, query: str, language: str = "pt-BR", page: int = 1) -> List[Dict[str, Any]]:
        """Search for series."""
        params = {"query": query, "language": language, "page": page}
        data = await self._request("GET", "/search/tv", params=params)
        return [self._format_list_item(item, "series") for item in data.get("results", [])]

    async def discover_series(self, genre_ids: Optional[List[int]] = None, language: str = "pt-BR", page: int = 1, **kwargs: Any) -> List[Dict[str, Any]]:
        """Discover series with various filters."""
        params: Dict[str, Any] = {"language": language, "page": page}
        if genre_ids:
            params["with_genres"] = ",".join(map(str, genre_ids))
        params.update(kwargs)
        data = await self._request("GET", "/discover/tv", params=params)
        return [self._format_list_item(item, "series") for item in data.get("results", [])]

    # --- External IDs ---

    async def get_external_ids(self, tmdb_id: int, media_type: str = "movie") -> Dict[str, Any]:
        """
        Get external ids (IMDB, TVDB, etc.) for a movie or TV series.
        
        Args:
            tmdb_id (int): TMDB ID.
            media_type (str): 'movie' or 'series' (or 'tv')
            
        Returns:
            Dict[str, Any]: Dictionary of external IDs.
        """
        # Internal map for media_type 'series' -> 'tv'
        if media_type == "series":
            media_type = "tv"
            
        data = await self._request("GET", f"/{media_type}/{tmdb_id}/external_ids")
        return data
