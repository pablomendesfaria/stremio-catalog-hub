"""Utility helpers for config parsing, extra params, and date logic."""

from __future__ import annotations

import base64
import json
import logging
import urllib.parse
from datetime import datetime, timezone

from app.models.config import UserConfig

logger = logging.getLogger(__name__)


# ── User config encoding / decoding ─────────────────────────────────────

def decode_user_config(config_str: str | None) -> UserConfig | None:
    """Decode a Base64-encoded JSON config segment from the URL path.

    Returns ``None`` if the string is missing or cannot be decoded, which
    signals that the addon hasn't been configured yet.
    """
    if not config_str:
        return None

    try:
        # Add padding if needed
        padded = config_str + "=" * (-len(config_str) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        data = json.loads(decoded)
        return UserConfig(**data)
    except Exception:
        logger.debug("Failed to decode user config: %s…", config_str[:30])
        return None


def encode_user_config(config: UserConfig) -> str:
    """Encode a ``UserConfig`` to a URL-safe Base64 JSON string."""
    payload = config.model_dump(exclude_none=True)
    raw = json.dumps(payload, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


# ── Extra params parsing ────────────────────────────────────────────────

def parse_extra_params(extra_str: str | None) -> dict[str, str]:
    """Parse Stremio extra parameters from the URL path segment.

    Stremio encodes extras like ``genre=Action&skip=100`` (no leading ``?``).
    The segment may also end with ``.json`` which must be stripped.
    """
    if not extra_str:
        return {}

    clean = extra_str.removesuffix(".json")
    return dict(urllib.parse.parse_qsl(clean))


# ── AniList season helpers ──────────────────────────────────────────────

_SEASON_MAP = {
    1: "WINTER",   # Jan–Mar
    2: "WINTER",
    3: "WINTER",
    4: "SPRING",   # Apr–Jun
    5: "SPRING",
    6: "SPRING",
    7: "SUMMER",   # Jul–Sep
    8: "SUMMER",
    9: "SUMMER",
    10: "FALL",    # Oct–Dec
    11: "FALL",
    12: "FALL",
}


def get_current_anime_season() -> tuple[str, int]:
    """Return the current anime season and year, e.g. ``("FALL", 2026)``."""
    now = datetime.now(timezone.utc)
    return _SEASON_MAP[now.month], now.year


def get_current_month() -> int:
    """Return the current month (1–12) in UTC."""
    return datetime.now(timezone.utc).month
