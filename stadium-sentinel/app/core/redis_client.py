import redis.asyncio as redis
from app.config import settings

_pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=50,
    decode_responses=True,
    socket_keepalive=True,
    health_check_interval=30,
)


def get_redis() -> redis.Redis:
    """Return a Redis client backed by the shared pool. Do not call .aclose() on this."""
    return redis.Redis(connection_pool=_pool)


async def close_pool() -> None:
    """Call on app shutdown only."""
    await _pool.aclose()
