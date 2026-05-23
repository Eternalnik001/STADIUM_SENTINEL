from redis.asyncio import Redis

_IDEMPOTENCY_TTL = 300  # seconds — 5 min window covers most retry storms
_KEY = "idem:{event_id}"


async def claim(redis: Redis, event_id: str) -> bool:
    """Returns True if this is the first time we've seen event_id.
    False = duplicate, caller should short-circuit and return cached ack."""
    return bool(await redis.set(_KEY.format(event_id=event_id), "1",
                                nx=True, ex=_IDEMPOTENCY_TTL))
