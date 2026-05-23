from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Any


async def get_zone_snapshot(session: AsyncSession, zone_id: str) -> dict[str, Any]:
    """Fetch current density, capacity, utilization, and trend for a zone."""
    # 1. Fetch zone details
    res = await session.execute(
        text("SELECT id, name, capacity FROM zones WHERE id = :id OR name = :id"),
        {"id": zone_id},
    )
    row = res.first()
    if not row:
        return {"error": f"Zone {zone_id} not found"}
    actual_id, name, capacity = row

    # 2. Fetch latest crowd metrics (for density, flow rate, and trend)
    # We fetch the last 3 samples to calculate trend
    metric_res = await session.execute(
        text("""
            SELECT density, flow_rate, ts
            FROM crowd_metrics
            WHERE zone_id = :zone_id
            ORDER BY ts DESC
            LIMIT 3
        """),
        {"zone_id": actual_id},
    )
    m_rows = metric_res.all()

    density = 0
    flow_rate = 0
    trend = "stable"
    last_updated = ""

    if m_rows:
        density = m_rows[0][0]
        flow_rate = m_rows[0][1]
        last_updated = m_rows[0][2].isoformat()

        # Calculate trend based on direction of density changes
        if len(m_rows) >= 2:
            diff = m_rows[0][0] - m_rows[1][0]
            if diff > 0:
                trend = "rising"
            elif diff < 0:
                trend = "falling"

    # Calculate utilization percentage (density represents persons/100m2 in schemas)
    # To compute a meaningful utilization percentage, we assume density * 10 is the approximate count
    # or treat density directly as count for mock/simplified calculation.
    # Let's align with the prompt rules: utilization_pct = (current count / capacity) * 100
    utilization_pct = (float(density) / capacity * 100.0) if capacity > 0 else 0.0

    return {
        "zone_id": actual_id,
        "name": name,
        "capacity": capacity,
        "density": density,
        "flow_rate": flow_rate,
        "utilization_pct": round(utilization_pct, 1),
        "trend": trend,
        "last_updated": last_updated,
        "samples_count": len(m_rows),
    }


async def get_adjacent_zones(
    session: AsyncSession, zone_id: str, max_distance_m: float = 100
) -> list[dict[str, Any]]:
    """Query PostGIS to find zones within max_distance_m of the focus zone."""
    res = await session.execute(
        text("""
            SELECT z2.id, z2.name, ST_Distance(z1.geom::geography, z2.geom::geography) as distance
            FROM zones z1, zones z2
            WHERE (z1.id = :id OR z1.name = :id) AND z2.id != z1.id
              AND ST_DWithin(z1.geom::geography, z2.geom::geography, :dist)
            ORDER BY distance ASC
        """),
        {"id": zone_id, "dist": max_distance_m},
    )
    rows = res.all()
    return [
        {"zone_id": r[0], "name": r[1], "distance_m": round(r[2], 1)}
        for r in rows
    ]
