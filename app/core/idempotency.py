"""Redis-backed idempotency helpers."""

from __future__ import annotations

import logging
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@lru_cache(maxsize=1)
def _get_redis_client() -> Redis:
    """Return a cached Redis client."""

    return Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)


def claim_webhook_idempotency(key: str, ttl_seconds: int) -> bool:
    """Try to claim a webhook idempotency key.

    Returns:
        True when the caller should continue to the database layer.
        False when Redis already considers this key a recent duplicate.

    Any Redis failure is logged and treated as a soft failure so the caller
    can fall back to database uniqueness as the final correctness layer.
    """

    try:
        claimed = _get_redis_client().set(name=key, value="1", ex=ttl_seconds, nx=True)
    except RedisError:
        logger.exception("failed to claim webhook idempotency key=%s", key)
        return True

    return bool(claimed)
