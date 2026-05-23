"""init schema with postgis

Revision ID: 0001
Revises:
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import geoalchemy2

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. PostGIS extension — must exist before geometry columns
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # 2. Enum types
    role_enum = sa.Enum(
        "fan", "volunteer", "security", "medical", "admin",
        name="role",
    )
    severity_enum = sa.Enum("info", "warn", "critical", name="alertseverity")
    vstatus_enum = sa.Enum(
        "available", "dispatched", "break", "offline",
        name="volunteerstatus",
    )

    # 3. users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role", "users", ["role"])

    # 4. zones (PostGIS polygon)
    op.create_table(
        "zones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("capacity", sa.Integer, nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="POLYGON", srid=4326),
            nullable=False,
        ),
    )

    # 5. tickets
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("zone_id", sa.String(36), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("qr_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])
    op.create_index("ix_tickets_zone_id", "tickets", ["zone_id"])
    op.create_index("ix_tickets_qr_hash", "tickets", ["qr_hash"])

    # 6. crowd_metrics
    op.create_table(
        "crowd_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("zone_id", sa.String(36), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("density", sa.Integer, nullable=False),
        sa.Column("flow_rate", sa.Integer, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crowd_metrics_zone_id", "crowd_metrics", ["zone_id"])
    op.create_index("ix_crowd_metrics_ts", "crowd_metrics", ["ts"])
    op.create_index("ix_zone_ts", "crowd_metrics", ["zone_id", "ts"])

    # 7. alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("zone_id", sa.String(36), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("issued_by_agent", sa.String(64), nullable=False,
                  server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_zone_id", "alerts", ["zone_id"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    # 8. directives
    op.create_table(
        "directives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_zone", sa.String(36), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("to_zone", sa.String(36), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("issued_by_agent", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("acked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_directives_created_at", "directives", ["created_at"])

    # 9. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("input_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("input_payload", sa.JSON, nullable=False),
        sa.Column("output_payload", sa.JSON, nullable=False),
        sa.Column("reasoning", sa.String(2048), nullable=False, server_default=""),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_log_agent_name", "audit_log", ["agent_name"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    # 10. volunteer_positions
    op.create_table(
        "volunteer_positions",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lng", sa.Float, nullable=False),
        sa.Column("status", vstatus_enum, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_volunteer_positions_status", "volunteer_positions", ["status"])


def downgrade() -> None:
    op.drop_table("volunteer_positions")
    op.drop_table("audit_log")
    op.drop_table("directives")
    op.drop_table("alerts")
    op.drop_table("crowd_metrics")
    op.drop_table("tickets")
    op.drop_table("zones")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS volunteerstatus")
    op.execute("DROP TYPE IF EXISTS alertseverity")
    op.execute("DROP TYPE IF EXISTS role")
    # PostGIS extension is left in place — dropping it can break shared DBs
