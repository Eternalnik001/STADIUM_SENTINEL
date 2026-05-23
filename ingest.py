from datetime import datetime, timezone
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, field_validator
import uuid


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TurnstileEvent(_Base):
    """Single scan at a physical gate."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    gate_id: Annotated[str, Field(min_length=1, max_length=32)]
    zone_id: Annotated[str, Field(min_length=36, max_length=36)]  # UUID
    direction: Literal["in", "out"]
    ticket_hash: Annotated[str, Field(min_length=16, max_length=128)]
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("ts")
    @classmethod
    def _no_future(cls, v: datetime) -> datetime:
        # reject events claiming to be from the future (clock-skew attack / replay)
        now = datetime.now(timezone.utc)
        if (v - now).total_seconds() > 60:
            raise ValueError("ts in future > 60s")
        return v


class DensityReading(_Base):
    """Crowd-density signal from CCTV edge inference or LiDAR."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    zone_id: Annotated[str, Field(min_length=36, max_length=36)]
    density: Annotated[int, Field(ge=0, le=2000)]   # persons / 100m²
    flow_rate: Annotated[int, Field(ge=-1000, le=1000)]  # net persons/min (in - out)
    source: Literal["cctv", "lidar", "manual"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TicketScan(_Base):
    """Mobile-app ticket scan (pre-gate, indicates inbound intent)."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticket_hash: Annotated[str, Field(min_length=16, max_length=128)]
    expected_zone_id: Annotated[str, Field(min_length=36, max_length=36)]
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WeatherSignal(_Base):
    """Open-Meteo poll output, triggers re-plan."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rain_mm_next_30min: Annotated[float, Field(ge=0.0, le=200.0)]
    wind_kmh: Annotated[float, Field(ge=0.0, le=300.0)]
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestAck(_Base):
    accepted: bool
    event_id: str
    stream_id: str | None = None   # Redis XADD return ID
    reason: str | None = None
