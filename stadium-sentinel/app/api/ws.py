import asyncio
import logging
from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from app.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)
router = APIRouter()


class ConnectionManager:
    def __init__(self, name: str = ""):
        self.name = name
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("[%s] client connected (total=%d)", self.name, len(self.active_connections))

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info("[%s] client disconnected (total=%d)", self.name, len(self.active_connections))

    async def broadcast(self, message: str):
        """Fan out message to all connected clients. Drops dead ones."""
        dead = []
        async with self._lock:
            conns = list(self.active_connections)
        for connection in conns:
            try:
                await connection.send_text(message)
            except (WebSocketDisconnect, ConnectionClosed, RuntimeError):
                dead.append(connection)
        for c in dead:
            await self.disconnect(c)


# Separate managers so directives and alerts don't cross-contaminate
manager = ConnectionManager(name="directives")
alerts_manager = ConnectionManager(name="alerts")


async def _make_pubsub_listener(channel: str, mgr: ConnectionManager):
    """Generic Redis pub/sub listener that broadcasts to a ConnectionManager."""
    print(f"starting redis pubsub listener on channel={channel}", flush=True)
    redis = get_redis()
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            logger.info("[%s] broadcast: %s", channel, data[:120])
            await mgr.broadcast(data)
    except asyncio.CancelledError:
        logger.info("[%s] pubsub listener cancelled", channel)
        raise
    except Exception as e:
        logger.exception("[%s] pubsub listener crashed: %s", channel, e)
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:
            pass


async def listen_to_redis_pubsub():
    """Directives channel listener — started by the lifespan in app/main.py."""
    await _make_pubsub_listener(settings.DIRECTIVE_CHANNEL, manager)


async def listen_to_alerts_pubsub():
    """Alerts channel listener — started by the lifespan in app/main.py."""
    await _make_pubsub_listener(settings.ALERT_CHANNEL, alerts_manager)


@router.websocket("/directives")
async def websocket_endpoint(websocket: WebSocket):
    """Push-only WebSocket. Clients receive live RoutingDirective JSON."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.warning("[directives] ws error: %s", e)
        await manager.disconnect(websocket)


@router.websocket("/alerts")
async def alerts_websocket_endpoint(websocket: WebSocket):
    """Push-only WebSocket. Clients receive live ThreatAlert JSON."""
    await alerts_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await alerts_manager.disconnect(websocket)
    except Exception as e:
        logger.warning("[alerts] ws error: %s", e)
        await alerts_manager.disconnect(websocket)
