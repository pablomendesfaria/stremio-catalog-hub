from typing import Any
from app.config import settings
from app.models.stremio import Manifest, BehaviorHints, ResourceDescriptor
from app.models.config import UserConfig

async def build_manifest(user_config: UserConfig | None, catalog_registry: Any) -> dict:
    """
    Builds the Stremio manifest dynamically based on user config and active catalogs.
    """
    catalog_entries = await catalog_registry.get_all_catalog_entries(user_config)
    
    manifest = Manifest(
        id=settings.addon_id,
        version=settings.addon_version,
        name=settings.addon_name,
        description=settings.addon_description,
        types=['movie', 'series', 'anime'],
        resources=[
            'catalog',
            ResourceDescriptor(
                name='meta',
                types=['anime'],
                id_prefixes=['kitsu:', 'anilist:'],
            ),
        ],
        catalogs=catalog_entries,
        id_prefixes=['tt', 'kitsu:', 'anilist:'],
        behavior_hints=BehaviorHints(
            configurable=True,
            configuration_required=True,
        ),
    )
    
    return manifest.model_dump(by_alias=True, exclude_none=True)
