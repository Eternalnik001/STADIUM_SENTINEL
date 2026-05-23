import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.core.redis_client import get_redis, close_pool
from app.api import ingest, health, ws, zones
from fastapi.staticfiles import StaticFiles

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MIN}/minute"],
)


from app.api.ws import listen_to_redis_pubsub, listen_to_alerts_pubsub

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    r = get_redis()
    await r.ping()
    listener_task = asyncio.create_task(listen_to_redis_pubsub())
    alert_listener = asyncio.create_task(listen_to_alerts_pubsub())
    yield
    # Shutdown
    listener_task.cancel()
    alert_listener.cancel()
    try:
        await asyncio.gather(listener_task, alert_listener, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    await close_pool()


app = FastAPI(
    title="Stadium Sentinel",
    description="Agentic crowd intelligence and emergency command platform",
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # tighten before pilot — set explicit allowlist
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(ingest.router, prefix="/v1/ingest", tags=["ingest"])
app.include_router(ws.router, prefix="/v1/ws", tags=["websockets"])
app.include_router(zones.router, prefix="/v1/zones", tags=["zones"])

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
