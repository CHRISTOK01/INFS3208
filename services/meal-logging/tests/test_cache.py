"""Tests for the Redis cache helpers, with Redis replaced by a fake that's always down."""
import redis

from app import cache


class BrokenRedis:
    def __init__(self):
        self.calls = 0

    def get(self, key):
        self.calls += 1
        raise redis.ConnectionError("Redis is down")

    def set(self, key, value, ex):
        self.calls += 1
        raise redis.ConnectionError("Redis is down")


def test_redis_being_down_is_not_an_error_and_we_back_off(monkeypatch):
    broken = BrokenRedis()
    monkeypatch.setattr(cache, "client", broken)
    monkeypatch.setattr(cache, "skip_until", 0.0)

    assert cache.get_json("search:milk") is None   # treated as "not cached"
    cache.set_json("search:milk", [1, 2], 60)       # quietly skipped
    cache.get_json("search:milk")
    assert broken.calls == 1                         # after the first failure, Redis is left alone
