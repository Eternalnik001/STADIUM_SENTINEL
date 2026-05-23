from fastapi import APIRouter
from app.core.redis_client import get_redis

router = APIRouter()


@router.get("/healthz")
async def healthz():
    """Cloud Run readiness probe."""
    try:
        await get_redis().ping()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "degraded", "err": type(e).__name__}
