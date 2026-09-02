"""Models package."""

from app.models.catalog import (
    AnimeGroup,
    AnimeSeasonEntry,
    CatalogDefinition,
    CatalogProvider,
    ContentType,
    ThematicSlot,
)
from app.models.config import UserConfig
from app.models.stremio import (
    BehaviorHints,
    CatalogEntry,
    CatalogResponse,
    ExtraParam,
    LinkInfo,
    Manifest,
    MetaDetail,
    MetaPreview,
    MetaResponse,
    ResourceDescriptor,
    TrailerInfo,
    Video,
)

__all__ = [
    "AnimeGroup",
    "AnimeSeasonEntry",
    "BehaviorHints",
    "CatalogDefinition",
    "CatalogEntry",
    "CatalogProvider",
    "CatalogResponse",
    "ContentType",
    "ExtraParam",
    "LinkInfo",
    "Manifest",
    "MetaDetail",
    "MetaPreview",
    "MetaResponse",
    "ResourceDescriptor",
    "ThematicSlot",
    "TrailerInfo",
    "UserConfig",
    "Video",
]
