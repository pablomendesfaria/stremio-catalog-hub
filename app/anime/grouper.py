import logging
from typing import Any, Dict, List, Optional

from app.providers.anilist import AniListClient
from app.providers.id_mapper import IDMapper
from app.cache.redis_cache import RedisCache
from app.models.catalog import AnimeGroup, AnimeSeasonEntry

logger = logging.getLogger(__name__)

class AnimeGrouper:
    """
    Groups anime seasons into a single franchise entry using AniList relations data.
    """

    def __init__(self, anilist_client: AniListClient, id_mapper: IDMapper, cache: RedisCache):
        self.anilist_client = anilist_client
        self.id_mapper = id_mapper
        self.cache = cache
        self.ttl_seconds = 7 * 24 * 60 * 60  # 7 days

    async def _get_relations(self, anilist_id: int) -> List[Dict[str, Any]]:
        """Fetch relations and normalize to a list of edges."""
        try:
            relations_data = await self.anilist_client.get_anime_relations(anilist_id)
            if not relations_data:
                return []
            if isinstance(relations_data, dict) and "edges" in relations_data:
                return relations_data["edges"]
            if isinstance(relations_data, list):
                return relations_data
            return []
        except Exception as e:
            logger.error(f"Failed to fetch relations for {anilist_id}: {e}")
            return []

    async def group_anime(self, anilist_id: int) -> AnimeGroup:
        """
        Group anime seasons into a single franchise entry instantly using Fribb TMDB IDs.
        """
        if not self.id_mapper._is_loaded:
            await self.id_mapper.load_database()
            
        mappings = self.id_mapper.anilist_to_mappings.get(anilist_id)
        
        # If no TMDB ID, we return a standalone group
        if not mappings or not mappings.themoviedb_id:
            stremio_id = await self.id_mapper.get_stremio_id(anilist_id)
            group = AnimeGroup(
                root_anilist_id=anilist_id,
                title="",
                stremio_id=stremio_id,
                seasons=[AnimeSeasonEntry(anilist_id=anilist_id, season_number=1, title="", stremio_id=stremio_id)]
            )
            return group

        # Fetch all AniList IDs sharing the same TMDB ID
        tmdb_id = mappings.themoviedb_id
        related_seasons = self.id_mapper.tmdb_to_anilist_seasons.get(tmdb_id, [])
        
        if not related_seasons:
            related_seasons = [(anilist_id, mappings.tmdb_season or 1)]
            
        # Deduplicate and sort by season
        unique_seasons = {}
        for a_id, s_num in related_seasons:
            if s_num not in unique_seasons or unique_seasons[s_num] == a_id:
                unique_seasons[s_num] = a_id
            # If Fribb has multiple anilist_ids for the same season (like Part 1 / Part 2), 
            # we keep the first one or we can just append them sequentially.
            # But Stremio only supports one list of episodes per season.
            # We'll just map both! Let's allow multiple AniList IDs per season!
            # Wait, our meta_videos logic uses `season_entry.season_number`.
            # If two entries have the same season number, their episodes will append!
        
        # Better: just use a list, sort by season
        seasons: List[AnimeSeasonEntry] = []
        # Sort by season number, then by anilist_id to maintain part1/part2 order
        related_seasons.sort(key=lambda x: (x[1], x[0]))
        
        for a_id, s_num in related_seasons:
            s_id = await self.id_mapper.get_stremio_id(a_id)
            seasons.append(AnimeSeasonEntry(anilist_id=a_id, season_number=s_num, title="", stremio_id=s_id))

        # Find the root (lowest season)
        root_id = seasons[0].anilist_id
        stremio_id = await self.id_mapper.get_stremio_id(root_id)

        # 6. Build AnimeGroup
        title = ""
        poster = ""
        banner = ""
        genres = []
        
        # We purposefully do NOT fetch root_node from AniList here to avoid rate limits!
        # The deduplicate_catalog method will naturally fallback to using the current item's
        # title, poster, etc. which is perfectly fine for the catalog UI.
        
        group = AnimeGroup(
            root_anilist_id=root_id,
            title="",
            poster="",
            banner="",
            genres=[],
            stremio_id=stremio_id,
            seasons=seasons
        )
        
        # 7. Cache the result
        try:
            group_json = group.model_dump_json()
            await self.cache.set(f"anime_group:{root_id}", group_json, expire=self.ttl_seconds)
            
            for season in seasons:
                await self.cache.set(
                    f"anime_group_member:{season.anilist_id}", 
                    str(root_id), 
                    expire=self.ttl_seconds
                )
        except Exception as e:
            logger.error(f"Failed to cache AnimeGroup for root {root_id}: {e}")
            
        return group

    async def deduplicate_catalog(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicates a list of anime items by replacing them with their root franchise entry.
        """
        deduplicated = []
        seen_roots = set()
        
        for item in items:
            anilist_id = item.get("id")
            if not anilist_id:
                deduplicated.append(item)
                continue
                
            try:
                group = await self.group_anime(anilist_id)
                root_id = group.root_anilist_id
                
                if root_id not in seen_roots:
                    seen_roots.add(root_id)
                    # Replace item with root entry info, preserving original properties where missing
                    if anilist_id == root_id:
                        deduplicated.append(item)
                    else:
                        root_item = dict(item)
                        root_item["id"] = root_id
                        if group.title:
                            if isinstance(root_item.get("title"), dict):
                                root_item["title"]["english"] = group.title
                            else:
                                root_item["title"] = group.title
                        
                        if group.poster:
                            if isinstance(root_item.get("coverImage"), dict):
                                root_item["coverImage"]["large"] = group.poster
                            else:
                                root_item["coverImage"] = {"large": group.poster}
                                
                        if group.banner:
                            root_item["bannerImage"] = group.banner
                            
                        deduplicated.append(root_item)
            except Exception as e:
                logger.error(f"Error deduplicating item {anilist_id}: {e}")
                if anilist_id not in seen_roots:
                    seen_roots.add(anilist_id)
                    deduplicated.append(item)
                
        return deduplicated

    async def get_group_for_meta(self, anilist_id: int) -> Optional[AnimeGroup]:
        """
        Returns the full group for an anime, used by the meta handler.
        """
        try:
            return await self.group_anime(anilist_id)
        except Exception as e:
            logger.error(f"Error getting group for meta (ID {anilist_id}): {e}")
            return None
