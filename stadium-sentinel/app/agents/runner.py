import asyncio
import logging
import signal
import orjson
from typing import Any

from app.config import settings
from app.core.redis_client import get_redis
from app.db.session import SessionLocal
from app.agents.crowd_flow import evaluate_zone, AGENT_NAME
from app.agents.threat import evaluate_threat, AGENT_NAME as THREAT_AGENT_NAME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("agent.runner")

CONSUMER_GROUP = "agents"
CONSUMER_NAME  = "crowd-flow-1"   # bump per replica: crowd-flow-2, crowd-flow-3...
BLOCK_MS = 2000                   # how long XREADGROUP blocks waiting for events
BATCH = 50                        # max events per read
EVAL_COOLDOWN_S = 30              # minimum seconds between Gemini evaluations per zone

_shutdown = asyncio.Event()
_last_eval: dict[str, float] = {}  # zone_id -> epoch time of last evaluation


async def _ensure_group(redis) -> None:
    """Create the consumer group if it doesn't exist. Idempotent."""
    try:
        await redis.xgroup_create(
            settings.INGEST_STREAM, CONSUMER_GROUP, id="0", mkstream=True,
        )
        log.info("created consumer group %s", CONSUMER_GROUP)
    except Exception as e:
        # BUSYGROUP = already exists, ignore. Anything else is fatal.
        if "BUSYGROUP" not in str(e):
            raise


async def _process_event(entry_id: str, fields: dict[str, str]) -> None:
    """Route a single stream entry to CrowdFlowAgent AND ThreatAgent concurrently."""
    kind = fields.get("kind")
    try:
        data = orjson.loads(fields["data"])
    except (KeyError, orjson.JSONDecodeError) as e:
        log.warning("malformed entry %s: %s", entry_id, e)
        return

    zone_id = None
    if kind == "density":
        zone_id = data.get("zone_id")
    elif kind == "ticket_scan":
        zone_id = data.get("expected_zone_id")
    elif kind == "turnstile":
        zone_id = data.get("zone_id")
    # weather is global — handled by a future scheduled task, skip here.

    if not zone_id:
        return

    # Step 1: Persist the metric in its own session so both agents can read it
    if kind == "density":
        try:
            async with SessionLocal() as session:
                from sqlalchemy import text
                from datetime import datetime
                ts_str = data["ts"].replace('Z', '+00:00') if data["ts"].endswith('Z') else data["ts"]
                dt = datetime.fromisoformat(ts_str)
                await session.execute(
                    text("INSERT INTO crowd_metrics (zone_id, density, flow_rate, ts) VALUES (:z, :d, :f, :ts)"),
                    {"z": zone_id, "d": data["density"], "f": data["flow_rate"], "ts": dt}
                )
                await session.commit()
        except Exception as e:
            log.exception("metric insert error on %s: %s", entry_id, e)

    # Step 2: Cooldown gate — skip Gemini calls if we evaluated this zone recently
    import time as _time
    now = _time.monotonic()
    last = _last_eval.get(zone_id, 0.0)
    if now - last < EVAL_COOLDOWN_S:
        log.debug("zone=%s cooldown active (%.1fs remaining) — skipping agent eval",
                  zone_id, EVAL_COOLDOWN_S - (now - last))
        return
    _last_eval[zone_id] = now

    # Step 2: Run both agents concurrently, each with its own isolated session
    async def _run_crowd():
        async with SessionLocal() as s:
            return await evaluate_zone(s, zone_id)

    async def _run_threat():
        async with SessionLocal() as s:
            return await evaluate_threat(s, zone_id)

    try:
        results = await asyncio.gather(_run_crowd(), _run_threat(), return_exceptions=True)

        if isinstance(results[0], Exception):
            log.exception("agent=%s error on %s: %s", AGENT_NAME, entry_id, results[0])
        else:
            decision = results[0]
            log.info(
                "agent=%s entry=%s zone=%s action=%s conf=%.2f",
                AGENT_NAME, entry_id, zone_id, decision.action, decision.confidence,
            )

        if isinstance(results[1], Exception):
            log.exception("agent=%s error on %s: %s", THREAT_AGENT_NAME, entry_id, results[1])
        else:
            threat_result = results[1]
            log.info(
                "agent=%s entry=%s zone=%s action=%s conf=%.2f",
                THREAT_AGENT_NAME, entry_id, zone_id,
                threat_result.get("action", "?"), threat_result.get("confidence", 0.0),
            )
    except Exception as e:
        log.exception("runner error on %s: %s", entry_id, e)


async def _consume_loop() -> None:
    redis = get_redis()
    await _ensure_group(redis)
    log.info("agent runner started: stream=%s group=%s consumer=%s",
             settings.INGEST_STREAM, CONSUMER_GROUP, CONSUMER_NAME)

    while not _shutdown.is_set():
        try:
            # XREADGROUP with '>' returns only never-delivered messages.
            resp = await redis.xreadgroup(
                CONSUMER_GROUP, CONSUMER_NAME,
                streams={settings.INGEST_STREAM: ">"},
                count=BATCH, block=BLOCK_MS,
            )
        except Exception as e:
            log.exception("xreadgroup failed: %s — backing off 2s", e)
            await asyncio.sleep(2)
            continue

        if not resp:
            continue   # block timeout, loop again

        # resp shape: [(stream_name, [(id, {field: value}), ...])]
        for _stream_name, entries in resp:
            ack_ids = []
            for entry_id, fields in entries:
                await _process_event(entry_id, fields)
                ack_ids.append(entry_id)
            if ack_ids:
                await redis.xack(settings.INGEST_STREAM, CONSUMER_GROUP, *ack_ids)

    log.info("agent runner shutdown complete")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    def _handler():
        log.info("shutdown signal received")
        _shutdown.set()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handler)


async def main() -> None:
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop)
    await _consume_loop()


if __name__ == "__main__":
    asyncio.run(main())
