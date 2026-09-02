import json
import logging
import re
from typing import Optional, Dict, Any, List
import httpx
from pydantic import BaseModel, ConfigDict

from app.cache.redis_cache import RedisCache

logger = logging.getLogger(__name__)

FRIBB_URL = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json"
ANIZIP_URL = "https://api.ani.zip/mappings"

class Mappings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    anilist_id: Optional[int] = None
    imdb_id: Optional[str] = None
    kitsu_id: Optional[int] = None
    mal_id: Optional[int] = None
    thetvdb_id: Optional[int] = None
    themoviedb_id: Optional[int] = None

class IDMapper:
    """
    Maps AniList IDs to IMDB IDs (and Kitsu IDs as fallback) for Stremio compatibility.
    
    Two-Layer Mapping Strategy:
    1. Layer 1: Fribb anime-lists (Primary, Static Dataset)
    2. Layer 2: AniZip API (Fallback, Dynamic)
    """

    def __init__(self, cache: RedisCache):
        self.cache = cache
        self.anilist_to_mappings: Dict[int, Mappings] = {}
        self.imdb_to_anilist: Dict[str, int] = {}
        self.mal_to_anilist: Dict[int, int] = {}
        self.kitsu_to_anilist: Dict[int, int] = {}
        self._is_loaded = False

    async def load_database(self) -> None:
        """
        Loads the Fribb database from Redis cache. If it misses, downloads from GitHub.
        """
        cached_data = await self.cache.get("id_mapper:fribb_db")
        if cached_data:
            try:
                # Assuming RedisCache returns string/bytes
                if isinstance(cached_data, bytes):
                    cached_data = cached_data.decode("utf-8")
                data = json.loads(cached_data)
                self._populate_indexes(data)
                self._is_loaded = True
                logger.info("Loaded Fribb mapping database from Redis cache.")
                return
            except Exception as e:
                logger.error(f"Failed to parse cached Fribb database: {e}")

        logger.info("Downloading Fribb mapping database...")
        await self.refresh_database()

    async def refresh_database(self) -> None:
        """
        Re-downloads Fribb data, builds the mappings, and stores in Redis.
        Usually called by a scheduler or when cache is empty.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(FRIBB_URL)
                response.raise_for_status()
                data = response.json()

            self._populate_indexes(data)
            self._is_loaded = True
            
            # Store in Redis with TTL of 24 hours (86400 seconds)
            await self.cache.set("id_mapper:fribb_db", json.dumps(data), ttl=86400)
            logger.info(f"Successfully downloaded and indexed {len(data)} items from Fribb database.")
        except Exception as e:
            logger.warning(f"Failed to refresh Fribb database (network or parse error): {e}")

    def _extract_anilist_id(self, item: Dict[str, Any]) -> Optional[int]:
        """Helper to extract anilist_id directly or from the sources array."""
        if item.get("anilist_id"):
            try:
                return int(item["anilist_id"])
            except ValueError:
                pass
        
        # Fallback to parse from sources array
        for source in item.get("sources", []):
            if "anilist.co/anime/" in source:
                match = re.search(r'anilist\.co/anime/(\d+)', source)
                if match:
                    return int(match.group(1))
        return None

    def _populate_indexes(self, data: List[Dict[str, Any]]) -> None:
        """Builds in-memory dictionaries for fast O(1) lookups."""
        self.anilist_to_mappings.clear()
        self.imdb_to_anilist.clear()
        self.mal_to_anilist.clear()
        self.kitsu_to_anilist.clear()

        for item in data:
            anilist_id = self._extract_anilist_id(item)
            if not anilist_id:
                continue

            try:
                mappings = Mappings(
                    anilist_id=anilist_id,
                    imdb_id=item.get("imdb_id"),
                    kitsu_id=int(item["kitsu_id"]) if item.get("kitsu_id") else None,
                    mal_id=int(item["mal_id"]) if item.get("mal_id") else None,
                    thetvdb_id=int(item["thetvdb_id"]) if item.get("thetvdb_id") else None,
                    themoviedb_id=int(item["themoviedb_id"]) if item.get("themoviedb_id") else None,
                )
                
                self.anilist_to_mappings[anilist_id] = mappings
                
                if mappings.imdb_id:
                    self.imdb_to_anilist[mappings.imdb_id] = anilist_id
                if mappings.mal_id:
                    self.mal_to_anilist[mappings.mal_id] = anilist_id
                if mappings.kitsu_id:
                    self.kitsu_to_anilist[mappings.kitsu_id] = anilist_id
            except (ValueError, TypeError) as e:
                # Ignore invalid entries rather than failing the whole load
                logger.debug(f"Failed to parse item IDs for {anilist_id}: {e}")

    async def _fetch_anizip_mappings(self, anilist_id: int) -> Optional[Mappings]:
        """Fetches dynamic mappings from AniZip if not in Fribb, and caches them."""
        cache_key = f"id_mapper:anizip:{anilist_id}"
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            try:
                if isinstance(cached_data, bytes):
                    cached_data = cached_data.decode("utf-8")
                return Mappings.model_validate_json(cached_data)
            except Exception as e:
                logger.error(f"Failed to parse cached AniZip mappings for {anilist_id}: {e}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{ANIZIP_URL}?anilist_id={anilist_id}")
                if response.status_code == 200:
                    data = response.json()
                    mappings_data = data.get("mappings", {})
                    if mappings_data:
                        mappings = Mappings(
                            anilist_id=anilist_id,
                            imdb_id=mappings_data.get("imdb_id"),
                            kitsu_id=int(mappings_data["kitsu_id"]) if mappings_data.get("kitsu_id") else None,
                            mal_id=int(mappings_data["mal_id"]) if mappings_data.get("mal_id") else None,
                            thetvdb_id=int(mappings_data["thetvdb_id"]) if mappings_data.get("thetvdb_id") else None,
                            themoviedb_id=int(mappings_data["themoviedb_id"]) if mappings_data.get("themoviedb_id") else None,
                        )
                        # Cache for 7 days
                        await self.cache.set(cache_key, mappings.model_dump_json(), ttl=604800)
                        return mappings
                elif response.status_code == 404:
                    logger.debug(f"AniZip returned 404 for anilist_id {anilist_id}")
                else:
                    logger.warning(f"AniZip API returned {response.status_code} for anilist_id {anilist_id}")
        except Exception as e:
            logger.warning(f"Error fetching from AniZip for anilist_id {anilist_id}: {e}")
        
        return None

    async def get_all_mappings(self, anilist_id: int) -> Dict[str, Any]:
        """Returns all known IDs for a given AniList ID."""
        if not self._is_loaded:
            await self.load_database()
            
        mappings = self.anilist_to_mappings.get(anilist_id)
        if not mappings:
            mappings = await self._fetch_anizip_mappings(anilist_id)
            
        if mappings:
            return mappings.model_dump(exclude_none=True)
        return {}

    async def get_imdb_id(self, anilist_id: int) -> Optional[str]:
        """Tries Fribb then AniZip to get IMDB ID."""
        mappings = await self.get_all_mappings(anilist_id)
        return mappings.get("imdb_id")

    async def get_kitsu_id(self, anilist_id: int) -> Optional[int]:
        """Tries Fribb then AniZip to get Kitsu ID."""
        mappings = await self.get_all_mappings(anilist_id)
        return mappings.get("kitsu_id")

    async def get_mal_id(self, anilist_id: int) -> Optional[int]:
        mappings = await self.get_all_mappings(anilist_id)
        return mappings.get("mal_id")

    async def get_tmdb_id(self, anilist_id: int) -> Optional[int]:
        mappings = await self.get_all_mappings(anilist_id)
        return mappings.get("themoviedb_id")

    async def get_anilist_id_from_imdb(self, imdb_id: str) -> Optional[int]:
        """Reverse lookup: returns anilist_id for a given imdb_id."""
        if not self._is_loaded:
            await self.load_database()
        return self.imdb_to_anilist.get(imdb_id)

    async def get_stremio_id(self, anilist_id: int) -> str:
        """
        Returns tt{imdb_id} if available, else kitsu:{kitsu_id}, else anilist:{anilist_id} as last resort.
        """
        mappings = await self.get_all_mappings(anilist_id)
        
        imdb_id = mappings.get("imdb_id")
        if imdb_id:
            imdb_id_str = str(imdb_id)
            return imdb_id_str if imdb_id_str.startswith("tt") else f"tt{imdb_id_str}"
            
        kitsu_id = mappings.get("kitsu_id")
        if kitsu_id:
            return f"kitsu:{kitsu_id}"
            
        return f"anilist:{anilist_id}"

    async def get_anilist_id_from_kitsu(self, kitsu_id: int) -> Optional[int]:
        """Reverse lookup: returns anilist_id for a given kitsu_id."""
        if not self._is_loaded:
            await self.load_database()
        return self.kitsu_to_anilist.get(kitsu_id)
