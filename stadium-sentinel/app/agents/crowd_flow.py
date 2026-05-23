import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.agents.llm import call_structured
from app.agents.tools import get_zone_snapshot, get_adjacent_zones
from app.core.pubsub import publish
from app.core.redis_client import get_redis
from app.db.models import AuditLog, Directive
from app.schemas.directive import RoutingDirective, AgentDecision

AGENT_NAME = "CrowdFlowAgent"
CONFIDENCE_FLOOR = 0.75    # below this we defer to a human commander

# Pinned system prompt — never includes user-supplied content (anti-injection).
_SYSTEM_PROMPT = """You are CrowdFlowAgent, an autonomous decision-maker for stadium crowd safety.

Your job: given a zone's current density, capacity, recent trend, and a list of adjacent
zones with their capacities, decide whether to issue a routing directive that redirects
inbound flow away from the overloaded zone toward a neighbour with spare capacity.

Decision rules (apply in order):
1. If utilization_pct < 70 AND trend != "rising": action = "no_action".
2. If utilization_pct >= 70 AND a neighbour has utilization headroom: action = "emit_directive",
   choose the neighbour with the lowest utilization and highest absolute spare capacity.
3. If utilization_pct >= 90 but no safe neighbour exists: action = "defer_to_human"
   (the commander must intervene — possibly halt new entries entirely).
4. Confidence: be honest. If data is sparse (samples < 3), confidence should be <= 0.6.
5. Severity: utilization < 80 -> "info"; 80-90 -> "warn"; >= 90 -> "critical".

Return ONLY JSON matching the provided schema. Reasoning field: 1-3 sentences,
explain the numbers you used."""


# JSON schema enforced on Gemini's response
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["emit_directive", "no_action", "defer_to_human"]},
        "directive": {
            "type": "object",
            "nullable": True,
            "properties": {
                "from_zone_id": {"type": "string"},
                "to_zone_id":   {"type": "string"},
                "reason":       {"type": "string"},
                "severity":     {"type": "string", "enum": ["info", "warn", "critical"]},
            },
            "required": ["from_zone_id", "to_zone_id", "reason", "severity"],
        },
        "reasoning":  {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["action", "reasoning", "confidence"],
}


def _hash_input(payload: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON, for audit-trail input fingerprinting."""
    import orjson
    canonical = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(canonical).hexdigest()


async def evaluate_zone(
    session: AsyncSession, zone_id: str,
) -> AgentDecision:
    """Single-shot evaluation: gather context, call Gemini, persist, optionally publish."""
    started = time.perf_counter()

    # 1. Gather context with our tools (pure DB reads).
    snapshot = await get_zone_snapshot(session, zone_id)
    if "error" in snapshot:
        return AgentDecision(
            action="no_action",
            reasoning=f"Zone {zone_id} not found in catalog.",
            confidence=0.0,
        )

    neighbours_lite = await get_adjacent_zones(session, zone_id, max_distance_m=100)
    # Enrich each neighbour with its current snapshot
    neighbours: list[dict[str, Any]] = []
    for nb in neighbours_lite:
        nb_snap = await get_zone_snapshot(session, nb["zone_id"])
        if "error" not in nb_snap:
            neighbours.append(nb_snap)

    user_prompt = (
        f"FOCUS ZONE:\n{snapshot}\n\n"
        f"ADJACENT ZONES ({len(neighbours)}):\n{neighbours}\n\n"
        f"Decide now."
    )

    input_payload = {"focus": snapshot, "neighbours": neighbours}
    input_hash = _hash_input(input_payload)

    # 2. Call Gemini with structured-output enforcement.
    try:
        raw = await call_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.2,
        )
    except ValueError as e:
        # Model misbehaved — fail safe, escalate to human.
        decision = AgentDecision(
            action="defer_to_human",
            reasoning=f"Model returned invalid output: {e}",
            confidence=0.0,
        )
    else:
        # 3. Build the structured decision. Pydantic re-validates everything.
        directive_obj = None
        if raw.get("action") == "emit_directive" and raw.get("directive"):
            d = raw["directive"]
            directive_obj = RoutingDirective(
                from_zone_id=d["from_zone_id"],
                to_zone_id=d["to_zone_id"],
                reason=d["reason"],
                issued_by_agent=AGENT_NAME,
                confidence=float(raw["confidence"]),
                severity=d["severity"],
            )

        decision = AgentDecision(
            action=raw["action"],
            directive=directive_obj,
            reasoning=raw["reasoning"],
            confidence=float(raw["confidence"]),
        )

    latency_ms = int((time.perf_counter() - started) * 1000)

    # 4. Audit-log every decision (the Chinnaswamy forensic-trail story).
    session.add(AuditLog(
        agent_name=AGENT_NAME,
        input_snapshot_hash=input_hash,
        input_payload=input_payload,
        output_payload=decision.model_dump(mode="json"),
        reasoning=decision.reasoning[:2048],
        latency_ms=latency_ms,
    ))

    # 5. Confidence gate — only emit if model is confident enough.
    if (
        decision.action == "emit_directive"
        and decision.directive is not None
        and decision.confidence >= CONFIDENCE_FLOOR
    ):
        # Persist directive
        session.add(Directive(
            id=decision.directive.id,
            from_zone=decision.directive.from_zone_id,
            to_zone=decision.directive.to_zone_id,
            reason=decision.directive.reason,
            issued_by_agent=AGENT_NAME,
            confidence=decision.confidence,
        ))
        await session.commit()

        # Publish on pub/sub for WebSocket fanout
        await publish(get_redis(), settings.DIRECTIVE_CHANNEL, decision.directive)
    else:
        # Still persist audit row even if we didn't act
        await session.commit()

    return decision
