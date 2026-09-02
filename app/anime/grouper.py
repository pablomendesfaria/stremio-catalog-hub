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
        Group anime seasons into a single franchise entry starting from the given ID.
        """
        # 1. Check cache first
        member_cache_key = f"anime_group_member:{anilist_id}"
        root_id_str = await self.cache.get(member_cache_key)
        
        if root_id_str:
            root_id = int(root_id_str)
            group_cache_key = f"anime_group:{root_id}"
            group_data_str = await self.cache.get(group_cache_key)
            if group_data_str:
                try:
                    return AnimeGroup.model_validate_json(group_data_str)
                except Exception as e:
                    logger.warning(f"Failed to parse cached AnimeGroup for root {root_id}: {e}")
        
        # 3. Find root (Season 1)
        current_id = anilist_id
        depth = 0
        visited_prequels = set()
        
        # Cache of node details to avoid re-fetching root details if not necessary
        node_details = {}
        
        while depth < 20:
            if current_id in visited_prequels:
                break
            visited_prequels.add(current_id)
            
            edges = await self._get_relations(current_id)
            if not edges:
                break
                
            found_prequel = False
            for edge in edges:
                rel_type = edge.get("relationType")
                node = edge.get("node", {})
                node_type = node.get("type")
                node_format = node.get("format")
                
                if rel_type == "PREQUEL" and node_type == "ANIME" and node_format in ("TV", "TV_SHORT", "ONA"):
                    node_id = node.get("id")
                    if node_id:
                        node_details[node_id] = node
                        current_id = node_id
                        found_prequel = True
                        break
                        
            if not found_prequel:
                break
            depth += 1
            
        root_id = current_id
        
        # 4. Build season chain
        seasons: List[AnimeSeasonEntry] = []
        visited_sequels = set()
        
        current_seq_id = root_id
        season_number = 1
        depth = 0
        
        while depth < 20:
            if current_seq_id in visited_sequels:
                break
            visited_sequels.add(current_seq_id)
            
            # Record current season
            seasons.append(AnimeSeasonEntry(
                anilist_id=current_seq_id,
                season_number=season_number
            ))
            
            edges = await self._get_relations(current_seq_id)
            found_sequel = False
            if edges:
                for edge in edges:
                    rel_type = edge.get("relationType")
                    node = edge.get("node", {})
                    node_type = node.get("type")
                    node_format = node.get("format")
                    
                    if rel_type == "SEQUEL" and node_type == "ANIME" and node_format in ("TV", "TV_SHORT", "ONA"):
                        node_id = node.get("id")
                        if node_id:
                            node_details[node_id] = node
                            current_seq_id = node_id
                            found_sequel = True
                            season_number += 1
                            break
                            
            if not found_sequel:
                break
            depth += 1
            
        # 5. Resolve Stremio ID
        stremio_id = None
        try:
            stremio_id = await self.id_mapper.get_stremio_id(root_id)
        except Exception as e:
            logger.error(f"Failed to resolve Stremio ID for root {root_id}: {e}")

        # 6. Build AnimeGroup
        title = ""
        poster = ""
        banner = ""
        genres = []
        
        # Attempt to get root info from node_details or fetch directly if missing
        root_node = node_details.get(root_id)
        if not root_node and hasattr(self.anilist_client, 'get_anime'):
            try:
                root_node = await self.anilist_client.get_anime(root_id)
            except Exception:
                pass
                
        if root_node:
            title_dict = root_node.get("title", {})
            title = title_dict.get("english") or title_dict.get("romaji") or ""
            
            cover_img = root_node.get("coverImage", {})
            if isinstance(cover_img, dict):
                poster = cover_img.get("large") or cover_img.get("medium") or ""
            elif isinstance(cover_img, str):
                poster = cover_img
                
            banner = root_node.get("bannerImage", "")
            genres = root_node.get("genres", [])
        
        group = AnimeGroup(
            root_anilist_id=root_id,
            title=title,
            poster=poster,
            banner=banner,
            genres=genres,
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
