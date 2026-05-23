from typing import Literal
from redis.asyncio import Redis
from pydantic import BaseModel
import orjson

EventKind = Literal["turnstile", "density", "ticket_scan", "weather"]

# Cap at 1M entries (~ several hours at peak ingest).
# MAXLEN ~ N means approximate trim — Redis trims in batches for performance.
_MAX_STREAM_LEN = 1_000_000


async def publish(
    redis: Redis,
    stream_key: str,
    kind: EventKind,
    payload: BaseModel,
) -> str:
    """Push an event onto the ingest stream. Returns the Redis stream ID
    (format: 'timestamp-sequence', e.g. '1716461234567-0')."""
    body = orjson.dumps(payload.model_dump(mode="json")).decode()
    return await redis.xadd(
        stream_key,
        {"kind": kind, "data": body},
        maxlen=_MAX_STREAM_LEN,
        approximate=True,
    )
