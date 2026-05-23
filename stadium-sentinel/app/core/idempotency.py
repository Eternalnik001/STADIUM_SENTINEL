from redis.asyncio import Redis

_IDEMPOTENCY_TTL = 300   # seconds — 5 min covers most retry storms
_KEY = "idem:{event_id}"


async def claim(redis: Redis, event_id: str) -> bool:
    """Returns True if this is the FIRST time we have seen event_id.
    Returns False if event_id was already processed — caller should short-circuit
    and return a 'duplicate' ack without processing the event again."""
    return bool(
        await redis.set(
            _KEY.format(event_id=event_id), "1",
            nx=True, ex=_IDEMPOTENCY_TTL,
        )
    )
