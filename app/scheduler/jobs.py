"""APScheduler background jobs for periodic cache refresh and catalog rotation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from app.cache.redis_cache import RedisCache
    from app.catalogs.rotating import RotatingCatalogEngine
    from app.providers.id_mapper import IDMapper

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages all recurring background jobs.

    Jobs:
      1. Rotate thematic catalog slots (seasonal + random)
      2. Refresh the Fribb anime-lists ID mapping database
      3. Warm the Redis cache for popular catalog queries (optional future)
    """

    def __init__(
        self,
        cache: RedisCache,
        rotating_engine: RotatingCatalogEngine,
        id_mapper: IDMapper,
    ) -> None:
        self._cache = cache
        self._rotating_engine = rotating_engine
        self._id_mapper = id_mapper
        self._scheduler = AsyncIOScheduler()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Register all jobs and start the scheduler."""
        # Rotate seasonal slot — check every hour (cheap operation)
        self._scheduler.add_job(
            self._rotate_seasonal,
            trigger=IntervalTrigger(hours=1),
            id="rotate_seasonal",
            name="Rotate seasonal thematic slot",
            replace_existing=True,
        )

        # Rotate random thematic slots — check every hour
        # (the engine itself decides if enough time has passed)
        self._scheduler.add_job(
            self._rotate_random,
            trigger=IntervalTrigger(hours=1),
            id="rotate_random",
            name="Rotate random thematic slots",
            replace_existing=True,
        )

        # Refresh Fribb ID mapping database — daily
        self._scheduler.add_job(
            self._refresh_id_mapping,
            trigger=IntervalTrigger(hours=24),
            id="refresh_id_mapping",
            name="Refresh Fribb anime ID mappings",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info("Scheduler started with %d jobs", len(self._scheduler.get_jobs()))

    def stop(self) -> None:
        """Shutdown the scheduler gracefully."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    # ── Job implementations ─────────────────────────────────────────────

    async def _rotate_seasonal(self) -> None:
        """Check if the seasonal slot needs updating (month change)."""
        try:
            await self._rotating_engine.rotate_seasonal_slot()
        except Exception:
            logger.exception("Failed to rotate seasonal slot")

    async def _rotate_random(self) -> None:
        """Check if random thematic slots need rotating (daily/weekly)."""
        try:
            await self._rotating_engine.rotate_random_slots()
        except Exception:
            logger.exception("Failed to rotate random slots")

    async def _refresh_id_mapping(self) -> None:
        """Re-download and index the Fribb anime-lists database."""
        try:
            await self._id_mapper.refresh_database()
            logger.info("Fribb ID mapping database refreshed successfully")
        except Exception:
            logger.exception("Failed to refresh Fribb ID mapping database")
