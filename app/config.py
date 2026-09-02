"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Global application settings.

    Values are loaded from environment variables and/or a `.env` file.
    The TMDB key is *not* here — it's provided per-user via the config page
    and encoded in the addon URL path.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    addon_port: int = 7000
    addon_host: str = "0.0.0.0"
    log_level: str = "info"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Defaults
    default_language: str = "pt-BR"

    # Addon identity (placeholder — user will choose a name later)
    addon_id: str = "community.stremio.catalog-hub"
    addon_name: str = "Catalog Hub"
    addon_version: str = "1.0.0"
    addon_description: str = (
        "Dynamic catalog addon with movies, series, and anime. "
        "Features rotating thematic catalogs and intelligent anime season grouping."
    )


settings = AppSettings()
