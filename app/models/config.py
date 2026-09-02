"""Pydantic models for per-user addon configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserConfig(BaseModel):
    """Settings provided by each user via the ``/configure`` page.

    Serialised as Base64-encoded JSON in the addon URL path segment so that
    Stremio propagates it on every request.
    """

    tmdb_api_key: str = Field(
        ...,
        description="TMDB API key (v3 auth). Required for movie/series catalogs.",
    )
    language: str = Field(
        default="pt-BR",
        description="Language code for titles and descriptions (e.g. pt-BR, en-US).",
    )
    enabled_catalogs: list[str] | None = Field(
        default=None,
        description=(
            "List of catalog IDs the user wants to see. "
            "None means all catalogs are enabled."
        ),
    )
