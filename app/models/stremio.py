"""Pydantic models for the Stremio addon protocol."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Manifest ────────────────────────────────────────────────────────────

class ExtraParam(BaseModel):
    """Declares a filter/pagination parameter for a catalog."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    is_required: bool = Field(default=False, alias="isRequired")
    options: list[str] | None = None
    options_limit: int = Field(default=1, alias="optionsLimit")


class CatalogEntry(BaseModel):
    """A catalog declaration inside the addon manifest."""

    type: str
    id: str
    name: str
    extra: list[ExtraParam] | None = None


class BehaviorHints(BaseModel):
    """Addon behavior flags communicated to the Stremio client."""

    model_config = ConfigDict(populate_by_name=True)

    configurable: bool = True
    configuration_required: bool = Field(default=True, alias="configurationRequired")
    adult: bool = False
    p2p: bool = False


class ResourceDescriptor(BaseModel):
    """Granular resource declaration (object form)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    types: list[str] | None = None
    id_prefixes: list[str] | None = Field(default=None, alias="idPrefixes")


class Manifest(BaseModel):
    """The addon manifest served at ``/manifest.json``."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    version: str
    name: str
    description: str
    logo: str | None = None
    background: str | None = None
    types: list[str]
    resources: list[str | ResourceDescriptor | dict[str, Any]]
    catalogs: list[CatalogEntry]
    id_prefixes: list[str] | None = Field(default=None, alias="idPrefixes")
    behavior_hints: BehaviorHints | None = Field(default=None, alias="behaviorHints")


# ── Catalog response (MetaPreview) ──────────────────────────────────────

class MetaPreview(BaseModel):
    """A single item returned inside a catalog ``metas`` array.

    Contains just enough data for the Stremio board/discover card.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    name: str
    poster: str | None = None
    poster_shape: str | None = Field(default="poster", alias="posterShape")
    banner: str | None = None
    logo: str | None = None
    description: str | None = None
    release_info: str | None = Field(default=None, alias="releaseInfo")
    imdb_rating: str | None = Field(default=None, alias="imdbRating")
    genres: list[str] | None = None


# ── Meta response (MetaDetail + Video) ──────────────────────────────────

class Video(BaseModel):
    """An episode/video entry inside ``MetaDetail.videos``."""

    id: str
    title: str
    season: int | None = None
    episode: int | None = None
    released: str | None = None
    thumbnail: str | None = None
    overview: str | None = None


class TrailerInfo(BaseModel):
    """A trailer reference (YouTube video ID)."""

    source: str
    type: str = "Trailer"


class LinkInfo(BaseModel):
    """An external link shown on the detail page."""

    name: str
    category: str
    url: str


class MetaDetail(BaseModel):
    """Full metadata returned by the ``/meta`` endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    name: str
    poster: str | None = None
    poster_shape: str | None = Field(default="poster", alias="posterShape")
    background: str | None = None
    logo: str | None = None
    description: str | None = None
    release_info: str | None = Field(default=None, alias="releaseInfo")
    imdb_rating: str | None = Field(default=None, alias="imdbRating")
    genres: list[str] | None = None
    runtime: str | None = None
    director: list[str] | None = None
    cast: list[str] | None = None
    trailers: list[TrailerInfo] | None = None
    links: list[LinkInfo] | None = None
    behavior_hints: dict[str, Any] | None = Field(default=None, alias="behaviorHints")
    videos: list[Video] | None = None
    released: str | None = None


# ── Wrapper responses ───────────────────────────────────────────────────

class CatalogResponse(BaseModel):
    """JSON body returned by ``/catalog/…``."""

    model_config = ConfigDict(populate_by_name=True)

    metas: list[MetaPreview]
    cache_max_age: int | None = Field(default=None, alias="cacheMaxAge")
    stale_revalidate: int | None = Field(default=None, alias="staleRevalidate")
    stale_error: int | None = Field(default=None, alias="staleError")


class MetaResponse(BaseModel):
    """JSON body returned by ``/meta/…``."""

    model_config = ConfigDict(populate_by_name=True)

    meta: MetaDetail | None
    cache_max_age: int | None = Field(default=None, alias="cacheMaxAge")
