from datetime import datetime, timezone
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict
import uuid


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RoutingDirective(_Base):
    """An actionable rerouting instruction emitted by CrowdFlowAgent.
    Pushed via Redis pub/sub to all clients subscribed to the affected zones."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_zone_id: Annotated[str, Field(min_length=36, max_length=36)]
    to_zone_id: Annotated[str, Field(min_length=36, max_length=36)]
    reason: Annotated[str, Field(min_length=8, max_length=255)]
    issued_by_agent: Annotated[str, Field(min_length=1, max_length=64)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    severity: Literal["info", "warn", "critical"] = "warn"
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentDecision(_Base):
    """Internal envelope returned by Gemini tool-call. Either emits a
    directive (with confidence >= 0.75) or explicitly defers to the commander."""
    action: Literal["emit_directive", "no_action", "defer_to_human"]
    directive: RoutingDirective | None = None
    reasoning: Annotated[str, Field(min_length=10, max_length=2000)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
