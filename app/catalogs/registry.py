from typing import Optional

from app.models.stremio import CatalogEntry, ExtraParam
from app.models.catalog import CatalogDefinition, ContentType, CatalogProvider
from app.models.config import UserConfig
from app.catalogs.fixed import FIXED_CATALOGS
from app.catalogs.rotating import RotatingCatalogEngine
from app.catalogs.themes import Theme


class CatalogRegistry:
    def __init__(self, rotating_engine: RotatingCatalogEngine):
        self.rotating_engine = rotating_engine

    def _theme_to_catalog_definition(self, theme: Theme, content_type_str: str, slot_index: int) -> CatalogDefinition:
        """Converts a Theme to a CatalogDefinition dynamically."""
        content_type = ContentType(content_type_str)
        provider_params = {
            'endpoint': 'discover',
        }
        if theme.genre_ids:
            provider_params['with_genres'] = ','.join(map(str, theme.genre_ids))
        if theme.keywords:
            provider_params['with_keywords'] = ','.join(theme.keywords)
        if theme.vote_average_gte is not None:
            provider_params['vote_average.gte'] = theme.vote_average_gte
        if theme.release_year_range:
            provider_params['primary_release_date.gte'] = f"{theme.release_year_range[0]}-01-01"
            provider_params['primary_release_date.lte'] = f"{theme.release_year_range[1]}-12-31"
        if theme.with_original_language:
            provider_params['with_original_language'] = ','.join(theme.with_original_language)
        if theme.exclude_original_language:
            provider_params['without_original_language'] = ','.join(theme.exclude_original_language)

        return CatalogDefinition(
            id=f"thematic_{slot_index}_{content_type_str}",
            content_type=content_type,
            name=f"{theme.name}",
            provider=CatalogProvider.TMDB,
            refresh_interval_seconds=86400,
            provider_params=provider_params,
            genre_options=[],
            genre_filter_supported=False,
        )

    async def get_all_catalog_entries(self, user_config: Optional[UserConfig]) -> list[CatalogEntry]:
        """Returns Stremio manifest CatalogEntry objects for all active catalogs."""
        active_catalogs = []
        
        # 1. Fixed catalogs
        for cat in FIXED_CATALOGS:
            if user_config and user_config.enabled_catalogs:
                if cat.id not in user_config.enabled_catalogs:
                    continue
            active_catalogs.append(self._create_catalog_entry(cat))

        # 2. Rotating thematic catalogs
        slots = await self.rotating_engine.get_active_slots()
        
        for slot in slots:
            theme = await self.rotating_engine.get_slot_theme(slot.slot_index)
            if theme:
                for ct in theme.content_types:
                    # Verify user config if needed
                    cat_id = f"thematic_{slot.slot_index}_{ct}"
                    if user_config and user_config.enabled_catalogs and cat_id not in user_config.enabled_catalogs:
                        continue
                    
                    cat_def = self._theme_to_catalog_definition(theme, ct, slot.slot_index)
                    active_catalogs.append(self._create_catalog_entry(cat_def))
                    
        return active_catalogs

    async def get_catalog_definition(self, catalog_id: str) -> Optional[CatalogDefinition]:
        """Looks up a catalog by ID (fixed or rotating)."""
        # Check fixed catalogs
        for cat in FIXED_CATALOGS:
            if cat.id == catalog_id:
                return cat
                
        # Check rotating catalogs
        if catalog_id.startswith("thematic_"):
            parts = catalog_id.split("_")
            if len(parts) >= 3:
                try:
                    slot_index = int(parts[1])
                    content_type_str = parts[2]
                    theme = await self.rotating_engine.get_slot_theme(slot_index)
                    if theme and content_type_str in theme.content_types:
                        return self._theme_to_catalog_definition(theme, content_type_str, slot_index)
                except ValueError:
                    pass
                    
        return None

    def get_fixed_catalogs(self) -> list[CatalogDefinition]:
        """Returns all fixed catalog definitions."""
        return FIXED_CATALOGS

    def _create_catalog_entry(self, catalog: CatalogDefinition) -> CatalogEntry:
        """Converts a CatalogDefinition to a Stremio CatalogEntry."""
        extras = []
        
        # Search extra
        extras.append(ExtraParam(name="search", isRequired=False))
        
        # Genre extra
        if catalog.genre_filter_supported and catalog.genre_options:
            extras.append(ExtraParam(
                name="genre",
                isRequired=False,
                options=catalog.genre_options
            ))
            
        # Skip extra
        extras.append(ExtraParam(name="skip", isRequired=False))
        
        return CatalogEntry(
            type=catalog.content_type.value,
            id=catalog.id,
            name=catalog.name,
            extra=extras
        )
