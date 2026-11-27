import asyncio
from typing import List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from loguru import logger
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.redis import ADMIN_CHANNEL
from app.core import security
from app.configs.db_config import MySQLSessionLocal

ws_router = APIRouter(tags=["WebSockets"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Create an async redis client for the WebSocket manager to avoid blocking the event loop
        self.redis_client = aioredis.from_url(settings.REDIS_URL or "redis://localhost:6379/0")
        self.pubsub = self.redis_client.pubsub()
        self.listen_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket Client connected. Total: {len(self.active_connections)}")
        
        # If this is the first connection, start listening to Redis
        if len(self.active_connections) == 1 and (self.listen_task is None or self.listen_task.done()):
            self.listen_task = asyncio.create_task(self.listen_to_redis())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending ws message: {e}")
                self.disconnect(connection)

    async def listen_to_redis(self):
        try:
            await self.pubsub.subscribe(ADMIN_CHANNEL)
            logger.info(f"Subscribed to Redis channel: {ADMIN_CHANNEL}")
            
            # Loop while there's at least one connection
            while len(self.active_connections) > 0:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    data = message["data"].decode("utf-8")
                    await self.broadcast(data)
                
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Redis PubSub Error: {e}")
        finally:
            logger.info(f"Unsubscribing from Redis channel: {ADMIN_CHANNEL}")
            try:
                await self.pubsub.unsubscribe(ADMIN_CHANNEL)
            except Exception:
                pass

manager = ConnectionManager()

def _authorize_ws(websocket: WebSocket) -> bool:
    """Admin events contain lead/payment details — require an admin/employee JWT.

    Browsers cannot set headers on WebSocket requests, so accept the token from
    `?token=` or the `access_token` cookie set at login.
    """
    token = websocket.query_params.get("token") or websocket.cookies.get("access_token")
    if not token:
        return False
    db = MySQLSessionLocal()
    try:
        user = security.get_user_from_token(token, db)
        return bool(user and user.role in ("admin", "employee"))
    except Exception as e:
        logger.error(f"WebSocket auth error: {e}")
        return False
    finally:
        db.close()


@ws_router.websocket("/ws/admin")
async def websocket_admin_endpoint(websocket: WebSocket):
    if not _authorize_ws(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection open and respond to simple pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
