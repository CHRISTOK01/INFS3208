"""A small Redis cache for food search results.

Searching 43,000 foods is quick, but the same searches ("banana", "milk") come up all the time,
so we keep the results in Redis for an hour. The food list only changes when the data is
reloaded, so cached results don't go stale in practice.

If Redis is down, nothing breaks: we just skip the cache and ask the database instead.
After an error we leave Redis alone for 30 seconds, rather than making every search wait for it
to fail again. (When the Redis container is stopped, even looking up its name takes Docker a few
seconds to give up on.)
"""
import json
import logging
import time

import redis

from app import config

log = logging.getLogger(config.SERVICE_NAME)

RETRY_AFTER_SECONDS = 30

# Short timeouts, so a slow Redis can't hold a search up for long
client = redis.Redis.from_url(
    config.REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True
)

# When Redis last failed, we don't try it again until this time (from time.monotonic())
skip_until = 0.0


def redis_is_resting() -> bool:
    return time.monotonic() < skip_until


def redis_failed(exc: Exception):
    global skip_until
    skip_until = time.monotonic() + RETRY_AFTER_SECONDS
    log.warning("redis unavailable, skipping the cache for %ss: %s", RETRY_AFTER_SECONDS, exc)


def get_json(key: str):
    """Return the cached value, or None if it isn't cached (or Redis is down)."""
    if redis_is_resting():
        return None
    try:
        raw = client.get(key)
    except redis.RedisError as exc:
        redis_failed(exc)
        return None
    return None if raw is None else json.loads(raw)


def set_json(key: str, value, seconds: int):
    if redis_is_resting():
        return
    try:
        # ex=seconds: Redis deletes the entry by itself after this many seconds
        client.set(key, json.dumps(value), ex=seconds)
    except redis.RedisError as exc:
        redis_failed(exc)
