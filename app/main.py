"""Stremio Dynamic Catalog Hub — FastAPI application entry point.

Run with:
    uv run uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.cache.redis_cache import RedisCache
from app.catalogs.registry import CatalogRegistry
from app.catalogs.rotating import RotatingCatalogEngine
from app.config import settings
from app.handlers.catalog import router as catalog_router
from app.handlers.configure import router as configure_router
from app.handlers.meta import router as meta_router
from app.manifest.builder import build_manifest
from app.providers.anilist import AniListClient
from app.providers.id_mapper import IDMapper
from app.providers.mal import MALClient
from app.anime.grouper import AnimeGrouper
from app.scheduler.jobs import SchedulerManager
from app.utils.helpers import decode_user_config

# ── Logging ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Application lifespan ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for shared resources."""

    logger.info("Starting Catalog Hub addon v%s", settings.addon_version)

    # 1. Redis
    cache = RedisCache(settings.redis_url)
    await cache.connect()
    app.state.cache = cache

    # 2. Providers (AniList + MAL — no API key needed)
    anilist_client = AniListClient()
    mal_client = MALClient()
    app.state.anilist_client = anilist_client
    app.state.mal_client = mal_client

    # 3. ID Mapper (Fribb + AniZip)
    id_mapper = IDMapper(cache)
    await id_mapper.load_database()
    app.state.id_mapper = id_mapper

    # 4. Anime Grouper
    anime_grouper = AnimeGrouper(anilist_client, id_mapper, cache)
    app.state.anime_grouper = anime_grouper

    # 5. Catalog system
    rotating_engine = RotatingCatalogEngine(cache)
    await rotating_engine.initialize()
    catalog_registry = CatalogRegistry(rotating_engine)
    app.state.rotating_engine = rotating_engine
    app.state.catalog_registry = catalog_registry

    # 6. Scheduler
    scheduler = SchedulerManager(cache, rotating_engine, id_mapper)
    scheduler.start()
    app.state.scheduler = scheduler

    logger.info("All services initialised — addon ready on port %d", settings.addon_port)

    yield  # ── Application runs here ──

    # Shutdown
    logger.info("Shutting down…")
    scheduler.stop()
    await anilist_client.close()
    await mal_client.close()
    await cache.disconnect()
    logger.info("Shutdown complete")


# ── FastAPI app ─────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.addon_name,
    version=settings.addon_version,
    description=settings.addon_description,
    lifespan=lifespan,
)

# CORS — mandatory for Stremio Web (web.stremio.com)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Manifest routes ────────────────────────────────────────────────────

@app.get("/manifest.json")
async def manifest_root(request: Request) -> dict[str, Any]:
    """Serve manifest without user config (pre-install discovery)."""
    return await build_manifest(None, request.app.state.catalog_registry)


@app.get("/{config}/manifest.json")
async def manifest_configured(config: str, request: Request) -> dict[str, Any]:
    """Serve manifest with user-specific config (post-install)."""
    user_config = decode_user_config(config)
    return await build_manifest(user_config, request.app.state.catalog_registry)


# ── Include routers ────────────────────────────────────────────────────

app.include_router(configure_router)
app.include_router(catalog_router)
app.include_router(meta_router)


# ── Health check ────────────────────────────────────────────────────────

@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Simple health check for monitoring."""
    try:
        await request.app.state.cache.client.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    return {
        "status": "ok",
        "version": settings.addon_version,
        "redis": redis_status,
    }


# ── Global error handler ───────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
