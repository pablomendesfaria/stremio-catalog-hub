"""Internal models for the catalog system (not part of the Stremio protocol)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """Stremio content types supported by this addon."""

    MOVIE = "movie"
    SERIES = "series"
    ANIME = "anime"


class CatalogProvider(str, Enum):
    """Which data provider backs a catalog."""

    TMDB = "tmdb"
    ANILIST = "anilist"


class CatalogDefinition(BaseModel):
    """Internal definition of a catalog — maps to a provider and refresh policy."""

    id: str
    content_type: ContentType
    name: str
    provider: CatalogProvider
    refresh_interval_seconds: int = Field(
        default=21600,
        description="How often the cached data should be refreshed (in seconds).",
    )
    is_rotating: bool = False
    provider_params: dict = Field(
        default_factory=dict,
        description="Extra params passed to the provider (e.g. sort, genre_ids, tags).",
    )
    search_supported: bool = True
    genre_filter_supported: bool = True
    genre_options: list[str] | None = None


class ThematicSlot(BaseModel):
    """State of a rotating thematic catalog slot, persisted in Redis."""

    slot_index: int
    current_theme_id: str
    theme_name: str
    last_rotated_ts: float = 0.0
    content_types: list[ContentType] = Field(
        default_factory=lambda: [ContentType.MOVIE, ContentType.SERIES],
    )


class AnimeGroup(BaseModel):
    """An anime franchise grouped by season via AniList relations."""

    root_anilist_id: int
    title: str
    poster: str | None = None
    banner: str | None = None
    genres: list[str] = Field(default_factory=list)
    stremio_id: str = Field(
        description="Primary Stremio ID: IMDB (tt…) or kitsu:… fallback.",
    )
    seasons: list[AnimeSeasonEntry] = Field(default_factory=list)


class AnimeSeasonEntry(BaseModel):
    """A single season within an anime franchise group."""

    season_number: int
    anilist_id: int
    mal_id: int | None = None
    title: str
    episodes: int | None = None
    stremio_id: str | None = None
    format: str | None = None  # TV, TV_SHORT, ONA
    status: str | None = None


# Forward reference resolution
AnimeGroup.model_rebuild()
