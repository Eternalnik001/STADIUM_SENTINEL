from typing import Literal
from redis.asyncio import Redis
from pydantic import BaseModel
import orjson

EventKind = Literal["turnstile", "density", "ticket_scan", "weather"]

# Stream is capped at 1M entries (~ several hours at peak ingest);
# MAXLEN ~ means approximate trim for performance.
_MAX_STREAM_LEN = 1_000_000


async def publish(
    redis: Redis,
    stream_key: str,
    kind: EventKind,
    payload: BaseModel,
) -> str:
    """Push an event onto the ingest stream. Returns Redis stream ID."""
    body = orjson.dumps(payload.model_dump(mode="json")).decode()
    return await redis.xadd(
        stream_key,
        {"kind": kind, "data": body},
        maxlen=_MAX_STREAM_LEN,
        approximate=True,
    )
