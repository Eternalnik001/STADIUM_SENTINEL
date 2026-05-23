from datetime import datetime, timezone
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict
import uuid


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ThreatAlert(_Base):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    zone_id: Annotated[str, Field(min_length=36, max_length=36)]
    severity: Literal["info", "warn", "critical"]
    title: Annotated[str, Field(min_length=5, max_length=120)]
    detail: Annotated[str, Field(min_length=10, max_length=500)]
    issued_by_agent: Annotated[str, Field(min_length=1, max_length=64)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
