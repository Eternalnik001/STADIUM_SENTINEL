from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

router = APIRouter()


@router.get("")
async def get_zones(db: AsyncSession = Depends(get_db)):
    """Existing endpoint — returns zones with raw GeoJSON string for Leaflet.
    Kept for backward-compat with the frontend Antigravity generated."""
    res = await db.execute(text("""
        SELECT id, name, kind, capacity, ST_AsGeoJSON(geom) AS geojson
        FROM zones
        ORDER BY name
    """))
    zones = []
    for row in res.fetchall():
        zones.append({
            "id": row.id,
            "name": row.name,
            "kind": row.kind,
            "capacity": row.capacity,
            "geojson": row.geojson,
        })
    return {"zones": zones}


@router.get("/all-snapshots")
async def all_snapshots(db: AsyncSession = Depends(get_db)):
    """Bulk live density per zone, for heatmap refresh."""
    res = await db.execute(text("""
        SELECT
            z.id, z.name, z.capacity,
            COALESCE(cm.density, 0) AS density,
            COALESCE(cm.flow_rate, 0) AS flow_rate
        FROM zones z
        LEFT JOIN LATERAL (
            SELECT density, flow_rate
            FROM crowd_metrics
            WHERE zone_id = z.id
            ORDER BY ts DESC
            LIMIT 1
        ) cm ON TRUE
    """))
    out = {}
    for r in res.mappings().all():
        cap = r["capacity"] or 1
        out[r["id"]] = {
            "name": r["name"],
            "capacity": cap,
            "density": r["density"],
            "flow_rate": r["flow_rate"],
            "utilization_pct": round((r["density"] / cap) * 100, 1),
        }
    return out


@router.get("/recent-directives")
async def recent_directives(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Last N directives, for feed backfill when the console first loads."""
    res = await db.execute(text("""
        SELECT
            d.id, d.reason, d.confidence, d.issued_by_agent, d.created_at,
            zf.name AS from_zone_name,
            zt.name AS to_zone_name,
            d.from_zone, d.to_zone
        FROM directives d
        JOIN zones zf ON zf.id = d.from_zone
        JOIN zones zt ON zt.id = d.to_zone
        ORDER BY d.created_at DESC
        LIMIT :lim
    """), {"lim": limit})
    return [dict(r) for r in res.mappings().all()]
