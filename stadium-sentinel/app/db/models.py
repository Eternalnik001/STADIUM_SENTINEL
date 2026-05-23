from datetime import datetime
from sqlalchemy import (
    String, Integer, Float, ForeignKey, DateTime, JSON, Enum, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
import enum
import uuid

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────────────────

class Role(str, enum.Enum):
    fan = "fan"
    volunteer = "volunteer"
    security = "security"
    medical = "medical"
    admin = "admin"


class AlertSeverity(str, enum.Enum):
    info = "info"
    warn = "warn"
    critical = "critical"


class VolunteerStatus(str, enum.Enum):
    available = "available"
    dispatched = "dispatched"
    break_ = "break"
    offline = "offline"


# ─── Core tables ──────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.fan, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Zone(Base):
    """A spatial region of the stadium — gate, stand, concourse, exit ramp.
    Geometry is a Polygon in WGS84 (SRID 4326) for compatibility with Leaflet."""
    __tablename__ = "zones"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(32))  # 'gate' | 'stand' | 'concourse' | 'exit'
    capacity: Mapped[int] = mapped_column(Integer)
    geom: Mapped[str] = mapped_column(Geometry("POLYGON", srid=4326))


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    qr_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrowdMetric(Base):
    """Time-series of density per zone. Indexed on (zone_id, ts) for
    fast windowed queries by the CrowdFlowAgent."""
    __tablename__ = "crowd_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    density: Mapped[int] = mapped_column(Integer)          # persons / 100m²
    flow_rate: Mapped[int] = mapped_column(Integer)        # net persons/min
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    __table_args__ = (Index("ix_zone_ts", "zone_id", "ts"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), index=True)
    title: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    issued_by_agent: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Directive(Base):
    """Routing instruction from CrowdFlowAgent or commander.
    from_zone and to_zone reference Zone.id."""
    __tablename__ = "directives"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_zone: Mapped[str] = mapped_column(ForeignKey("zones.id"))
    to_zone: Mapped[str] = mapped_column(ForeignKey("zones.id"))
    reason: Mapped[str] = mapped_column(String(255))
    issued_by_agent: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    acked_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AuditLog(Base):
    """Immutable forensic trail of every agent decision.
    This is what the magistrate uses to reconstruct events post-incident —
    exactly the gap the Chinnaswamy probe is dealing with right now."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64))
    input_payload: Mapped[dict] = mapped_column(JSON)
    output_payload: Mapped[dict] = mapped_column(JSON)
    reasoning: Mapped[str] = mapped_column(String(2048))
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class VolunteerPosition(Base):
    """Last-known volunteer location + status. EvacAgent uses this for dispatch."""
    __tablename__ = "volunteer_positions"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    status: Mapped[VolunteerStatus] = mapped_column(
        Enum(VolunteerStatus), default=VolunteerStatus.offline, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
