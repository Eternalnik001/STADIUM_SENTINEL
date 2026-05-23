from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from app.config import settings
from app.core.redis_client import get_redis
from app.core.idempotency import claim
from app.core.streams import publish
from app.schemas.ingest import (
    TurnstileEvent, DensityReading, TicketScan, WeatherSignal, IngestAck,
)

router = APIRouter()


async def _redis() -> Redis:
    return get_redis()


async def _ingest(redis: Redis, kind, payload) -> IngestAck:
    """Common path: dedup -> XADD -> ack. Fails closed on stream errors."""
    if not await claim(redis, payload.event_id):
        return IngestAck(accepted=False, event_id=payload.event_id, reason="duplicate")
    try:
        stream_id = await publish(redis, settings.INGEST_STREAM, kind, payload)
    except Exception as e:
        # Fail closed — caller MUST retry. Do not swallow.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"stream unavailable: {type(e).__name__}",
        )
    return IngestAck(accepted=True, event_id=payload.event_id, stream_id=stream_id)


@router.post("/turnstile", response_model=IngestAck, status_code=202)
async def turnstile(evt: TurnstileEvent, redis: Redis = Depends(_redis)):
    return await _ingest(redis, "turnstile", evt)


@router.post("/density", response_model=IngestAck, status_code=202)
async def density(evt: DensityReading, redis: Redis = Depends(_redis)):
    return await _ingest(redis, "density", evt)


@router.post("/ticket-scan", response_model=IngestAck, status_code=202)
async def ticket_scan(evt: TicketScan, redis: Redis = Depends(_redis)):
    return await _ingest(redis, "ticket_scan", evt)


@router.post("/weather", response_model=IngestAck, status_code=202)
async def weather(evt: WeatherSignal, redis: Redis = Depends(_redis)):
    return await _ingest(redis, "weather", evt)


@router.post("/batch", response_model=list[IngestAck], status_code=202)
async def batch_turnstile(events: list[TurnstileEvent], redis: Redis = Depends(_redis)):
    """Edge devices that buffer offline (cell drop) flush on reconnect.
    Capped at 500 to prevent DoS."""
    if len(events) > 500:
        raise HTTPException(413, "batch too large; max 500")
    return [await _ingest(redis, "turnstile", e) for e in events]
