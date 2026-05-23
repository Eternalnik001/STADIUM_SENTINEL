import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import settings
from app.agents.llm import call_structured
from app.core.pubsub import publish
from app.core.redis_client import get_redis
from app.db.models import AuditLog
from app.schemas.alert import ThreatAlert

AGENT_NAME = "ThreatAgent"
CONFIDENCE_FLOOR = 0.65   # lower than CrowdFlow — catching anomalies early matters more

_SYSTEM_PROMPT = """You are ThreatAgent, an autonomous safety monitor for a stadium.

Given a zone's recent crowd metrics (last 60 seconds), detect EMERGENCY
conditions that require immediate human attention:

1. SUDDEN SURGE: density grew >50% in under 60 seconds
2. PRESSURE WAVE: flow_rate exceeded 600 persons/min (compression risk)
3. RAPID FLUCTUATION: density swung by >30% in alternating direction (panic)

Severity rules:
- info: anomaly detected but contained
- warn: trending toward unsafe
- critical: active danger, evacuate or halt entry NOW

If no anomaly: action = "no_action".
If anomaly: action = "emit_alert" with severity and 1-sentence detail.
Confidence below 0.6 on sparse data.

Return ONLY JSON matching the schema."""

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["emit_alert", "no_action"]},
        "alert": {
            "type": "object",
            "nullable": True,
            "properties": {
                "severity": {"type": "string", "enum": ["info", "warn", "critical"]},
                "title": {"type": "string"},
                "detail": {"type": "string"},
            },
            "required": ["severity", "title", "detail"],
        },
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["action", "reasoning", "confidence"],
}


def _hash_input(payload: dict[str, Any]) -> str:
    import orjson
    canonical = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(canonical).hexdigest()


async def _get_recent_metrics(session: AsyncSession, zone_id: str) -> list[dict]:
    """Fetch the last 60 seconds of crowd_metrics for a zone."""
    res = await session.execute(
        text("""
            SELECT density, flow_rate, ts
            FROM crowd_metrics
            WHERE zone_id = :z
              AND ts >= NOW() - INTERVAL '60 seconds'
            ORDER BY ts ASC
        """),
        {"z": zone_id},
    )
    rows = res.mappings().all()
    return [{"density": r["density"], "flow_rate": r["flow_rate"], "ts": r["ts"].isoformat()} for r in rows]


async def evaluate_threat(session: AsyncSession, zone_id: str) -> dict:
    """Evaluate a zone for safety anomalies and optionally emit a ThreatAlert."""
    started = time.perf_counter()

    # 1. Pull recent metrics window
    metrics = await _get_recent_metrics(session, zone_id)

    if len(metrics) == 0:
        return {"action": "no_action", "reasoning": "No metrics available.", "confidence": 0.0}

    # 2. Pre-compute signals for the prompt
    densities = [m["density"] for m in metrics]
    flow_rates = [m["flow_rate"] for m in metrics]

    density_min = min(densities)
    density_max = max(densities)
    density_latest = densities[-1]
    density_first = densities[0]
    flow_max = max(flow_rates)

    density_delta_pct = ((density_latest - density_first) / max(density_first, 1)) * 100
    density_swing_pct = ((density_max - density_min) / max(density_min, 1)) * 100

    user_prompt = (
        f"ZONE: {zone_id}\n"
        f"Samples in last 60s: {len(metrics)}\n"
        f"Density — first: {density_first}, latest: {density_latest}, "
        f"min: {density_min}, max: {density_max}, delta: {density_delta_pct:.1f}%\n"
        f"Flow rate — max: {flow_max} persons/min\n"
        f"Density swing (max-min / min): {density_swing_pct:.1f}%\n\n"
        f"Raw metrics (last 10): {metrics[-10:]}\n\n"
        f"Detect anomalies now."
    )

    input_payload = {
        "zone_id": zone_id,
        "sample_count": len(metrics),
        "density_first": density_first,
        "density_latest": density_latest,
        "density_delta_pct": round(density_delta_pct, 2),
        "density_swing_pct": round(density_swing_pct, 2),
        "flow_max": flow_max,
    }
    input_hash = _hash_input(input_payload)

    # 3. Call Gemini
    try:
        raw = await call_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.1,
        )
    except ValueError as e:
        raw = {
            "action": "no_action",
            "reasoning": f"Model returned invalid output: {e}",
            "confidence": 0.0,
        }

    latency_ms = int((time.perf_counter() - started) * 1000)

    # 4. Audit every evaluation
    session.add(AuditLog(
        agent_name=AGENT_NAME,
        input_snapshot_hash=input_hash,
        input_payload=input_payload,
        output_payload=raw,
        reasoning=str(raw.get("reasoning", ""))[:2048],
        latency_ms=latency_ms,
    ))

    # 5. Confidence gate + emit alert
    action = raw.get("action", "no_action")
    confidence = float(raw.get("confidence", 0.0))

    if action == "emit_alert" and confidence >= CONFIDENCE_FLOOR and raw.get("alert"):
        a = raw["alert"]
        alert = ThreatAlert(
            zone_id=zone_id,
            severity=a["severity"],
            title=a["title"],
            detail=a["detail"],
            issued_by_agent=AGENT_NAME,
            confidence=confidence,
        )
        await session.commit()

        # Publish on channel:alerts for WebSocket fanout
        await publish(get_redis(), settings.ALERT_CHANNEL, alert)
    else:
        await session.commit()

    return raw
