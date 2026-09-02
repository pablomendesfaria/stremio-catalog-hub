import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.cache.redis_cache import RedisCache
from app.catalogs.themes import Theme, get_seasonal_theme, get_random_themes, SEASONAL_THEMES, RANDOM_THEMES
from app.models.catalog import ThematicSlot

logger = logging.getLogger(__name__)

class RotatingCatalogEngine:
    def __init__(self, cache: RedisCache):
        self.cache = cache

    async def get_active_slots(self) -> list[ThematicSlot]:
        """Returns the current state of all 4 slots from Redis."""
        slots = []
        for i in range(4):
            slot_data = await self.cache.get(f"thematic_slot:{i}")
            if slot_data:
                try:
                    # Parse from dict/json appropriately
                    if isinstance(slot_data, str):
                        slots.append(ThematicSlot.model_validate_json(slot_data))
                    else:
                        slots.append(ThematicSlot.model_validate(slot_data))
                except Exception as e:
                    logger.error(f"Error parsing slot {i}: {e}")
        return slots

    async def _save_slot(self, slot: ThematicSlot) -> None:
        """Saves a slot to Redis."""
        # Note: RedisCache.set already serializes to JSON
        await self.cache.set(f"thematic_slot:{slot.slot_index}", slot.model_dump())

    def _get_theme_by_id(self, theme_id: str) -> Optional[Theme]:
        """Helper to find a theme by ID across all themes."""
        for theme_list in SEASONAL_THEMES.values():
            for t in theme_list:
                if t.id == theme_id:
                    return t
        for t in RANDOM_THEMES:
            if t.id == theme_id:
                return t
        return None

    async def rotate_seasonal_slot(self) -> None:
        """Checks current month, sets the seasonal theme if needed."""
        now = datetime.now(timezone.utc)
        current_month = now.month
        
        slot_data = await self.cache.get("thematic_slot:0")
        if slot_data:
            try:
                if isinstance(slot_data, str):
                    slot = ThematicSlot.model_validate_json(slot_data)
                else:
                    slot = ThematicSlot.model_validate(slot_data)
                    
                # Rotate if the month has changed
                last_rotated_dt = datetime.fromtimestamp(slot.last_rotated_ts, tz=timezone.utc)
                if last_rotated_dt.month != current_month or last_rotated_dt.year != now.year:
                    new_theme = get_seasonal_theme(current_month)
                    if new_theme:
                        slot.current_theme_id = new_theme.id
                        slot.theme_name = new_theme.name
                        slot.last_rotated_ts = now.timestamp()
                        await self._save_slot(slot)
                        logger.info(f"Rotated seasonal slot to {new_theme.id}")
                return
            except Exception as e:
                logger.error(f"Error rotating seasonal slot: {e}")
        
        # If no slot or error parsing, create a new one
        new_theme = get_seasonal_theme(current_month)
        if new_theme:
            new_slot = ThematicSlot(
                slot_index=0,
                current_theme_id=new_theme.id,
                theme_name=new_theme.name,
                last_rotated_ts=now.timestamp()
            )
            await self._save_slot(new_slot)
            logger.info(f"Initialized seasonal slot to {new_theme.id}")

    async def rotate_random_slots(self) -> None:
        """Picks new random themes for slots 1-3 based on rotation intervals."""
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        slots = await self.get_active_slots()
        slots_dict = {s.slot_index: s for s in slots}
        
        active_theme_ids = [s.current_theme_id for s in slots]
        
        # Determine which slots need rotation
        slots_to_rotate = []
        for i in range(1, 4):
            slot = slots_dict.get(i)
            if not slot:
                slots_to_rotate.append(i)
                continue
                
            delta_seconds = now_ts - slot.last_rotated_ts
            if i in [1, 2] and delta_seconds >= 86400:  # Daily rotation
                slots_to_rotate.append(i)
                active_theme_ids.remove(slot.current_theme_id)
            elif i == 3 and delta_seconds >= 604800:  # Weekly rotation
                slots_to_rotate.append(i)
                active_theme_ids.remove(slot.current_theme_id)
                
        if not slots_to_rotate:
            return
            
        new_themes = get_random_themes(len(slots_to_rotate), exclude_ids=active_theme_ids)
        
        for i, new_theme in zip(slots_to_rotate, new_themes):
            new_slot = ThematicSlot(
                slot_index=i,
                current_theme_id=new_theme.id,
                theme_name=new_theme.name,
                last_rotated_ts=now_ts
            )
            await self._save_slot(new_slot)
            logger.info(f"Rotated random slot {i} to {new_theme.id}")

    async def get_slot_theme(self, slot_index: int) -> Optional[Theme]:
        """Returns the Theme for a given slot."""
        slot_data = await self.cache.get(f"thematic_slot:{slot_index}")
        if not slot_data:
            return None
            
        try:
            if isinstance(slot_data, str):
                slot = ThematicSlot.model_validate_json(slot_data)
            else:
                slot = ThematicSlot.model_validate(slot_data)
            return self._get_theme_by_id(slot.current_theme_id)
        except Exception as e:
            logger.error(f"Error getting slot theme: {e}")
            return None

    async def initialize(self) -> None:
        """Called on startup, sets up slots if not already in Redis."""
        await self.rotate_seasonal_slot()
        await self.rotate_random_slots()
        
        # For completely missing random slots (first run)
        slots = await self.get_active_slots()
        missing_slots = [i for i in range(1, 4) if not any(s.slot_index == i for s in slots)]
        
        if missing_slots:
            active_theme_ids = [s.current_theme_id for s in slots]
            new_themes = get_random_themes(len(missing_slots), exclude_ids=active_theme_ids)
            now_ts = datetime.now(timezone.utc).timestamp()
            for i, new_theme in zip(missing_slots, new_themes):
                new_slot = ThematicSlot(
                    slot_index=i,
                    current_theme_id=new_theme.id,
                    theme_name=new_theme.name,
                    last_rotated_ts=now_ts
                )
                await self._save_slot(new_slot)
                logger.info(f"Initialized random slot {i} to {new_theme.id}")
